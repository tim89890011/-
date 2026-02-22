"""TradingOpsMixin — position queries, open/close orders, balance, sizing, persistence, notifications."""

from __future__ import annotations

import time
import logging
from typing import Optional

from backend.config import settings
from backend.database.db import async_session
from backend.trading.models import TradeRecord
from backend.notification.telegram_bot import send_telegram_message
from backend.market.binance_ws import get_price as ws_get_price
from backend.utils.symbol import to_raw, to_ccxt, to_base
from backend.core.execution.state_manager import StateManager

logger = logging.getLogger(__name__)

# Singleton state aliases
_state = StateManager()
_symbol_sl_tracker = _state.sl_tracker
_symbol_atr = _state.symbol_atr


class TradingOpsMixin:
    """Position queries, open/close orders, balance, sizing, persistence, notifications."""

    # ========================================================
    # 合约仓位查询
    # ========================================================
    async def _fetch_all_positions(self) -> list:
        """从交易所获取所有合约仓位"""
        if not self._exchange:
            return []
        now = time.time()
        if self._position_cache and (now - self._position_cache_ts) < self._position_cache_ttl:
            return list(self._position_cache)
        try:
            positions = await self._exchange.fetch_positions()
            result = []
            for p in positions:
                contracts = float(p.get("contracts", 0))
                if contracts > 0:
                    result.append({
                        "symbol": p.get("symbol", ""),
                        "side": p.get("side", ""),
                        "contracts": contracts,
                        "contractSize": float(p.get("contractSize") or 1),
                        "entryPrice": float(p.get("entryPrice") or 0),
                        "markPrice": float(p.get("markPrice") or 0),
                        "notional": float(p.get("notional") or 0),
                        "unrealizedPnl": float(p.get("unrealizedPnl") or 0),
                        "leverage": float(p.get("leverage") or settings.TRADE_LEVERAGE),
                        "liquidationPrice": float(p.get("liquidationPrice") or 0),
                        "marginMode": p.get("marginMode", ""),
                        "initialMargin": float(p.get("initialMargin") or 0),
                        "percentage": float(p.get("percentage") or 0),
                    })
            self._position_cache = result
            self._position_cache_ts = now
            return list(result)
        except Exception as e:
            logger.error(f"[交易] 获取合约仓位失败: {e}")
            return []

    async def _get_contract_position(self, symbol: str, pos_side: str = "long") -> Optional[dict]:
        """获取单个币种的合约仓位（支持 long/short）"""
        positions = await self._fetch_all_positions()
        ccxt_symbol = to_ccxt(symbol)
        for p in positions:
            if p["symbol"] == ccxt_symbol and p["side"] == pos_side:
                return p
        return None

    async def _get_position_value(self, symbol: str, pos_side: str = "long") -> float:
        """获取单币种持仓市值（合约版）"""
        pos = await self._get_contract_position(symbol, pos_side=pos_side)
        if pos:
            return abs(pos.get("notional", 0))
        return 0.0

    # ========================================================
    # 动态仓位计算
    # ========================================================
    async def _calc_dynamic_amount(
        self, confidence: int, user_settings=None,
        symbol: str = "",
    ) -> float:
        """
        根据置信度和账户余额计算动态仓位大小（保证金金额）。
        基础仓位 = 可用余额资金池 × TRADE_AMOUNT_PCT%（可选兜底上限 TRADE_AMOUNT_USDT）
        其中"可用余额资金池"由 TRADE_BALANCE_UTILIZATION_PCT 控制：默认只动用可用余额的 80%（留 20% 备用）。
        置信度系数：60% → 0.6x  |  70% → 0.8x  |  80% → 1.0x  |  90% → 1.3x  |  95%+ → 1.5x
        注意：实际开仓名义价值 = 保证金 × 杠杆
        """
        # 计算基础仓位
        base = float(
            (user_settings.amount_usdt if user_settings and user_settings.amount_usdt is not None else settings.TRADE_AMOUNT_USDT)
            or 0
        )
        amount_pct = float(
            (user_settings.amount_pct if user_settings and user_settings.amount_pct is not None else settings.TRADE_AMOUNT_PCT)
            or 0
        )
        if amount_pct > 0 and self._exchange:
            try:
                balance = await self._exchange.fetch_balance()
                usdt_free = float(balance.get("USDT", {}).get("free", 0))
                util_pct = float(getattr(settings, "TRADE_BALANCE_UTILIZATION_PCT", 80.0) or 80.0)
                util_pct = max(0.0, min(100.0, util_pct))
                # 资金池：只动用可用余额的 util_pct%
                pool = usdt_free * util_pct / 100.0
                pct_amount = pool * amount_pct / 100.0

                # 允许将 TRADE_AMOUNT_USDT=0 表示"不要固定上限，仅按比例"
                if base > 0:
                    base = min(pct_amount, base) if pct_amount > 0 else base
                    cap_desc = f"兜底上限 ${base:.0f}"
                else:
                    base = pct_amount
                    cap_desc = "无固定上限(TRADE_AMOUNT_USDT=0)"

                # 额外防护：保证金不允许超过资金池（留出备用余额）
                base = min(base, pool)
                logger.info(
                    f"[交易] 动态仓位: 利用率{util_pct:.0f}%，"
                    f"资金池 × {amount_pct}% （{cap_desc}）→ 基础仓位已计算"
                )
            except Exception as e:
                logger.warning(f"[交易] 获取余额失败，使用固定仓位 ${base}: {e}")

        # 配置兜底：如果基础仓位<=0，直接返回 0（上层会因为数量=0 而跳过/失败）
        if base <= 0:
            return 0.0

        # 置信度系数
        if confidence >= 95:
            multiplier = 1.5
        elif confidence >= 90:
            multiplier = 1.3
        elif confidence >= 80:
            multiplier = 1.0
        elif confidence >= 70:
            multiplier = 0.8
        else:
            multiplier = 0.6

        # 连亏减仓：连续止损 ≥2 次，仓位缩小 30%
        if symbol:
            sl_count = _symbol_sl_tracker.get(symbol, {}).get("count", 0)
            if sl_count >= 2:
                multiplier *= 0.7
                logger.info(f"[仓位] {symbol} 连亏{sl_count}次，仓位系数×0.7 → {multiplier:.2f}")

        return round(base * multiplier, 2)

    async def get_balances(self) -> dict:
        """获取合约账户 USDT 余额"""
        if not self._exchange:
            return {}

        try:
            balance = await self._exchange.fetch_balance()
            result = {}

            # 合约账户只关心 USDT
            usdt_info = balance.get("USDT", {})
            free = float(usdt_info.get("free", 0))
            used = float(usdt_info.get("used", 0))
            total = free + used
            if total > 0:
                result["USDT"] = {"free": free, "used": used, "total": total}

            return result
        except Exception as e:
            logger.error(f"[交易] 获取合约余额失败: {e}")
            return {}

    # ========================================================
    # 持仓计算（合约版：供 debate.py 使用）
    # ========================================================
    async def _calc_positions(self) -> dict:
        """
        获取合约持仓信息（供 AI 辩论注入使用）。
        返回格式：{symbol_long: {...}, symbol_short: {...}}
        key 格式为 "BTCUSDT_long" / "BTCUSDT_short"
        """
        positions = await self._fetch_all_positions()
        result = {}
        for p in positions:
            raw_symbol = to_raw(p["symbol"])
            if p["side"] in ("long", "short") and p["contracts"] > 0:
                key = f"{raw_symbol}_{p['side']}"
                result[key] = {
                    "qty": p["contracts"],
                    "cost_total": p["contracts"] * p["entryPrice"],
                    "entry_price": p["entryPrice"],
                    "mark_price": p["markPrice"],
                    "unrealized_pnl": p["unrealizedPnl"],
                    "leverage": p["leverage"],
                    "liquidation_price": p["liquidationPrice"],
                    "notional": p["notional"],
                    "side": p["side"],
                }
        return result

    # ========================================================
    # 合约下单方法
    # ========================================================
    async def _open_long(
        self, symbol: str, amount_usdt: float = 0, leverage: Optional[int] = None,
        signal_price: float = 0,
    ) -> dict:
        """开多仓：用指定 USDT 保证金开多（名义价值 = 保证金 × 杠杆）"""
        assert self._exchange is not None

        if amount_usdt <= 0:
            amount_usdt = settings.TRADE_AMOUNT_USDT

        balance = await self._exchange.fetch_balance()
        usdt_free = float(balance.get("USDT", {}).get("free", 0))

        if usdt_free < amount_usdt:
            raise ValueError(f"USDT 余额不足: {usdt_free:.2f} < {amount_usdt:.2f}")

        ccxt_symbol = to_ccxt(symbol)

        # 优先用 WebSocket 缓存价格（零延迟），缓存未命中时回退 REST
        ws_data = ws_get_price(symbol)
        if ws_data and ws_data.get("price", 0) > 0:
            current_price = ws_data["price"]
        else:
            ticker = await self._exchange.fetch_ticker(ccxt_symbol)
            current_price = ticker["last"]

        # 滑点保护：价格偏差超过 2% 拒绝执行
        if signal_price > 0:
            deviation = abs(current_price - signal_price) / signal_price * 100
            if deviation > 2.0:
                raise ValueError(
                    f"[滑点保护] {symbol} 开多价格偏差 {deviation:.2f}% > 2%"
                    f"（信号价 {signal_price}, 当前价 {current_price}），拒绝执行"
                )

        # 名义价值 = 保证金 × 杠杆
        lev = int(leverage) if leverage is not None else int(settings.TRADE_LEVERAGE)
        try:
            await self._exchange.set_leverage(lev, ccxt_symbol)
        except Exception as e:
            if "No need to change" not in str(e):
                logger.warning(f"[交易] {symbol} 设置杠杆 {lev}x 失败: {e}")
        notional_value = amount_usdt * lev
        quantity = notional_value / current_price

        quantity = float(self._exchange.amount_to_precision(ccxt_symbol, quantity))

        if quantity <= 0:
            raise ValueError(f"计算后数量为 0，保证金 ${amount_usdt} 可能不足")

        order = await self._exchange.create_market_buy_order(
            ccxt_symbol, quantity, params={"positionSide": "LONG"}
        )
        self._invalidate_position_cache()
        parsed = self._parse_order(order)
        if parsed.get("order_id"):
            self._mark_order_processed(str(parsed["order_id"]))

        fill_qty = parsed.get("quantity", 0)
        fill_price = parsed.get("price", 0)
        if fill_qty > 0 and fill_price > 0:
            try:
                await self._place_exchange_tp_sl(
                    symbol, "long", fill_price, fill_qty, lev,
                )
            except Exception as e:
                logger.warning(f"[交易所条件单] {symbol} 开多后挂 TP/SL 失败（本地检查仍兜底）: {e}")
        return parsed

    async def _close_long(self, symbol: str) -> dict:
        """平多仓：平掉当前所有多头仓位"""
        assert self._exchange is not None

        pos = await self._get_contract_position(symbol, pos_side="long")
        if not pos or pos["contracts"] <= 0:
            base = to_base(symbol)
            raise ValueError(f"{base} 无多仓持仓，无法平仓")

        ccxt_symbol = to_ccxt(symbol)
        quantity = pos["contracts"]

        quantity = float(self._exchange.amount_to_precision(ccxt_symbol, quantity))

        if quantity <= 0:
            raise ValueError("平仓数量计算后为 0")

        order = await self._exchange.create_market_sell_order(
            ccxt_symbol, quantity,
            params={"positionSide": "LONG"}
        )
        self._invalidate_position_cache()
        parsed = self._parse_order(order)
        if parsed.get("order_id"):
            self._mark_order_processed(str(parsed["order_id"]))

        await self._cancel_exchange_orders(symbol, "long")
        return parsed

    async def _open_short(
        self, symbol: str, amount_usdt: float = 0, leverage: Optional[int] = None,
        signal_price: float = 0,
    ) -> dict:
        """开空仓：用指定 USDT 保证金开空（名义价值 = 保证金 × 杠杆）"""
        assert self._exchange is not None

        if amount_usdt <= 0:
            amount_usdt = settings.TRADE_AMOUNT_USDT

        balance = await self._exchange.fetch_balance()
        usdt_free = float(balance.get("USDT", {}).get("free", 0))

        if usdt_free < amount_usdt:
            raise ValueError(f"USDT 余额不足: {usdt_free:.2f} < {amount_usdt:.2f}")

        ccxt_symbol = to_ccxt(symbol)

        ws_data = ws_get_price(symbol)
        if ws_data and ws_data.get("price", 0) > 0:
            current_price = ws_data["price"]
        else:
            ticker = await self._exchange.fetch_ticker(ccxt_symbol)
            current_price = ticker["last"]

        # 滑点保护：价格偏差超过 2% 拒绝执行
        if signal_price > 0:
            deviation = abs(current_price - signal_price) / signal_price * 100
            if deviation > 2.0:
                raise ValueError(
                    f"[滑点保护] {symbol} 开空价格偏差 {deviation:.2f}% > 2%"
                    f"（信号价 {signal_price}, 当前价 {current_price}），拒绝执行"
                )

        # 名义价值 = 保证金 × 杠杆
        lev = int(leverage) if leverage is not None else int(settings.TRADE_LEVERAGE)
        try:
            await self._exchange.set_leverage(lev, ccxt_symbol)
        except Exception as e:
            if "No need to change" not in str(e):
                logger.warning(f"[交易] {symbol} 设置杠杆 {lev}x 失败: {e}")
        notional_value = amount_usdt * lev
        quantity = notional_value / current_price

        quantity = float(self._exchange.amount_to_precision(ccxt_symbol, quantity))

        if quantity <= 0:
            raise ValueError(f"计算后数量为 0，保证金 ${amount_usdt} 可能不足")

        # 开空仓 = 卖出开仓
        order = await self._exchange.create_market_sell_order(
            ccxt_symbol, quantity, params={"positionSide": "SHORT"}
        )
        self._invalidate_position_cache()
        parsed = self._parse_order(order)
        if parsed.get("order_id"):
            self._mark_order_processed(str(parsed["order_id"]))

        fill_qty = parsed.get("quantity", 0)
        fill_price = parsed.get("price", 0)
        if fill_qty > 0 and fill_price > 0:
            try:
                await self._place_exchange_tp_sl(
                    symbol, "short", fill_price, fill_qty, lev,
                )
            except Exception as e:
                logger.warning(f"[交易所条件单] {symbol} 开空后挂 TP/SL 失败（本地检查仍兜底）: {e}")
        return parsed

    async def _close_short(self, symbol: str) -> dict:
        """平空仓：平掉当前所有空头仓位"""
        assert self._exchange is not None

        pos = await self._get_contract_position(symbol, pos_side="short")
        if not pos or pos["contracts"] <= 0:
            base = to_base(symbol)
            raise ValueError(f"{base} 无空仓持仓，无法平仓")

        ccxt_symbol = to_ccxt(symbol)
        quantity = pos["contracts"]

        quantity = float(self._exchange.amount_to_precision(ccxt_symbol, quantity))

        if quantity <= 0:
            raise ValueError("平仓数量计算后为 0")

        order = await self._exchange.create_market_buy_order(
            ccxt_symbol, quantity,
            params={"positionSide": "SHORT"}
        )
        self._invalidate_position_cache()
        parsed = self._parse_order(order)
        if parsed.get("order_id"):
            self._mark_order_processed(str(parsed["order_id"]))

        await self._cancel_exchange_orders(symbol, "short")
        return parsed

    def _parse_order(self, order: dict) -> dict:
        """解析 ccxt 订单结果"""
        filled = float(order.get("filled", 0))
        cost = float(order.get("cost", 0))
        avg_price = cost / filled if filled > 0 else 0

        fee = order.get("fee", {}) or {}
        commission = float(fee.get("cost", 0))

        return {
            "order_id": str(order.get("id", "")),
            "quantity": filled,
            "price": avg_price,
            "quote_amount": cost,
            "commission": commission,
        }

    # ========================================================
    # Telegram 交易通知
    # ========================================================
    async def _notify_trade(
        self, symbol: str, side: str, confidence: int, result: dict,
        leverage_used: int = 0, margin_mode_used: str = "",
    ):
        """交易成交后推送 Telegram 通知（优先使用传入的实际参数，否则从 DB/config fallback）"""
        try:
            side_emoji = {"BUY": "🟢 开多", "SELL": "🔴 平多", "SHORT": "🔻 开空", "COVER": "🔺 平空"}.get(side, side)
            qty = result.get("quantity", 0)
            price = result.get("price", 0)
            amount = result.get("quote_amount", 0)

            # 优先使用调用方传入的实际值，否则从 DB → config fallback
            if not leverage_used or not margin_mode_used:
                us = await self._load_user_settings_by_username(settings.ADMIN_USERNAME)
                if not leverage_used:
                    leverage_used = (
                        int(us.leverage)
                        if us and us.leverage is not None
                        else int(settings.TRADE_LEVERAGE)
                    )
                if not margin_mode_used:
                    margin_mode_used = (
                        str(us.margin_mode)
                        if us and us.margin_mode
                        else str(settings.TRADE_MARGIN_MODE)
                    )

            text = (
                f"<b>💰 钢子出击 - 合约成交</b>\n\n"
                f"币种: <b>{symbol}</b>\n"
                f"方向: {side_emoji}\n"
                f"数量: {qty:.6f}\n"
                f"价格: ${price:.2f}\n"
                f"名义价值: <b>${amount:.2f} USDT</b>\n"
                f"杠杆: {leverage_used}x | 模式: {margin_mode_used}\n"
                f"置信度: {confidence}%\n\n"
                f"<i>📊 USDT永续合约 · 自动波段交易</i>"
            )
            await send_telegram_message(text)
        except Exception as e:
            logger.warning(f"[交易] Telegram 通知失败（不影响交易）: {e}")

    async def _notify_tp_sl(
        self, symbol: str, reason: str, pnl_pct: float, entry_price: float,
        mark_price: float, result: dict, pos_side: str = "long",
        leverage_used: int = 0,
    ):
        """止盈/止损/移动止盈触发后推送 Telegram 通知（优先使用传入的实际杠杆值）"""
        try:
            emoji = "🎯" if "止盈" in reason else "📐" if "移动" in reason else "⏰" if "超时" in reason else "🛑"
            qty = result.get("quantity", 0)
            amount = result.get("quote_amount", 0)
            side_cn = "多仓" if pos_side == "long" else "空仓"
            side_emoji = "🔴" if pos_side == "long" else "🔺"

            if not leverage_used:
                us = await self._load_user_settings_by_username(settings.ADMIN_USERNAME)
                leverage_used = (
                    int(us.leverage)
                    if us and us.leverage is not None
                    else int(settings.TRADE_LEVERAGE)
                )

            text = (
                f"<b>{emoji} 钢子出击 - {reason}触发</b>\n\n"
                f"币种: <b>{symbol}</b>\n"
                f"方向: {side_emoji} 自动平{side_cn}\n"
                f"数量: {qty:.6f}\n"
                f"开仓价: ${entry_price:.2f}\n"
                f"平仓价: ${mark_price:.2f}\n"
                f"名义价值: <b>${amount:.2f} USDT</b>\n"
                f"盈亏: <b>{pnl_pct:+.2f}%</b>\n"
                f"杠杆: {leverage_used}x\n\n"
                f"<i>🤖 自动{reason}执行</i>"
            )
            await send_telegram_message(text)
        except Exception as e:
            logger.warning(f"[交易] Telegram 通知失败（不影响交易）: {e}")

    async def _save_record(self, **kwargs):
        """保存交易记录到数据库，成功后标记 order_id 并广播状态"""
        try:
            oid = str(kwargs.get("exchange_order_id", "") or "")
            incoming_msg = str(kwargs.get("error_msg", "") or "")

            def _msg_priority(msg: str) -> int:
                """同一 order_id 的文案优先级：手动/一键 > AI > 交易所/其他"""
                m = str(msg or "")
                if m.startswith("[手动平仓]") or m.startswith("[一键平仓]"):
                    return 3
                if m.startswith("[AI"):
                    return 2
                return 1

            from sqlalchemy import select
            async with async_session() as db:
                async with db.begin():
                    # 同一交易所订单只保留一条记录，避免 AI 执行链路 + 交易所回报链路重复入库。
                    if oid:
                        stmt = (
                            select(TradeRecord)
                            .where(TradeRecord.exchange_order_id == oid)
                            .order_by(TradeRecord.id.desc())
                            .limit(1)
                        )
                        existing = (await db.execute(stmt)).scalar_one_or_none()
                        if existing:
                            # 同一 order_id 按优先级覆盖文案，保证来源展示准确。
                            if _msg_priority(incoming_msg) > _msg_priority(str(existing.error_msg or "")):
                                existing.error_msg = incoming_msg
                                if kwargs.get("signal_id") is not None:
                                    existing.signal_id = kwargs.get("signal_id")
                                if kwargs.get("signal_confidence") is not None:
                                    existing.signal_confidence = kwargs.get("signal_confidence")
                                if kwargs.get("signal_price") is not None:
                                    existing.signal_price = kwargs.get("signal_price")
                            # 用有值数据补齐已有记录（避免并发时先写入的记录字段不完整）
                            if kwargs.get("realized_pnl_usdt") not in (None, 0, 0.0) and float(existing.realized_pnl_usdt or 0) == 0:
                                existing.realized_pnl_usdt = kwargs.get("realized_pnl_usdt")
                            if kwargs.get("commission") not in (None, 0, 0.0) and float(existing.commission or 0) == 0:
                                existing.commission = kwargs.get("commission")
                            if kwargs.get("status") and existing.status != "filled":
                                existing.status = kwargs.get("status")
                        else:
                            record = TradeRecord(**kwargs)
                            db.add(record)
                    else:
                        record = TradeRecord(**kwargs)
                        db.add(record)
            if oid:
                self._mark_order_processed(oid)
            if self._trade_status_broadcast_cb:
                try:
                    await self._trade_status_broadcast_cb({
                        "signal_id": kwargs.get("signal_id"),
                        "symbol": kwargs.get("symbol", ""),
                        "side": kwargs.get("side", ""),
                        "status": kwargs.get("status", ""),
                        "price": kwargs.get("price"),
                        "quantity": kwargs.get("quantity"),
                        "quote_amount": kwargs.get("quote_amount"),
                        "error_msg": kwargs.get("error_msg", ""),
                    })
                except Exception as e:
                    logger.debug(f"[交易记录] 广播交易状态失败: {e}")
        except Exception as e:
            logger.error(f"[交易] 保存交易记录失败: {e}")

    async def _backfill_exchange_pnl(self, order_id: str, realized_pnl: float, commission: float):
        """用交易所 WebSocket 推送的 realized_pnl / commission 回填已有交易记录"""
        if not order_id:
            return
        try:
            from sqlalchemy import select
            async with async_session() as db:
                stmt = (
                    select(TradeRecord)
                    .where(TradeRecord.exchange_order_id == str(order_id))
                    .order_by(TradeRecord.id.desc())
                    .limit(1)
                )
                result = await db.execute(stmt)
                record = result.scalar_one_or_none()
                if not record:
                    return
                changed = False
                if realized_pnl != 0 and (record.realized_pnl_usdt is None or float(record.realized_pnl_usdt or 0) == 0):
                    record.realized_pnl_usdt = realized_pnl
                    changed = True
                if commission != 0 and (record.commission is None or float(record.commission or 0) == 0):
                    record.commission = commission
                    changed = True
                if changed:
                    await db.commit()
                    logger.info(
                        f"[交易所回填] {order_id} realized_pnl={realized_pnl:.4f} commission={commission:.6f}"
                    )
        except Exception as e:
            logger.warning(f"[交易所回填] 更新 {order_id} 失败: {e}")
