"""
Phase B: 价格波动触发器

在 1 分钟定时之外，当价格在短窗口内异常波动时额外触发分析。
测试阶段目标：更快收集“极端行情”样本。
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass
from typing import Awaitable, Callable


AnalyzeCallback = Callable[[str, str], Awaitable[None]]


@dataclass
class TriggerConfig:
    one_min_pct: float = 1.0
    five_min_pct: float = 2.0
    cooldown_seconds: int = 60


class PriceTrigger:
    def __init__(self, analyze_cb: AnalyzeCallback, cfg: TriggerConfig | None = None):
        self._cb = analyze_cb
        self._cfg = cfg or TriggerConfig()
        self._hist: dict[str, deque[tuple[float, float]]] = {}
        self._last_fire: dict[str, float] = {}
        self._in_flight: set[str] = set()
        self._lock = asyncio.Lock()

    async def on_price(self, symbol: str, price: float) -> None:
        if not symbol or price <= 0:
            return
        now = time.time()

        async with self._lock:
            last = self._last_fire.get(symbol, 0)
            if now - last < self._cfg.cooldown_seconds:
                return
            if symbol in self._in_flight:
                return

            hist = self._hist.get(symbol)
            if hist is None:
                hist = deque(maxlen=600)  # store ~10 minutes at 1Hz-ish worst case
                self._hist[symbol] = hist
            hist.append((now, price))

            # find reference prices
            p_1m = None
            p_5m = None
            for ts, p in reversed(hist):
                if p_1m is None and now - ts >= 60:
                    p_1m = p
                if p_5m is None and now - ts >= 300:
                    p_5m = p
                if p_1m is not None and p_5m is not None:
                    break

            reason = None
            if p_1m and abs((price - p_1m) / p_1m * 100.0) >= self._cfg.one_min_pct:
                reason = f"price_move_1m>={self._cfg.one_min_pct}%"
            elif p_5m and abs((price - p_5m) / p_5m * 100.0) >= self._cfg.five_min_pct:
                reason = f"price_move_5m>={self._cfg.five_min_pct}%"

            if not reason:
                return

            self._last_fire[symbol] = now
            self._in_flight.add(symbol)

        try:
            await self._cb(symbol, reason)
        finally:
            async with self._lock:
                self._in_flight.discard(symbol)

