"""Shared constants and module-level utility functions for the trading package."""

import time
import logging
from datetime import datetime, timezone, timedelta

from backend.core.execution.state_manager import StateManager
from backend.database.db import async_session

logger = logging.getLogger(__name__)

# Singleton state aliases (same dict objects as executor.py)
_state = StateManager()
_symbol_atr = _state.symbol_atr
_symbol_accuracy_cache = _state.accuracy_cache

# 平仓冷却时间（秒）：30 秒，平仓需要最快响应（SELL/COVER 共用）
_CLOSE_COOLDOWN_SECONDS = 30

# 准确率缓存 TTL
_ACCURACY_CACHE_TTL = 1800  # 30 分钟刷新


def _clamp_conf(v: int) -> int:
    try:
        n = int(v)
    except Exception:
        n = 0
    return max(0, min(100, n))


def _parse_symbols_csv(raw: str) -> set[str]:
    return {s.strip().upper() for s in str(raw or "").split(",") if s.strip()}


def _update_atr_cache(symbol: str, atr_pct: float):
    """从 AI 信号中更新 ATR 缓存"""
    if atr_pct > 0:
        _symbol_atr[symbol] = {"atr_pct": atr_pct, "time": time.time()}


async def _get_symbol_accuracy(symbol: str) -> float:
    """查询币种近 7 天方向准确率（带缓存）"""
    cached = _symbol_accuracy_cache.get(symbol)
    if cached and (time.time() - cached["time"]) < _ACCURACY_CACHE_TTL:
        return cached["accuracy"]
    try:
        from backend.database.models import AISignal, SignalResult
        from sqlalchemy import select
        async with async_session() as db:
            seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
            stmt = (
                select(SignalResult.direction_result)
                .join(AISignal, SignalResult.signal_id == AISignal.id)
                .where(
                    AISignal.symbol == symbol,
                    AISignal.signal.notin_(["HOLD"]),
                    SignalResult.direction_result.in_(["CORRECT", "INCORRECT"]),
                    AISignal.created_at >= seven_days_ago,
                )
            )
            result = await db.execute(stmt)
            rows = result.all()
            if not rows:
                _symbol_accuracy_cache[symbol] = {"accuracy": 50.0, "time": time.time()}
                return 50.0
            correct = sum(1 for r in rows if r.direction_result == "CORRECT")
            acc = correct / len(rows) * 100
            _symbol_accuracy_cache[symbol] = {"accuracy": acc, "time": time.time()}
            return acc
    except Exception as e:
        logger.warning(f"[币种分级] 查询 {symbol} 准确率失败: {e}")
        return 50.0
