"""WebSocket endpoint handlers."""

from __future__ import annotations

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.auth.jwt_utils import verify_token_active
from backend.market.binance_ws import get_live_prices
from backend.utils.logger import get_logger, set_request_id
from backend.websocket.manager import (
    WS_MAX_CLIENTS,
    ws_market_clients,
    ws_signal_clients,
    ws_client_health,
    ws_authenticate,
    update_client_health,
)

logger = get_logger(__name__)

router = APIRouter()


@router.websocket("/ws/market")
async def ws_market(websocket: WebSocket):
    """Market WebSocket - push live prices."""
    await websocket.accept()

    try:
        token = await ws_authenticate(websocket)
        if not token:
            await websocket.close(code=4001, reason="缺少认证 Token")
            return
        await verify_token_active(token)
    except Exception as e:
        logger.debug("[WS/market] Token 验证失败: %s", e)
        await websocket.close(code=4001, reason="Token 无效")
        return

    if len(ws_market_clients) >= WS_MAX_CLIENTS:
        await websocket.close(code=4002, reason="连接数已满")
        return

    ws_market_clients.add(websocket)
    client_ip = websocket.client.host if websocket.client else "unknown"
    update_client_health(websocket, "market")

    set_request_id()
    logger.info(
        "WebSocket 行情连接建立",
        extra={
            "context": {"client_ip": client_ip, "client_count": len(ws_market_clients)}
        },
    )

    try:
        prices = get_live_prices()
        if prices:
            await websocket.send_text(
                json.dumps({"type": "prices", "data": prices}, default=str)
            )

        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
                update_client_health(websocket, "market")
    except WebSocketDisconnect:
        logger.info(
            "WebSocket 行情连接断开",
            extra={"context": {"client_ip": client_ip, "reason": "normal"}},
        )
    except Exception as e:
        logger.warning(
            "WebSocket 行情连接异常",
            extra={"context": {"client_ip": client_ip, "error": str(e)}},
        )
    finally:
        ws_market_clients.discard(websocket)
        ws_client_health.pop(websocket, None)
        logger.info(
            "WebSocket 行情连接关闭",
            extra={
                "context": {"client_ip": client_ip, "remaining": len(ws_market_clients)}
            },
        )


@router.websocket("/ws/signals")
async def ws_signals(websocket: WebSocket):
    """Signal WebSocket - push new AI signals."""
    await websocket.accept()

    client_ip = websocket.client.host if websocket.client else "unknown"

    try:
        token = await ws_authenticate(websocket)
        if not token:
            await websocket.close(code=4001, reason="缺少认证 Token")
            return
        await verify_token_active(token)
    except Exception as e:
        logger.debug("[WS/signal] Token 验证失败: %s", e)
        await websocket.close(code=4001, reason="Token 无效")
        return

    if len(ws_signal_clients) >= WS_MAX_CLIENTS:
        await websocket.close(code=4002, reason="连接数已满")
        return

    ws_signal_clients.add(websocket)
    update_client_health(websocket, "signal")
    logger.info(
        "WebSocket 信号连接建立",
        extra={
            "context": {"client_ip": client_ip, "client_count": len(ws_signal_clients)}
        },
    )

    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
                update_client_health(websocket, "signal")
    except WebSocketDisconnect:
        logger.info(
            "WebSocket 信号连接断开",
            extra={"context": {"client_ip": client_ip, "reason": "normal"}},
        )
    except Exception as e:
        logger.warning(
            "WebSocket 信号连接异常",
            extra={"context": {"client_ip": client_ip, "error": str(e)}},
        )
    finally:
        ws_signal_clients.discard(websocket)
        ws_client_health.pop(websocket, None)
        logger.info(
            "WebSocket 信号连接关闭",
            extra={
                "context": {"client_ip": client_ip, "remaining": len(ws_signal_clients)}
            },
        )
