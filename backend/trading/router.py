"""
钢子出击 - 自动交易 API 端点
提供交易状态查看、开关控制、历史查询、持仓盈亏、交易统计
"""

import logging
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, and_

from backend.database.db import get_db
from backend.auth.jwt_utils import get_current_user
from backend.trading.executor import auto_trader, _symbol_sl_tracker, _symbol_atr, _cooldown_map, _symbol_accuracy_cache
from backend.trading.models import TradeRecord
from backend.config import settings
from backend.ai_engine.signal_history import get_accuracy_stats
from backend.utils.symbol import to_raw, to_base
from backend.database.models import UserSettings, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/trade", tags=["自动交易"])


async def _load_effective_params() -> dict:
    """加载有效交易参数：优先 UserSettings（管理员），fallback config.py。

    返回 8 个高频调整参数的当前有效值，供 API 展示。
    """
    from backend.database.db import async_session
    us = None
    try:
        async with async_session() as db:
            u = await db.execute(select(User).where(User.username == settings.ADMIN_USERNAME))
            user = u.scalar_one_or_none()
            if user:
                s = await db.execute(select(UserSettings).where(UserSettings.user_id == int(user.id)))
                us = s.scalar_one_or_none()
    except Exception as e:
        logger.warning(f"[router] 读取 UserSettings 失败: {e}")

    return {
        "leverage": int(us.leverage) if us and us.leverage is not None else int(settings.TRADE_LEVERAGE),
        "margin_mode": str(us.margin_mode) if us and us.margin_mode else str(settings.TRADE_MARGIN_MODE),
        "amount_usdt": float(us.amount_usdt) if us and us.amount_usdt is not None else float(settings.TRADE_AMOUNT_USDT),
        "cooldown_seconds": int(us.cooldown_seconds) if us and us.cooldown_seconds is not None else int(settings.TRADE_COOLDOWN_SECONDS),
        "close_cooldown_seconds": int(us.close_cooldown_seconds) if us and getattr(us, "close_cooldown_seconds", None) is not None else 30,
        "min_confidence": int(us.min_confidence) if us and us.min_confidence is not None else int(settings.TRADE_MIN_CONFIDENCE),
        "take_profit_pct": float(us.take_profit_pct) if us and us.take_profit_pct is not None else float(settings.TRADE_TAKE_PROFIT_PCT),
        "stop_loss_pct": float(us.stop_loss_pct) if us and us.stop_loss_pct is not None else float(settings.TRADE_STOP_LOSS_PCT),
        "symbols": str(us.symbols) if us and us.symbols else str(settings.TRADE_SYMBOLS),
    }


def _ok(data: dict) -> dict:
    return {"code": 0, "message": "ok", **data}


