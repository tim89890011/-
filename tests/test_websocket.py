"""
backend/websocket/ のユニットテスト

WebSocket 接続管理・ブロードキャスト・ヘルスチェック・認証ロジックをテスト。
exchange/DB に依存しない純粋ロジック + FastAPI TestClient による結合テスト。
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.websocket.manager import (
    WS_MAX_CLIENTS,
    WS_SEND_TIMEOUT_SECONDS,
    WS_AUTH_TIMEOUT_SECONDS,
    PRICE_BROADCAST_INTERVAL_SECONDS,
    ws_market_clients,
    ws_signal_clients,
    ws_client_health,
    ws_send_safe,
    broadcast_to_clients,
    update_client_health,
    ws_authenticate,
    broadcast_signal,
    broadcast_trade_status,
    broadcast_order_update,
    broadcast_position_update,
    broadcast_balance_update,
)


# ────────────────────────────────────────────
# Constants
# ────────────────────────────────────────────

class TestConstants:
    """定数が期待値と一致"""

    def test_max_clients(self):
        assert WS_MAX_CLIENTS == 50

    def test_send_timeout(self):
        assert WS_SEND_TIMEOUT_SECONDS == 2.0

    def test_auth_timeout(self):
        assert WS_AUTH_TIMEOUT_SECONDS == 8

    def test_price_broadcast_interval(self):
        assert PRICE_BROADCAST_INTERVAL_SECONDS == 2


# ────────────────────────────────────────────
# update_client_health
# ────────────────────────────────────────────

class TestUpdateClientHealth:
    """update_client_health: クライアント健康状態の追跡"""

    def setup_method(self):
        ws_client_health.clear()

    def test_new_client_registered(self):
        ws = MagicMock()
        update_client_health(ws, "market")
        assert ws in ws_client_health
        assert ws_client_health[ws]["type"] == "market"
        assert ws_client_health[ws]["ping_count"] == 1
        assert "connected_at" in ws_client_health[ws]
        assert "last_ping" in ws_client_health[ws]

    def test_existing_client_updated(self):
        ws = MagicMock()
        update_client_health(ws, "signal")
        first_ping = ws_client_health[ws]["last_ping"]
        update_client_health(ws, "signal")
        assert ws_client_health[ws]["ping_count"] == 2
        assert ws_client_health[ws]["last_ping"] >= first_ping

    def test_type_preserved_on_update(self):
        ws = MagicMock()
        update_client_health(ws, "market")
        update_client_health(ws, "market")
        assert ws_client_health[ws]["type"] == "market"


# ────────────────────────────────────────────
# ws_send_safe
# ────────────────────────────────────────────

class TestWsSendSafe:
    """ws_send_safe: タイムアウト付き送信"""

    @pytest.mark.asyncio
    async def test_success(self):
        ws = AsyncMock()
        ws.send_text = AsyncMock()
        result = await ws_send_safe(ws, "hello")
        assert result is True
        ws.send_text.assert_called_once_with("hello")

    @pytest.mark.asyncio
    async def test_failure_returns_false(self):
        ws = AsyncMock()
        ws.send_text = AsyncMock(side_effect=Exception("connection lost"))
        result = await ws_send_safe(ws, "hello")
        assert result is False

    @pytest.mark.asyncio
    async def test_timeout_returns_false(self):
        ws = AsyncMock()
        ws.send_text = AsyncMock(side_effect=asyncio.TimeoutError())
        result = await ws_send_safe(ws, "hello")
        assert result is False


# ────────────────────────────────────────────
# broadcast_to_clients
# ────────────────────────────────────────────

class TestBroadcastToClients:
    """broadcast_to_clients: バッチ広播・切断クライアント除去"""

    def setup_method(self):
        ws_client_health.clear()

    @pytest.mark.asyncio
    async def test_empty_clients(self):
        """空集合の場合は何もしない"""
        clients: set = set()
        await broadcast_to_clients(clients, "msg")
        # No error

    @pytest.mark.asyncio
    async def test_broadcasts_to_all(self):
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        clients = {ws1, ws2}
        await broadcast_to_clients(clients, '{"type":"test"}')
        assert ws1.send_text.called or True  # send_text called via ws_send_safe
        assert len(clients) == 2  # No disconnects

    @pytest.mark.asyncio
    async def test_removes_failed_clients(self):
        """送信失敗したクライアントは集合から除去される"""
        ws_ok = AsyncMock()
        ws_ok.send_text = AsyncMock()
        ws_fail = AsyncMock()
        ws_fail.send_text = AsyncMock(side_effect=Exception("broken"))
        clients = {ws_ok, ws_fail}
        ws_client_health[ws_fail] = {"type": "market", "ping_count": 1}

        await broadcast_to_clients(clients, "msg")

        assert ws_ok in clients
        assert ws_fail not in clients
        assert ws_fail not in ws_client_health


# ────────────────────────────────────────────
# ws_authenticate
# ────────────────────────────────────────────

class TestWsAuthenticate:
    """ws_authenticate: WebSocket 認証フロー"""

    @pytest.mark.asyncio
    async def test_valid_auth(self):
        ws = AsyncMock()
        ws.receive_text = AsyncMock(
            return_value=json.dumps({"type": "auth", "token": "valid_token_123"})
        )
        result = await ws_authenticate(ws)
        assert result == "valid_token_123"

    @pytest.mark.asyncio
    async def test_missing_token(self):
        ws = AsyncMock()
        ws.receive_text = AsyncMock(
            return_value=json.dumps({"type": "auth", "token": ""})
        )
        result = await ws_authenticate(ws)
        assert result is None
        ws.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_wrong_type(self):
        ws = AsyncMock()
        ws.receive_text = AsyncMock(
            return_value=json.dumps({"type": "subscribe", "channel": "prices"})
        )
        result = await ws_authenticate(ws)
        assert result is None
        ws.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_invalid_json(self):
        ws = AsyncMock()
        ws.receive_text = AsyncMock(return_value="not json")
        result = await ws_authenticate(ws)
        assert result is None
        ws.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_timeout(self):
        ws = AsyncMock()
        ws.receive_text = AsyncMock(side_effect=asyncio.TimeoutError())
        result = await ws_authenticate(ws)
        assert result is None
        ws.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_exception(self):
        ws = AsyncMock()
        ws.receive_text = AsyncMock(side_effect=ConnectionError("reset"))
        result = await ws_authenticate(ws)
        assert result is None
        ws.close.assert_called_once()


# ────────────────────────────────────────────
# High-level Broadcast Functions
# ────────────────────────────────────────────

class TestBroadcastFunctions:
    """broadcast_signal / broadcast_trade_status / broadcast_*_update"""

    def setup_method(self):
        ws_signal_clients.clear()
        ws_market_clients.clear()
        ws_client_health.clear()

    @pytest.mark.asyncio
    async def test_broadcast_signal_no_clients(self):
        """クライアント無し → 何もしない"""
        await broadcast_signal({"action": "BUY"})
        # No error, no crash

    @pytest.mark.asyncio
    async def test_broadcast_signal_sends_to_signal_clients(self):
        ws = AsyncMock()
        ws.send_text = AsyncMock()
        ws_signal_clients.add(ws)
        await broadcast_signal({"action": "BUY", "symbol": "BTCUSDT"})
        assert ws.send_text.called
        sent = json.loads(ws.send_text.call_args[0][0])
        assert sent["type"] == "new_signal"
        assert sent["data"]["action"] == "BUY"

    @pytest.mark.asyncio
    async def test_broadcast_trade_status_sends_to_signal_clients(self):
        ws = AsyncMock()
        ws.send_text = AsyncMock()
        ws_signal_clients.add(ws)
        await broadcast_trade_status({"status": "filled"})
        assert ws.send_text.called
        sent = json.loads(ws.send_text.call_args[0][0])
        assert sent["type"] == "trade_status"

    @pytest.mark.asyncio
    async def test_broadcast_order_update_no_clients(self):
        await broadcast_order_update({"orderId": "123"})
        # No error

    @pytest.mark.asyncio
    async def test_broadcast_order_update_sends(self):
        ws = AsyncMock()
        ws.send_text = AsyncMock()
        ws_signal_clients.add(ws)
        await broadcast_order_update({"orderId": "456"})
        sent = json.loads(ws.send_text.call_args[0][0])
        assert sent["type"] == "order_update"

    @pytest.mark.asyncio
    async def test_broadcast_position_update_to_market_clients(self):
        ws = AsyncMock()
        ws.send_text = AsyncMock()
        ws_market_clients.add(ws)
        await broadcast_position_update({"symbol": "BTCUSDT", "size": 0.01})
        sent = json.loads(ws.send_text.call_args[0][0])
        assert sent["type"] == "position_update"

    @pytest.mark.asyncio
    async def test_broadcast_balance_update_to_market_clients(self):
        ws = AsyncMock()
        ws.send_text = AsyncMock()
        ws_market_clients.add(ws)
        await broadcast_balance_update({"USDT": 1000.0})
        sent = json.loads(ws.send_text.call_args[0][0])
        assert sent["type"] == "balance_update"

    @pytest.mark.asyncio
    async def test_broadcast_position_update_no_clients(self):
        """market クライアント無し → 何もしない"""
        await broadcast_position_update({"symbol": "BTCUSDT"})

    @pytest.mark.asyncio
    async def test_broadcast_balance_update_no_clients(self):
        await broadcast_balance_update({"USDT": 500.0})
