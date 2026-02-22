"""SignalExecutionMixin — signal processing with full risk gates."""

from __future__ import annotations

import time
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select, func, and_

from backend.config import settings
from backend.database.db import async_session
from backend.trading.models import TradeRecord
from backend.notification.telegram_bot import send_telegram_message
from backend.core.execution.state_manager import StateManager

from backend.trading._utils import (
    _clamp_conf,
    _parse_symbols_csv,
    _update_atr_cache,
    _get_symbol_accuracy,
    _CLOSE_COOLDOWN_SECONDS,
)

logger = logging.getLogger(__name__)

# Singleton state aliases
_state = StateManager()
_cooldown_map = _state.cooldown_map
_sell_tighten_map = _state.sell_tighten_map
_symbol_atr = _state.symbol_atr
_symbol_sl_tracker = _state.sl_tracker


class SignalExecutionMixin:
    """Signal processing with full risk gates."""

    # ========================================================
    # 核心：信号执行（含全部风控检查）
    # ========================================================
    async def execute_signal(self, signal_obj: dict, user_id: Optional[int] = None):
        """根据 AI 信号执行合约交易，含风控检查"""
        if not self.is_active or self._shutting_down:
            return

        # C-04 安全门：拒绝执行未经 RiskGate 处理或被强制降级的信号
        # debate.py 的 run_debate 调用 apply_risk_gate 后，HOLD 信号不会到达此处
        # 若有代码直接构造并传入 signal_obj 绕过 debate，需携带 _risk_gate_passed=True 标记
        side_raw = str(signal_obj.get("signal", "") or "")
        if side_raw in ("BUY", "SHORT", "SELL", "COVER"):
            if not signal_obj.get("_risk_gate_passed"):
                logger.warning(
                    f"[安全门] 信号 {signal_obj.get('symbol')} {side_raw} 未携带 RiskGate 通过标记，"
                    f"拒绝执行以防风控被绕过"
                )
                return

        task = asyncio.current_task()
        if task:
            self._in_flight_tasks.add(task)

        symbol = str(signal_obj.get("symbol", "") or "")
        side = str(signal_obj.get("signal", "") or "")
        confidence = int(signal_obj.get("confidence", 0) or 0)
        signal_price = float(signal_obj.get("price_at_signal", 0) or 0)
        signal_id = signal_obj.get("id")

        # 方案3：更新 ATR 缓存（供止盈止损使用）
        _update_atr_cache(symbol, float(signal_obj.get("atr_pct", 0) or 0))

        try:
            # 测试阶段默认按管理员配置执行（不传 user_id 时也能生效）
            if user_id:
                user_settings = await self._load_user_settings(user_id)
            else:
                user_settings = await self._load_user_settings_by_username(
                    settings.ADMIN_USERNAME
                )

            leverage_used = (
                int(user_settings.leverage)
                if user_settings and user_settings.leverage is not None
                else int(settings.TRADE_LEVERAGE)
            )
            margin_mode_used = (
                str(user_settings.margin_mode)
                if user_settings and user_settings.margin_mode
                else str(settings.TRADE_MARGIN_MODE)
            )

            # --- 检查 1: 允许交易的币种 ---
            symbols_raw = (
                user_settings.symbols
                if user_settings and user_settings.symbols
                else settings.TRADE_SYMBOLS
            )
            allowed_symbols = [
                s.strip().upper() for s in str(symbols_raw).split(",") if s.strip()
            ]
            if symbol.upper() not in allowed_symbols:
                return

            # --- 检查 2: 分类型置信度门槛 ---
            conf_thresholds = {
                "BUY": settings.TRADE_MIN_CONF_BUY,
                "COVER": settings.TRADE_MIN_CONF_BUY,
                "SHORT": settings.TRADE_MIN_CONF_SHORT,
                "SELL": settings.TRADE_MIN_CONF_SELL,
            }

            # 方案B：按币种分层门槛（Tier1=主流币用基础门槛；其他币在基础上加 delta 更严格）
            tiered_enabled = bool(getattr(settings, "TRADE_TIERED_CONFIDENCE_ENABLED", False))
            tier1_set = _parse_symbols_csv(getattr(settings, "TRADE_TIER1_SYMBOLS", "") or "")
            is_tier1 = symbol.upper() in tier1_set if tier1_set else False

            base_min_conf = int(conf_thresholds.get(side, settings.TRADE_MIN_CONFIDENCE))
            if tiered_enabled and (not is_tier1) and side in ("BUY", "COVER", "SHORT", "SELL"):
                if side in ("BUY", "COVER"):
                    base_min_conf += int(getattr(settings, "TRADE_ALTCOIN_CONF_BUY_DELTA", 0) or 0)
                elif side == "SHORT":
                    base_min_conf += int(getattr(settings, "TRADE_ALTCOIN_CONF_SHORT_DELTA", 0) or 0)
                elif side == "SELL":
                    base_min_conf += int(getattr(settings, "TRADE_ALTCOIN_CONF_SELL_DELTA", 0) or 0)
                base_min_conf = _clamp_conf(base_min_conf)

            # 方案4：基于历史准确率动态调整门槛
            try:
                sym_acc = await _get_symbol_accuracy(symbol)
                if sym_acc > 55:
                    base_min_conf = max(0, base_min_conf - 5)
                    logger.debug(f"[币种分级] {symbol} 准确率{sym_acc:.1f}% > 55% → A级，门槛-5")
                elif sym_acc < 40:
                    base_min_conf += 10
                    logger.debug(f"[币种分级] {symbol} 准确率{sym_acc:.1f}% < 40% → C级，门槛+10")
            except Exception as e:
                logger.debug(f"[币种分级] {symbol} 查询准确率失败，跳过动态调整: {e}")

            if (
                user_settings
                and isinstance(user_settings.min_confidence, int)
                and user_settings.min_confidence > 0
            ):
                min_conf = _clamp_conf(int(user_settings.min_confidence))
            else:
                min_conf = _clamp_conf(base_min_conf)

            if confidence < min_conf:
                tier_tag = "Tier1" if is_tier1 else ("Alt" if tiered_enabled else "All")
                logger.info(
                    f"[交易] {symbol} {side} 置信度 {confidence}% < {min_conf}%（{tier_tag}），跳过"
                )
                await self._save_record(
                    signal_id=signal_id,
                    symbol=symbol,
                    side=side,
                    signal_confidence=confidence,
                    signal_price=signal_price,
                    status="skipped",
                    error_msg=f"置信度不足: {confidence}% < {min_conf}%({side})",
                )
                return

            # --- 检查 3: 冷却时间 ---
            cooldown_key = f"{symbol}_{side}"
            now = time.time()
            last_time = await self._get_cooldown_ts(symbol, side)
            open_cooldown = (
                int(user_settings.cooldown_seconds)
                if user_settings and user_settings.cooldown_seconds is not None
                else int(settings.TRADE_COOLDOWN_SECONDS)
            )
            if side in ("SELL", "COVER"):
                cooldown_sec = (
                    int(user_settings.close_cooldown_seconds)
                    if user_settings and user_settings.close_cooldown_seconds is not None
                    else _CLOSE_COOLDOWN_SECONDS
                )
            else:
                cooldown_sec = open_cooldown
                # 动态冷却：根据 ATR 波动率调整开仓冷却时间
                atr_pct = _symbol_atr.get(symbol, {}).get("atr_pct", 0)
                if atr_pct > 2.0:
                    cooldown_sec = int(open_cooldown * 1.5)
                elif atr_pct < 0.5 and atr_pct > 0:
                    cooldown_sec = int(open_cooldown * 0.7)
                logger.debug(f"[冷却] {symbol} ATR={atr_pct:.2f}% 冷却={cooldown_sec}s")

            if now - last_time < cooldown_sec:
                remaining = int(cooldown_sec - (now - last_time))
                logger.info(f"[交易] {symbol} {side} 冷却中（{remaining}s），跳过")
                await self._save_record(
                    signal_id=signal_id,
                    symbol=symbol,
                    side=side,
                    signal_confidence=confidence,
                    signal_price=signal_price,
                    status="skipped",
                    error_msg=f"冷却中（剩余{remaining}s）",
                )
                return

            # --- 检查 3.6: 单币种连续止损暂停 ---
            if side in ("BUY", "SHORT"):
                tracker = _symbol_sl_tracker.get(symbol, {})
                pause_until = float(tracker.get("pause_until", 0) or 0)
                if now < pause_until:
                    remaining_min = int((pause_until - now) / 60)
                    sl_count = tracker.get("count", 0)
                    logger.info(f"[交易] {symbol} {side} 连续止损{sl_count}次暂停中（剩余{remaining_min}分钟），跳过")
                    await self._save_record(
                        signal_id=signal_id,
                        symbol=symbol,
                        side=side,
                        signal_confidence=confidence,
                        signal_price=signal_price,
                        status="skipped",
                        error_msg=f"连续止损{sl_count}次暂停中（剩余{remaining_min}min）",
                    )
                    return

            # --- 检查 3.5: 每日交易限额（仅开仓计入：BUY/SHORT） ---
            if side in ("BUY", "SHORT"):
                daily_limit = float(
                    user_settings.daily_limit_usdt
                    if user_settings and user_settings.daily_limit_usdt is not None
                    else getattr(settings, "TRADE_DAILY_LIMIT_USDT", 0.0) or 0.0
                )
                if daily_limit and daily_limit > 0:
                    tz_cn = timezone(timedelta(hours=8))
                    today_start = (
                        datetime.now(tz_cn)
                        .replace(hour=0, minute=0, second=0, microsecond=0)
                        .astimezone(timezone.utc)
                    )
                    try:
                        async with async_session() as db:
                            stmt = (
                                select(func.coalesce(func.sum(TradeRecord.quote_amount), 0.0))
                                .where(
                                    and_(
                                        TradeRecord.status == "filled",
                                        TradeRecord.created_at >= today_start,
                                        TradeRecord.side.in_(["BUY", "SHORT"]),
                                    )
                                )
                            )
                            daily_used = float((await db.execute(stmt)).scalar_one() or 0.0)
                        if daily_used >= daily_limit:
                            logger.info(
                                f"[交易] {symbol} {side} 今日开仓额 ${daily_used:.2f} >= 限额 ${daily_limit:.2f}，跳过"
                            )
                            await self._save_record(
                                signal_id=signal_id,
                                symbol=symbol,
                                side=side,
                                signal_confidence=confidence,
                                signal_price=signal_price,
                                status="skipped",
                                error_msg=f"每日限额: ${daily_used:.2f} >= ${daily_limit:.2f}",
                            )
                            return
                    except Exception as e:
                        logger.warning(f"[交易] 检查每日限额失败: {e}（将继续执行）")

            # --- 检查 4: 开仓持仓上限 ---
            if side in ("BUY", "SHORT"):
                pos_side = "long" if side == "BUY" else "short"
                pos = await self._get_contract_position(symbol, pos_side=pos_side)
                if pos:
                    notional = abs(pos.get("notional", 0))
                    max_position = float(
                        user_settings.max_position_usdt
                        if user_settings and user_settings.max_position_usdt is not None
                        else settings.TRADE_MAX_POSITION_USDT
                    )
                    limit_desc = f"固定上限 ${max_position:.0f}"

                    max_pct = float(
                        user_settings.max_position_pct
                        if user_settings and user_settings.max_position_pct is not None
                        else settings.TRADE_MAX_POSITION_PCT
                    )
                    if max_pct > 0 and self._exchange:
                        try:
                            balance = await self._exchange.fetch_balance()
                            usdt_total = float(balance.get("USDT", {}).get("total", 0))
                            pct_limit = usdt_total * max_pct / 100.0
                            if pct_limit > 0:
                                fixed = float(max_position or 0)
                                if fixed <= 0:
                                    max_position = pct_limit
                                    limit_desc = (
                                        f"总资金 ${usdt_total:.0f} × {max_pct}% = ${pct_limit:.0f}（无固定兜底）"
                                    )
                                else:
                                    max_position = max(pct_limit, fixed)
                                    limit_desc = (
                                        f"总资金 ${usdt_total:.0f} × {max_pct}% = ${pct_limit:.0f}（兜底 ${fixed:.0f}）"
                                    )
                        except Exception as e:
                            logger.warning(f"[持仓上限] 查询余额计算百分比上限失败: {e}")

                    if notional >= max_position:
                        side_cn = "多仓" if side == "BUY" else "空仓"
                        logger.info(
                            f"[交易] {symbol} {side_cn}名义 ${notional:.0f} >= 上限 ${max_position:.0f}（{limit_desc}），不再加仓"
                        )
                        await self._save_record(
                            signal_id=signal_id,
                            symbol=symbol,
                            side=side,
                            signal_confidence=confidence,
                            signal_price=signal_price,
                            status="skipped",
                            error_msg=f"{side_cn}上限: ${notional:.0f}>=${max_position:.0f}",
                        )
                        return

            # --- 执行交易 ---
            flip_conf = int(getattr(settings, "TRADE_FLIP_CONFIDENCE", 85) or 85)

            if side == "BUY":
                cover_res = None
                if confidence >= flip_conf:
                    short_pos = await self._get_contract_position(symbol, pos_side="short")
                    if short_pos and short_pos.get("contracts", 0) > 0:
                        under_hold, remaining = await self._is_under_min_hold(symbol, pos_side="short")
                        if under_hold:
                            logger.info(
                                f"[最短持仓] {symbol} 当前空仓未满 {getattr(settings, 'TRADE_MIN_HOLD_SECONDS', 0)}s，"
                                f"剩余 {remaining}s → 不允许先平空翻多，本次 BUY 跳过"
                            )
                            await self._save_record(
                                signal_id=signal_id,
                                symbol=symbol,
                                side=side,
                                signal_confidence=confidence,
                                signal_price=signal_price,
                                status="skipped",
                                error_msg=f"最短持仓({remaining}s)未到，禁止平空翻多",
                            )
                            return
                        logger.info(
                            f"[翻仓] {symbol} BUY 置信度 {confidence}% >= {flip_conf}% 且当前有空仓 → 先平空再开多"
                        )
                        cover_res = await self._close_short(symbol)
                        await self._set_cooldown_ts(symbol, "COVER", time.time())
                        await self._save_record(
                            signal_id=signal_id,
                            symbol=symbol,
                            side="COVER",
                            signal_confidence=confidence,
                            signal_price=signal_price,
                            quantity=cover_res.get("quantity", 0),
                            price=cover_res.get("price", 0),
                            quote_amount=cover_res.get("quote_amount", 0),
                            commission=cover_res.get("commission", 0),
                            status="filled",
                            exchange_order_id=cover_res.get("order_id", ""),
                            error_msg=f"翻仓：BUY>={flip_conf} 先平空(COVER)再开多(BUY)",
                        )
                        await self._notify_trade(symbol, "COVER", confidence, cover_res, leverage_used=leverage_used, margin_mode_used=margin_mode_used)

                try:
                    dynamic_amount = await self._calc_dynamic_amount(
                        confidence, user_settings=user_settings, symbol=symbol,
                    )
                    logger.info(
                        f"[交易] {symbol} 置信度 {confidence}% → 动态仓位 ${dynamic_amount:.2f}（{leverage_used}x杠杆）开多"
                    )
                    result = await self._open_long(
                        symbol, amount_usdt=dynamic_amount, leverage=leverage_used,
                        signal_price=signal_price,
                    )
                except Exception as e:
                    if cover_res is not None:
                        msg = f"[翻仓失败] {symbol} 已平空(COVER)但开多(BUY)失败：{e}，1秒后自动重试一次"
                        logger.error(msg)
                        await send_telegram_message(msg)
                        try:
                            await asyncio.sleep(1)
                            result = await self._open_long(
                                symbol, amount_usdt=dynamic_amount, leverage=leverage_used,
                                signal_price=signal_price,
                            )
                            logger.info(f"[翻仓重试] {symbol} 开多重试成功")
                        except Exception as e2:
                            err_msg = f"[翻仓失败] {symbol} 开多重试也失败：{e2}，仓位已裸奔，请手动处理"
                            logger.error(err_msg)
                            await send_telegram_message(err_msg)
                            raise
                    else:
                        raise

            elif side == "SELL":
                under_hold, remaining = await self._is_under_min_hold(symbol, pos_side="long")
                if under_hold:
                    logger.info(
                        f"[最短持仓] {symbol} 当前多仓未满 {getattr(settings, 'TRADE_MIN_HOLD_SECONDS', 0)}s，"
                        f"剩余 {remaining}s → 忽略 SELL 信号（不平仓/不收紧）"
                    )
                    await self._save_record(
                        signal_id=signal_id,
                        symbol=symbol,
                        side=side,
                        signal_confidence=confidence,
                        signal_price=signal_price,
                        status="skipped",
                        error_msg=f"最短持仓({remaining}s)未到，忽略SELL",
                    )
                    return
                sell_close_conf = int(
                    getattr(settings, "TRADE_SELL_CLOSE_CONFIDENCE", 85) or 85
                )
                if confidence >= sell_close_conf:
                    long_pos = await self._get_contract_position(symbol, pos_side="long")
                    if not long_pos or long_pos.get("contracts", 0) <= 0:
                        await self._save_record(
                            signal_id=signal_id,
                            symbol=symbol,
                            side=side,
                            signal_confidence=confidence,
                            signal_price=signal_price,
                            status="skipped",
                            error_msg=f"SELL≥{sell_close_conf} 但当前无多仓，已忽略",
                        )
                        logger.info(f"[交易] {symbol} SELL(>={sell_close_conf}) 但无多仓，跳过")
                        return
                    logger.info(
                        f"[交易] {symbol} SELL 置信度 {confidence}% >= {sell_close_conf}% → 直接平多"
                    )
                    result = await self._close_long(symbol)
                else:
                    self._tighten_trailing_stop(symbol, confidence)
                    await self._save_record(
                        signal_id=signal_id,
                        symbol=symbol,
                        side=side,
                        signal_confidence=confidence,
                        signal_price=signal_price,
                        status="skipped",
                        error_msg=f"SELL→收紧止损(不直接平仓) 置信度{confidence}%",
                    )
                    logger.info(
                        f"[交易] {symbol} SELL 信号 → 不直接平仓，收紧移动止损（置信度{confidence}%）"
                    )
                    return

            elif side == "SHORT":
                sell_res = None
                if confidence >= flip_conf:
                    long_pos = await self._get_contract_position(symbol, pos_side="long")
                    if long_pos and long_pos.get("contracts", 0) > 0:
                        under_hold, remaining = await self._is_under_min_hold(symbol, pos_side="long")
                        if under_hold:
                            logger.info(
                                f"[最短持仓] {symbol} 当前多仓未满 {getattr(settings, 'TRADE_MIN_HOLD_SECONDS', 0)}s，"
                                f"剩余 {remaining}s → 不允许先平多翻空，本次 SHORT 跳过"
                            )
                            await self._save_record(
                                signal_id=signal_id,
                                symbol=symbol,
                                side=side,
                                signal_confidence=confidence,
                                signal_price=signal_price,
                                status="skipped",
                                error_msg=f"最短持仓({remaining}s)未到，禁止平多翻空",
                            )
                            return
                        logger.info(
                            f"[翻仓] {symbol} SHORT 置信度 {confidence}% >= {flip_conf}% 且当前有多仓 → 先平多再开空"
                        )
                        sell_res = await self._close_long(symbol)
                        await self._set_cooldown_ts(symbol, "SELL", time.time())
                        await self._save_record(
                            signal_id=signal_id,
                            symbol=symbol,
                            side="SELL",
                            signal_confidence=confidence,
                            signal_price=signal_price,
                            quantity=sell_res.get("quantity", 0),
                            price=sell_res.get("price", 0),
                            quote_amount=sell_res.get("quote_amount", 0),
                            commission=sell_res.get("commission", 0),
                            status="filled",
                            exchange_order_id=sell_res.get("order_id", ""),
                            error_msg=f"翻仓：SHORT>={flip_conf} 先平多(SELL)再开空(SHORT)",
                        )
                        await self._notify_trade(symbol, "SELL", confidence, sell_res, leverage_used=leverage_used, margin_mode_used=margin_mode_used)

                try:
                    dynamic_amount = await self._calc_dynamic_amount(
                        confidence, user_settings=user_settings, symbol=symbol,
                    )
                    logger.info(
                        f"[交易] {symbol} 置信度 {confidence}% → 动态仓位 ${dynamic_amount:.2f}（{leverage_used}x杠杆）开空"
                    )
                    result = await self._open_short(
                        symbol, amount_usdt=dynamic_amount, leverage=leverage_used,
                        signal_price=signal_price,
                    )
                except Exception as e:
                    if sell_res is not None:
                        msg = f"[翻仓失败] {symbol} 已平多(SELL)但开空(SHORT)失败：{e}，1秒后自动重试一次"
                        logger.error(msg)
                        await send_telegram_message(msg)
                        try:
                            await asyncio.sleep(1)
                            result = await self._open_short(
                                symbol, amount_usdt=dynamic_amount, leverage=leverage_used,
                                signal_price=signal_price,
                            )
                            logger.info(f"[翻仓重试] {symbol} 开空重试成功")
                        except Exception as e2:
                            err_msg = f"[翻仓失败] {symbol} 开空重试也失败：{e2}，仓位已裸奔，请手动处理"
                            logger.error(err_msg)
                            await send_telegram_message(err_msg)
                            raise
                    else:
                        raise

            elif side == "COVER":
                under_hold, remaining = await self._is_under_min_hold(symbol, pos_side="short")
                if under_hold:
                    logger.info(
                        f"[最短持仓] {symbol} 当前空仓未满 {getattr(settings, 'TRADE_MIN_HOLD_SECONDS', 0)}s，"
                        f"剩余 {remaining}s → 忽略 COVER 信号"
                    )
                    await self._save_record(
                        signal_id=signal_id,
                        symbol=symbol,
                        side=side,
                        signal_confidence=confidence,
                        signal_price=signal_price,
                        status="skipped",
                        error_msg=f"最短持仓({remaining}s)未到，忽略COVER",
                    )
                    return
                result = await self._close_short(symbol)
            else:
                return

            await self._set_cooldown_ts(symbol, side, time.time())

            # 生成交易原因描述（供前端 closeTag 使用）
            if side == "SELL":
                _exec_reason = f"[AI平仓|反向信号] 看空信号平多 置信度{confidence}%"
            elif side == "COVER":
                _exec_reason = f"[AI平仓|反向信号] 看多信号平空 置信度{confidence}%"
            elif side == "BUY":
                _exec_reason = f"[AI开仓] 看多信号开多 置信度{confidence}%"
            elif side == "SHORT":
                _exec_reason = f"[AI开仓] 看空信号开空 置信度{confidence}%"
            else:
                _exec_reason = f"[AI信号] {side} 置信度{confidence}%"

            await self._save_record(
                signal_id=signal_id,
                symbol=symbol,
                side=side,
                signal_confidence=confidence,
                signal_price=signal_price,
                quantity=result.get("quantity", 0),
                price=result.get("price", 0),
                quote_amount=result.get("quote_amount", 0),
                commission=result.get("commission", 0),
                status="filled",
                exchange_order_id=result.get("order_id", ""),
                error_msg=_exec_reason,
            )

            logger.info(
                f"[交易] ✅ {symbol} {side} 成功 | "
                f"数量: {result.get('quantity', 0):.6f} | "
                f"价格: {result.get('price', 0):.2f} | "
                f"金额: {result.get('quote_amount', 0):.2f} USDT | "
                f"杠杆: {leverage_used}x"
            )

            await self._notify_trade(symbol, side, confidence, result, leverage_used=leverage_used, margin_mode_used=margin_mode_used)

        except Exception as e:
            logger.error(f"[交易] ❌ {symbol} {side} 失败: {e}")
            await self._save_record(
                signal_id=signal_id,
                symbol=symbol,
                side=side,
                signal_confidence=confidence,
                signal_price=signal_price,
                status="failed",
                error_msg=str(e),
            )
        finally:
            if task:
                self._in_flight_tasks.discard(task)

    # ========================================================
    # SELL 信号 → 收紧止损（不直接平仓）
    # ========================================================
    def _tighten_trailing_stop(self, symbol: str, confidence: int):
        """
        SELL 信号不直接平多，而是记录收紧标记。
        check_stop_loss_take_profit 会读取此标记，将移动止盈门槛降低：
        - 正常：盈利 >= 1.5% 才启动 L1（保本）
        - 收紧后：盈利 >= 0.5% 才开始启用移动止盈（更快锁利）
        收紧标记有效期 30 分钟，过期自动恢复正常。
        """
        _sell_tighten_map[symbol] = {
            "time": time.time(),
            "confidence": confidence,
        }
        logger.info(f"[收紧止损] {symbol} SELL信号触发收紧模式（置信度{confidence}%），30分钟内移动止损升级")

    def _is_tightened(self, symbol: str) -> bool:
        """检查该币种是否处于 SELL 信号收紧模式（30 分钟有效期）"""
        info = _sell_tighten_map.get(symbol)
        if not info:
            return False
        if time.time() - info["time"] > 1800:  # 30 分钟过期
            del _sell_tighten_map[symbol]
            return False
        return True
