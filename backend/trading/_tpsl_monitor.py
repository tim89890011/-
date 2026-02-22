"""TpSlMonitorMixin — TP/SL monitoring loop, trailing stop, position timeout."""

from __future__ import annotations

import time
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, and_

from backend.config import settings
from backend.database.db import async_session
from backend.trading.models import TradeRecord
from backend.trading.pnl import calc_pnl_pct
from backend.utils.symbol import to_raw
from backend.core.execution.state_manager import StateManager

logger = logging.getLogger(__name__)

# Singleton state aliases
_state = StateManager()
_symbol_atr = _state.symbol_atr
_symbol_sl_tracker = _state.sl_tracker


class TpSlMonitorMixin:
    """TP/SL monitoring loop, trailing stop, position timeout."""

    # ========================================================
    # 止盈止损检查（合约版：支持移动止盈）
    # ========================================================
    async def check_stop_loss_take_profit(self):
        """
        检查所有合约仓位（多仓+空仓），触发止盈或止损自动平仓。
        如果该仓位已有交易所 TP/SL 条件单，则跳过本地固定 TP/SL（交易所毫秒级触发更可靠），
        仅保留移动止盈的本地逻辑（交易所无法完全复刻多级递进）。
        """
        if not self.is_active or not self._exchange:
            return
        user_settings = await self._load_user_settings_by_username(settings.ADMIN_USERNAME)
        default_tp = (
            float(user_settings.take_profit_pct)
            if user_settings and user_settings.take_profit_pct is not None
            else float(settings.TRADE_TAKE_PROFIT_PCT)
        )
        default_sl = (
            float(user_settings.stop_loss_pct)
            if user_settings and user_settings.stop_loss_pct is not None
            else float(settings.TRADE_STOP_LOSS_PCT)
        )
        trailing_enabled = (
            bool(user_settings.trailing_stop_enabled)
            if user_settings and user_settings.trailing_stop_enabled is not None
            else bool(settings.TRADE_TRAILING_STOP_ENABLED)
        )

        positions = await self._fetch_all_positions()

        # 检测交易所条件单是否已触发平仓（仓位消失 = 条件单已触发）
        await self._detect_exchange_triggered_closes(positions)

        for pos in positions:
            symbol = pos["symbol"]
            qty = pos["contracts"]
            entry_price = pos["entryPrice"]
            mark_price = pos["markPrice"]
            side = pos["side"]  # "long" or "short"

            if qty <= 0 or side not in ("long", "short"):
                continue

            leverage = float(pos.get("leverage", settings.TRADE_LEVERAGE))
            pnl_pct = calc_pnl_pct(entry_price, mark_price, side, leverage)

            raw_symbol = to_raw(symbol)
            side_cn = "多仓" if side == "long" else "空仓"

            atr_info = _symbol_atr.get(raw_symbol)
            saved = self._get_saved_tp_sl(raw_symbol, side)
            if saved:
                tp_pct = saved["tp_pct"]
                sl_pct = saved["sl_pct"]
            elif atr_info and atr_info["atr_pct"] > 0:
                atr = atr_info["atr_pct"]
                tp_pct = max(min(atr * 2.5, 8.0), 2.5)
                sl_pct = max(min(atr * 1.5, 4.0), 1.5)
            else:
                tp_pct = default_tp
                sl_pct = default_sl

            # 该仓位是否已有交易所条件单（有则跳过本地固定 TP/SL，交易所毫秒级触发更可靠）
            exchange_key = f"{raw_symbol}_{side}"
            has_exchange_orders = exchange_key in self._exchange_tp_sl

            # 最短持仓门禁：开仓后 N 秒内禁止止盈/移动止盈，止损门槛翻倍（防标记价格瞬间偏差）
            under_hold, remaining = await self._is_under_min_hold(raw_symbol, pos_side=side)
            if under_hold:
                if not has_exchange_orders:
                    sl_pct_hold = sl_pct * 2.0
                    if pnl_pct <= -sl_pct_hold:
                        logger.info(
                            f"[止损] 🛑 {symbol} {side_cn}亏损 {pnl_pct:.2f}% <= -{sl_pct_hold:.2f}%（最短持仓加严×2），"
                            f"剩余{remaining}s 但允许止损 | 开仓 ${entry_price:.2f} → 标记 ${mark_price:.2f}"
                        )
                        await self._execute_tp_sl_close(
                            raw_symbol, "STOP_LOSS", pnl_pct, entry_price, mark_price, pos_side=side
                        )
                    else:
                        logger.debug(
                            f"[最短持仓] {symbol} {side_cn} 持仓未满 {getattr(settings, 'TRADE_MIN_HOLD_SECONDS', 0)}s，"
                            f"剩余 {remaining}s → 跳过止盈/移动止盈检查"
                        )
                else:
                    logger.debug(
                        f"[最短持仓] {symbol} {side_cn} 剩余 {remaining}s，交易所条件单已兜底"
                    )
                continue

            # --- 有交易所条件单时：跳过固定 TP/SL，仅保留移动止盈的本地逻辑 ---
            if has_exchange_orders:
                if trailing_enabled and pnl_pct > 0:
                    await self._local_trailing_stop_check(
                        raw_symbol, symbol, side, side_cn, pnl_pct,
                        entry_price, mark_price, atr_info,
                    )
                continue

            # --- 无交易所条件单（兜底）：完整本地 TP/SL + 移动止盈 ---

            # 固定止盈（加 0.001% 容差防止浮点边界漏判）
            if pnl_pct >= tp_pct - 0.001:
                logger.info(
                    f"[止盈] 🎯 {symbol} {side_cn}盈利 {pnl_pct:.2f}% >= {tp_pct}%，触发固定止盈 | "
                    f"开仓 ${entry_price:.2f} → 标记 ${mark_price:.2f}"
                )
                await self._execute_tp_sl_close(raw_symbol, "TAKE_PROFIT", pnl_pct, entry_price, mark_price, pos_side=side)

            # 移动止盈：4 级递进盈利回撤保护（激进版：提高触发门槛，减少被洗出）
            elif trailing_enabled and pnl_pct > 0:
                trailing_stop_price = None
                trailing_reason = ""
                tightened = self._is_tightened(raw_symbol) and side == "long"

                # 收紧模式仅对多仓生效；激进版：收紧触发从">0"改为">=0.5%"
                if tightened and pnl_pct < 0.5:
                    continue

                # 移动止盈门槛基于 ATR 动态调整
                atr_base = atr_info["atr_pct"] if (atr_info and atr_info["atr_pct"] > 0) else 1.5
                l1_thr = max(atr_base * 0.8, 0.8)
                l2_thr = max(atr_base * 1.2, 1.5)
                l3_thr = max(atr_base * 1.8, 2.5)
                l4_thr = max(atr_base * 2.5, 3.5)

                if pnl_pct >= l4_thr:
                    lock = atr_base * 1.5
                    trailing_stop_price = entry_price * (1 + lock / 100) if side == "long" else entry_price * (1 - lock / 100)
                    trailing_reason = f"移动止盈L4(锁利+{lock:.1f}%): {side_cn}盈利已达 {pnl_pct:.2f}%"
                elif pnl_pct >= l3_thr:
                    lock = atr_base * 0.8
                    trailing_stop_price = entry_price * (1 + lock / 100) if side == "long" else entry_price * (1 - lock / 100)
                    trailing_reason = f"移动止盈L3(锁利+{lock:.1f}%): {side_cn}盈利已达 {pnl_pct:.2f}%"
                elif pnl_pct >= l2_thr:
                    lock = atr_base * 0.4
                    trailing_stop_price = entry_price * (1 + lock / 100) if side == "long" else entry_price * (1 - lock / 100)
                    trailing_reason = f"移动止盈L2(锁利+{lock:.1f}%): {side_cn}盈利已达 {pnl_pct:.2f}%"
                elif pnl_pct >= l1_thr:
                    trailing_stop_price = entry_price
                    trailing_reason = f"移动止盈L1(保本): {side_cn}盈利已达 {pnl_pct:.2f}%"

                if tightened and trailing_reason:
                    trailing_reason = "[SELL收紧]" + trailing_reason

                if trailing_stop_price:
                    # 多仓：价格跌破止损位触发；空仓：价格涨破止损位触发
                    trigger = (mark_price <= trailing_stop_price) if side == "long" else (mark_price >= trailing_stop_price)
                    if trigger:
                        logger.info(
                            f"[移动止盈] 📐 {symbol} {trailing_reason}，"
                            f"价格{'回落' if side == 'long' else '反弹'}至 ${mark_price:.2f}，触发平仓"
                        )
                        await self._execute_tp_sl_close(
                            raw_symbol, "TRAILING_STOP", pnl_pct, entry_price, mark_price, pos_side=side
                        )

            # 固定止损（加 0.001% 容差防止浮点边界漏判）
            elif pnl_pct <= -sl_pct + 0.001:
                logger.info(
                    f"[止损] 🛑 {symbol} {side_cn}亏损 {pnl_pct:.2f}% <= -{sl_pct}%，触发止损平仓 | "
                    f"开仓 ${entry_price:.2f} → 标记 ${mark_price:.2f}"
                )
                await self._execute_tp_sl_close(raw_symbol, "STOP_LOSS", pnl_pct, entry_price, mark_price, pos_side=side)

    async def _local_trailing_stop_check(
        self, raw_symbol: str, symbol: str, side: str, side_cn: str,
        pnl_pct: float, entry_price: float, mark_price: float,
        atr_info: Optional[dict],
    ) -> None:
        """移动止盈本地检查（4 级递进），有交易所条件单时也会调用此方法。"""
        tightened = self._is_tightened(raw_symbol) and side == "long"
        if tightened and pnl_pct < 0.5:
            return

        atr_base = atr_info["atr_pct"] if (atr_info and atr_info["atr_pct"] > 0) else 1.5
        l1_thr = max(atr_base * 0.8, 0.8)
        l2_thr = max(atr_base * 1.2, 1.5)
        l3_thr = max(atr_base * 1.8, 2.5)
        l4_thr = max(atr_base * 2.5, 3.5)

        trailing_stop_price = None
        trailing_reason = ""

        if pnl_pct >= l4_thr:
            lock = atr_base * 1.5
            trailing_stop_price = entry_price * (1 + lock / 100) if side == "long" else entry_price * (1 - lock / 100)
            trailing_reason = f"移动止盈L4(锁利+{lock:.1f}%): {side_cn}盈利已达 {pnl_pct:.2f}%"
        elif pnl_pct >= l3_thr:
            lock = atr_base * 0.8
            trailing_stop_price = entry_price * (1 + lock / 100) if side == "long" else entry_price * (1 - lock / 100)
            trailing_reason = f"移动止盈L3(锁利+{lock:.1f}%): {side_cn}盈利已达 {pnl_pct:.2f}%"
        elif pnl_pct >= l2_thr:
            lock = atr_base * 0.4
            trailing_stop_price = entry_price * (1 + lock / 100) if side == "long" else entry_price * (1 - lock / 100)
            trailing_reason = f"移动止盈L2(锁利+{lock:.1f}%): {side_cn}盈利已达 {pnl_pct:.2f}%"
        elif pnl_pct >= l1_thr:
            trailing_stop_price = entry_price
            trailing_reason = f"移动止盈L1(保本): {side_cn}盈利已达 {pnl_pct:.2f}%"

        if tightened and trailing_reason:
            trailing_reason = "[SELL收紧]" + trailing_reason

        if not trailing_stop_price:
            return

        # 有交易所条件单时：将止损单更新为移动止盈价格（升级条件单），而非本地平仓
        exchange_key = f"{raw_symbol}_{side}"
        if exchange_key in self._exchange_tp_sl:
            await self._update_exchange_sl(
                raw_symbol, side, trailing_stop_price,
                reason=f"({trailing_reason})",
            )
            return

        # 无交易所条件单时：本地触发判断
        trigger = (mark_price <= trailing_stop_price) if side == "long" else (mark_price >= trailing_stop_price)
        if trigger:
            logger.info(
                f"[移动止盈] 📐 {symbol} {trailing_reason}，"
                f"价格{'回落' if side == 'long' else '反弹'}至 ${mark_price:.2f}，触发平仓"
            )
            await self._execute_tp_sl_close(
                raw_symbol, "TRAILING_STOP", pnl_pct, entry_price, mark_price, pos_side=side
            )

    async def _execute_tp_sl_close(self, symbol: str, reason: str, pnl_pct: float, entry_price: float, mark_price: float, pos_side: str = "long"):
        """执行止盈/止损/移动止盈平仓（支持多仓和空仓）"""
        try:
            if pos_side == "long":
                result = await self._close_long(symbol)
                trade_side = "SELL"
                side_cn = "多仓"
            else:
                result = await self._close_short(symbol)
                trade_side = "COVER"
                side_cn = "空仓"

            reason_cn = {
                "TAKE_PROFIT": "止盈",
                "STOP_LOSS": "止损",
                "TRAILING_STOP": "移动止盈",
                "TIMEOUT": "AI平仓|超时",
                "WEAK_TIMEOUT": "AI平仓|超时",
            }.get(reason, "止损")
            if reason == "STOP_LOSS":
                reason_cn = "AI平仓|风控"
            await self._save_record(
                symbol=symbol, side=trade_side,
                quantity=result.get("quantity", 0),
                price=result.get("price", 0),
                quote_amount=result.get("quote_amount", 0),
                commission=result.get("commission", 0),
                status="filled",
                exchange_order_id=result.get("order_id", ""),
                signal_price=entry_price,
                error_msg=f"[{reason_cn}] {side_cn}盈亏 {pnl_pct:+.2f}% | 开仓${entry_price:.2f}→${mark_price:.2f}",
            )

            logger.info(
                f"[{reason_cn}] ✅ {symbol} 平{side_cn}成功 | "
                f"数量: {result.get('quantity', 0):.6f} | "
                f"价格: {result.get('price', 0):.2f} | "
                f"盈亏: {pnl_pct:+.2f}%"
            )

            await self._notify_tp_sl(symbol, reason_cn, pnl_pct, entry_price, mark_price, result, pos_side=pos_side)

            # 止损磨损防护：止损后冷却加倍 + 连续止损计数
            reopen_side = "BUY" if pos_side == "long" else "SHORT"
            if reason == "STOP_LOSS":
                sl_multiplier = float(getattr(settings, "TRADE_SL_COOLDOWN_MULTIPLIER", 2.0) or 2.0)
                if sl_multiplier > 1.0:
                    # 优先从 UserSettings 读取冷却秒数，fallback 到 config.py
                    _us = await self._load_user_settings_by_username(settings.ADMIN_USERNAME)
                    open_cd = (
                        int(_us.cooldown_seconds)
                        if _us and _us.cooldown_seconds is not None
                        else int(getattr(settings, "TRADE_COOLDOWN_SECONDS", 300) or 300)
                    )
                    extra = int(open_cd * (sl_multiplier - 1.0))
                    await self._set_cooldown_ts(symbol, reopen_side, time.time() + extra)
                    logger.info(f"[止损冷却] {symbol} 止损后冷却加倍: {open_cd}s × {sl_multiplier} = {open_cd + extra}s")

                tracker = _symbol_sl_tracker.get(symbol, {"count": 0, "pause_until": 0})
                tracker["count"] = tracker.get("count", 0) + 1
                max_sl = int(getattr(settings, "TRADE_MAX_CONSECUTIVE_SL", 3) or 3)
                if tracker["count"] >= max_sl:
                    pause_min = int(getattr(settings, "TRADE_SL_PAUSE_MINUTES", 30) or 30)
                    tracker["pause_until"] = time.time() + pause_min * 60
                    logger.warning(
                        f"[止损暂停] {symbol} 连续止损 {tracker['count']} 次 >= {max_sl}，"
                        f"暂停开仓 {pause_min} 分钟"
                    )
                _symbol_sl_tracker[symbol] = tracker
            elif reason in ("TAKE_PROFIT", "TRAILING_STOP"):
                if symbol in _symbol_sl_tracker:
                    _symbol_sl_tracker[symbol] = {"count": 0, "pause_until": 0}

        except Exception as e:
            logger.error(f"[止盈止损] ❌ {symbol} 平{pos_side}仓失败: {e}")

    # ========================================================
    # 持仓超时检查
    # ========================================================
    async def check_position_timeout(self):
        """
        检查持仓超时（多仓+空仓）：超过 TRADE_POSITION_TIMEOUT_HOURS 且无盈利的仓位自动平仓。
        波段策略设计持仓 1-24 小时，超时未盈利说明判断可能失误，应释放资金。
        """
        user_settings = await self._load_user_settings_by_username(settings.ADMIN_USERNAME)
        timeout_hours = (
            int(user_settings.position_timeout_hours)
            if user_settings and user_settings.position_timeout_hours is not None
            else int(settings.TRADE_POSITION_TIMEOUT_HOURS)
        )
        if timeout_hours <= 0 or not self.is_active or not self._exchange:
            return

        positions = await self._fetch_all_positions()

        for pos in positions:
            symbol = pos["symbol"]
            qty = pos["contracts"]
            entry_price = pos["entryPrice"]
            mark_price = pos["markPrice"]
            side = pos["side"]  # "long" or "short"

            if qty <= 0 or side not in ("long", "short"):
                continue

            raw_symbol = to_raw(symbol)
            side_cn = "多仓" if side == "long" else "空仓"

            leverage = float(pos.get("leverage", settings.TRADE_LEVERAGE))
            pnl_pct = calc_pnl_pct(entry_price, mark_price, side, leverage)

            # 查询该币种最后一次开仓（BUY/SHORT）成交的时间
            open_side = "BUY" if side == "long" else "SHORT"
            try:
                async with async_session() as db:
                    stmt = (
                        select(TradeRecord.created_at)
                        .where(
                            and_(
                                TradeRecord.symbol == raw_symbol,
                                TradeRecord.side == open_side,
                                TradeRecord.status == "filled",
                            )
                        )
                        .order_by(TradeRecord.created_at.desc())
                        .limit(1)
                    )
                    result = await db.execute(stmt)
                    row = result.scalar_one_or_none()

                if not row:
                    continue

                open_time = row
                now = datetime.now(timezone.utc)
                if open_time.tzinfo is None:
                    open_time = open_time.replace(tzinfo=timezone.utc)

                held_hours = (now - open_time).total_seconds() / 3600

                # 硬超时：持仓 ≥24h 且亏损 → 强制平仓
                if held_hours >= timeout_hours and pnl_pct <= 0:
                    logger.info(
                        f"[超时] ⏰ {raw_symbol} {side_cn}持仓 {held_hours:.1f}h >= {timeout_hours}h 且浮亏 {pnl_pct:.2f}%，触发超时平仓"
                    )
                    await self._execute_tp_sl_close(
                        raw_symbol, "TIMEOUT", pnl_pct, entry_price, mark_price, pos_side=side
                    )
                # 弱超时：持仓 ≥12h 且利润 <0.5% → 释放低效资金
                elif held_hours >= 12 and pnl_pct < 0.5:
                    logger.info(
                        f"[弱超时] ⏰ {raw_symbol} {side_cn}持仓 {held_hours:.1f}h >= 12h 且利润仅 {pnl_pct:.2f}% < 0.5%，触发弱超时平仓（释放低效资金）"
                    )
                    await self._execute_tp_sl_close(
                        raw_symbol, "WEAK_TIMEOUT", pnl_pct, entry_price, mark_price, pos_side=side
                    )

            except Exception as e:
                logger.error(f"[超时] 检查 {raw_symbol} {side_cn}持仓超时失败: {e}")
