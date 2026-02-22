"""
Phase A: 信号归因分析（最小可用版）

说明：
- SignalResult.direction_result 是“最终 AI 信号”的方向一致性结果
- 本模块额外用 SignalResult.pnl_percent 推导“角色/预筛”的正确性（同一套判定规则）
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from backend.ai_engine.signal_history import get_volatility_threshold
from backend.database.models import AISignal, SignalResult
from backend.trading.models import TradeRecord


def _infer_result(signal_type: str, symbol: str, pnl_percent: float) -> str:
    """复用 signal_history 的一致性口径，但只依赖 pnl_percent。"""
    st = (signal_type or "").upper()
    if st in ("BUY", "COVER"):
        return "CORRECT" if pnl_percent > 0 else "INCORRECT"
    if st in ("SELL", "SHORT"):
        return "CORRECT" if pnl_percent < 0 else "INCORRECT"
    if st == "HOLD":
        thr = get_volatility_threshold(symbol)
        return "NEUTRAL" if abs(pnl_percent) < thr else "INCORRECT"
    return "INCORRECT"


def _acc_bucket(conf: float) -> str:
    c = int(conf or 0)
    if c >= 90:
        return "90-100"
    if c >= 80:
        return "80-89"
    if c >= 70:
        return "70-79"
    if c >= 60:
        return "60-69"
    return "0-59"


async def build_attribution(db: AsyncSession, days: int = 14, limit: int = 3000) -> dict[str, Any]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    stmt = (
        select(AISignal, SignalResult)
        .join(SignalResult, SignalResult.signal_id == AISignal.id)
        .where(AISignal.created_at >= cutoff)
        .order_by(desc(AISignal.created_at))
        .limit(limit)
    )
    rows = (await db.execute(stmt)).all()

    # totals
    total = 0
    ai_correct = ai_incorrect = ai_neutral = 0

    # by_role[name] -> counters
    by_role = defaultdict(lambda: {"total": 0, "correct": 0, "incorrect": 0, "neutral": 0})
    by_symbol = defaultdict(lambda: {"total": 0, "correct": 0, "incorrect": 0, "neutral": 0})
    by_conf = defaultdict(lambda: {"total": 0, "correct": 0, "incorrect": 0, "neutral": 0})

    # pre-filter buckets
    pf_strong = {"total": 0, "correct": 0, "incorrect": 0, "neutral": 0}
    pf_all = {"total": 0, "correct": 0, "incorrect": 0, "neutral": 0}

    for sig, sr in rows:
        if sr is None or sr.pnl_percent is None:
            continue
        pnl = float(sr.pnl_percent or 0)
        total += 1

        # final AI result
        ai_res = (sr.direction_result or "").upper()
        if ai_res == "CORRECT":
            ai_correct += 1
        elif ai_res == "NEUTRAL":
            ai_neutral += 1
        else:
            ai_incorrect += 1

        sym = sig.symbol or ""
        by_symbol[sym]["total"] += 1
        if ai_res == "CORRECT":
            by_symbol[sym]["correct"] += 1
        elif ai_res == "NEUTRAL":
            by_symbol[sym]["neutral"] += 1
        else:
            by_symbol[sym]["incorrect"] += 1

        b = _acc_bucket(float(sig.confidence or 0))
        by_conf[b]["total"] += 1
        if ai_res == "CORRECT":
            by_conf[b]["correct"] += 1
        elif ai_res == "NEUTRAL":
            by_conf[b]["neutral"] += 1
        else:
            by_conf[b]["incorrect"] += 1

        # pre-filter correctness (using same pnl sign rules)
        if getattr(sig, "pf_direction", None):
            pf_dir = str(sig.pf_direction or "")
            pf_res = _infer_result(pf_dir, sym, pnl)
            pf_all["total"] += 1
            pf_all[pf_res.lower()] += 1 if pf_res.lower() in pf_all else 0
            if str(getattr(sig, "pf_level", "") or "").upper() == "STRONG":
                pf_strong["total"] += 1
                pf_strong[pf_res.lower()] += 1 if pf_res.lower() in pf_strong else 0

        # role attribution (best-effort parsing)
        try:
            opinions = json.loads(sig.role_opinions or "[]")
            if not isinstance(opinions, list):
                opinions = []
        except Exception as e:
            logger.debug("[归因] role_opinions JSON 解析失败: %s", e)
            opinions = []

        for op in opinions:
            name = str(op.get("name") or op.get("role_id") or "unknown")
            rs = _infer_result(str(op.get("signal", "")), sym, pnl)
            by_role[name]["total"] += 1
            if rs == "CORRECT":
                by_role[name]["correct"] += 1
            elif rs == "NEUTRAL":
                by_role[name]["neutral"] += 1
            else:
                by_role[name]["incorrect"] += 1

    def _rate(x: dict) -> float:
        decided = (x["correct"] + x["incorrect"]) or 0
        return round((x["correct"] / decided * 100) if decided else 0.0, 2)

    role_rank = sorted(
        (
            {
                "role": k,
                **v,
                "accuracy": _rate(v),
            }
            for k, v in by_role.items()
        ),
        key=lambda r: (r["accuracy"], r["total"]),
        reverse=True,
    )
    symbol_rank = sorted(
        (
            {
                "symbol": k,
                **v,
                "accuracy": _rate(v),
            }
            for k, v in by_symbol.items()
        ),
        key=lambda r: (r["accuracy"], r["total"]),
        reverse=True,
    )
    conf_buckets = [
        {"bucket": k, **v, "accuracy": _rate(v)}
        for k, v in sorted(by_conf.items(), key=lambda kv: kv[0])
    ]

    ai_overall = {
        "total": total,
        "correct": ai_correct,
        "incorrect": ai_incorrect,
        "neutral": ai_neutral,
        "accuracy": round((ai_correct / (ai_correct + ai_incorrect) * 100) if (ai_correct + ai_incorrect) else 0.0, 2),
    }

    def _fix_pf(d: dict) -> dict:
        # our dict uses keys correct/incorrect/neutral; infer_result lower mapping
        return {
            "total": int(d.get("total", 0) or 0),
            "correct": int(d.get("correct", 0) or 0),
            "incorrect": int(d.get("incorrect", 0) or 0),
            "neutral": int(d.get("neutral", 0) or 0),
            "accuracy": round((d.get("correct", 0) / (d.get("correct", 0) + d.get("incorrect", 0)) * 100) if (d.get("correct", 0) + d.get("incorrect", 0)) else 0.0, 2),
        }

    # v1.1: 按 horizon 分桶
    by_horizon = defaultdict(lambda: {"total": 0, "correct": 0, "incorrect": 0, "neutral": 0, "pnl_sum": 0.0})
    # v1.1: 角色 × 币种交叉下钻
    role_symbol_cross = defaultdict(lambda: {"total": 0, "correct": 0, "incorrect": 0})

    for sig, sr in rows:
        if sr is None or sr.pnl_percent is None:
            continue
        pnl = float(sr.pnl_percent or 0)
        sym = sig.symbol or ""
        ai_res = (sr.direction_result or "").upper()

        hz = getattr(sig, "horizon", None) or "1h"
        by_horizon[hz]["total"] += 1
        by_horizon[hz]["pnl_sum"] += pnl
        if ai_res == "CORRECT":
            by_horizon[hz]["correct"] += 1
        elif ai_res == "NEUTRAL":
            by_horizon[hz]["neutral"] += 1
        else:
            by_horizon[hz]["incorrect"] += 1

        try:
            opinions = json.loads(sig.role_opinions or "[]")
            if not isinstance(opinions, list):
                opinions = []
        except Exception as e:
            logger.debug("[归因] role_opinions JSON 解析失败: %s", e)
            opinions = []
        for op in opinions:
            rname = str(op.get("name") or op.get("role_id") or "unknown")
            rs = _infer_result(str(op.get("signal", "")), sym, pnl)
            cross_key = f"{rname}|{sym}"
            role_symbol_cross[cross_key]["total"] += 1
            if rs == "CORRECT":
                role_symbol_cross[cross_key]["correct"] += 1
            else:
                role_symbol_cross[cross_key]["incorrect"] += 1

    horizon_stats = []
    for hz, d in sorted(by_horizon.items()):
        decided = d["correct"] + d["incorrect"]
        acc = round((d["correct"] / decided * 100) if decided else 0.0, 2)
        avg_pnl = round(d["pnl_sum"] / d["total"], 4) if d["total"] else 0
        ev = round(acc / 100 * avg_pnl, 4) if avg_pnl != 0 else 0
        horizon_stats.append({"horizon": hz, **d, "accuracy": acc, "avg_pnl_pct": avg_pnl, "ev": ev})

    cross_top = sorted(
        [
            {"key": k, **v, "accuracy": round((v["correct"] / (v["correct"] + v["incorrect"]) * 100) if (v["correct"] + v["incorrect"]) else 0, 2)}
            for k, v in role_symbol_cross.items() if v["total"] >= 3
        ],
        key=lambda x: x["accuracy"],
        reverse=True,
    )

    # v1.1: 关联 trade_records 计算实际交易 PnL
    trade_pnl_stats = {"total_trades": 0, "total_pnl_usdt": 0.0, "avg_pnl_usdt": 0.0}
    try:
        trade_stmt = (
            select(TradeRecord)
            .where(TradeRecord.created_at >= cutoff)
            .where(TradeRecord.status == "filled")
        )
        trade_rows = (await db.execute(trade_stmt)).scalars().all()
        if trade_rows:
            total_pnl = sum(float(getattr(t, "quote_amount", 0) or 0) for t in trade_rows)
            trade_pnl_stats["total_trades"] = len(trade_rows)
            trade_pnl_stats["total_pnl_usdt"] = round(total_pnl, 2)
            trade_pnl_stats["avg_pnl_usdt"] = round(total_pnl / len(trade_rows), 2) if trade_rows else 0
    except Exception as e:
        logger.warning("[SignalAttribution] 交易PnL统计失败: %s", e)

    return {
        "window_days": days,
        "sample_limit": limit,
        "ai_overall": ai_overall,
        "roles": role_rank[:20],
        "symbols": symbol_rank[:20],
        "confidence_buckets": conf_buckets,
        "prefilter_all": _fix_pf(pf_all),
        "prefilter_strong": _fix_pf(pf_strong),
        # v1.1 增补
        "horizon_stats": horizon_stats,
        "role_symbol_cross_top": cross_top[:30],
        "trade_pnl_stats": trade_pnl_stats,
    }