@router.post("/close-all")
async def close_all_positions(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """一键平仓：平掉所有合约持仓"""
    if not auto_trader._exchange:
        return {"code": 1, "message": "交易所未连接"}

    positions = await auto_trader._fetch_all_positions()
    if not positions:
        return _ok({"closed": 0, "message": "当前无持仓"})

    results = []
    for p in positions:
        raw_symbol = to_raw(p["symbol"])
        side = p["side"]
        contracts = p["contracts"]
        try:
            if side == "long":
                res = await auto_trader._close_long(raw_symbol)
                trade_side = "SELL"
            else:
                res = await auto_trader._close_short(raw_symbol)
                trade_side = "COVER"

            # 记录到交易表
            record = TradeRecord(
                symbol=raw_symbol,
                side=trade_side,
                order_type="MARKET",
                quantity=res.get("quantity", 0),
                price=res.get("price", 0),
                quote_amount=res.get("quote_amount", 0),
                commission=res.get("commission", 0),
                status="filled",
                exchange_order_id=res.get("order_id", ""),
                error_msg=f"[一键平仓] 手动平{'多' if side == 'long' else '空'}仓",
            )
            db.add(record)
            results.append({
                "symbol": raw_symbol, "side": side,
                "qty": contracts, "status": "ok",
            })
            logger.info(f"[一键平仓] ✅ {raw_symbol} {side} 已平仓 | 数量: {contracts}")
        except Exception as e:
            results.append({
                "symbol": raw_symbol, "side": side,
                "qty": contracts, "status": "fail", "error": str(e),
            })
            logger.error(f"[一键平仓] ❌ {raw_symbol} {side} 平仓失败: {e}")

    await db.commit()

    ok_count = sum(1 for r in results if r["status"] == "ok")
    fail_count = sum(1 for r in results if r["status"] == "fail")
    return _ok({
        "closed": ok_count,
        "failed": fail_count,
        "total": len(results),
        "details": results,
        "message": f"已平仓 {ok_count} 个仓位" + (f"，{fail_count} 个失败" if fail_count else ""),
    })


@router.post("/close-position")
async def close_single_position(
    request: Request,
    user=Depends(get_current_user),
):
    """单币种手动平仓"""
    body = await request.json()
    symbol = (body.get("symbol") or "").strip().upper()
    pos_side = (body.get("side") or "long").strip().lower()

    if not symbol:
        return {"code": 1, "message": "缺少 symbol 参数"}
    if pos_side not in ("long", "short"):
        return {"code": 1, "message": "side 参数错误，需为 long 或 short"}
    if not auto_trader._exchange:
        return {"code": 1, "message": "交易所未连接"}

    raw_symbol = to_raw(symbol)
    side_cn = "多" if pos_side == "long" else "空"

    try:
        if pos_side == "long":
            res = await auto_trader._close_long(raw_symbol)
            trade_side = "SELL"
        else:
            res = await auto_trader._close_short(raw_symbol)
            trade_side = "COVER"

        await auto_trader._save_record(
            symbol=raw_symbol,
            side=trade_side,
            quantity=res.get("quantity", 0),
            price=res.get("price", 0),
            quote_amount=res.get("quote_amount", 0),
            commission=res.get("commission", 0),
            status="filled",
            exchange_order_id=res.get("order_id", ""),
            error_msg=f"[手动平仓] 手动平{side_cn}仓",
        )

        logger.info(f"[手动平仓] ✅ {raw_symbol} {pos_side} 已平仓")
        return _ok({
            "symbol": raw_symbol,
            "side": pos_side,
            "status": "ok",
            "message": f"{raw_symbol} {side_cn}仓已平仓",
        })
    except Exception as e:
        logger.error(f"[手动平仓] ❌ {raw_symbol} {pos_side} 平仓失败: {e}")
        return {"code": 1, "message": f"平仓失败: {str(e)}"}


@router.get("/status")
async def get_trade_status(user=Depends(get_current_user)):
    """查看自动交易状态"""
    balances = await auto_trader.get_balances()
    usdt_free = float((balances or {}).get("USDT", {}).get("free", 0))

    ep = await _load_effective_params()
    return _ok({
        "trade_enabled": settings.TRADE_ENABLED,
        "runtime_active": auto_trader.is_active,
        "exchange_connected": auto_trader.exchange_connected,
        "exchange_error": auto_trader.exchange_error or "",
        "balance_warning": usdt_free < 10,
        "amount_usdt": ep["amount_usdt"],
        "min_confidence": ep["min_confidence"],
        "symbols": ep["symbols"],
        "balances": balances,
    })


@router.post("/toggle")
async def toggle_trade(user=Depends(get_current_user)):
    """切换自动交易开关（运行时）"""
    if not settings.TRADE_ENABLED:
        return _ok({
            "message": "自动交易未在配置中启用（TRADE_ENABLED=false），请修改 .env 后重启",
            "active": False,
            "reason": "config_disabled",
        })

    if not auto_trader.exchange_connected:
        error_hint = auto_trader.exchange_error
        if "429" in error_hint or "Too Many" in error_hint:
            msg = "交易所 API 请求过于频繁被限速，系统将自动恢复，请稍后重试"
        elif "Key" in error_hint or "key" in error_hint or "auth" in error_hint.lower():
            msg = "交易所 API Key 无效或过期，请检查 .env 配置"
        else:
            msg = f"交易所连接断开，请稍后重试（{error_hint[:80]}）" if error_hint else "交易所连接断开，请稍后重试"
        return _ok({
            "message": msg,
            "active": False,
            "reason": "exchange_disconnected",
        })

    new_state = not auto_trader.is_active
    auto_trader.toggle(new_state)

    return _ok({
        "message": f"自动交易已{'开启' if new_state else '暂停'}",
        "active": new_state,
        "reason": "ok",
    })


@router.get("/history")
async def get_trade_history(
    limit: int = 20,
    offset: int = 0,
    symbol: str = "",
    today: bool = False,
    status: str = "",
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """查看交易历史"""
    query = select(TradeRecord).order_by(desc(TradeRecord.created_at))
    count_query = select(func.count(TradeRecord.id))

    filters = []
    if symbol:
        filters.append(TradeRecord.symbol == symbol.upper())

    # today=1：按北京时间零点作为“今日”起点，再换算回 UTC 过滤 created_at
    if today:
        tz_cn = timezone(timedelta(hours=8))
        now_cn = datetime.now(tz_cn)
        today_start = (
            now_cn.replace(hour=0, minute=0, second=0, microsecond=0)
            .astimezone(timezone.utc)
        )
        filters.append(TradeRecord.created_at >= today_start)

    if filters:
        query = query.where(and_(*filters))
        count_query = count_query.where(and_(*filters))

    # status=filled/failed/skipped：服务端过滤，避免 filled 被大量 skipped 挤出分页窗口
    if status:
        st = status.strip().lower()
        if st in ("filled", "failed", "skipped", "pending"):
            query = query.where(TradeRecord.status == st)
            count_query = count_query.where(TradeRecord.status == st)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # 分页
    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    records = result.scalars().all()

    # 为 SELL/COVER 增加“已实现盈亏（不扣手续费）”
    # 计算方式：均价成本法按时间顺序配对 BUY<->SELL、SHORT<->COVER
    realized_map: dict[int, float] = {}
    try:
        close_ids = [r.id for r in records if r.status == "filled" and r.side in ("SELL", "COVER") and r.id]
        if close_ids:
            involved_symbols = sorted({r.symbol for r in records if r.status == "filled" and r.side in ("SELL", "COVER")})
            max_dt = max((r.created_at for r in records if r.created_at), default=None)
            if involved_symbols and max_dt:
                all_q = (
                    select(TradeRecord)
                    .where(
                        and_(
                            TradeRecord.status == "filled",
                            TradeRecord.symbol.in_(involved_symbols),
                            TradeRecord.side.in_(("BUY", "SELL", "SHORT", "COVER")),
                            TradeRecord.created_at <= max_dt,
                        )
                    )
                    .order_by(TradeRecord.created_at)
                )
                all_res = await db.execute(all_q)
                all_records = all_res.scalars().all()

                _long_pos: dict[str, dict] = {}   # symbol -> {qty, cost_total}
                _short_pos: dict[str, dict] = {}  # symbol -> {qty, cost_total}

                for r in all_records:
                    sym = r.symbol
                    qty = float(r.quantity or 0)
                    price = float(r.price or 0)
                    if qty <= 0 or price <= 0:
                        continue

                    if r.side == "BUY":
                        p = _long_pos.setdefault(sym, {"qty": 0.0, "cost_total": 0.0})
                        p["qty"] += qty
                        p["cost_total"] += qty * price
                    elif r.side == "SELL":
                        p = _long_pos.setdefault(sym, {"qty": 0.0, "cost_total": 0.0})
                        if p["qty"] > 0:
                            avg_cost = p["cost_total"] / p["qty"]
                            sell_qty = min(qty, p["qty"])
                            trade_pnl = sell_qty * (price - avg_cost)
                            realized_map[r.id] = round(trade_pnl, 8)
                            p["cost_total"] -= sell_qty * avg_cost
                            p["qty"] -= sell_qty
                    elif r.side == "SHORT":
                        p = _short_pos.setdefault(sym, {"qty": 0.0, "cost_total": 0.0})
                        p["qty"] += qty
                        p["cost_total"] += qty * price
                    elif r.side == "COVER":
                        p = _short_pos.setdefault(sym, {"qty": 0.0, "cost_total": 0.0})
                        if p["qty"] > 0:
                            avg_cost = p["cost_total"] / p["qty"]
                            cover_qty = min(qty, p["qty"])
                            trade_pnl = cover_qty * (avg_cost - price)
                            realized_map[r.id] = round(trade_pnl, 8)
                            p["cost_total"] -= cover_qty * avg_cost
                            p["qty"] -= cover_qty
    except Exception as e:
        logger.warning(f"[history] 计算已实现盈亏失败（忽略，不影响返回）: {e}")

    history = []
    for r in records:
        history.append({
            "id": r.id,
            "signal_id": r.signal_id,
            "symbol": r.symbol,
            "side": r.side,
            "order_type": r.order_type,
            "quantity": r.quantity,
            "price": r.price,
            "quote_amount": r.quote_amount,
            "commission": r.commission,
            "signal_confidence": r.signal_confidence,
            "signal_price": r.signal_price,
            "status": r.status,
            "exchange_order_id": r.exchange_order_id,
            "error_msg": r.error_msg,
            "realized_pnl_usdt": (
                round(float(r.realized_pnl_usdt), 2)
                if r.realized_pnl_usdt is not None and float(r.realized_pnl_usdt or 0) != 0
                else (round(float(realized_map.get(r.id)), 2) if r.id in realized_map else None)
            ),
            "created_at": (r.created_at.isoformat() + "Z") if r.created_at else "",
        })

    return _ok({"total": total, "history": history})


@router.get("/positions")
async def get_positions(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    查看当前合约持仓 & 盈亏
    直接从交易所获取合约仓位信息（更准确，含杠杆、强平价等）
    """
    # 从交易所获取合约仓位（多仓 + 空仓）
    raw_positions = await auto_trader._fetch_all_positions()

    pos_list = []
    total_notional = 0.0
    total_pnl = 0.0
    total_margin = 0.0

    for p in raw_positions:
        if p["contracts"] <= 0 or p["side"] not in ("long", "short"):
            continue

        raw_symbol = to_raw(p["symbol"])
        base_currency = to_base(p["symbol"])
        entry_price = p["entryPrice"]
        mark_price = p["markPrice"]
        notional = abs(p["notional"])
        unrealized_pnl = p["unrealizedPnl"]
        leverage = p["leverage"]
        liq_price = p["liquidationPrice"]
        margin = p["initialMargin"]
        pnl_pct = p["percentage"]
        pos_side = p["side"]  # "long" or "short"

        total_notional += notional
        total_pnl += unrealized_pnl
        total_margin += margin

        # 获取交易记录中的开/平仓次数
        open_side = "BUY" if pos_side == "long" else "SHORT"
        close_side = "SELL" if pos_side == "long" else "COVER"
        open_count_result = await db.execute(
            select(func.count(TradeRecord.id)).where(
                and_(TradeRecord.symbol == raw_symbol, TradeRecord.side == open_side, TradeRecord.status == "filled")
            )
        )
        close_count_result = await db.execute(
            select(func.count(TradeRecord.id)).where(
                and_(TradeRecord.symbol == raw_symbol, TradeRecord.side == close_side, TradeRecord.status == "filled")
            )
        )
        open_count = open_count_result.scalar() or 0
        close_count = close_count_result.scalar() or 0

        # 动态止盈止损等级（实时计算）
        atr_info = _symbol_atr.get(raw_symbol, {})
        atr_pct = atr_info.get("atr_pct", 0) if atr_info else 0
        atr_base = atr_pct if atr_pct > 0 else 1.5
        tp_pct = max(min(atr_base * 2.5, 8.0), 2.5)
        sl_pct = max(min(atr_base * 1.5, 4.0), 1.5)
        fixed_tp = float(getattr(settings, "TRADE_TAKE_PROFIT_PCT", 0) or 0)
        fixed_sl = float(getattr(settings, "TRADE_STOP_LOSS_PCT", 0) or 0)
        final_tp = min(tp_pct, fixed_tp) if fixed_tp > 0 else tp_pct
        final_sl = min(sl_pct, fixed_sl) if fixed_sl > 0 else sl_pct

        # 移动止盈等级判断
        abs_pnl_pct = abs(pnl_pct) if pnl_pct else 0
        l1_thr = max(atr_base * 0.8, 0.8)
        l2_thr = max(atr_base * 1.2, 1.5)
        l3_thr = max(atr_base * 1.8, 2.5)
        l4_thr = max(atr_base * 2.5, 3.5)
        if abs_pnl_pct >= l4_thr:
            trailing_level = "L4"
        elif abs_pnl_pct >= l3_thr:
            trailing_level = "L3"
        elif abs_pnl_pct >= l2_thr:
            trailing_level = "L2"
        elif abs_pnl_pct >= l1_thr:
            trailing_level = "L1"
        else:
            trailing_level = "无"

        pos_list.append({
            "symbol": raw_symbol,
            "currency": base_currency,
            "side": pos_side,
            "quantity": round(p["contracts"], 8),
            "avg_price": float(entry_price),
            "current_price": float(mark_price),
            "cost_value": round(margin, 2),
            "market_value": round(notional, 2),
            "pnl": round(unrealized_pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "leverage": int(leverage),
            "liquidation_price": float(liq_price),
            "buy_count": open_count,
            "sell_count": close_count,
            "dynamic_tp_sl": {
                "atr_pct": round(atr_pct, 2),
                "dynamic_tp": round(final_tp, 2),
                "dynamic_sl": round(final_sl, 2),
                "fixed_tp": fixed_tp,
                "fixed_sl": fixed_sl,
                "trailing_level": trailing_level,
            },
        })

    total_pnl_pct = (total_pnl / total_margin * 100) if total_margin > 0 else 0

    return _ok({
        "positions": pos_list,
        "summary": {
            "total_cost": round(total_margin, 2),
            "total_value": round(total_notional, 2),
            "total_pnl": round(total_pnl, 2),
            "total_pnl_pct": round(total_pnl_pct, 2),
            "position_count": len(pos_list),
        },
    })


@router.get("/stats")
async def get_trade_stats(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    交易统计：今日战绩、累计数据、账户总览
    """
    # 按中国习惯：以北京时间（UTC+8）零点作为“今日”起点，再换算回 UTC 查库。
    # 说明：TradeRecord.created_at 统一用 UTC 存储/比较，这里只调整“今日窗口”的边界。
    tz_cn = timezone(timedelta(hours=8))
    now_cn = datetime.now(tz_cn)
    today_start = (
        now_cn.replace(hour=0, minute=0, second=0, microsecond=0)
        .astimezone(timezone.utc)
    )

    # --- 今日统计 ---
    today_status_result = await db.execute(
        select(TradeRecord.status, func.count(TradeRecord.id)).where(
            TradeRecord.created_at >= today_start
        ).group_by(TradeRecord.status)
    )
    today_status_counts = {r[0]: r[1] for r in today_status_result.all()}

    today_filled = await db.execute(
        select(TradeRecord).where(
            and_(
                TradeRecord.created_at >= today_start,
                TradeRecord.status == "filled",
            )
        )
    )
    today_records = today_filled.scalars().all()

    today_buy_count = sum(1 for r in today_records if r.side == "BUY")
    today_sell_count = sum(1 for r in today_records if r.side == "SELL")
    today_short_count = sum(1 for r in today_records if r.side == "SHORT")
    today_cover_count = sum(1 for r in today_records if r.side == "COVER")
    today_buy_volume = sum(r.quote_amount for r in today_records if r.side == "BUY")
    today_sell_volume = sum(r.quote_amount for r in today_records if r.side == "SELL")
    today_short_volume = sum(r.quote_amount for r in today_records if r.side == "SHORT")
    today_cover_volume = sum(r.quote_amount for r in today_records if r.side == "COVER")
    today_commission = sum(r.commission for r in today_records)

    # --- 今日止盈/止损次数（从 error_msg 标记统计） ---
    today_tp_count = sum(1 for r in today_records if r.error_msg and "[止盈]" in r.error_msg)
    today_sl_count = sum(1 for r in today_records if r.error_msg and "[止损]" in r.error_msg)
    today_trailing_count = sum(1 for r in today_records if r.error_msg and "[移动止盈]" in r.error_msg)

    # --- 今日止损暂停拦截次数 ---
    sl_blocked_result = await db.execute(
        select(func.count(TradeRecord.id)).where(
            and_(
                TradeRecord.created_at >= today_start,
                TradeRecord.status == "skipped",
                TradeRecord.error_msg.like("%连续止损%暂停%"),
            )
        )
    )
    today_sl_blocked = sl_blocked_result.scalar() or 0

    # --- 累计统计 ---
    all_filled_result = await db.execute(
        select(
            func.count(TradeRecord.id),
            func.sum(TradeRecord.quote_amount),
            func.sum(TradeRecord.commission),
        ).where(TradeRecord.status == "filled")
    )
    row = all_filled_result.one()
    total_trades = row[0] or 0
    total_volume = float(row[1] or 0)
    total_commission = float(row[2] or 0)

    # 各状态计数
    status_result = await db.execute(
        select(TradeRecord.status, func.count(TradeRecord.id)).group_by(TradeRecord.status)
    )
    status_counts = {r[0]: r[1] for r in status_result.all()}

    # --- 已实现盈亏（从已完成的买卖配对计算） ---
    all_filled_records = await db.execute(
        select(TradeRecord)
        .where(TradeRecord.status == "filled")
        .order_by(TradeRecord.created_at)
    )
    all_records = all_filled_records.scalars().all()

    realized_pnl_gross = 0.0
    realized_trades = 0
    win_trades = 0
    total_commission_realized = 0.0
    # 分别跟踪多仓和空仓的持仓均价 + 累计手续费
    _long_pos: dict = {}   # symbol -> {qty, cost_total, comm_total}
    _short_pos: dict = {}  # symbol -> {qty, cost_total, comm_total}

    for r in all_records:
        sym = r.symbol
        comm = float(r.commission or 0)

        # 多仓：BUY 开仓，SELL 平仓
        if r.side == "BUY":
            if sym not in _long_pos:
                _long_pos[sym] = {"qty": 0.0, "cost_total": 0.0, "comm_total": 0.0}
            _long_pos[sym]["qty"] += r.quantity
            _long_pos[sym]["cost_total"] += r.quantity * r.price
            _long_pos[sym]["comm_total"] += comm
        elif r.side == "SELL":
            if sym not in _long_pos:
                _long_pos[sym] = {"qty": 0.0, "cost_total": 0.0, "comm_total": 0.0}
            p = _long_pos[sym]
            if p["qty"] > 0:
                avg_cost = p["cost_total"] / p["qty"]
                sell_qty = min(r.quantity, p["qty"])
                _calc_pnl = sell_qty * (r.price - avg_cost)
                price_pnl = (
                    float(r.realized_pnl_usdt)
                    if r.realized_pnl_usdt is not None and float(r.realized_pnl_usdt or 0) != 0
                    else _calc_pnl
                )
                open_comm_share = p["comm_total"] * (sell_qty / p["qty"]) if p["qty"] > 0 else 0
                trade_comm = open_comm_share + comm
                net_pnl = price_pnl - trade_comm
                realized_pnl_gross += price_pnl
                total_commission_realized += trade_comm
                realized_trades += 1
                if net_pnl > 0:
                    win_trades += 1
                p["cost_total"] -= sell_qty * avg_cost
                p["comm_total"] -= open_comm_share
                p["qty"] -= sell_qty

        # 空仓：SHORT 开仓，COVER 平仓（盈亏方向相反）
        elif r.side == "SHORT":
            if sym not in _short_pos:
                _short_pos[sym] = {"qty": 0.0, "cost_total": 0.0, "comm_total": 0.0}
            _short_pos[sym]["qty"] += r.quantity
            _short_pos[sym]["cost_total"] += r.quantity * r.price
            _short_pos[sym]["comm_total"] += comm
        elif r.side == "COVER":
            if sym not in _short_pos:
                _short_pos[sym] = {"qty": 0.0, "cost_total": 0.0, "comm_total": 0.0}
            p = _short_pos[sym]
            if p["qty"] > 0:
                avg_cost = p["cost_total"] / p["qty"]
                cover_qty = min(r.quantity, p["qty"])
                _calc_pnl = cover_qty * (avg_cost - r.price)
                price_pnl = (
                    float(r.realized_pnl_usdt)
                    if r.realized_pnl_usdt is not None and float(r.realized_pnl_usdt or 0) != 0
                    else _calc_pnl
                )
                open_comm_share = p["comm_total"] * (cover_qty / p["qty"]) if p["qty"] > 0 else 0
                trade_comm = open_comm_share + comm
                net_pnl = price_pnl - trade_comm
                realized_pnl_gross += price_pnl
                total_commission_realized += trade_comm
                realized_trades += 1
                if net_pnl > 0:
                    win_trades += 1
                p["cost_total"] -= cover_qty * avg_cost
                p["comm_total"] -= open_comm_share
                p["qty"] -= cover_qty

    realized_pnl_net = realized_pnl_gross - total_commission_realized
    win_rate = (win_trades / realized_trades * 100) if realized_trades > 0 else 0

    # --- 资金费率（从交易所查询） ---
    funding_fee_total = 0.0
    try:
        if auto_trader._exchange:
            income = await auto_trader._exchange.fapiPrivateGetIncome({
                "incomeType": "FUNDING_FEE",
                "limit": 1000,
            })
            funding_fee_total = sum(float(i.get("income", 0)) for i in income)
    except Exception as e:
        logger.warning(f"[统计] 获取资金费率失败: {e}")

    # --- 最近交易时间 ---
    last_trade_result = await db.execute(
        select(TradeRecord.created_at)
        .where(TradeRecord.status == "filled")
        .order_by(desc(TradeRecord.created_at))
        .limit(1)
    )
    last_trade_at = last_trade_result.scalar_one_or_none()

    # --- 信号准确率 ---
    try:
        accuracy = await get_accuracy_stats(db)
    except Exception as e:
        logger.warning(f"[统计] 获取准确率失败: {e}")
        accuracy = {}

    # --- 账户余额（构建总资产） ---
    balances = await auto_trader.get_balances()
    usdt_free = balances.get("USDT", {}).get("free", 0)
    usdt_total = balances.get("USDT", {}).get("total", 0)

    # P2 #16: 有效交易参数从 DB 读取（改参数不用重启）
    _ep = await _load_effective_params()

    return _ok({
        "today": {
            "trades": today_buy_count + today_sell_count + today_short_count + today_cover_count,
            "buy_count": today_buy_count,
            "sell_count": today_sell_count,
            "short_count": today_short_count,
            "cover_count": today_cover_count,
            "buy_volume": round(today_buy_volume, 2),
            "sell_volume": round(today_sell_volume, 2),
            "short_volume": round(today_short_volume, 2),
            "cover_volume": round(today_cover_volume, 2),
            "commission": round(today_commission, 4),
            "tp_count": today_tp_count,
            "sl_count": today_sl_count,
            "trailing_count": today_trailing_count,
            "sl_blocked": today_sl_blocked,
        },
        "today_status": {
            "filled": int(today_status_counts.get("filled", 0) or 0),
            "skipped": int(today_status_counts.get("skipped", 0) or 0),
            "failed": int(today_status_counts.get("failed", 0) or 0),
            "pending": int(today_status_counts.get("pending", 0) or 0),
        },
        "total": {
            "trades": total_trades,
            "volume": round(total_volume, 2),
            "commission": round(total_commission, 4),
            "filled": status_counts.get("filled", 0),
            "failed": status_counts.get("failed", 0),
            "skipped": status_counts.get("skipped", 0),
        },
        "realized_pnl": {
            "gross_pnl": round(realized_pnl_gross, 2),
            "commission": round(total_commission_realized, 4),
            "funding_fee": round(funding_fee_total, 4),
            "total_pnl": round(realized_pnl_net + funding_fee_total, 2),
            "trade_count": realized_trades,
            "win_count": win_trades,
            "win_rate": round(win_rate, 1),
        },
        "account": {
            "usdt_free": round(usdt_free, 2),
            "usdt_total": round(usdt_total, 2),
            "balances": balances,
        },
        "strategy": {
            "name": "USDT永续合约双向波段交易",
            "amount_usdt": _ep["amount_usdt"],
            "amount_pct": settings.TRADE_AMOUNT_PCT,
            "min_confidence": _ep["min_confidence"],
            "min_conf_buy": getattr(settings, "TRADE_MIN_CONF_BUY", 0) or _ep["min_confidence"],
            "min_conf_short": getattr(settings, "TRADE_MIN_CONF_SHORT", 0) or _ep["min_confidence"],
            "min_conf_sell": getattr(settings, "TRADE_MIN_CONF_SELL", 0) or _ep["min_confidence"],
            "flip_confidence": getattr(settings, "TRADE_FLIP_CONFIDENCE", 85),
            "sell_close_confidence": getattr(settings, "TRADE_SELL_CLOSE_CONFIDENCE", 0) or getattr(settings, "TRADE_FLIP_CONFIDENCE", 85),
            "symbols": _ep["symbols"],
            "cooldown_seconds": _ep["cooldown_seconds"],
            "close_cooldown_seconds": _ep["close_cooldown_seconds"],
            "analysis_interval": "所有币种每 1 分钟",
            "max_position_usdt": settings.TRADE_MAX_POSITION_USDT,
            "max_position_pct": settings.TRADE_MAX_POSITION_PCT,
            "daily_limit_usdt": settings.TRADE_DAILY_LIMIT_USDT,
            "take_profit_pct": _ep["take_profit_pct"],
            "stop_loss_pct": _ep["stop_loss_pct"],
            "leverage": _ep["leverage"],
            "margin_mode": _ep["margin_mode"],
            "trailing_stop_enabled": settings.TRADE_TRAILING_STOP_ENABLED,
            "position_timeout_hours": settings.TRADE_POSITION_TIMEOUT_HOURS,
        },
        "accuracy": {
            "total_signals": accuracy.get("total_signals", 0),
            "direction_accuracy": accuracy.get("direction_accuracy", 0),
            "weighted_accuracy": accuracy.get("weighted_accuracy", 0),
            "correct_count": accuracy.get("correct_count", 0),
            "incorrect_count": accuracy.get("incorrect_count", 0),
            "neutral_count": accuracy.get("neutral_count", 0),
            "by_signal_type": accuracy.get("by_signal_type", {}),
            "by_symbol": accuracy.get("by_symbol", {}),
        },
        "last_trade_at": (last_trade_at.isoformat() + "Z") if last_trade_at else None,
        "sl_protection": _build_sl_protection_info(today_start, db, today_status_counts),
    })


# ── 止损磨损防护状态 ──────────────────────────────
def _build_sl_protection_info(today_start, db, today_status_counts):
    """构建止损防护状态信息"""
    import time as _time
    now = _time.time()
    paused_symbols = []
    for sym, tracker in _symbol_sl_tracker.items():
        pause_until = float(tracker.get("pause_until", 0) or 0)
        count = tracker.get("count", 0)
        if count > 0 or now < pause_until:
            paused_symbols.append({
                "symbol": sym,
                "sl_count": count,
                "paused": now < pause_until,
                "remaining_seconds": max(0, int(pause_until - now)) if now < pause_until else 0,
            })
    return {
        "config": {
            "sl_cooldown_multiplier": float(getattr(settings, "TRADE_SL_COOLDOWN_MULTIPLIER", 2.0) or 2.0),
            "max_consecutive_sl": int(getattr(settings, "TRADE_MAX_CONSECUTIVE_SL", 3) or 3),
            "sl_pause_minutes": int(getattr(settings, "TRADE_SL_PAUSE_MINUTES", 30) or 30),
        },
        "symbols": paused_symbols,
    }


@router.get("/sl-protection")
async def get_sl_protection(user=Depends(get_current_user)):
    """获取止损防护配置及当前状态"""
    import time as _time
    now = _time.time()
    paused_symbols = []
    for sym, tracker in _symbol_sl_tracker.items():
        pause_until = float(tracker.get("pause_until", 0) or 0)
        count = tracker.get("count", 0)
        if count > 0 or now < pause_until:
            paused_symbols.append({
                "symbol": sym,
                "sl_count": count,
                "paused": now < pause_until,
                "remaining_seconds": max(0, int(pause_until - now)) if now < pause_until else 0,
            })
    return _ok({
        "config": {
            "sl_cooldown_multiplier": float(getattr(settings, "TRADE_SL_COOLDOWN_MULTIPLIER", 2.0) or 2.0),
            "max_consecutive_sl": int(getattr(settings, "TRADE_MAX_CONSECUTIVE_SL", 3) or 3),
            "sl_pause_minutes": int(getattr(settings, "TRADE_SL_PAUSE_MINUTES", 30) or 30),
        },
        "symbols": paused_symbols,
    })


@router.put("/sl-protection")
async def update_sl_protection(req: dict, user=Depends(get_current_user)):
    """更新止损防护配置（运行时生效）"""
    updated = []
    if "sl_cooldown_multiplier" in req:
        v = max(1.0, min(float(req["sl_cooldown_multiplier"]), 5.0))
        settings.TRADE_SL_COOLDOWN_MULTIPLIER = v
        updated.append(f"sl_cooldown_multiplier={v}")
    if "max_consecutive_sl" in req:
        v = max(1, min(int(req["max_consecutive_sl"]), 10))
        settings.TRADE_MAX_CONSECUTIVE_SL = v
        updated.append(f"max_consecutive_sl={v}")
    if "sl_pause_minutes" in req:
        v = max(5, min(int(req["sl_pause_minutes"]), 120))
        settings.TRADE_SL_PAUSE_MINUTES = v
        updated.append(f"sl_pause_minutes={v}")
    logger.info(f"[止损防护] 配置已更新: {', '.join(updated)}")
    return _ok({"updated": updated})


# ================================================================
# 引擎状态 / 动态止盈止损 / 币种准确率
# ================================================================

@router.get("/engine-status")
async def get_engine_status(user=Depends(get_current_user)):
    """交易引擎各币种实时状态（冷却/暂停/ATR）"""
    import time as _t
    now = _t.time()
    _ep = await _load_effective_params()
    statuses = []
    for sym in (_ep["symbols"] or "").split(","):
        sym = sym.strip().upper()
        if not sym:
            continue
        buy_cd = float(_cooldown_map.get(f"{sym}_BUY", 0) or 0)
        short_cd = float(_cooldown_map.get(f"{sym}_SHORT", 0) or 0)

        open_cooldown = _ep["cooldown_seconds"]
        buy_remaining = max(0, int(open_cooldown - (now - buy_cd))) if buy_cd > 0 else 0
        short_remaining = max(0, int(open_cooldown - (now - short_cd))) if short_cd > 0 else 0
        cd_remaining = max(buy_remaining, short_remaining)

        tracker = _symbol_sl_tracker.get(sym, {})
        pause_until = float(tracker.get("pause_until", 0) or 0)
        sl_count = tracker.get("count", 0)
        pause_remaining = max(0, int(pause_until - now))

        atr_info = _symbol_atr.get(sym, {})
        atr_pct = round(atr_info.get("atr_pct", 0), 2)

        if pause_remaining > 0:
            status = "paused"
        elif cd_remaining > 0:
            status = "cooldown"
        else:
            status = "ready"

        statuses.append({
            "symbol": sym,
            "status": status,
            "cooldown_remaining": cd_remaining,
            "pause_remaining": pause_remaining,
            "sl_streak": sl_count,
            "atr_pct": atr_pct,
        })

    return _ok({"symbols": statuses})


@router.get("/accuracy-grades")
async def get_accuracy_grades(user=Depends(get_current_user)):
    """各币种 AI 信号准确率分级（A/B/C/D）"""
    _ep = await _load_effective_params()
    grades = []
    for sym in (_ep["symbols"] or "").split(","):
        sym = sym.strip().upper()
        if not sym:
            continue
        cache = _symbol_accuracy_cache.get(sym, {})
        acc = cache.get("accuracy", 0)
        if acc >= 65:
            grade = "A"
        elif acc >= 50:
            grade = "B"
        elif acc >= 35:
            grade = "C"
        else:
            grade = "D"
        grades.append({
            "symbol": sym,
            "accuracy": round(acc, 1),
            "grade": grade,
        })
    return _ok({"grades": grades})
