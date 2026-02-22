"""
Binance Futures User Data Stream
实时接收持仓变动(ACCOUNT_UPDATE)、订单成交(ORDER_TRADE_UPDATE)、余额变动等事件，
替代高频 REST 轮询，实现毫秒级数据同步。
"""

import asyncio
import copy
import json
import time
import logging
from typing import Callable, Optional, Dict, Any

import aiohttp
import websockets

from backend.config import settings

logger = logging.getLogger(__name__)

# ==================== 缓存数据 ====================
# 最新持仓快照 {symbol: {"side": "long"|"short", "amount": float, "entry_price": float, ...}}
position_cache: Dict[str, dict] = {}

# 最新余额快照 {"USDT": {"balance": float, "available": float}}
balance_cache: Dict[str, dict] = {}

# 最新订单事件（供外部消费） list[dict]  – 仅最近 50 条
order_events: list[dict] = []
_ORDER_EVENT_MAX = 50

# 外部回调
_on_position_update: Optional[Callable] = None
_on_balance_update: Optional[Callable] = None
_on_order_update: Optional[Callable] = None

# 内部状态
_ws_task: Optional[asyncio.Task] = None
_keepalive_task: Optional[asyncio.Task] = None
_running = False
_listen_key: str = ""


def set_callbacks(
    on_position: Optional[Callable] = None,
    on_balance: Optional[Callable] = None,
    on_order: Optional[Callable] = None,
):
    global _on_position_update, _on_balance_update, _on_order_update
    _on_position_update = on_position
    _on_balance_update = on_balance
    _on_order_update = on_order


def _api_base() -> str:
    return "https://testnet.binancefuture.com"


def _ws_base() -> str:
    return "wss://stream.binancefuture.com"


def _headers() -> dict:
    return {"X-MBX-APIKEY": settings.BINANCE_TESTNET_API_KEY}


# ==================== Listen Key 管理 ====================

async def _get_listen_key() -> str:
    """POST /fapi/v1/listenKey 获取或刷新 listen key"""
    url = f"{_api_base()}/fapi/v1/listenKey"
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=_headers()) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"获取 listenKey 失败 status={resp.status}: {text}")
            data = await resp.json()
            return data["listenKey"]


async def _keepalive_listen_key():
    """每 30 分钟 PUT 续期 listenKey（Binance 60 分钟过期），失败最多重试 3 次"""
    global _listen_key
    while _running:
        await asyncio.sleep(30 * 60)
        if not _listen_key:
            continue
        for attempt in range(1, 4):
            try:
                url = f"{_api_base()}/fapi/v1/listenKey"
                async with aiohttp.ClientSession() as session:
                    async with session.put(url, headers=_headers()) as resp:
                        if resp.status == 200:
                            logger.debug("[UserDataStream] listenKey 续期成功")
                            break
                        else:
                            text = await resp.text()
                            logger.warning(
                                f"[UserDataStream] listenKey 续期失败(第{attempt}次): {text}"
                            )
            except Exception as e:
                logger.warning(
                    f"[UserDataStream] listenKey 续期异常(第{attempt}次): {e}"
                )
            if attempt < 3:
                await asyncio.sleep(5 * attempt)


# ==================== 事件处理 ====================

