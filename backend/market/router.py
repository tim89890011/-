"""
钢子出击 - 行情数据路由
提供价格、K 线、指标、资金费率等 API
"""
import asyncio
import logging
from fastapi import APIRouter, Depends, HTTPException
import httpx
from backend.auth.jwt_utils import get_current_user

logger = logging.getLogger(__name__)
from backend.market.binance_ws import get_live_prices, SYMBOLS
from backend.market.data_collector import (
    fetch_klines,
    fetch_funding_rate,
    fetch_open_interest,
    fetch_long_short_ratio,
    fetch_recent_large_trades,
)
from backend.market.indicators import calculate_indicators

router = APIRouter(prefix="/api/market", tags=["行情数据"])

# #76 修复：K 线 interval 白名单
VALID_INTERVALS = {"1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w", "1M"}


def _ok(payload: dict) -> dict:
    """统一响应格式：兼容旧字段 + 新增 success/data 包装。"""
    return {"success": True, "data": payload, **payload}


@router.get("/prices")
async def get_prices(username: str = Depends(get_current_user)):
    """获取所有币种实时价格"""
    prices = get_live_prices()
    # 如果 WebSocket 还没数据，返回空但不报错
    return _ok({
        "symbols": SYMBOLS,
        "prices": prices,
        "count": len(prices),
    })


@router.get("/kline/{symbol}")
async def get_kline(
    symbol: str,
    interval: str = "1h",
    limit: int = 100,
    username: str = Depends(get_current_user),
):
    """获取 K 线数据"""
    symbol = symbol.upper()
    if symbol not in SYMBOLS:
        raise HTTPException(status_code=400, detail=f"不支持的交易对: {symbol}")
    # #76 修复：interval 白名单校验
    if interval not in VALID_INTERVALS:
        raise HTTPException(status_code=400, detail=f"不支持的时间周期: {interval}，允许: {', '.join(sorted(VALID_INTERVALS))}")
    # #74 修复：limit 下界校验
    if limit < 1:
        limit = 1
    elif limit > 1000:
        limit = 1000

    df = await fetch_klines(symbol, interval, limit)
    if df.empty:
        raise HTTPException(status_code=502, detail="获取 K 线数据失败")

    # #27 修复：用 to_dict 替代 iterrows（性能提升 10-100 倍）
    df["time"] = (df["open_time"].astype("int64") // 10**6).astype(int)
    records = df[["time", "open", "high", "low", "close", "volume"]].to_dict("records")

    return _ok({"symbol": symbol, "interval": interval, "data": records})


@router.get("/indicators/{symbol}")
async def get_indicators(
    symbol: str,
    interval: str = "1h",
    username: str = Depends(get_current_user),
):
    """获取技术指标"""
    symbol = symbol.upper()
    if symbol not in SYMBOLS:
        raise HTTPException(status_code=400, detail=f"不支持的交易对: {symbol}")
    # #5 修复：indicators 端点也做 interval 白名单校验
    if interval not in VALID_INTERVALS:
        raise HTTPException(status_code=400, detail=f"不支持的时间周期: {interval}")

    df = await fetch_klines(symbol, interval, 100)
    if df.empty:
        raise HTTPException(status_code=502, detail="获取 K 线数据失败")

    indicators = calculate_indicators(df)
    return _ok({"symbol": symbol, "interval": interval, "indicators": indicators})


@router.get("/funding/{symbol}")
async def get_funding(
    symbol: str,
    username: str = Depends(get_current_user),
):
    """获取资金费率 + 持仓量 + 多空比"""
    symbol = symbol.upper()
    # #75 修复：验证 symbol
    if symbol not in SYMBOLS:
        raise HTTPException(status_code=400, detail=f"不支持的交易对: {symbol}")

    # #26 修复：三个请求改为并行
    funding, oi, ls = await asyncio.gather(
        fetch_funding_rate(symbol),
        fetch_open_interest(symbol),
        fetch_long_short_ratio(symbol),
    )

    return _ok({
        "symbol": symbol,
        "funding_rate": funding,
        "open_interest": oi,
        "long_short_ratio": ls,
    })


@router.get("/overview")
async def get_overview(username: str = Depends(get_current_user)):
    """获取市场总览（所有币种价格 + BTC/ETH 指标简要）"""
    prices = get_live_prices()

    # BTC 指标简要
    btc_indicators = {}
    try:
        df = await fetch_klines("BTCUSDT", "1h", 100)
        if not df.empty:
            btc_indicators = calculate_indicators(df)
    except Exception as e:
        logger.warning("[Market] BTC 指标获取失败: %s", e)

    return _ok({
        "prices": prices,
        "btc_indicators": btc_indicators,
        "symbols": SYMBOLS,
    })


@router.get("/large-trades/{symbol}")
async def get_large_trades(
    symbol: str,
    username: str = Depends(get_current_user),
):
    """获取近期大额交易（巨鲸监控）"""
    symbol = symbol.upper()
    # #75 修复：验证 symbol
    if symbol not in SYMBOLS:
        raise HTTPException(status_code=400, detail=f"不支持的交易对: {symbol}")
    trades = await fetch_recent_large_trades(symbol)
    return _ok({"symbol": symbol, "trades": trades})


@router.get("/sentiment")
async def get_market_sentiment(username: str = Depends(get_current_user)):
    """获取市场情绪（后端代理第三方 API，避免前端直连 CORS 不可控）"""
    url = "https://api.alternative.me/fng/?limit=1"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
        fng = (data or {}).get("data", [])
        if not fng:
            raise HTTPException(status_code=502, detail="情绪数据为空")
        row = fng[0]
        return _ok({
            "value": int(row.get("value", 50)),
            "label": row.get("value_classification", "Neutral"),
            "timestamp": row.get("timestamp", ""),
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"情绪数据获取失败: {e}")
