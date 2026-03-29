"""Tests for WebsocketClient."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pybticino import AuthHandler, WebsocketClient
from pybticino.exceptions import PyBticinoException

from .conftest import MOCK_ACCESS_TOKEN, MOCK_PASSWORD, MOCK_USERNAME


class AsyncIterFromList:
    """Async iterator wrapper for a list of items."""

    def __init__(self, items):
        self._items = iter(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._items)
        except StopIteration:
            raise StopAsyncIteration from None


# --- Instantiation ---


def test_websocket_requires_auth_handler():
    """Test WebsocketClient rejects non-AuthHandler."""

    async def cb(msg):
        pass

    with pytest.raises(TypeError, match="must be an instance of AuthHandler"):
        WebsocketClient("not_handler", cb)


def test_websocket_requires_async_callback():
    """Test WebsocketClient rejects non-async callback."""
    handler = AuthHandler(MOCK_USERNAME, MOCK_PASSWORD)

    def sync_cb(msg):
        pass

    with pytest.raises(TypeError, match="must be an async function"):
        WebsocketClient(handler, sync_cb)


def test_websocket_instantiation():
    """Test WebsocketClient can be instantiated."""
    handler = AuthHandler(MOCK_USERNAME, MOCK_PASSWORD)

    async def cb(msg):
        pass

    client = WebsocketClient(handler, cb)
    assert client._auth_handler is handler
    assert client._is_running is False
    assert client.get_listener_task() is None


# --- Connect / Disconnect ---


async def test_connect_and_subscribe():
    """Test connect establishes connection and subscribes."""
    handler = AuthHandler(MOCK_USERNAME, MOCK_PASSWORD)
    handler._access_token = MOCK_ACCESS_TOKEN
    handler._token_expires_at = 9999999999.0

    received_messages = []

    async def cb(msg):
        received_messages.append(msg)

    client = WebsocketClient(handler, cb)

    mock_ws = AsyncMock()
    mock_ws.state = MagicMock()
    mock_ws.send = AsyncMock()
    mock_ws.recv = AsyncMock(return_value=json.dumps({"status": "ok"}))

    with patch("pybticino.websocket.websockets.connect", new_callable=AsyncMock, return_value=mock_ws):
        await client.connect()

    assert client._is_running is True
    assert client._websocket is mock_ws
    mock_ws.send.assert_called_once()

    # Check subscription payload
    sent_payload = json.loads(mock_ws.send.call_args[0][0])
    assert sent_payload["access_token"] == MOCK_ACCESS_TOKEN
    assert sent_payload["action"] == "Subscribe"

    # Cleanup
    await client.disconnect()


async def test_connect_failure_resets_state():
    """Test that failed connection resets running state."""
    handler = AuthHandler(MOCK_USERNAME, MOCK_PASSWORD)
    handler._access_token = MOCK_ACCESS_TOKEN
    handler._token_expires_at = 9999999999.0

    async def cb(msg):
        pass

    client = WebsocketClient(handler, cb)

    with (
        patch(
            "pybticino.websocket.websockets.connect",
            new_callable=AsyncMock,
            side_effect=OSError("Connection refused"),
        ),
        pytest.raises(PyBticinoException, match="connection/subscription failed"),
    ):
        await client.connect()

    assert client._is_running is False
    assert client._websocket is None


async def test_disconnect_when_not_connected():
    """Test disconnect is safe when not connected."""
    handler = AuthHandler(MOCK_USERNAME, MOCK_PASSWORD)

    async def cb(msg):
        pass

    client = WebsocketClient(handler, cb)
    await client.disconnect()  # Should not raise


async def test_subscribe_failure_raises():
    """Test that subscription failure raises PyBticinoException."""
    handler = AuthHandler(MOCK_USERNAME, MOCK_PASSWORD)
    handler._access_token = MOCK_ACCESS_TOKEN
    handler._token_expires_at = 9999999999.0

    async def cb(msg):
        pass

    client = WebsocketClient(handler, cb)

    mock_ws = AsyncMock()
    mock_ws.state = MagicMock()
    mock_ws.send = AsyncMock()
    mock_ws.recv = AsyncMock(return_value=json.dumps({"status": "error", "msg": "bad token"}))
    mock_ws.close = AsyncMock()

    with (
        patch("pybticino.websocket.websockets.connect", new_callable=AsyncMock, return_value=mock_ws),
        pytest.raises(PyBticinoException, match="subscription failed"),
    ):
        await client.connect()

    assert client._is_running is False


async def test_listener_receives_messages():
    """Test that the listener invokes the callback for received messages."""
    handler = AuthHandler(MOCK_USERNAME, MOCK_PASSWORD)
    handler._access_token = MOCK_ACCESS_TOKEN
    handler._token_expires_at = 9999999999.0

    received = []

    async def cb(msg):
        received.append(msg)

    client = WebsocketClient(handler, cb)

    test_message = {"type": "push", "data": {"event": "call"}}

    mock_ws = AsyncMock()
    mock_ws.state = MagicMock()
    mock_ws.send = AsyncMock()
    mock_ws.recv = AsyncMock(return_value=json.dumps({"status": "ok"}))
    mock_ws.close = AsyncMock()

    # Make the websocket iterable: yield one message then stop
    mock_ws.__aiter__ = MagicMock(return_value=AsyncIterFromList([json.dumps(test_message)]))

    with patch("pybticino.websocket.websockets.connect", new_callable=AsyncMock, return_value=mock_ws):
        await client.connect()

        # Wait for listener to process
        if client._listener_task:
            await asyncio.wait_for(client._listener_task, timeout=2.0)

    assert len(received) == 1
    assert received[0] == test_message

    await client.disconnect()


async def test_listener_handles_invalid_json():
    """Test that the listener handles non-JSON messages gracefully."""
    handler = AuthHandler(MOCK_USERNAME, MOCK_PASSWORD)
    handler._access_token = MOCK_ACCESS_TOKEN
    handler._token_expires_at = 9999999999.0

    received = []

    async def cb(msg):
        received.append(msg)

    client = WebsocketClient(handler, cb)

    mock_ws = AsyncMock()
    mock_ws.state = MagicMock()
    mock_ws.send = AsyncMock()
    mock_ws.recv = AsyncMock(return_value=json.dumps({"status": "ok"}))
    mock_ws.close = AsyncMock()

    # Yield invalid JSON then valid message
    mock_ws.__aiter__ = MagicMock(return_value=AsyncIterFromList(["not json at all", json.dumps({"valid": True})]))

    with patch("pybticino.websocket.websockets.connect", new_callable=AsyncMock, return_value=mock_ws):
        await client.connect()
        if client._listener_task:
            await asyncio.wait_for(client._listener_task, timeout=2.0)

    # Only the valid message should have been received
    assert len(received) == 1
    assert received[0] == {"valid": True}

    await client.disconnect()