async def _handle_account_update(data: dict):
    """处理 ACCOUNT_UPDATE 事件 — 更新持仓和余额缓存"""
    update_data = data.get("a", {})
    event_reason = update_data.get("m", "")

    for b in update_data.get("B", []):
        asset = b.get("a", "")
        if asset:
            balance_cache[asset] = {
                "balance": float(b.get("wb", 0)),
                "cross_wallet": float(b.get("cw", 0)),
                "balance_change": float(b.get("bc", 0)),
            }

    for p in update_data.get("P", []):
        symbol = p.get("s", "")
        side_raw = p.get("ps", "")
        amount = float(p.get("pa", 0))
        entry_price = float(p.get("ep", 0))
        unrealized_pnl = float(p.get("up", 0))

        if side_raw in ("LONG", "SHORT"):
            side = "long" if side_raw == "LONG" else "short"
            key = f"{symbol}_{side}"
            if abs(amount) > 0:
                position_cache[key] = {
                    "symbol": symbol,
                    "side": side,
                    "amount": abs(amount),
                    "entry_price": entry_price,
                    "unrealized_pnl": unrealized_pnl,
                    "update_time": time.time(),
                    "reason": event_reason,
                }
            else:
                position_cache.pop(key, None)

    if _on_position_update:
        snap = copy.deepcopy(position_cache)
        await _safe_callback(_on_position_update, snap)

    if _on_balance_update:
        snap = copy.deepcopy(balance_cache)
        await _safe_callback(_on_balance_update, snap)


async def _handle_order_trade_update(data: dict):
    """处理 ORDER_TRADE_UPDATE 事件 — 记录订单状态"""
    o = data.get("o", {})
    event = {
        "symbol": o.get("s", ""),
        "client_order_id": o.get("c", ""),
        "side": o.get("S", ""),
        "type": o.get("o", ""),
        "status": o.get("X", ""),
        "price": float(o.get("p", 0)),
        "avg_price": float(o.get("ap", 0)),
        "stop_price": float(o.get("sp", 0)),
        "quantity": float(o.get("q", 0)),
        "filled_qty": float(o.get("z", 0)),
        "realized_pnl": float(o.get("rp", 0)),
        "commission": float(o.get("n", 0)),
        "position_side": o.get("ps", ""),
        "reduce_only": o.get("R", False),
        "close_position": o.get("cp", False),
        "order_id": o.get("i", ""),
        "time": time.time(),
    }

    order_events.append(event)
    if len(order_events) > _ORDER_EVENT_MAX:
        order_events.pop(0)

    logger.debug(
        f"[UserDataStream] 订单更新: {event['symbol']} {event['side']} "
        f"{event['type']} status={event['status']} ps={event['position_side']}"
    )

    if _on_order_update:
        evt = copy.deepcopy(event)
        await _safe_callback(_on_order_update, evt)


async def _safe_callback(cb: Callable, data: Any):
    try:
        result = cb(data)
        if asyncio.iscoroutine(result):
            await result
        logger.debug(f"[UserDataStream] 回调完成: {cb.__name__ if hasattr(cb, '__name__') else cb}")
    except Exception as e:
        logger.warning(f"[UserDataStream] 回调异常: {cb.__name__ if hasattr(cb, '__name__') else cb}: {e}", exc_info=True)


# ==================== WebSocket 主循环 ====================

