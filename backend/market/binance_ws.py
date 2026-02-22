"""
钢子出击 - Binance WebSocket 实时价格
订阅 10 币种实时价格，断线自动重连
"""
import asyncio
import json
import logging
from typing import Dict, Optional
import websockets

logger = logging.getLogger(__name__)

# 支持的 10 个币种
SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "DOTUSDT", "POLUSDT",
]

# 全局实时价格字典
live_prices: Dict[str, dict] = {}

# markPrice + funding rate 缓存 {symbol: {"mark_price": float, "funding_rate": float, ...}}
mark_price_cache: Dict[str, dict] = {}

# WebSocket 任务引用
_ws_task: Optional[asyncio.Task] = None
_mark_ws_task: Optional[asyncio.Task] = None
_running = False
_bg_tasks: set = set()  # 防止 fire-and-forget 任务被 GC 回收

# 价格触发回调（可选）：用于异常波动时额外触发分析
_price_trigger_cb = None


def set_price_trigger_callback(cb):
    """注入价格触发回调：async def cb(symbol:str, price:float)"""
    global _price_trigger_cb
    _price_trigger_cb = cb


def get_ws_url() -> str:
    """构建 Binance WebSocket 订阅 URL"""
    streams = [f"{s.lower()}@ticker" for s in SYMBOLS]
    return f"wss://fstream.binance.com/stream?streams={'/'.join(streams)}"


def get_mark_price_url() -> str:
    """构建 @markPrice 订阅 URL（包含 markPrice + fundingRate + 下次结算时间）"""
    streams = [f"{s.lower()}@markPrice" for s in SYMBOLS]
    return f"wss://fstream.binance.com/stream?streams={'/'.join(streams)}"


async def _connect_and_listen():
    """连接 Binance WebSocket 并持续监听"""
    global _running
    url = get_ws_url()
    reconnect_delay = 3  # 重连延迟（秒）

    while _running:
        try:
            logger.info("[行情WS] 正在连接 Binance WebSocket...")
            async with websockets.connect(url, ping_interval=20, ping_timeout=10) as ws:
                logger.info("[行情WS] 连接成功，开始接收数据")
                reconnect_delay = 3  # 重置重连延迟

                async for message in ws:
                    if not _running:
                        break
                    try:
                        data = json.loads(message)
                        stream_data = data.get("data", {})
                        symbol = stream_data.get("s", "")
                        if symbol and symbol in SYMBOLS:
                            price = float(stream_data.get("c", 0))
                            live_prices[symbol] = {
                                "symbol": symbol,
                                "price": price,
                                "change_24h": float(stream_data.get("P", 0)),
                                "high_24h": float(stream_data.get("h", 0)),
                                "low_24h": float(stream_data.get("l", 0)),
                                "volume_24h": float(stream_data.get("v", 0)),
                                "quote_volume_24h": float(stream_data.get("q", 0)),
                            }
                            cb = _price_trigger_cb
                            if cb and price > 0:
                                t = asyncio.create_task(cb(symbol, price))
                                _bg_tasks.add(t)
                                t.add_done_callback(_bg_tasks.discard)
                    except (json.JSONDecodeError, KeyError, ValueError) as e:
                        logger.warning(f"[行情WS] 数据解析异常: {e}")

        except websockets.exceptions.ConnectionClosed as e:
            logger.warning(f"[行情WS] 连接断开: {e}")
        except Exception as e:
            logger.warning(f"[行情WS] 连接异常: {e}")

        if _running:
            logger.info(f"[行情WS] {reconnect_delay}秒后重连...")
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, 30)  # 指数退避，最大 30 秒


async def _connect_mark_price():
    """连接 @markPrice 流，持续更新 mark_price_cache"""
    global _running
    url = get_mark_price_url()
    reconnect_delay = 3

    while _running:
        try:
            logger.info("[MarkPrice WS] 正在连接...")
            async with websockets.connect(url, ping_interval=20, ping_timeout=10) as ws:
                logger.info("[MarkPrice WS] 连接成功")
                reconnect_delay = 3

                async for message in ws:
                    if not _running:
                        break
                    try:
                        data = json.loads(message)
                        stream_data = data.get("data", {})
                        symbol = stream_data.get("s", "")
                        if symbol and symbol in SYMBOLS:
                            mark_price_cache[symbol] = {
                                "symbol": symbol,
                                "mark_price": float(stream_data.get("p", 0)),
                                "index_price": float(stream_data.get("i", 0)),
                                "funding_rate": float(stream_data.get("r", 0)),
                                "next_funding_time": int(stream_data.get("T", 0)),
                            }
                    except (json.JSONDecodeError, KeyError, ValueError) as e:
                        logger.warning(f"[MarkPrice WS] 数据解析异常: {e}")

        except websockets.exceptions.ConnectionClosed as e:
            logger.warning(f"[MarkPrice WS] 连接断开: {e}")
        except Exception as e:
            logger.warning(f"[MarkPrice WS] 连接异常: {e}")

        if _running:
            logger.info(f"[MarkPrice WS] {reconnect_delay}秒后重连...")
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, 30)


async def start_binance_ws():
    """启动 Binance WebSocket 连接（后台任务）"""
    global _ws_task, _mark_ws_task, _running
    _running = True
    _ws_task = asyncio.create_task(_connect_and_listen())
    _mark_ws_task = asyncio.create_task(_connect_mark_price())
    logger.info("[行情WS] WebSocket 任务已启动（含 @markPrice 流）")


async def stop_binance_ws():
    """停止 Binance WebSocket 连接"""
    global _running, _ws_task, _mark_ws_task
    _running = False
    for task in (_ws_task, _mark_ws_task):
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    _ws_task = None
    _mark_ws_task = None
    logger.info("[行情WS] WebSocket 任务已停止")


def get_live_prices() -> Dict[str, dict]:
    """获取所有币种的实时价格（#65 修复：深拷贝，防止调用者修改内部数据）"""
    import copy
    return copy.deepcopy(live_prices)


def get_price(symbol: str) -> Optional[dict]:
    """获取单个币种的实时价格"""
    data = live_prices.get(symbol)
    return dict(data) if data else None  # 浅拷贝即可


def get_mark_price(symbol: str) -> Optional[dict]:
    """获取单个币种的 mark price + funding rate（来自 @markPrice 流）"""
    data = mark_price_cache.get(symbol)
    return dict(data) if data else None


def get_funding_rate(symbol: str) -> float:
    """获取单个币种的实时资金费率（来自 @markPrice 流推送，非 REST）"""
    data = mark_price_cache.get(symbol)
    return float(data.get("funding_rate", 0)) if data else 0.0


def get_all_mark_prices() -> Dict[str, dict]:
    """获取所有币种的 mark price 缓存"""
    import copy
    return copy.deepcopy(mark_price_cache)
