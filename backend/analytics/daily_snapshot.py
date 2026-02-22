"""
Phase A: DailyPnL 日净值快照采集

增强版：精确的盈亏/胜率/回撤计算
- total_equity: 从交易所余额读取（若未启用交易则为 0）
- realized_pnl: 当日 filled 交易 FIFO 配对计算
- unrealized_pnl: 从持仓的 unrealizedPnl 累加
- win_trades / loss_trades: 配对交易的胜率统计
- max_drawdown_pct: 历史 equity 峰值到谷值的最大回撤
- api_cost: 从 quota_manager 快照读取 estimated_cost
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.models import DailyPnL
from backend.trading.executor import auto_trader
from backend.trading.models import TradeRecord
from backend.utils.quota import quota_manager

logger = logging.getLogger(__name__)


def _utc_date_str(now: datetime | None = None) -> str:
    if now is None:
        now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%d")


def _today_start() -> datetime:
    """返回今日 UTC 零点"""
    return datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


# ─────────────────────────────────────────────
# 辅助：FIFO 配对计算已实现盈亏
# ─────────────────────────────────────────────

def _calc_realized_pnl_fifo(
    trades: list[TradeRecord],
) -> tuple[float, int, int]:
    """
    按 symbol 分组，将 BUY 与 SELL 记录做 FIFO 配对。

    每对 PnL = (sell_price - buy_price) × matched_qty − 按比例分摊的手续费。
    此公式对多头平仓（先 BUY 后 SELL）和空头平仓（先 SELL 后 BUY）均成立。

    Returns:
        (total_realized_pnl, win_count, loss_count)
    """
    by_symbol: dict[str, dict[str, list]] = defaultdict(
        lambda: {"BUY": [], "SELL": []}
    )
    for t in trades:
        side = (t.side or "").upper()
        if side in ("BUY", "SELL"):
            by_symbol[t.symbol][side].append({
                "price": float(t.price or 0),
                "qty": float(t.quantity or 0),
                "commission": float(t.commission or 0),
            })

    total_pnl = 0.0
    win_count = 0
    loss_count = 0

    for _symbol, sides in by_symbol.items():
        buys = list(sides["BUY"])
        sells = list(sides["SELL"])
        if not buys or not sells:
            continue

        bi, si = 0, 0
        buy_remaining = buys[0]["qty"]
        sell_remaining = sells[0]["qty"]

        while bi < len(buys) and si < len(sells):
            matched_qty = min(buy_remaining, sell_remaining)
            if matched_qty <= 1e-12:
                break

            buy_entry = buys[bi]
            sell_entry = sells[si]

            # PnL = (卖价 − 买价) × 配对数量
            pair_pnl = (sell_entry["price"] - buy_entry["price"]) * matched_qty

            # 手续费按配对数量占原始数量的比例分摊
            if buy_entry["qty"] > 0:
                pair_pnl -= buy_entry["commission"] * (matched_qty / buy_entry["qty"])
            if sell_entry["qty"] > 0:
                pair_pnl -= sell_entry["commission"] * (matched_qty / sell_entry["qty"])

            total_pnl += pair_pnl
            if pair_pnl > 0:
                win_count += 1
            elif pair_pnl < 0:
                loss_count += 1

            # 扣减已配对数量，推进指针
            buy_remaining -= matched_qty
            sell_remaining -= matched_qty

            if buy_remaining <= 1e-12:
                bi += 1
                buy_remaining = buys[bi]["qty"] if bi < len(buys) else 0.0

            if sell_remaining <= 1e-12:
                si += 1
                sell_remaining = sells[si]["qty"] if si < len(sells) else 0.0

    return total_pnl, win_count, loss_count


# ─────────────────────────────────────────────
# 辅助：最大回撤
# ─────────────────────────────────────────────

async def _calc_max_drawdown(db: AsyncSession) -> float:
    """
    从 daily_pnl 历史记录计算峰值到谷值的最大回撤百分比（0~100）。
    """
    result = await db.execute(
        select(DailyPnL.total_equity)
        .where(DailyPnL.total_equity > 0)
        .order_by(DailyPnL.date)
    )
    equities = [float(row[0]) for row in result.fetchall()]

    if len(equities) < 2:
        return 0.0

    peak = equities[0]
    max_dd = 0.0

    for eq in equities:
        if eq > peak:
            peak = eq
        if peak > 0:
            dd = (peak - eq) / peak * 100.0
            if dd > max_dd:
                max_dd = dd

    return max_dd


# ─────────────────────────────────────────────
# 辅助：未实现盈亏
# ─────────────────────────────────────────────

async def _calc_unrealized_pnl() -> float:
    """
    从 auto_trader 持仓获取未实现盈亏总和。
    auto_trader 未启用或获取失败时返回 0。
    """
    try:
        if not auto_trader.is_active or not auto_trader._exchange:  # noqa: SLF001
            return 0.0
        positions = await auto_trader._fetch_all_positions()  # noqa: SLF001
        return sum(float(p.get("unrealizedPnl", 0)) for p in positions)
    except Exception as e:
        logger.warning("[快照] 获取未实现盈亏失败: %s", e)
        return 0.0


# ─────────────────────────────────────────────
# 主函数
# ─────────────────────────────────────────────

async def take_daily_snapshot(db: AsyncSession) -> DailyPnL:
    date_key = _utc_date_str()
    today_start = _today_start()

    total_equity = 0.0

    # ── 1. 交易所权益 ──
    try:
        if auto_trader.is_active and auto_trader._exchange:  # noqa: SLF001
            bal = await auto_trader._exchange.fetch_balance()  # noqa: SLF001
            total_equity = float(bal.get("USDT", {}).get("total", 0) or 0)
    except Exception as e:
        logger.warning("[快照] 获取交易所权益失败: %s", e)
        total_equity = 0.0

    # ── 2. 当日 filled 交易 → 已实现盈亏 + 胜率 ──
    total_trades = 0
    win_trades = 0
    loss_trades = 0
    realized_pnl = 0.0
    try:
        q = await db.execute(
            select(TradeRecord).where(
                TradeRecord.status == "filled",
                TradeRecord.created_at >= today_start,
            ).order_by(TradeRecord.created_at)
        )
        filled_trades = list(q.scalars().all())
        total_trades = len(filled_trades)

        if filled_trades:
            realized_pnl, win_trades, loss_trades = _calc_realized_pnl_fifo(
                filled_trades
            )
    except Exception as e:
        logger.warning("[快照] 计算已实现盈亏失败: %s", e)
        total_trades = 0
        realized_pnl = 0.0

    # ── 3. 未实现盈亏 ──
    unrealized_pnl = await _calc_unrealized_pnl()

    # ── 4. 最大回撤 ──
    max_drawdown_pct = await _calc_max_drawdown(db)

    # ── 5. API 成本 ──
    api_cost = float(quota_manager.get_snapshot(date_key).estimated_cost or 0.0)

    # ── 6. upsert by date ──
    existing = await db.execute(select(DailyPnL).where(DailyPnL.date == date_key))
    row = existing.scalar_one_or_none()
    if row is None:
        row = DailyPnL(date=date_key)
        db.add(row)

    row.total_equity = float(total_equity)
    row.realized_pnl = float(realized_pnl)
    row.unrealized_pnl = float(unrealized_pnl)
    row.total_trades = int(total_trades)
    row.win_trades = int(win_trades)
    row.loss_trades = int(loss_trades)
    row.max_drawdown_pct = float(max_drawdown_pct)
    row.api_cost = float(api_cost)
    row.net_pnl = float(realized_pnl - api_cost)
    row.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(row)
    return row