async def _rest_sync_positions_and_balance():
    """H-12: WS 断连重连后用 REST 补一次最新持仓和余额，防止断线期间数据陈旧"""
    try:
        base = _api_base()
        headers = _headers()
        import hmac, hashlib
        secret = settings.BINANCE_TESTNET_API_SECRET
        timestamp = int(time.time() * 1000)

        async with aiohttp.ClientSession() as session:
            # 查余额
            params_b = f"timestamp={timestamp}"
            sig_b = hmac.new(secret.encode(), params_b.encode(), hashlib.sha256).hexdigest()
            async with session.get(
                f"{base}/fapi/v2/balance?{params_b}&signature={sig_b}", headers=headers
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for item in (data if isinstance(data, list) else []):
                        asset = item.get("asset", "")
                        if asset:
                            balance_cache[asset] = {
                                "balance": float(item.get("balance", 0)),
                                "cross_wallet": float(item.get("crossWalletBalance", 0)),
                                "balance_change": 0.0,
                            }

            # 查持仓
            timestamp2 = int(time.time() * 1000)
            params_p = f"timestamp={timestamp2}"
            sig_p = hmac.new(secret.encode(), params_p.encode(), hashlib.sha256).hexdigest()
            async with session.get(
                f"{base}/fapi/v2/positionRisk?{params_p}&signature={sig_p}", headers=headers
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for item in (data if isinstance(data, list) else []):
                        symbol = item.get("symbol", "")
                        side_raw = item.get("positionSide", "")
                        amount = float(item.get("positionAmt", 0))
                        if side_raw in ("LONG", "SHORT"):
                            side = "long" if side_raw == "LONG" else "short"
                            key = f"{symbol}_{side}"
                            if abs(amount) > 0:
                                position_cache[key] = {
                                    "symbol": symbol,
                                    "side": side,
                                    "amount": abs(amount),
                                    "entry_price": float(item.get("entryPrice", 0)),
                                    "unrealized_pnl": float(item.get("unRealizedProfit", 0)),
                                    "update_time": time.time(),
                                    "reason": "REST_SYNC",
                                }
                            else:
                                position_cache.pop(key, None)
        logger.info("[UserDataStream] ✅ 重连后 REST 补数据完成")
    except Exception as e:
        logger.warning(f"[UserDataStream] 重连后 REST 补数据失败（不影响功能）: {e}")


async def _connect_and_listen():
    """建立 User Data Stream WebSocket 并持续监听"""
    global _running, _listen_key

    reconnect_delay = 3
    is_first_connect = True

    while _running:
        try:
            _listen_key = await _get_listen_key()
            url = f"{_ws_base()}/ws/{_listen_key}"
            logger.info(f"[UserDataStream] 正在连接 {url[:60]}...")

            async with websockets.connect(url, ping_interval=20, ping_timeout=10) as ws:
                logger.info("[UserDataStream] ✅ 连接成功")
                reconnect_delay = 3

                # 非首次连接（重连）时，用 REST 补一次最新数据
                if not is_first_connect:
                    _sync_task = asyncio.create_task(_rest_sync_positions_and_balance())
                is_first_connect = False

                async for message in ws:
                    if not _running:
                        break
                    try:
                        data = json.loads(message)
                        event_type = data.get("e", "")
                        if event_type == "ACCOUNT_UPDATE":
                            await _handle_account_update(data)
                        elif event_type == "ORDER_TRADE_UPDATE":
                            await _handle_order_trade_update(data)
                        elif event_type == "listenKeyExpired":
                            logger.warning("[UserDataStream] listenKey 已过期，重新获取")
                            break
                    except (json.JSONDecodeError, KeyError, ValueError) as e:
                        logger.warning(f"[UserDataStream] 数据解析异常: {e}")

        except websockets.exceptions.ConnectionClosed as e:
            logger.warning(f"[UserDataStream] 连接断开: {e}")
        except Exception as e:
            logger.warning(f"[UserDataStream] 连接异常: {e}")

        if _running:
            logger.info(f"[UserDataStream] {reconnect_delay}秒后重连...")
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, 30)


# ==================== 启动 / 停止 ====================

async def start_user_data_stream():
    """启动 User Data Stream（后台任务）"""
    global _ws_task, _keepalive_task, _running

    if not settings.BINANCE_TESTNET_API_KEY:
        logger.warning("[UserDataStream] 未配置 API Key，跳过启动")
        return

    _running = True
    _ws_task = asyncio.create_task(_connect_and_listen())
    _keepalive_task = asyncio.create_task(_keepalive_listen_key())
    logger.info("[UserDataStream] 启动完成")


async def stop_user_data_stream():
    """停止 User Data Stream"""
    global _running, _ws_task, _keepalive_task
    _running = False
    for task in (_ws_task, _keepalive_task):
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    _ws_task = None
    _keepalive_task = None
    logger.info("[UserDataStream] 已停止")


def get_cached_positions() -> Dict[str, dict]:
    """获取缓存的持仓数据"""
    return copy.deepcopy(position_cache)


def get_cached_balance() -> Dict[str, dict]:
    """获取缓存的余额数据"""
    return copy.deepcopy(balance_cache)


def get_recent_order_events() -> list[dict]:
    """获取最近的订单事件"""
    return list(order_events)
