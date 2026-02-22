"""
Phase A: 归因/度量 API
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, desc, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.jwt_utils import get_current_user
from backend.database.db import get_db
from backend.database.models import DailyPnL, AISignal
from backend.analytics.signal_attribution import build_attribution
from backend.analytics.benchmark import build_benchmark


router = APIRouter(prefix="/api/analytics", tags=["Analytics"])


def _ok(payload: dict[str, Any]) -> dict[str, Any]:
    return {"success": True, "data": payload, **payload}


@router.get("/daily-pnl")
async def get_daily_pnl(
    days: int = Query(default=30, ge=1, le=365),
    username: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    # date 是字符串，简单过滤：全部取最近 N 条更安全
    result = await db.execute(select(DailyPnL).order_by(desc(DailyPnL.date)).limit(days))
    rows = list(reversed(result.scalars().all()))
    return _ok(
        {
            "rows": [
                {
                    "date": r.date,
                    "total_equity": r.total_equity,
                    "realized_pnl": r.realized_pnl,
                    "unrealized_pnl": r.unrealized_pnl,
                    "total_trades": r.total_trades,
                    "win_trades": r.win_trades,
                    "loss_trades": r.loss_trades,
                    "max_drawdown_pct": r.max_drawdown_pct,
                    "api_cost": r.api_cost,
                    "net_pnl": r.net_pnl,
                }
                for r in rows
                if r
            ],
            "cutoff": cutoff.isoformat(),
        }
    )


@router.get("/prefilter")
async def get_prefilter_stats(
    days: int = Query(default=14, ge=1, le=180),
    username: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    q = await db.execute(
        select(
            func.count().label("total"),
            func.sum(case((AISignal.pf_agreed_with_ai.is_(True), 1), else_=0)).label("agreed"),
            func.sum(case((AISignal.pf_level == "STRONG", 1), else_=0)).label("strong_cnt"),
        ).where(AISignal.created_at >= cutoff)
    )
    row = q.one()
    total = int(row.total or 0)
    agreed = int(row.agreed or 0)
    strong_cnt = int(row.strong_cnt or 0)
    return _ok(
        {
            "total_signals": total,
            "pf_agreed_count": agreed,
            "pf_agreed_rate": round(agreed / total * 100, 2) if total else 0.0,
            "pf_strong_count": strong_cnt,
        }
    )


@router.get("/latest-dualtrack")
async def latest_dualtrack(
    symbol: str = Query(default="BTCUSDT"),
    username: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AISignal)
        .where(AISignal.symbol == symbol.upper())
        .order_by(desc(AISignal.created_at))
        .limit(1)
    )
    s = result.scalar_one_or_none()
    if not s:
        return _ok({"signal": None})
    return _ok(
        {
            "signal": {
                "id": s.id,
                "symbol": s.symbol,
                "signal": s.signal,
                "confidence": s.confidence,
                "created_at": s.created_at.isoformat() + "Z" if s.created_at else "",
                "pf_direction": getattr(s, "pf_direction", None),
                "pf_score": getattr(s, "pf_score", None),
                "pf_level": getattr(s, "pf_level", None),
                "pf_reasons": getattr(s, "pf_reasons", None),
                "pf_agreed_with_ai": getattr(s, "pf_agreed_with_ai", None),
                "role_opinions": json.loads(s.role_opinions) if s.role_opinions else [],
            }
        }
    )


@router.get("/attribution")
async def attribution(
    days: int = Query(default=14, ge=1, le=180),
    limit: int = Query(default=3000, ge=100, le=20000),
    username: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """信号归因分析（角色/币种/置信度分桶 + pre-filter 对比）"""
    data = await build_attribution(db, days=days, limit=limit)
    return _ok(data)


@router.get("/benchmark")
async def benchmark(
    days: int = Query(default=30, ge=1, le=365),
    username: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """策略 vs BTC 基准对比"""
    data = await build_benchmark(db, days=days)
    return _ok(data)

