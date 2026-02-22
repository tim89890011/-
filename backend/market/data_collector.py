"""
钢子出击 - 行情数据采集器
从 Binance REST API 获取 K 线、资金费率、持仓量、多空比等
"""
import asyncio
import logging
from typing import Optional
import httpx
import pandas as pd

logger = logging.getLogger(__name__)

# Binance API 基础地址
SPOT_BASE = "https://api.binance.com"
FUTURES_BASE = "https://fapi.binance.com"

# 共享 HTTP 客户端
_client: Optional[httpx.AsyncClient] = None
_client_lock = asyncio.Lock()


async def _get_client() -> httpx.AsyncClient:
    """获取或创建 HTTP 客户端（并发安全）"""
    global _client
    if _client is not None and not _client.is_closed:
        return _client
    async with _client_lock:
        if _client is None or _client.is_closed:
            _client = httpx.AsyncClient(timeout=15.0)
    return _client


async def fetch_klines(
    symbol: str,
    interval: str = "1h",
    limit: int = 100,
) -> pd.DataFrame:
    """
    获取 K 线数据
    返回 DataFrame，包含 open/high/low/close/volume 列
    """
    client = await _get_client()
    try:
        resp = await client.get(
            f"{SPOT_BASE}/api/v3/klines",
            params={"symbol": symbol, "interval": interval, "limit": limit},
        )
        resp.raise_for_status()
        data = resp.json()

        df = pd.DataFrame(data, columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades", "taker_buy_base",
            "taker_buy_quote", "ignore",
        ])

        # 转换数据类型
        for col in ["open", "high", "low", "close", "volume", "quote_volume"]:
            df[col] = df[col].astype(float)
        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
        df["close_time"] = pd.to_datetime(df["close_time"], unit="ms")

        return df

    except Exception as e:
        logger.error(f"[数据采集] 获取 K 线失败 ({symbol}): {e}")
        return pd.DataFrame()


async def fetch_funding_rate(symbol: str) -> float:
    """获取当前资金费率（优先从 @markPrice WS 缓存读取，回退 REST）"""
    from backend.market.binance_ws import get_funding_rate as ws_funding
    rate = ws_funding(symbol)
    if rate != 0.0:
        return rate
    client = await _get_client()
    try:
        resp = await client.get(
            f"{FUTURES_BASE}/fapi/v1/fundingRate",
            params={"symbol": symbol, "limit": 1},
        )
        resp.raise_for_status()
        data = resp.json()
        if data:
            return float(data[0].get("fundingRate", 0))
        return 0.0
    except Exception as e:
        logger.error(f"[数据采集] 获取资金费率失败 ({symbol}): {e}")
        return 0.0


async def fetch_open_interest(symbol: str) -> dict:
    """获取持仓量"""
    client = await _get_client()
    try:
        resp = await client.get(
            f"{FUTURES_BASE}/fapi/v1/openInterest",
            params={"symbol": symbol},
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "open_interest": float(data.get("openInterest", 0)),
            "symbol": data.get("symbol", symbol),
        }
    except Exception as e:
        logger.error(f"[数据采集] 获取持仓量失败 ({symbol}): {e}")
        return {"open_interest": 0, "symbol": symbol}


async def fetch_long_short_ratio(symbol: str) -> dict:
    """获取多空比（全局账户）"""
    client = await _get_client()
    try:
        resp = await client.get(
            f"{FUTURES_BASE}/futures/data/globalLongShortAccountRatio",
            params={"symbol": symbol, "period": "1h", "limit": 1},
        )
        resp.raise_for_status()
        data = resp.json()
        if data:
            return {
                "long_ratio": float(data[0].get("longAccount", 0)),
                "short_ratio": float(data[0].get("shortAccount", 0)),
                "long_short_ratio": float(data[0].get("longShortRatio", 0)),
            }
        return {"long_ratio": 0, "short_ratio": 0, "long_short_ratio": 0}
    except Exception as e:
        logger.error(f"[数据采集] 获取多空比失败 ({symbol}): {e}")
        return {"long_ratio": 0, "short_ratio": 0, "long_short_ratio": 0}


async def fetch_recent_large_trades(symbol: str, min_qty: float = 0) -> list:
    """获取最近的大额交易"""
    client = await _get_client()
    try:
        resp = await client.get(
            f"{SPOT_BASE}/api/v3/trades",
            params={"symbol": symbol, "limit": 100},
        )
        resp.raise_for_status()
        trades = resp.json()

        # 按成交量排序取前 10
        trades_sorted = sorted(
            trades,
            key=lambda t: float(t.get("quoteQty", 0)),
            reverse=True,
        )[:10]

        return [
            {
                "price": float(t["price"]),
                "qty": float(t["qty"]),
                "quote_qty": float(t["quoteQty"]),
                "is_buyer_maker": t["isBuyerMaker"],
                "time": t["time"],
            }
            for t in trades_sorted
        ]
    except Exception as e:
        logger.error(f"[数据采集] 获取大额交易失败 ({symbol}): {e}")
        return []


async def fetch_all_market_data(symbol: str) -> dict:
    """
    采集某个币种的全部市场数据
    返回包含 1h K 线、15m K 线、资金费率、持仓量、多空比的综合字典
    """
    klines_1h_task = fetch_klines(symbol, "1h", 100)
    klines_15m_task = fetch_klines(symbol, "15m", 50)
    klines_4h_task = fetch_klines(symbol, "4h", 20)
    funding_task = fetch_funding_rate(symbol)
    oi_task = fetch_open_interest(symbol)
    ls_task = fetch_long_short_ratio(symbol)

    klines_1h, klines_15m, klines_4h, funding_rate, open_interest, long_short = await asyncio.gather(
        klines_1h_task, klines_15m_task, klines_4h_task, funding_task, oi_task, ls_task,
        return_exceptions=True,
    )

    if isinstance(klines_1h, Exception):
        logger.error(f"[数据采集] 1h K 线异常: {klines_1h}")
        klines_1h = pd.DataFrame()
    if isinstance(klines_15m, Exception):
        logger.error(f"[数据采集] 15m K 线异常: {klines_15m}")
        klines_15m = pd.DataFrame()
    if isinstance(klines_4h, Exception):
        logger.error(f"[数据采集] 4h K 线异常: {klines_4h}")
        klines_4h = pd.DataFrame()
    if isinstance(funding_rate, Exception):
        funding_rate = 0.0
    if isinstance(open_interest, Exception):
        open_interest = {"open_interest": 0}
    if isinstance(long_short, Exception):
        long_short = {"long_ratio": 0, "short_ratio": 0, "long_short_ratio": 0}

    # 最新价格
    latest_price = 0
    if not klines_1h.empty:
        latest_price = float(klines_1h.iloc[-1]["close"])

    return {
        "symbol": symbol,
        "latest_price": latest_price,
        "klines": klines_1h,
        "klines_15m": klines_15m,
        "klines_4h": klines_4h,
        "funding_rate": funding_rate,
        "open_interest": open_interest,
        "long_short_ratio": long_short,
    }


async def close_client():
    """关闭 HTTP 客户端"""
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
    _client = None  # #17 修复：清理引用
