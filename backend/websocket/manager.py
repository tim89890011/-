"""
WebSocket state management, broadcasting, and health monitoring.

Extracted from main.py to reduce coupling and improve testability.
"""

from __future__ import annotations

import asyncio
import json
import time

from fastapi import WebSocket

from backend.utils.logger import get_logger
from backend.monitoring.metrics import metrics_collector

logger = get_logger(__name__)

# ============ Constants ============
WS_MAX_CLIENTS = 50
WS_SEND_TIMEOUT_SECONDS = 2.0
WS_SEND_BATCH_SIZE = 10
WS_CLIENT_HEARTBEAT_TIMEOUT_SECONDS = 120
WS_HEALTH_CHECK_INTERVAL = 60
PRICE_BROADCAST_INTERVAL_SECONDS = 2
WS_AUTH_TIMEOUT_SECONDS = 8

# ============ Connection State ============
ws_market_clients: set[WebSocket] = set()
ws_signal_clients: set[WebSocket] = set()
ws_client_health: dict[WebSocket, dict] = {}


# ============ Low-level Helpers ============

async def ws_send_safe(ws: WebSocket, message: str) -> bool:
    """Send WS message with timeout. Returns False on failure for cleanup."""
    try:
        await asyncio.wait_for(ws.send_text(message), timeout=WS_SEND_TIMEOUT_SECONDS)
        return True
    except Exception as e:
        logger.debug(
            "WebSocket 发送失败，准备清理连接",
            extra={"context": {"error": str(e)}},
        )
        return False


async def broadcast_to_clients(clients: set[WebSocket], message: str) -> None:
    """Batch-concurrent broadcast, isolating slow clients."""
    if not clients:
        return

    client_list = list(clients)
    disconnected: list[WebSocket] = []

    for i in range(0, len(client_list), WS_SEND_BATCH_SIZE):
        batch = client_list[i : i + WS_SEND_BATCH_SIZE]
        results = await asyncio.gather(*[ws_send_safe(ws, message) for ws in batch])
        for ws, ok in zip(batch, results):
            if not ok:
                disconnected.append(ws)

    for ws in disconnected:
        clients.discard(ws)
        ws_client_health.pop(ws, None)


def update_client_health(websocket: WebSocket, client_type: str) -> None:
    """Update client heartbeat health status."""
    now = time.time()
    if websocket not in ws_client_health:
        ws_client_health[websocket] = {
            "type": client_type,
            "connected_at": now,
            "ping_count": 0,
        }

    ws_client_health[websocket]["last_ping"] = now
    ws_client_health[websocket]["ping_count"] += 1


async def ws_authenticate(websocket: WebSocket) -> str | None:
    """WebSocket auth: expect first message as auth packet, close on failure."""
    try:
        first = await asyncio.wait_for(websocket.receive_text(), timeout=WS_AUTH_TIMEOUT_SECONDS)
        data = json.loads(first)
        if isinstance(data, dict) and data.get("type") == "auth":
            token = str(data.get("token", "")).strip()
            if token:
                return token
        await websocket.close(code=4001, reason="认证格式错误或缺少token")
        return None
    except asyncio.TimeoutError:
        await websocket.close(code=4002, reason="认证超时")
        return None
    except Exception as e:
        logger.warning("[WS] 认证异常: %s", e)
        await websocket.close(code=4003, reason="认证异常")
        return None


# ============ Background Task Loops ============

async def broadcast_prices() -> None:
    """Periodically broadcast live prices to market clients."""
    from backend.market.binance_ws import get_live_prices

    while True:
        try:
            prices = get_live_prices()
            if prices and ws_market_clients:
                message = json.dumps({"type": "prices", "data": prices}, default=str)
                await broadcast_to_clients(ws_market_clients, message)
        except Exception as e:
            logger.error(
                "价格推送异常", extra={"context": {"error": str(e)}}, exc_info=True
            )
        await asyncio.sleep(PRICE_BROADCAST_INTERVAL_SECONDS)


async def health_check_logger() -> None:
    """Periodically log WS connection health and prune stale clients."""
    while True:
        await asyncio.sleep(WS_HEALTH_CHECK_INTERVAL)

        now = time.time()

        stale_clients: list[WebSocket] = []
        for ws, health in list(ws_client_health.items()):
            last_ping = float(health.get("last_ping") or 0)
            connected_at = float(health.get("connected_at") or 0)
            last_seen = last_ping if last_ping > 0 else connected_at
            if last_seen > 0 and (now - last_seen) > WS_CLIENT_HEARTBEAT_TIMEOUT_SECONDS:
                stale_clients.append(ws)

        for ws in stale_clients:
            try:
                await ws.close(code=4003, reason="心跳超时")
            except Exception as e:
                logger.debug("关闭超时 WS 连接失败（已忽略）: %s", e)
            ws_market_clients.discard(ws)
            ws_signal_clients.discard(ws)
            ws_client_health.pop(ws, None)

        dead_clients = [
            ws
            for ws in ws_client_health.keys()
            if ws not in ws_market_clients and ws not in ws_signal_clients
        ]
        for ws in dead_clients:
            ws_client_health.pop(ws, None)

        market_count = len(ws_market_clients)
        signal_count = len(ws_signal_clients)

        metrics_collector.update_ws_connections(market_count, signal_count)

        if market_count > 0 or signal_count > 0:
            market_delays = []
            signal_delays = []

            for ws, health in ws_client_health.items():
                last_ping = health.get("last_ping", 0)
                if last_ping > 0:
                    delay = time.time() - last_ping
                    if ws in ws_market_clients:
                        market_delays.append(delay)
                    elif ws in ws_signal_clients:
                        signal_delays.append(delay)

            avg_market_delay = (
                sum(market_delays) / len(market_delays) if market_delays else 0
            )
            avg_signal_delay = (
                sum(signal_delays) / len(signal_delays) if signal_delays else 0
            )

            logger.info(
                "WebSocket 健康检查",
                extra={
                    "context": {
                        "market_clients": market_count,
                        "signal_clients": signal_count,
                        "avg_market_delay": round(avg_market_delay, 1),
                        "avg_signal_delay": round(avg_signal_delay, 1),
                    }
                },
            )


# ============ High-level Broadcast Functions ============

async def broadcast_signal(signal_data: dict) -> None:
    """Broadcast new AI signal to all subscribed clients."""
    if not ws_signal_clients:
        return
    message = json.dumps({"type": "new_signal", "data": signal_data}, default=str)
    await broadcast_to_clients(ws_signal_clients, message)


async def broadcast_trade_status(trade_info: dict) -> None:
    """Broadcast trade execution status to all subscribed clients."""
    if not ws_signal_clients:
        return
    message = json.dumps({"type": "trade_status", "data": trade_info}, default=str)
    await broadcast_to_clients(ws_signal_clients, message)


async def broadcast_order_update(event: dict) -> None:
    """Broadcast order update event to signal clients."""
    if not ws_signal_clients:
        return
    msg = json.dumps({"type": "order_update", "data": event}, default=str)
    await broadcast_to_clients(ws_signal_clients, msg)


async def broadcast_position_update(positions: dict) -> None:
    """Broadcast position change to market clients."""
    if not ws_market_clients:
        return
    msg = json.dumps({"type": "position_update", "data": positions}, default=str)
    await broadcast_to_clients(ws_market_clients, msg)


async def broadcast_balance_update(balances: dict) -> None:
    """Broadcast balance change to market clients."""
    if not ws_market_clients:
        return
    msg = json.dumps({"type": "balance_update", "data": balances}, default=str)
    await broadcast_to_clients(ws_market_clients, msg)
