"""ExchangeOrdersMixin — exchange order lifecycle, TP/SL placement, order event callbacks."""

from __future__ import annotations

import time
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func, and_, update

from backend.config import settings
from backend.database.db import async_session
from backend.trading.models import TradeRecord
from backend.trading.pnl import calc_pnl_pct
from backend.utils.symbol import to_raw, to_ccxt
from backend.core.execution.state_manager import StateManager

logger = logging.getLogger(__name__)

# Singleton state aliases
_state = StateManager()
_symbol_atr = _state.symbol_atr
_symbol_sl_tracker = _state.sl_tracker


class ExchangeOrdersMixin:
    """Exchange order lifecycle, TP/SL placement, order event callbacks."""

    async def restore_position_meta(self) -> None:
        """服务启动时从数据库恢复 _exchange_tp_sl，防止重启后阈值丢失"""
        try:
            from backend.trading.models import PositionMeta
            async with async_session() as db:
                rows = (await db.execute(
                    select(PositionMeta).where(PositionMeta.is_active == True)
                )).scalars().all()
                for pm in rows:
                    key = f"{pm.symbol}_{pm.pos_side}"
                    self._exchange_tp_sl[key] = {
                        "tp_id": pm.tp_order_id or None,
                        "sl_id": pm.sl_order_id or None,
                        "trailing_id": pm.trailing_order_id or None,
                        "quantity": pm.quantity,
                        "entry_price": pm.entry_price,
                        "tp_pct": pm.tp_pct,
                        "sl_pct": pm.sl_pct,
                        "leverage": pm.leverage,
                    }
                if rows:
                    logger.info(f"[PositionMeta] ✅ 从数据库恢复 {len(rows)} 个仓位的 TP/SL 参数")
        except Exception as e:
            logger.warning(f"[PositionMeta] ⚠️ 恢复失败: {e}")

    # ========================================================
    # 交易所条件单管理（TP / SL / Trailing）
    # ========================================================
    async def _place_exchange_tp_sl(
        self, symbol: str, pos_side: str, entry_price: float,
        quantity: float, leverage: int,
    ) -> dict:
        """
        开仓后在交易所挂 TAKE_PROFIT_MARKET + STOP_MARKET 条件单。
        触发价基于 entry_price、leverage 和当前 ATR/默认 TP/SL 百分比。
        返回 {"tp_id": str|None, "sl_id": str|None}
        """
        assert self._exchange is not None
        raw_symbol = to_raw(symbol)
        ccxt_symbol = to_ccxt(symbol)

        user_settings = await self._load_user_settings_by_username(settings.ADMIN_USERNAME)
        default_tp = float(
            user_settings.take_profit_pct
            if user_settings and user_settings.take_profit_pct is not None
            else settings.TRADE_TAKE_PROFIT_PCT
        )
        default_sl = float(
            user_settings.stop_loss_pct
            if user_settings and user_settings.stop_loss_pct is not None
            else settings.TRADE_STOP_LOSS_PCT
        )
        atr_info = _symbol_atr.get(raw_symbol)
        if atr_info and atr_info["atr_pct"] > 0:
            atr = atr_info["atr_pct"]
            tp_pct = max(min(atr * 2.5, 8.0), 2.5)
            sl_pct = max(min(atr * 1.5, 4.0), 1.5)
        else:
            tp_pct = default_tp
            sl_pct = default_sl

        lev = max(leverage, 1)
        if pos_side == "long":
            tp_price = entry_price * (1 + tp_pct / (100 * lev))
            sl_price = entry_price * (1 - sl_pct / (100 * lev))
            close_side = "sell"
            position_side = "LONG"
        else:
            tp_price = entry_price * (1 - tp_pct / (100 * lev))
            sl_price = entry_price * (1 + sl_pct / (100 * lev))
            close_side = "buy"
            position_side = "SHORT"

        tp_price = float(self._exchange.price_to_precision(ccxt_symbol, tp_price))
        sl_price = float(self._exchange.price_to_precision(ccxt_symbol, sl_price))
        qty = float(self._exchange.amount_to_precision(ccxt_symbol, quantity))

        key = f"{raw_symbol}_{pos_side}"
        result = {
            "tp_id": None, "sl_id": None, "trailing_id": None,
            "quantity": qty, "entry_price": entry_price,
            "tp_pct": tp_pct, "sl_pct": sl_pct, "leverage": lev,
        }

        try:
            tp_order = await self._exchange.create_order(
                ccxt_symbol, "TAKE_PROFIT_MARKET", close_side, qty,
                params={
                    "stopPrice": tp_price,
                    "positionSide": position_side,
                    "workingType": "MARK_PRICE",
                },
            )
            result["tp_id"] = str(tp_order.get("id", ""))
            logger.info(
                f"[交易所TP] ✅ {raw_symbol} {pos_side} 止盈单已挂: "
                f"stopPrice=${tp_price:.4f} (账户盈利≥{tp_pct:.1f}%)"
            )
        except Exception as e:
            logger.warning(f"[交易所TP] ⚠️ {raw_symbol} {pos_side} 止盈挂单失败: {e}")

        try:
            sl_order = await self._exchange.create_order(
                ccxt_symbol, "STOP_MARKET", close_side, qty,
                params={
                    "stopPrice": sl_price,
                    "positionSide": position_side,
                    "workingType": "MARK_PRICE",
                },
            )
            result["sl_id"] = str(sl_order.get("id", ""))
            logger.info(
                f"[交易所SL] ✅ {raw_symbol} {pos_side} 止损单已挂: "
                f"stopPrice=${sl_price:.4f} (账户亏损≥{sl_pct:.1f}%)"
            )
        except Exception as e:
            logger.warning(f"[交易所SL] ⚠️ {raw_symbol} {pos_side} 止损挂单失败: {e}")

        # Trailing Stop 基础保护：callbackRate 基于 ATR（兜底 1.5%）
        trailing_enabled = bool(getattr(settings, "TRADE_TRAILING_STOP_ENABLED", True))
        if trailing_enabled:
            atr_val = atr_info["atr_pct"] if atr_info and atr_info["atr_pct"] > 0 else 1.5
            callback_rate = max(min(atr_val * 0.6, 5.0), 0.1)
            callback_rate = round(callback_rate, 1)
            try:
                trailing_order = await self._exchange.create_order(
                    ccxt_symbol, "TRAILING_STOP_MARKET", close_side, qty,
                    params={
                        "callbackRate": callback_rate,
                        "positionSide": position_side,
                        "workingType": "MARK_PRICE",
                    },
                )
                result["trailing_id"] = str(trailing_order.get("id", ""))
                logger.info(
                    f"[交易所Trailing] ✅ {raw_symbol} {pos_side} 移动止盈单已挂: "
                    f"callbackRate={callback_rate}%"
                )
            except Exception as e:
                logger.warning(f"[交易所Trailing] ⚠️ {raw_symbol} {pos_side} 移动止盈挂单失败: {e}")

        has_any = any(result.get(k) for k in ("tp_id", "sl_id", "trailing_id"))
        if has_any:
            self._exchange_tp_sl[key] = result
        else:
            logger.warning(f"[交易所条件单] ⚠️ {raw_symbol} {pos_side} 全部挂单失败，不写入跟踪字典（本地 TP/SL 兜底）")

        await self._persist_position_meta(
            raw_symbol, pos_side, entry_price, quantity, lev,
            tp_pct, sl_pct, result,
        )
        return result

    async def _persist_position_meta(
        self, symbol: str, pos_side: str, entry_price: float,
        quantity: float, leverage: int, tp_pct: float, sl_pct: float,
        order_result: dict,
    ) -> None:
        """持久化仓位 TP/SL 参数到数据库，确保重启后可恢复"""
        try:
            from backend.trading.models import PositionMeta
            async with async_session() as db:
                async with db.begin():
                    existing = (await db.execute(
                        select(PositionMeta).where(
                            PositionMeta.symbol == symbol,
                            PositionMeta.pos_side == pos_side,
                            PositionMeta.is_active == True,
                        )
                    )).scalar_one_or_none()
                    if existing:
                        existing.entry_price = entry_price
                        existing.quantity = quantity
                        existing.leverage = leverage
                        existing.tp_pct = tp_pct
                        existing.sl_pct = sl_pct
                        existing.tp_order_id = str(order_result.get("tp_id") or "")
                        existing.sl_order_id = str(order_result.get("sl_id") or "")
                        existing.trailing_order_id = str(order_result.get("trailing_id") or "")
                    else:
                        db.add(PositionMeta(
                            symbol=symbol,
                            pos_side=pos_side,
                            entry_price=entry_price,
                            quantity=quantity,
                            leverage=leverage,
                            tp_pct=tp_pct,
                            sl_pct=sl_pct,
                            tp_order_id=str(order_result.get("tp_id") or ""),
                            sl_order_id=str(order_result.get("sl_id") or ""),
                            trailing_order_id=str(order_result.get("trailing_id") or ""),
                        ))
            logger.info(f"[PositionMeta] ✅ {symbol} {pos_side} TP={tp_pct:.1f}% SL={sl_pct:.1f}% 已持久化")
        except Exception as e:
            logger.warning(f"[PositionMeta] ⚠️ {symbol} {pos_side} 持久化失败: {e}")

    def _get_saved_tp_sl(self, symbol: str, pos_side: str) -> dict | None:
        """从内存字典获取开仓时保存的 TP/SL 参数（启动时已从 DB 恢复）"""
        key = f"{symbol}_{pos_side}"
        orders = self._exchange_tp_sl.get(key)
        if orders and orders.get("tp_pct") and orders.get("sl_pct"):
            return {"tp_pct": orders["tp_pct"], "sl_pct": orders["sl_pct"]}
        return None

    async def _deactivate_position_meta(self, symbol: str, pos_side: str) -> None:
        """标记仓位元数据为已关闭"""
        try:
            from backend.trading.models import PositionMeta
            async with async_session() as db:
                async with db.begin():
                    await db.execute(
                        update(PositionMeta)
                        .where(
                            PositionMeta.symbol == symbol,
                            PositionMeta.pos_side == pos_side,
                            PositionMeta.is_active == True,
                        )
                        .values(is_active=False, closed_at=datetime.now(timezone.utc))
                    )
            logger.debug(f"[PositionMeta] {symbol} {pos_side} 已标记关闭")
        except Exception as e:
            logger.warning(f"[PositionMeta] ⚠️ {symbol} {pos_side} 标记关闭失败: {e}")

    async def _cancel_exchange_orders(self, symbol: str, pos_side: str = None) -> None:
        """
        取消某币种 / 某方向的所有 TP/SL/Trailing 条件单。
        平仓、翻仓、超时平仓时调用，保证不留孤儿单。
        先从内存字典取消已知 ID，再 fallback 查交易所 open orders 取消条件单类型。
        """
        if not self._exchange:
            return
        raw = to_raw(symbol)
        ccxt_sym = to_ccxt(symbol)
        sides = [pos_side] if pos_side else ["long", "short"]
        cancelled_ids: set[str] = set()

        for side in sides:
            key = f"{raw}_{side}"
            orders = self._exchange_tp_sl.pop(key, None)
            await self._deactivate_position_meta(raw, side)
            if not orders:
                continue
            for tag in ("tp_id", "sl_id", "trailing_id"):
                oid = orders.get(tag)
                if not oid:
                    continue
                try:
                    await self._exchange.cancel_order(oid, ccxt_sym)
                    cancelled_ids.add(str(oid))
                    logger.info(f"[取消条件单] ✅ {raw} {side} 取消 {tag}={oid}")
                except Exception as e:
                    logger.debug(
                        f"[取消条件单] {raw} {side} {tag}={oid} 取消失败(可能已触发): {e}"
                    )

        conditional_types = {
            "TAKE_PROFIT_MARKET", "TAKE_PROFIT",
            "STOP_MARKET", "STOP", "TRAILING_STOP_MARKET",
        }
        try:
            open_orders = await self._exchange.fetch_open_orders(ccxt_sym)
            for o in open_orders:
                oid_str = str(o.get("id", ""))
                o_type = (o.get("info", {}).get("type") or o.get("type", "")).upper()
                if oid_str in cancelled_ids:
                    continue
                if o_type not in conditional_types:
                    continue
                o_ps = (o.get("info", {}).get("positionSide") or "").lower()
                if pos_side and o_ps and o_ps != pos_side:
                    continue
                try:
                    await self._exchange.cancel_order(oid_str, ccxt_sym)
                    logger.info(f"[取消条件单-fallback] ✅ {raw} 取消遗留 {o_type} id={oid_str}")
                except Exception as e2:
                    logger.debug(f"[取消条件单-fallback] {raw} id={oid_str} 取消失败: {e2}")
        except Exception as e:
            logger.debug(f"[取消条件单-fallback] 查询 {raw} open orders 失败: {e}")

    async def _detect_exchange_triggered_closes(self, current_positions: list) -> None:
        """
        兜底检测：如果 on_exchange_order_update 因 WS 断连等原因漏处理，
        通过持仓消失来补录记录。正常情况下 on_exchange_order_update 已处理，
        此处只做清理。
        """
        current_keys = set()
        for pos in current_positions:
            sym = to_raw(pos["symbol"])
            current_keys.add(f"{sym}_{pos['side']}")

        for key in list(self._exchange_tp_sl.keys()):
            if key not in current_keys:
                orders = self._exchange_tp_sl.pop(key)
                raw_symbol, pos_side = key.rsplit("_", 1)
                await self._deactivate_position_meta(raw_symbol, pos_side)
                entry_price = orders.get("entry_price", 0)
                side_cn = "多仓" if pos_side == "long" else "空仓"
                logger.warning(
                    f"[兜底检测] ⚠️ {raw_symbol} {side_cn} 持仓已消失但未收到 ORDER_TRADE_UPDATE，"
                    f"可能 WS 漏推。清理跟踪记录 (开仓价${entry_price:.2f})"
                )

    async def _record_exists_by_order_id(self, order_id: str) -> bool:
        """按交易所 order_id 检查交易记录是否已存在（DB 去重兜底）"""
        oid = str(order_id or "")
        if not oid:
            return False
        try:
            async with async_session() as db:
                stmt = (
                    select(TradeRecord.id)
                    .where(TradeRecord.exchange_order_id == oid)
                    .limit(1)
                )
                row = (await db.execute(stmt)).scalar_one_or_none()
                return row is not None
        except Exception as e:
            logger.debug(f"[交易记录去重] 检查 order_id={oid} 失败: {e}")
            return False

    async def on_exchange_order_update(self, event: dict) -> None:
        """
        处理 User Data Stream 推送的订单更新事件。
        当交易所条件单（TP/SL/Trailing）被触发成交时，
        记录交易记录、推送通知，效果与本地止盈止损完全一致。
        """
        order_id = str(event.get("order_id", ""))
        status = event.get("status", "")
        symbol = event.get("symbol", "")
        logger.info(
            f"[订单回调] 收到事件: {symbol} {event.get('side','')} "
            f"status={status} oid={order_id} ps={event.get('position_side','')}"
        )
        if status != "FILLED" or not order_id:
            return

        self._invalidate_position_cache()

        if order_id in self._processed_order_ids:
            _rpnl = float(event.get("realized_pnl", 0))
            _comm = float(event.get("commission", 0))
            if _rpnl != 0 or _comm != 0:
                await self._backfill_exchange_pnl(order_id, _rpnl, _comm)
            return
        self._mark_order_processed(order_id)

        if await self._record_exists_by_order_id(order_id):
            _rpnl = float(event.get("realized_pnl", 0))
            _comm = float(event.get("commission", 0))
            if _rpnl != 0 or _comm != 0:
                await self._backfill_exchange_pnl(order_id, _rpnl, _comm)
            return
        logger.info(f"[订单回调] {symbol} oid={order_id} DB无记录，匹配TP/SL...")

        matched_key = None
        matched_reason = None
        matched_orders = None

        for key, orders in self._exchange_tp_sl.items():
            if order_id == str(orders.get("tp_id", "")):
                matched_key, matched_reason, matched_orders = key, "TAKE_PROFIT", orders
                break
            elif order_id == str(orders.get("sl_id", "")):
                matched_key, matched_reason, matched_orders = key, "STOP_LOSS", orders
                break
            elif order_id == str(orders.get("trailing_id", "")):
                matched_key, matched_reason, matched_orders = key, "TRAILING_STOP", orders
                break

        if not matched_key:
            logger.info(f"[订单回调] {symbol} oid={order_id} 非TP/SL，走外部订单处理")
            await self._handle_external_close(event)
            return

        raw_symbol, pos_side = matched_key.rsplit("_", 1)
        entry_price = matched_orders.get("entry_price", 0)
        leverage = matched_orders.get("leverage", 1)

        fill_price = float(event.get("avg_price", 0)) or float(event.get("price", 0))
        fill_qty = float(event.get("filled_qty", 0)) or float(event.get("quantity", 0))
        realized_pnl = float(event.get("realized_pnl", 0))
        commission = float(event.get("commission", 0))
        quote_amount = fill_price * fill_qty if fill_price and fill_qty else 0

        pnl_pct = calc_pnl_pct(entry_price, fill_price, pos_side, leverage) if fill_price > 0 and leverage > 0 else 0

        trade_side = "SELL" if pos_side == "long" else "COVER"
        side_cn = "多仓" if pos_side == "long" else "空仓"
        reason_cn = {
            "TAKE_PROFIT": "止盈",
            "STOP_LOSS": "止损",
            "TRAILING_STOP": "移动止盈",
        }.get(matched_reason, "止损")

        logger.info(
            f"[{reason_cn}] ✅ {raw_symbol} 交易所条件单触发平{side_cn} | "
            f"数量: {fill_qty:.6f} | 价格: ${fill_price:.2f} | "
            f"盈亏: {pnl_pct:+.2f}% | 已实现: ${realized_pnl:.4f}"
        )

        try:
            await self._save_record(
                symbol=raw_symbol,
                side=trade_side,
                quantity=fill_qty,
                price=fill_price,
                quote_amount=quote_amount,
                commission=commission,
                status="filled",
                exchange_order_id=order_id,
                signal_price=entry_price,
                realized_pnl_usdt=realized_pnl,
                error_msg=f"[{reason_cn}] {side_cn}盈亏 {pnl_pct:+.2f}% | 开仓${entry_price:.2f}→${fill_price:.2f}",
            )
        except Exception as e:
            logger.warning(f"[交易所条件单] 保存 {raw_symbol} 交易记录失败: {e}")

        try:
            result = {"quantity": fill_qty, "quote_amount": quote_amount, "price": fill_price}
            await self._notify_tp_sl(raw_symbol, reason_cn, pnl_pct, entry_price, fill_price, result, pos_side=pos_side)
        except Exception as e:
            logger.warning(f"[交易所条件单] 推送通知失败: {e}")

        try:
            await self._cancel_exchange_orders(raw_symbol, pos_side)
        except Exception as e:
            logger.warning(f"[交易所条件单] 取消 {raw_symbol} 剩余条件单失败: {e}")

        if matched_reason == "STOP_LOSS":
            reopen_side = "BUY" if pos_side == "long" else "SHORT"
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
                await self._set_cooldown_ts(raw_symbol, reopen_side, time.time() + extra)
                logger.info(f"[止损冷却] {raw_symbol} 交易所止损后冷却加倍: {open_cd}s × {sl_multiplier} = {open_cd + extra}s")

            tracker = _symbol_sl_tracker.get(raw_symbol, {"count": 0, "pause_until": 0})
            tracker["count"] = tracker.get("count", 0) + 1
            max_sl = int(getattr(settings, "TRADE_MAX_CONSECUTIVE_SL", 3) or 3)
            if tracker["count"] >= max_sl:
                pause_min = int(getattr(settings, "TRADE_SL_PAUSE_MINUTES", 30) or 30)
                tracker["pause_until"] = time.time() + pause_min * 60
                logger.warning(
                    f"[连续止损] 🚫 {raw_symbol} 连续止损 {tracker['count']} 次 >= {max_sl}，暂停 {pause_min} 分钟"
                )
            _symbol_sl_tracker[raw_symbol] = tracker

    async def _handle_external_close(self, event: dict) -> None:
        """
        处理非系统下单的订单事件（用户在币安APP/网页直接开仓或平仓）。
        支持双向持仓(LONG/SHORT)和单向持仓(BOTH)模式。
        注意：调用方 on_exchange_order_update 已做过 _processed_order_ids 去重，
        此处不再重复检查，仅做 DB 去重兜底。
        """
        oid = str(event.get("order_id", ""))
        if oid and await self._record_exists_by_order_id(oid):
            return

        order_side = event.get("side", "")           # BUY / SELL
        pos_side = event.get("position_side", "")     # LONG / SHORT / BOTH
        symbol = event.get("symbol", "")
        realized_pnl = float(event.get("realized_pnl", 0))

        # 兼容单向持仓模式(positionSide="BOTH")：用 realized_pnl 推断开/平仓
        if pos_side == "BOTH":
            if abs(realized_pnl) > 0:
                # 有已实现盈亏 → 平仓
                if order_side == "SELL":
                    pos_side = "LONG"
                elif order_side == "BUY":
                    pos_side = "SHORT"
            else:
                # 无已实现盈亏 → 开仓
                if order_side == "BUY":
                    pos_side = "LONG"
                elif order_side == "SELL":
                    pos_side = "SHORT"
            logger.info(
                f"[外部订单] {symbol} positionSide=BOTH, 推断为 {pos_side} "
                f"(side={order_side}, pnl={realized_pnl:.4f})"
            )

        is_close_long = (order_side == "SELL" and pos_side == "LONG")
        is_close_short = (order_side == "BUY" and pos_side == "SHORT")
        is_open_long = (order_side == "BUY" and pos_side == "LONG")
        is_open_short = (order_side == "SELL" and pos_side == "SHORT")

        fill_price = float(event.get("avg_price", 0)) or float(event.get("price", 0))
        fill_qty = float(event.get("filled_qty", 0)) or float(event.get("quantity", 0))
        commission = float(event.get("commission", 0))
        order_id = str(event.get("order_id", ""))
        quote_amount = fill_price * fill_qty if fill_price and fill_qty else 0

        if is_close_long or is_close_short:
            order_type_raw = (event.get("type") or "").upper()
            if fill_qty <= 0:
                return
            trade_side = "SELL" if is_close_long else "COVER"
            side_cn = "多仓" if is_close_long else "空仓"

            reason_map = {
                "TAKE_PROFIT_MARKET": "止盈",
                "TAKE_PROFIT": "止盈",
                "STOP_MARKET": "止损",
                "STOP": "止损",
                "TRAILING_STOP_MARKET": "移动止盈",
            }
            reason = reason_map.get(order_type_raw, "")
            if reason:
                tag = f"[{reason}]"
                pnl_pct_str = ""
                pos = await self._get_contract_position(symbol, pos_side=pos_side.lower())
                if pos:
                    entry = pos.get("entryPrice", 0)
                    _us_ext = await self._load_user_settings_by_username(settings.ADMIN_USERNAME)
                    _fallback_lev = (
                        int(_us_ext.leverage)
                        if _us_ext and _us_ext.leverage is not None
                        else int(settings.TRADE_LEVERAGE)
                    )
                    lev = pos.get("leverage", _fallback_lev)
                    if entry > 0 and fill_price > 0 and lev > 0:
                        pct = calc_pnl_pct(entry, fill_price, "long" if is_close_long else "short", lev)
                        pnl_pct_str = f" {pct:+.2f}%"
                elif quote_amount > 0 and realized_pnl != 0:
                    _us_ext2 = await self._load_user_settings_by_username(settings.ADMIN_USERNAME)
                    lev = (
                        int(_us_ext2.leverage)
                        if _us_ext2 and _us_ext2.leverage is not None
                        else int(settings.TRADE_LEVERAGE)
                    ) or 1
                    pct = realized_pnl / quote_amount * lev * 100
                    pnl_pct_str = f" {pct:+.2f}%"
                error_msg = f"[{reason}] {side_cn}盈亏{pnl_pct_str} | 平仓${fill_price} | 已实现 ${realized_pnl:.4f}"
            else:
                tag = "[交易所平仓]"
                error_msg = f"[交易所平仓] 平{side_cn} | 已实现盈亏 ${realized_pnl:.4f}"

            logger.info(
                f"{tag} ✅ {symbol} 外部平{side_cn} | "
                f"类型: {order_type_raw} | 数量: {fill_qty:.6f} | 价格: ${fill_price:.2f} | "
                f"已实现盈亏: ${realized_pnl:.4f}"
            )
            try:
                await self._save_record(
                    symbol=symbol,
                    side=trade_side,
                    quantity=fill_qty,
                    price=fill_price,
                    quote_amount=quote_amount,
                    commission=commission,
                    status="filled",
                    exchange_order_id=order_id,
                    realized_pnl_usdt=realized_pnl,
                    error_msg=error_msg,
                    source="exchange",
                )
            except Exception as e:
                logger.warning(f"[交易所平仓] 保存 {symbol} 交易记录失败: {e}")

            try:
                pos_key = pos_side.lower()
                await self._cancel_exchange_orders(symbol, pos_key)
            except Exception as e:
                logger.warning(f"[交易所平仓] 清理 {symbol} 条件单失败: {e}")

        elif is_open_long or is_open_short:
            trade_side = "BUY" if is_open_long else "SHORT"
            side_cn = "做多" if is_open_long else "做空"

            logger.info(
                f"[交易所开仓] ✅ {symbol} 外部{side_cn} | "
                f"数量: {fill_qty:.6f} | 价格: ${fill_price:.2f} | "
                f"金额: ${quote_amount:.2f}"
            )
            try:
                await self._save_record(
                    symbol=symbol,
                    side=trade_side,
                    quantity=fill_qty,
                    price=fill_price,
                    quote_amount=quote_amount,
                    commission=commission,
                    status="filled",
                    exchange_order_id=order_id,
                    realized_pnl_usdt=realized_pnl,
                    error_msg=f"[交易所开仓] 外部手动{side_cn}",
                    source="exchange",
                )
            except Exception as e:
                logger.warning(f"[交易所开仓] 保存 {symbol} 交易记录失败: {e}")
            return

        else:
            logger.warning(
                f"[外部订单] ⚠️ {symbol} 未识别的订单类型: side={order_side} "
                f"positionSide={event.get('position_side', '')} type={event.get('type', '')} "
                f"pnl={realized_pnl:.4f} — 跳过处理"
            )

    async def cleanup_orphan_orders(self) -> int:
        """
        清理孤儿条件单：查交易所全部挂单 vs 全部持仓，
        没有对应持仓的条件单直接取消。返回取消数量。
        """
        if not self._exchange:
            return 0

        try:
            self._invalidate_position_cache()
            positions = await self._exchange.fetch_positions()
            held_keys: set[str] = set()
            for p in positions:
                contracts = float(p.get("contracts", 0))
                if contracts > 0:
                    sym = p["symbol"]
                    side = p.get("side", "")
                    raw = to_raw(sym)
                    held_keys.add(f"{raw}_{side}")

            # 优先从 UserSettings 读取交易币种，fallback 到 config.py
            _us = await self._load_user_settings_by_username(settings.ADMIN_USERNAME)
            symbols_raw = (
                _us.symbols
                if _us and _us.symbols
                else settings.TRADE_SYMBOLS
            )
            trade_symbols = [
                to_ccxt(s.strip())
                for s in str(symbols_raw).split(",") if s.strip()
            ]
            all_open: list[dict] = []
            for ts in trade_symbols:
                try:
                    all_open.extend(await self._exchange.fetch_open_orders(ts))
                except Exception as e:
                    logger.warning(f"[孤儿单清理] 查询 {ts} 挂单失败: {e}")

            conditional_types = {
                "stop_market", "take_profit_market", "trailing_stop_market",
                "stop", "take_profit",
            }
            orphans = []
            for o in all_open:
                otype = (o.get("type") or "").lower().replace(" ", "_")
                if otype not in conditional_types:
                    continue
                sym = o.get("symbol", "")
                raw = to_raw(sym)
                info = o.get("info", {})
                ps = (info.get("positionSide") or "").lower()  # LONG/SHORT
                if not ps:
                    side_str = o.get("side", "")
                    ps = "long" if side_str == "sell" else "short"
                key = f"{raw}_{ps}"
                if key not in held_keys:
                    orphans.append(o)

            cancelled = 0
            for o in orphans:
                oid = o.get("id")
                sym = o.get("symbol", "")
                otype = o.get("type", "")
                try:
                    await self._exchange.cancel_order(oid, sym)
                    cancelled += 1
                    logger.info(f"[孤儿清理] ✅ 取消 {sym} {otype} id={oid}")
                except Exception as e:
                    logger.debug(f"[孤儿清理] 取消 {sym} id={oid} 失败: {e}")

            if cancelled:
                logger.info(f"[孤儿清理] 共取消 {cancelled}/{len(orphans)} 个孤儿条件单")
            else:
                logger.info("[孤儿清理] 无孤儿条件单")
            return cancelled

        except Exception as e:
            logger.error(f"[孤儿清理] 执行失败: {e}")
            return 0

    async def _update_exchange_sl(
        self, symbol: str, pos_side: str, new_sl_price: float, reason: str = "",
    ) -> None:
        """更新交易所止损单触发价（移动止盈升级条件单时调用）"""
        if not self._exchange:
            return
        raw = to_raw(symbol)
        ccxt_sym = to_ccxt(symbol)
        key = f"{raw}_{pos_side}"
        orders = self._exchange_tp_sl.get(key)
        if not orders:
            return
        old_id = orders.get("sl_id")
        if old_id:
            try:
                await self._exchange.cancel_order(old_id, ccxt_sym)
            except Exception as e:
                logger.debug(f"[更新SL] 取消旧止损单 {old_id} 失败(可能已触发): {e}")
            orders["sl_id"] = None
        close_side = "sell" if pos_side == "long" else "buy"
        position_side = "LONG" if pos_side == "long" else "SHORT"
        qty = orders.get("quantity", 0)
        new_sl_price = float(self._exchange.price_to_precision(ccxt_sym, new_sl_price))
        try:
            sl_order = await self._exchange.create_order(
                ccxt_sym, "STOP_MARKET", close_side, qty,
                params={
                    "stopPrice": new_sl_price,
                    "positionSide": position_side,
                    "workingType": "MARK_PRICE",
                },
            )
            orders["sl_id"] = str(sl_order.get("id", ""))
            logger.info(
                f"[更新SL] ✅ {raw} {pos_side} 止损单已更新: "
                f"stopPrice=${new_sl_price:.4f} {reason}"
            )
        except Exception as e:
            logger.warning(f"[更新SL] ⚠️ {raw} {pos_side} 更新止损单失败: {e}")

    async def _get_position_open_time(self, symbol: str, pos_side: str) -> Optional[datetime]:
        """
        尽力推断当前持仓的开仓时间，用于"最短持仓"门禁。

        规则（基于本系统 trade_records）：
        - long：最近一次 BUY 在最近一次 SELL 之后 → 视为当前多仓开仓时间
        - short：最近一次 SHORT 在最近一次 COVER 之后 → 视为当前空仓开仓时间

        若无法推断（比如历史数据缺失/不一致），返回 None（不做门禁，避免误伤）。
        """
        if pos_side not in ("long", "short"):
            return None

        open_side = "BUY" if pos_side == "long" else "SHORT"
        close_side = "SELL" if pos_side == "long" else "COVER"

        async with async_session() as session:
            last_open = (
                await session.execute(
                    select(func.max(TradeRecord.created_at)).where(
                        and_(
                            TradeRecord.symbol == symbol,
                            TradeRecord.status == "filled",
                            TradeRecord.side == open_side,
                        )
                    )
                )
            ).scalar_one_or_none()

            if not last_open:
                return None

            last_close = (
                await session.execute(
                    select(func.max(TradeRecord.created_at)).where(
                        and_(
                            TradeRecord.symbol == symbol,
                            TradeRecord.status == "filled",
                            TradeRecord.side == close_side,
                        )
                    )
                )
            ).scalar_one_or_none()

            # 如果最近一次平仓时间不早于开仓时间，说明无法确认当前仓位对应哪次开仓
            if last_close and last_close >= last_open:
                return None

            return last_open

    async def _is_under_min_hold(self, symbol: str, pos_side: str) -> tuple[bool, int]:
        """
        是否处于最短持仓期内。
        返回：(是否未到最短持仓, 剩余秒数)
        """
        min_hold = int(getattr(settings, "TRADE_MIN_HOLD_SECONDS", 0) or 0)
        if min_hold <= 0:
            return (False, 0)

        opened_at = await self._get_position_open_time(symbol, pos_side=pos_side)
        if not opened_at:
            return (False, 0)

        # SQLite 里 DateTime 可能被解析为 naive datetime；统一按 UTC 处理，避免减法报错
        if opened_at.tzinfo is None:
            opened_at = opened_at.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        age_sec = int((now - opened_at).total_seconds())
        remaining = max(0, min_hold - age_sec)
        return (remaining > 0, remaining)
