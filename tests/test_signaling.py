"""Tests for the SignalingClient WebRTC signaling."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from pybticino.exceptions import PyBticinoException
from pybticino.signaling import SignalingClient

from .conftest import MOCK_ACCESS_TOKEN, MOCK_BRIDGE_ID


@pytest.fixture
def mock_auth_handler():
    """Create a mock auth handler that returns a token."""
    handler = AsyncMock()
    handler.get_access_token = AsyncMock(return_value=MOCK_ACCESS_TOKEN)
    return handler


@pytest.fixture
def signaling_client(mock_auth_handler):
    """Create a SignalingClient with mocked auth."""
    return SignalingClient(
        auth_handler=mock_auth_handler,
        on_answer=AsyncMock(),
        on_candidate=AsyncMock(),
        on_event=AsyncMock(),
    )


class TestSignalingMessages:
    """Test that signaling messages have the correct format."""

    async def test_send_offer_message_format(self, signaling_client):
        """send_offer should produce the correct RTC offer message."""
        sent_messages = []

        async def mock_send(msg):
            sent_messages.append(msg)

        signaling_client._send = mock_send
        signaling_client._is_connected = True
        signaling_client._websocket = MagicMock()

        # Set up a fake ack response
        async def fake_send_offer():
            return await signaling_client.send_offer(
                device_id=MOCK_BRIDGE_ID,
                sdp="v=0\r\nfake sdp",
                module_id="ext-unit-123",
            )

        task = asyncio.create_task(fake_send_offer())

        # Give send_offer a chance to send and create the pending ack
        await asyncio.sleep(0.01)

        # Resolve the pending ack
        for fut in signaling_client._pending_acks.values():
            if not fut.done():
                fut.set_result({"session_id": "sess-123", "tag_id": "tag-abc"})

        session_id = await task

        assert session_id == "sess-123"
        assert len(sent_messages) == 1

        msg = sent_messages[0]
        assert msg["action"] == "rtc"
        assert msg["data"]["type"] == "offer"
        assert msg["data"]["session_description"]["type"] == "call"
        assert msg["data"]["session_description"]["sdp"] == "v=0\r\nfake sdp"
        assert msg["data"]["session_description"]["module_id"] == "ext-unit-123"
        assert msg["device_id"] == MOCK_BRIDGE_ID

    async def test_send_answer_message_format(self, signaling_client):
        """send_answer should use the stored session state."""
        sent_messages = []

        async def mock_send(msg):
            sent_messages.append(msg)

        signaling_client._send = mock_send
        signaling_client._session_id = "sess-123"
        signaling_client._tag_id = "tag-abc"
        signaling_client._device_id = MOCK_BRIDGE_ID
        signaling_client._correlation_id = "corr-456"

        await signaling_client.send_answer(sdp="v=0\r\nanswer sdp")

        assert len(sent_messages) == 1
        msg = sent_messages[0]
        assert msg["action"] == "rtc"
        assert msg["data"]["type"] == "answer"
        assert msg["data"]["session_description"]["sdp"] == "v=0\r\nanswer sdp"
        assert msg["session_id"] == "sess-123"
        assert msg["tag_id"] == "tag-abc"
        assert msg["device_id"] == MOCK_BRIDGE_ID
        assert msg["correlation_id"] == "corr-456"

    async def test_send_candidate_message_format(self, signaling_client):
        """send_candidate should format ICE candidate correctly."""
        sent_messages = []

        async def mock_send(msg):
            sent_messages.append(msg)

        signaling_client._send = mock_send
        signaling_client._session_id = "sess-123"
        signaling_client._tag_id = "tag-abc"
        signaling_client._device_id = MOCK_BRIDGE_ID
        signaling_client._correlation_id = "corr-456"

        await signaling_client.send_candidate(
            candidate="candidate:1 1 UDP 2122260223 192.168.1.1 12345 typ host",
            sdp_m_line_index=0,
        )

        msg = sent_messages[0]
        assert msg["action"] == "rtc"
        assert msg["data"]["type"] == "candidate"
        assert msg["data"]["ice_candidate"]["sdp_m_line_index"] == 0
        assert "192.168.1.1" in msg["data"]["ice_candidate"]["candidate"]

    async def test_send_terminate_message_format(self, signaling_client):
        """send_terminate should clear session state."""
        sent_messages = []

        async def mock_send(msg):
            sent_messages.append(msg)

        signaling_client._send = mock_send
        signaling_client._session_id = "sess-123"
        signaling_client._tag_id = "tag-abc"
        signaling_client._device_id = MOCK_BRIDGE_ID
        signaling_client._correlation_id = "corr-456"

        await signaling_client.send_terminate()

        msg = sent_messages[0]
        assert msg["action"] == "rtc"
        assert msg["data"]["type"] == "terminate"
        assert msg["session_id"] == "sess-123"

        # Session should be cleared after terminate
        assert signaling_client._session_id is None
        assert signaling_client._tag_id is None

    async def test_send_answer_without_session_raises(self, signaling_client):
        """send_answer without an active session should raise."""
        with pytest.raises(PyBticinoException, match="No active session"):
            await signaling_client.send_answer(sdp="fake")

    async def test_send_candidate_without_session_raises(self, signaling_client):
        """send_candidate without an active session should raise."""
        with pytest.raises(PyBticinoException, match="No active session"):
            await signaling_client.send_candidate(candidate="fake", sdp_m_line_index=0)


class TestSessionFromPush:
    """Test set_session_from_push for incoming calls."""

    async def test_set_session_from_push(self, signaling_client):
        """set_session_from_push should store all session fields."""
        signaling_client.set_session_from_push(
            session_id="push-sess-789",
            tag_id="push-tag-xyz",
            correlation_id="push-corr-123",
            device_id=MOCK_BRIDGE_ID,
        )

        assert signaling_client._session_id == "push-sess-789"
        assert signaling_client._tag_id == "push-tag-xyz"
        assert signaling_client._correlation_id == "push-corr-123"
        assert signaling_client._device_id == MOCK_BRIDGE_ID

    async def test_can_send_answer_after_push_session(self, signaling_client):
        """After set_session_from_push, send_answer should work."""
        sent_messages = []

        async def mock_send(msg):
            sent_messages.append(msg)

        signaling_client._send = mock_send
        signaling_client.set_session_from_push(
            session_id="push-sess",
            tag_id="push-tag",
            correlation_id="push-corr",
            device_id=MOCK_BRIDGE_ID,
        )

        await signaling_client.send_answer(sdp="answer-sdp")

        assert len(sent_messages) == 1
        assert sent_messages[0]["session_id"] == "push-sess"


class TestMessageHandling:
    """Test incoming message routing."""

    async def test_handle_answer_message(self, signaling_client):
        """An incoming answer message should invoke on_answer callback."""
        message = {
            "session_id": "sess-123",
            "data": {
                "type": "answer",
                "session_description": {
                    "type": "call",
                    "sdp": "v=0\r\nremote answer",
                },
            },
        }

        signaling_client._session_id = "sess-123"
        await signaling_client._handle_message(message)

        signaling_client._on_answer.assert_called_once_with("sess-123", "v=0\r\nremote answer")

    async def test_handle_candidate_message(self, signaling_client):
        """An incoming candidate message should invoke on_candidate callback."""
        message = {
            "session_id": "sess-123",
            "data": {
                "type": "candidate",
                "ice_candidate": {
                    "sdp_m_line_index": 0,
                    "candidate": "candidate:1 1 UDP 2122260223 10.0.0.1 5000 typ host",
                },
            },
        }

        signaling_client._session_id = "sess-123"
        await signaling_client._handle_message(message)

        signaling_client._on_candidate.assert_called_once()
        call_args = signaling_client._on_candidate.call_args
        assert call_args[0][0] == "sess-123"
        assert "candidate" in call_args[0][1]

    async def test_handle_terminate_message(self, signaling_client):
        """An incoming terminate message should invoke on_event callback."""
        message = {
            "session_id": "sess-123",
            "data": {"type": "terminate"},
        }

        signaling_client._session_id = "sess-123"
        await signaling_client._handle_message(message)

        signaling_client._on_event.assert_called_once_with("sess-123", "terminate", message)

    async def test_handle_ack_message(self, signaling_client):
        """An ack message (type=ack with session_id + tag_id) should set session state."""
        ack = {
            "type": "ack",
            "session_id": "new-sess",
            "tag_id": "new-tag",
            "status": "ok",
            "correlation_id": "123",
        }

        await signaling_client._handle_message(ack)

        assert signaling_client._session_id == "new-sess"
        assert signaling_client._tag_id == "new-tag"

    async def test_subscribe_message_format(self, signaling_client):
        """Subscribe should use app_security and version 1.0."""
        sent_raw = []
        mock_ws = AsyncMock()
        mock_ws.send = AsyncMock(side_effect=lambda m: sent_raw.append(m))
        mock_ws.recv = AsyncMock(return_value=json.dumps({"status": "ok"}))

        signaling_client._websocket = mock_ws

        await signaling_client._subscribe()

        assert len(sent_raw) == 1
        subscribe = json.loads(sent_raw[0])
        assert subscribe["action"] == "subscribe"
        assert subscribe["app_type"] == "app_security"
        assert subscribe["version"] == "1.0"
        assert subscribe["access_token"] == MOCK_ACCESS_TOKEN
