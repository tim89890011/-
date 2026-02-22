"""
Phase A: 策略 vs 基准（BTC）对比（最小可用版）

策略侧：
- 使用 daily_pnl.net_pnl 的累计作为策略净收益（USDT）

基准侧：
- 使用 Binance spot 的 BTCUSDT 日K close 计算累计收益率（%）
"""

from __future__ import annotations

import logging
from datetime import timezone
from typing import Any

logger = logging.getLogger(__name__)

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.models import DailyPnL
from backend.market.data_collector import fetch_klines


async def build_benchmark(db: AsyncSession, days: int = 30) -> dict[str, Any]:
    days = max(1, min(int(days), 365))

    # strategy curve (USDT)
    rows = (
        await db.execute(select(DailyPnL).order_by(desc(DailyPnL.date)).limit(days))
    ).scalars().all()
    rows = list(reversed(rows))

    strat_dates: list[str] = []
    strat_cum_usdt: list[float] = []
    cum = 0.0
    for r in rows:
        strat_dates.append(r.date)
        cum += float(r.net_pnl or 0.0)
        strat_cum_usdt.append(round(cum, 4))

    # btc benchmark (%)
    btc_dates: list[str] = []
    btc_cum_pct: list[float] = []
    try:
        df = await fetch_klines("BTCUSDT", interval="1d", limit=days + 2)
        if not df.empty:
            # align by date string
            closes = df["close"].tolist()
            times = df["close_time"].tolist()
            base = float(closes[0]) if closes else 0.0
            if base > 0:
                for t, c in zip(times, closes):
                    d = t.to_pydatetime().astimezone(timezone.utc).strftime("%Y-%m-%d")
                    btc_dates.append(d)
                    btc_cum_pct.append(round((float(c) - base) / base * 100.0, 4))
    except Exception as e:
        logger.warning("[Benchmark] BTC 基准数据获取失败: %s", e)

    return {
        "days": days,
        "strategy": {"dates": strat_dates, "cum_net_pnl_usdt": strat_cum_usdt},
        "btc": {"dates": btc_dates, "cum_return_pct": btc_cum_pct},
        "note": "策略为净盈亏累计(USDT)，基准为BTCUSDT累计涨跌幅(%)",
    }

