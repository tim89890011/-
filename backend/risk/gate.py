"""
Phase C: RiskGate（增强版）

能力清单：
1. 日回撤阈值（从 trade_records 实时计算 + DailyPnL 兜底）
2. 连续 INCORRECT 熔断
3. 波动率尖峰降级（ATR 滚动窗口检测）
4. 相关性暴露检查（BTC+ETH 同向暴露上限）

决策类型：
- PASS    — 不干预
- HOLD    — 信号强制改为 HOLD（熔断级）
- DOWNGRADE — 保留信号方向，但下调置信度（降级级）
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy import select, desc, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.database.models import DailyPnL, AISignal, SignalResult, User, UserSettings
from backend.trading.models import TradeRecord
from backend.trading.pnl import pair_trades

logger = logging.getLogger(__name__)


@dataclass
class GateDecision:
    action: str  # PASS / HOLD / DOWNGRADE
    reason: str
    confidence_reduction: float = 0.0  # DOWNGRADE 时的置信度下调量


@dataclass
class GateResult:
    """聚合多条检查结果：HOLD 优先级最高，DOWNGRADE 可叠加。"""
    decisions: list[GateDecision] = field(default_factory=list)

    @property
    def final_action(self) -> str:
        if any(d.action == "HOLD" for d in self.decisions):
            return "HOLD"
        if any(d.action == "DOWNGRADE" for d in self.decisions):
            return "DOWNGRADE"
        return "PASS"

    @property
    def total_confidence_reduction(self) -> float:
        return sum(d.confidence_reduction for d in self.decisions if d.action == "DOWNGRADE")

    @property
    def combined_reason(self) -> str:
        parts = [d.reason for d in self.decisions if d.action != "PASS"]
        return "; ".join(parts)

    @property
    def hold_reason(self) -> str:
        parts = [d.reason for d in self.decisions if d.action == "HOLD"]
        return "; ".join(parts) if parts else self.combined_reason


class RiskGate:
    # 类级别：ATR 滚动窗口（跨实例持久化，单进程足够）
    _atr_history: dict[str, deque] = {}

    def __init__(self) -> None:
        # ---- 原有配置 ----
        self.max_daily_drawdown_pct = float(
            getattr(settings, "RISK_MAX_DAILY_DRAWDOWN_PCT", 5.0) or 5.0
        )
        self.max_consecutive_incorrect = int(
            getattr(settings, "RISK_MAX_CONSECUTIVE_INCORRECT", 5) or 5
        )

        # ---- 波动率尖峰 ----
        self.atr_spike_multiplier = float(
            getattr(settings, "RISK_ATR_SPIKE_MULTIPLIER", 0.0) or 0.0
        )
        self.atr_spike_confidence_reduction = float(
            getattr(settings, "RISK_ATR_SPIKE_CONFIDENCE_REDUCTION", 30.0) or 30.0
        )
        self.atr_history_window = int(
            getattr(settings, "RISK_ATR_HISTORY_WINDOW", 20) or 20
        )

        # ---- 相关性暴露 ----
        _corr_raw = str(getattr(settings, "RISK_CORRELATED_SYMBOLS", "") or "")
        self.correlated_symbols: list[str] = [
            s.strip().upper() for s in _corr_raw.split(",") if s.strip()
        ]
        self.max_correlated_exposure_pct = float(
            getattr(settings, "RISK_MAX_CORRELATED_EXPOSURE_PCT", 50.0) or 50.0
        )
        self.correlated_exposure_confidence_reduction = float(
            getattr(settings, "RISK_CORRELATED_EXPOSURE_CONFIDENCE_REDUCTION", 20.0) or 20.0
        )

        # ---- 连亏两段式（警戒 / 硬停） ----
        self.loss_streak_caution = int(
            getattr(settings, "RISK_RECENT_LOSS_STREAK_CAUTION", 5) or 5
        )
        self.loss_streak_halt = int(
            getattr(settings, "RISK_RECENT_LOSS_STREAK_HALT", 10) or 10
        )

    # ================================================================
    # 主入口
    # ================================================================
    async def check(
        self,
        db: AsyncSession,
        signal: dict[str, Any] | None = None,
    ) -> GateResult:
        """
        运行全部检查，返回聚合结果。
        signal: apply_risk_gate 传入的信号 dict（含 symbol / indicators / signal 等）。
        """
        result = GateResult()
        signal = signal or {}

        # 1) 日内回撤（优先从 trade_records 实时计算）
        dd = await self._get_today_drawdown(db)
        if dd >= self.max_daily_drawdown_pct:
            result.decisions.append(
                GateDecision("HOLD", f"日回撤超限 {dd:.2f}%>={self.max_daily_drawdown_pct}%")
            )

        # 2) 连续 INCORRECT 熔断
        streak = await self._get_consecutive_incorrect(db, limit=self.max_consecutive_incorrect)
        if streak >= self.max_consecutive_incorrect:
            result.decisions.append(
                GateDecision("HOLD", f"近期连续错误 {streak}>={self.max_consecutive_incorrect}")
            )

        # 3) 波动率尖峰降级
        vol_decision = self._check_volatility_spike(signal)
        if vol_decision:
            result.decisions.append(vol_decision)

        # 4) 相关性暴露检查
        corr_decision = await self._check_correlated_exposure(signal, db)
        if corr_decision:
            result.decisions.append(corr_decision)

        # 5) 连亏两段式（警戒降级 / 硬停熔断）
        if self.loss_streak_caution > 0:
            loss_decision = await self._check_loss_streak(signal, db)
            if loss_decision:
                result.decisions.append(loss_decision)

        # 无任何触发时补一个 PASS
        if not result.decisions:
            result.decisions.append(GateDecision("PASS", ""))

        return result

    # ================================================================
    # 1) 日内回撤（增强：优先从 trade_records 实时计算）
    # ================================================================
    async def _get_today_drawdown(self, db: AsyncSession) -> float:
        tz_cn = timezone(timedelta(hours=8))
        today_str = datetime.now(tz_cn).strftime("%Y-%m-%d")
        today_start = (
            datetime.now(tz_cn)
            .replace(hour=0, minute=0, second=0, microsecond=0)
            .astimezone(timezone.utc)
        )

        # 尝试从 trade_records 实时统计当日已实现盈亏
        try:
            stmt = (
                select(
                    func.coalesce(
                        func.sum(
                            # SELL 方向为正（回款），BUY 方向为负（支出）
                            # 对于合约：平多=SELL(+), 平空=BUY(-)
                            # 净值 = sum(SELL) - sum(BUY) = 已实现盈亏
                            func.case(
                                (TradeRecord.side == "SELL", TradeRecord.quote_amount),
                                else_=-TradeRecord.quote_amount,
                            )
                        ),
                        0.0,
                    ).label("net_pnl")
                )
                .where(
                    and_(
                        TradeRecord.status == "filled",
                        TradeRecord.created_at >= today_start,
                    )
                )
            )
            row = (await db.execute(stmt)).one()
            realized_pnl = float(row.net_pnl)

            if realized_pnl < 0:
                # 需要基准权益来计算回撤百分比
                equity = await self._get_reference_equity(db, today_str)
                if equity and equity > 0:
                    drawdown_pct = abs(realized_pnl) / equity * 100.0
                    logger.debug(
                        f"[RiskGate] 日内实时回撤: PnL={realized_pnl:.2f}, "
                        f"权益={equity:.2f}, 回撤={drawdown_pct:.2f}%"
                    )
                    return drawdown_pct
        except Exception as e:
            logger.debug(f"[RiskGate] trade_records 回撤计算失败，回退 DailyPnL: {e}")

        # 回退：从 DailyPnL 表读取快照
        r = await db.execute(select(DailyPnL).where(DailyPnL.date == today_str))
        row_pnl = r.scalar_one_or_none()
        return float(row_pnl.max_drawdown_pct or 0.0) if row_pnl else 0.0

    async def _get_reference_equity(self, db: AsyncSession, today_str: str) -> float | None:
        """获取基准权益：优先当日 DailyPnL.total_equity，否则前一日。"""
        r = await db.execute(select(DailyPnL).where(DailyPnL.date == today_str))
        row = r.scalar_one_or_none()
        if row and row.total_equity and row.total_equity > 0:
            return float(row.total_equity)

        # 回退：最近一条 DailyPnL
        r2 = await db.execute(
            select(DailyPnL).order_by(desc(DailyPnL.date)).limit(1)
        )
        row2 = r2.scalar_one_or_none()
        if row2 and row2.total_equity and row2.total_equity > 0:
            return float(row2.total_equity)

        return None

    # ================================================================
    # 2) 连续 INCORRECT 熔断（保持原逻辑）
    # ================================================================
    async def _get_consecutive_incorrect(self, db: AsyncSession, limit: int = 5) -> int:
        stmt = (
            select(AISignal, SignalResult)
            .join(SignalResult, SignalResult.signal_id == AISignal.id, isouter=True)
            .where(AISignal.signal.in_(["BUY", "SELL", "SHORT", "COVER"]))
            .order_by(desc(AISignal.created_at))
            .limit(limit)
        )
        rows = (await db.execute(stmt)).all()
        streak = 0
        for sig, sr in rows:
            if not sr or (sr.direction_result or "").upper() != "INCORRECT":
                break
            streak += 1
        return streak

    # ================================================================
    # 3) 波动率尖峰降级
    # ================================================================
    def _check_volatility_spike(self, signal: dict[str, Any]) -> GateDecision | None:
        """
        当前 ATR > 滚动均值 × multiplier 时，返回 DOWNGRADE 决策。
        需要积累至少 atr_history_window 个样本才开始检测。
        """
        if self.atr_spike_multiplier <= 0:
            return None  # 功能禁用

        symbol = str(signal.get("symbol", "")).upper()
        indicators = signal.get("indicators") or {}
        current_atr = indicators.get("atr")

        if not symbol or current_atr is None or current_atr <= 0:
            return None

        current_atr = float(current_atr)

        # 维护滚动窗口
        if symbol not in RiskGate._atr_history:
            RiskGate._atr_history[symbol] = deque(maxlen=self.atr_history_window)

        window = RiskGate._atr_history[symbol]

        # 样本不足，不检测（append 前判断）
        if len(window) < self.atr_history_window:
            window.append(current_atr)
            return None

        # 先算均值（排除当前值）
        avg_atr = sum(window) / len(window)
        # 再加入当前值
        window.append(current_atr)
        if avg_atr <= 0:
            return None

        ratio = current_atr / avg_atr
        if ratio >= self.atr_spike_multiplier:
            reason = (
                f"ATR尖峰 {symbol}: 当前={current_atr:.4f}, "
                f"均值={avg_atr:.4f}, 倍率={ratio:.2f}x>={self.atr_spike_multiplier}x"
            )
            logger.info(f"[RiskGate] {reason}")
            return GateDecision(
                "DOWNGRADE",
                reason,
                confidence_reduction=self.atr_spike_confidence_reduction,
            )

        return None

    # ================================================================
    # 4) 相关性暴露检查
    # ================================================================
    async def _check_correlated_exposure(
        self, signal: dict[str, Any], db: AsyncSession
    ) -> GateDecision | None:
        """
        当相关币种（如 BTC+ETH）同方向持仓，且总暴露超过账户 N% 时，
        返回 DOWNGRADE 决策。

        暴露 = 当日 filled 的同方向净额 / 账户权益。
        """
        if not self.correlated_symbols or len(self.correlated_symbols) < 2:
            return None  # 功能禁用或配置不足

        symbol = str(signal.get("symbol", "")).upper()
        sig_direction = str(signal.get("signal", "")).upper()

        if symbol not in self.correlated_symbols:
            return None  # 当前币种不在相关性列表中

        if sig_direction not in ("BUY", "SHORT"):
            return None  # 只检查开仓信号

        tz_cn = timezone(timedelta(hours=8))
        today_str = datetime.now(tz_cn).strftime("%Y-%m-%d")

        # 获取基准权益
        equity = await self._get_reference_equity(db, today_str)
        if not equity or equity <= 0:
            return None  # 无权益数据，跳过检查

        today_start = (
            datetime.now(tz_cn)
            .replace(hour=0, minute=0, second=0, microsecond=0)
            .astimezone(timezone.utc)
        )

        # 查询所有相关币种当日的 filled 交易
        try:
            stmt = (
                select(
                    TradeRecord.symbol,
                    TradeRecord.side,
                    func.sum(TradeRecord.quote_amount).label("total_amount"),
                )
                .where(
                    and_(
                        TradeRecord.status == "filled",
                        TradeRecord.created_at >= today_start,
                        TradeRecord.symbol.in_(self.correlated_symbols),
                    )
                )
                .group_by(TradeRecord.symbol, TradeRecord.side)
            )
            rows = (await db.execute(stmt)).all()
        except Exception as e:
            logger.debug(f"[RiskGate] 相关性暴露查询失败: {e}")
            return None

        # 计算每个币种的净暴露方向和金额
        # net > 0 表示净做多暴露，net < 0 表示净做空暴露
        exposure_by_symbol: dict[str, float] = {}
        for row in rows:
            sym = row.symbol
            side = row.side
            amount = float(row.total_amount or 0)
            if sym not in exposure_by_symbol:
                exposure_by_symbol[sym] = 0.0
            if side == "BUY":
                exposure_by_symbol[sym] += amount
            else:  # SELL
                exposure_by_symbol[sym] -= amount

        # 加入当前待执行信号的预估暴露
        signal_amount = float(signal.get("price_at_signal", 0) or 0)
        trade_amount_pct: float | None = None
        trade_amount_usdt: float | None = None

        # 与 executor 对齐：尽量使用 admin 的 user_settings 来估算仓位（否则回退全局配置）
        try:
            r = await db.execute(
                select(UserSettings)
                .join(User, UserSettings.user_id == User.id)
                .where(User.username == str(settings.ADMIN_USERNAME))
                .limit(1)
            )
            us = r.scalar_one_or_none()
            if us is not None:
                if us.amount_pct is not None:
                    trade_amount_pct = float(us.amount_pct)
                if us.amount_usdt is not None:
                    trade_amount_usdt = float(us.amount_usdt)
        except Exception as e:
            logger.warning(f"[RiskGate] 查询用户交易设置失败，使用默认值: {e}")
            us = None

        if trade_amount_pct is None:
            trade_amount_pct = float(getattr(settings, "TRADE_AMOUNT_PCT", 5.0) or 5.0)
        estimated_order = equity * trade_amount_pct / 100.0
        if estimated_order <= 0:
            if trade_amount_usdt is None:
                trade_amount_usdt = float(getattr(settings, "TRADE_AMOUNT_USDT", 100.0) or 100.0)
            estimated_order = float(trade_amount_usdt)

        if symbol not in exposure_by_symbol:
            exposure_by_symbol[symbol] = 0.0

        if sig_direction == "BUY":
            exposure_by_symbol[symbol] += estimated_order
        elif sig_direction == "SHORT":
            exposure_by_symbol[symbol] -= estimated_order

        # 判断是否同方向
        long_exposure = sum(v for v in exposure_by_symbol.values() if v > 0)
        short_exposure = abs(sum(v for v in exposure_by_symbol.values() if v < 0))

        # 取同方向的最大暴露
        same_dir_exposure = max(long_exposure, short_exposure)
        exposure_pct = same_dir_exposure / equity * 100.0

        # 检查是否有 >=2 个相关币种在同一方向
        if long_exposure > 0:
            long_symbols = [s for s, v in exposure_by_symbol.items() if v > 0]
            corr_count_long = len([s for s in long_symbols if s in self.correlated_symbols])
        else:
            corr_count_long = 0

        if short_exposure > 0:
            short_symbols = [s for s, v in exposure_by_symbol.items() if v < 0]
            corr_count_short = len([s for s in short_symbols if s in self.correlated_symbols])
        else:
            corr_count_short = 0

        max_corr_count = max(corr_count_long, corr_count_short)

        if max_corr_count >= 2 and exposure_pct >= self.max_correlated_exposure_pct:
            reason = (
                f"相关性暴露超限: 同向暴露={same_dir_exposure:.1f} USDT "
                f"({exposure_pct:.1f}%>={self.max_correlated_exposure_pct}%), "
                f"涉及 {max_corr_count} 个相关币种"
            )
            logger.info(f"[RiskGate] {reason}")
            return GateDecision(
                "DOWNGRADE",
                reason,
                confidence_reduction=self.correlated_exposure_confidence_reduction,
            )

        return None

    # ================================================================
    # 5) 连亏两段式检查
    # ================================================================
    async def _check_loss_streak(
        self, signal: dict[str, Any], db: AsyncSession
    ) -> GateDecision | None:
        symbol = signal.get("symbol", "")
        sig_direction = signal.get("signal", "HOLD")
        if sig_direction == "HOLD":
            return None

        is_long_action = sig_direction in ("BUY", "SELL")
        check_dir = "多" if is_long_action else "空"

        try:
            stmt = (
                select(
                    TradeRecord.side,
                    TradeRecord.quote_amount,
                    TradeRecord.created_at,
                )
                .where(
                    TradeRecord.symbol == symbol,
                    TradeRecord.status == "filled",
                )
                .order_by(desc(TradeRecord.created_at))
                .limit(30)
            )
            result = await db.execute(stmt)
            rows = list(result.all())

            if len(rows) < 2:
                return None

            pairs = pair_trades(rows, sort_order="desc")

            streak = 0
            for p in pairs:
                direction = p["direction"]
                pnl = p["pnl"]
                if direction == check_dir and pnl < 0:
                    streak += 1
                else:
                    break

            if streak >= self.loss_streak_halt:
                logger.warning(
                    f"[RiskGate] {symbol} 做{check_dir}连亏{streak}次 >= {self.loss_streak_halt}，硬停"
                )
                return GateDecision(
                    "HOLD",
                    f"连亏硬停: {symbol}做{check_dir}连续亏损{streak}次>={self.loss_streak_halt}",
                )
            elif streak >= self.loss_streak_caution:
                reduction = 15.0 + (streak - self.loss_streak_caution) * 5.0
                reduction = min(reduction, 40.0)
                logger.info(
                    f"[RiskGate] {symbol} 做{check_dir}连亏{streak}次 >= {self.loss_streak_caution}，警戒降级-{reduction}"
                )
                return GateDecision(
                    "DOWNGRADE",
                    f"连亏警戒: {symbol}做{check_dir}连续亏损{streak}次>={self.loss_streak_caution}",
                    confidence_reduction=reduction,
                )

        except Exception as e:
            logger.warning(f"[RiskGate] {symbol} 连亏检查失败: {e}")

        return None


# ================================================================
# 公开接口
# ================================================================
async def apply_risk_gate(signal: dict[str, Any], db: AsyncSession) -> dict[str, Any]:
    """
    对 signal_obj 做风控降级（返回新 dict）。

    决策优先级：
    - HOLD      → 信号改为 HOLD，置信度压到 ≤40（熔断）
    - DOWNGRADE → 保留信号方向，但下调置信度（降级）
    - PASS      → 不干预
    """
    if not signal:
        return signal

    gate = RiskGate()
    result = await gate.check(db, signal=signal)
    action = result.final_action

    if action == "PASS":
        return signal

    old_sig = str(signal.get("signal") or "HOLD")

    # ---- HOLD：熔断级（信号强制改为 HOLD） ----
    if action == "HOLD" and old_sig in ("BUY", "SELL", "SHORT", "COVER"):
        signal = dict(signal)
        signal["signal"] = "HOLD"
        signal["confidence"] = min(float(signal.get("confidence", 0) or 0), 40.0)
        signal["final_reason"] = (
            (signal.get("final_reason", "") or "")
            + f"\n[RiskGate:HOLD] {result.hold_reason}"
        )
        signal["risk_level"] = "高"
        return signal

    # ---- DOWNGRADE：降级（保留方向，下调置信度） ----
    if action == "DOWNGRADE" and old_sig in ("BUY", "SELL", "SHORT", "COVER"):
        signal = dict(signal)
        reduction = result.total_confidence_reduction
        old_conf = float(signal.get("confidence", 0) or 0)
        new_conf = max(old_conf - reduction, 0.0)
        signal["confidence"] = new_conf
        signal["final_reason"] = (
            (signal.get("final_reason", "") or "")
            + f"\n[RiskGate:DOWNGRADE] {result.combined_reason} (置信度 {old_conf:.0f}→{new_conf:.0f})"
        )
        # 风险等级上调一档（低→中，中→高）
        current_risk = str(signal.get("risk_level", "中"))
        if current_risk == "低":
            signal["risk_level"] = "中"
        elif current_risk == "中":
            signal["risk_level"] = "高"
        # 置信度降至 20% 以下，自动转 HOLD 避免执行低信心方向性交易
        if new_conf < 20.0:
            signal["signal"] = "HOLD"
            signal["final_reason"] = (
                (signal.get("final_reason", "") or "")
                + f"\n[RiskGate:DOWNGRADE→HOLD] 置信度过低({new_conf:.0f}%<20%)，已强制转HOLD"
            )
            signal["risk_level"] = "高"
            logger.warning(
                f"[RiskGate] DOWNGRADE 后置信度过低 {new_conf:.0f}% < 20%，强制转 HOLD"
            )
        return signal

    return signal
