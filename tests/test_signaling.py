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

        await signaling_client.send_answer(sdp="v=0\r\nanswer sdp", wait_for_ack=False)

        assert len(sent_messages) == 1
        msg = sent_messages[0]
        assert msg["action"] == "rtc"
        assert msg["data"]["type"] == "answer"
        assert msg["data"]["session_description"]["sdp"] == "v=0\r\nanswer sdp"
        assert msg["session_id"] == "sess-123"
        assert msg["tag_id"] == "tag-abc"
        assert msg["device_id"] == MOCK_BRIDGE_ID
        assert msg["correlation_id"] == "corr-456"

    async def test_send_answer_returns_its_own_ack(self, signaling_client):
        """The answer should complete on its own ack, not on one that precedes it."""
        signaling_client._send = AsyncMock()
        signaling_client.set_session_from_push(
            session_id="sess-123",
            tag_id="tag-abc",
            correlation_id="corr-456",
            device_id=MOCK_BRIDGE_ID,
        )

        async def feed_acks():
            # The resubscribe sent before every answer is acked first, 3 ms
            # earlier in the field. It is not the answer's ack.
            await signaling_client._handle_ack({"type": "ack", "correlation_id": 0})
            await signaling_client._handle_ack({"type": "ack", "correlation_id": "corr-456", "session_id": "sess-123"})

        feeder = asyncio.create_task(feed_acks())
        ack = await signaling_client.send_answer(sdp="v=0\r\nanswer sdp", timeout=1)
        await feeder

        assert ack["correlation_id"] == "corr-456"
        assert not signaling_client._pending_answer_acks

    async def test_send_answer_ack_keeps_the_session_addressable(self, signaling_client):
        """An answer's ack should not overwrite the session it belongs to."""
        signaling_client._send = AsyncMock()
        signaling_client.set_session_from_push(
            session_id="sess-123",
            tag_id="tag-abc",
            correlation_id="corr-456",
            device_id=MOCK_BRIDGE_ID,
        )

        async def feed_ack():
            # The ack of an answer carries no tag_id and no device_id.
            await signaling_client._handle_ack({"type": "ack", "correlation_id": "corr-456", "session_id": "sess-123"})

        feeder = asyncio.create_task(feed_ack())
        await signaling_client.send_answer(sdp="v=0\r\nanswer sdp", timeout=1)
        await feeder

        session = signaling_client._sessions["sess-123"]
        assert session.tag_id == "tag-abc"
        assert session.device_id == MOCK_BRIDGE_ID

    async def test_send_answer_returns_a_refused_ack(self, signaling_client):
        """A refused answer should be returned, so the caller can recover."""
        signaling_client._send = AsyncMock()
        signaling_client.set_session_from_push(
            session_id="sess-123",
            tag_id="tag-abc",
            correlation_id="corr-456",
            device_id=MOCK_BRIDGE_ID,
        )
        error = {"code": 2, "message": "Invalid access_token"}

        async def feed_ack():
            await signaling_client._handle_ack({"type": "ack", "correlation_id": "corr-456", "error": error})

        feeder = asyncio.create_task(feed_ack())
        ack = await signaling_client.send_answer(sdp="v=0\r\nanswer sdp", timeout=1)
        await feeder

        assert ack["error"] == error

    async def test_send_answer_times_out_without_an_ack(self, signaling_client):
        """An answer nobody acks should fail rather than wait forever."""
        signaling_client._send = AsyncMock()
        signaling_client.set_session_from_push(
            session_id="sess-123",
            tag_id="tag-abc",
            correlation_id="corr-456",
            device_id=MOCK_BRIDGE_ID,
        )

        with pytest.raises(PyBticinoException, match="Timeout"):
            await signaling_client.send_answer(sdp="v=0\r\nanswer sdp", timeout=0.01)

        assert not signaling_client._pending_answer_acks

    async def test_send_answer_without_waiting(self, signaling_client):
        """wait_for_ack=False should keep the previous fire-and-forget behaviour."""
        signaling_client._send = AsyncMock()
        signaling_client.set_session_from_push(
            session_id="sess-123",
            tag_id="tag-abc",
            correlation_id="corr-456",
            device_id=MOCK_BRIDGE_ID,
        )

        ack = await signaling_client.send_answer(sdp="v=0\r\nanswer sdp", wait_for_ack=False)

        assert ack is None
        assert not signaling_client._pending_answer_acks
        signaling_client._send.assert_awaited_once()

    async def test_answer_ack_does_not_complete_a_pending_offer(self, signaling_client):
        """An offer waiting on the same socket should not take the answer's ack."""
        signaling_client._send = AsyncMock()
        signaling_client.set_session_from_push(
            session_id="sess-123",
            tag_id="tag-abc",
            correlation_id="corr-456",
            device_id=MOCK_BRIDGE_ID,
        )
        offer_future = asyncio.get_running_loop().create_future()
        signaling_client._pending_acks["corr-999"] = offer_future

        async def feed_ack():
            await signaling_client._handle_ack({"type": "ack", "correlation_id": "corr-456", "session_id": "sess-123"})

        feeder = asyncio.create_task(feed_ack())
        await signaling_client.send_answer(sdp="v=0\r\nanswer sdp", timeout=1)
        await feeder

        assert not offer_future.done()

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

        await signaling_client.send_answer(sdp="answer-sdp", wait_for_ack=False)

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


def _capture_sends(client):
    """Replace _send with a recorder and mark the client connected."""
    sent = []

    async def mock_send(msg):
        sent.append(msg)

    client._send = mock_send
    client._is_connected = True
    client._websocket = MagicMock()
    return sent


async def _start_offer(client, device_id=MOCK_BRIDGE_ID, module_id="ext-unit-123"):
    """Start send_offer in a task and wait until its message is on the wire."""
    task = asyncio.create_task(client.send_offer(device_id=device_id, sdp="v=0\r\nfake", module_id=module_id))
    await asyncio.sleep(0.01)
    return task


class TestOfferAckCorrelation:
    """An offer must complete on its own ack, not on whatever ack comes first (#105 downstream)."""

    async def test_subscribe_ack_does_not_complete_a_pending_offer(self, signaling_client):
        """A resubscribe ack carries no session; it must not be taken for the offer's ack."""
        _capture_sends(signaling_client)
        task = await _start_offer(signaling_client)

        await signaling_client._handle_message({"type": "ack", "status": "ok", "correlation_id": 0})
        await asyncio.sleep(0)
        assert not task.done()

        await signaling_client._handle_message(
            {"type": "ack", "status": "ok", "session_id": "real-sess", "tag_id": "real-tag"}
        )
        assert await task == "real-sess"

    async def test_ack_with_matching_correlation_id_completes_that_offer(self, signaling_client):
        """With two offers pending, an ack naming a correlation id completes that offer only."""
        sent = _capture_sends(signaling_client)
        first = await _start_offer(signaling_client, module_id="unit-1")
        second = await _start_offer(signaling_client, module_id="unit-2")
        second_corr = sent[1]["correlation_id"]

        await signaling_client._handle_message(
            {"type": "ack", "status": "ok", "session_id": "sess-2", "tag_id": "tag-2", "correlation_id": second_corr}
        )
        assert await second == "sess-2"
        assert not first.done()

        await signaling_client._handle_message(
            {"type": "ack", "status": "ok", "session_id": "sess-1", "tag_id": "tag-1"}
        )
        assert await first == "sess-1"


class TestPerSessionState:
    """Each session keeps its own tag, correlation id and device (pybticino#28)."""

    async def _open(self, client, session_id, tag_id, device_id=MOCK_BRIDGE_ID):
        sent = _capture_sends(client) if not hasattr(client, "_test_sent") else client._test_sent
        client._test_sent = sent
        task = await _start_offer(client, device_id=device_id)
        corr = sent[-1]["correlation_id"]
        await client._handle_message({"type": "ack", "status": "ok", "session_id": session_id, "tag_id": tag_id})
        await task
        return corr

    async def test_terminate_targets_the_named_session_after_a_newer_offer(self, signaling_client):
        """Terminating an older session uses its own fields and leaves the newer one intact."""
        old_corr = await self._open(signaling_client, "old-sess", "old-tag")
        new_corr = await self._open(signaling_client, "new-sess", "new-tag")
        sent = signaling_client._test_sent

        await signaling_client.send_terminate("old-sess")

        msg = sent[-1]
        assert msg["data"]["type"] == "terminate"
        assert msg["session_id"] == "old-sess"
        assert msg["tag_id"] == "old-tag"
        assert msg["correlation_id"] == old_corr
        assert signaling_client.session_id == "new-sess"

        await signaling_client.send_candidate("candidate:1 1 udp 1 1.2.3.4 5 typ host", 0)
        assert sent[-1]["session_id"] == "new-sess"
        assert sent[-1]["tag_id"] == "new-tag"
        assert sent[-1]["correlation_id"] == new_corr

    async def test_terminate_of_an_unknown_session_sends_nothing(self, signaling_client):
        """A session the client never saw has no tag to terminate with."""
        await self._open(signaling_client, "live-sess", "live-tag")
        sent = signaling_client._test_sent
        before = len(sent)

        await signaling_client.send_terminate("never-seen")

        assert len(sent) == before
        assert signaling_client.session_id == "live-sess"

    async def test_terminate_without_argument_keeps_closing_the_current_session(self, signaling_client):
        """The old call shape still terminates the most recent session."""
        await self._open(signaling_client, "only-sess", "only-tag")

        await signaling_client.send_terminate()

        assert signaling_client._test_sent[-1]["session_id"] == "only-sess"
        assert signaling_client.session_id is None

    async def test_candidate_for_a_named_session_uses_its_fields(self, signaling_client):
        """send_candidate(session_id=...) addresses that session, not the latest."""
        old_corr = await self._open(signaling_client, "old-sess", "old-tag")
        await self._open(signaling_client, "new-sess", "new-tag")

        await signaling_client.send_candidate("candidate:x", 1, session_id="old-sess")

        msg = signaling_client._test_sent[-1]
        assert msg["session_id"] == "old-sess"
        assert msg["tag_id"] == "old-tag"
        assert msg["correlation_id"] == old_corr

    async def test_push_session_can_be_answered_by_id(self, signaling_client):
        """A session set from a push is addressable even after another offer."""
        signaling_client.set_session_from_push(
            session_id="push-sess", tag_id="push-tag", correlation_id="push-corr", device_id=MOCK_BRIDGE_ID
        )
        await self._open(signaling_client, "offer-sess", "offer-tag")

        await signaling_client.send_answer("v=0\r\nanswer", session_id="push-sess", wait_for_ack=False)

        msg = signaling_client._test_sent[-1]
        assert msg["data"]["type"] == "answer"
        assert msg["session_id"] == "push-sess"
        assert msg["tag_id"] == "push-tag"
        assert msg["correlation_id"] == "push-corr"


class TestCorrelationIds:
    """Each offer needs its own correlation id: acks are matched on it."""

    async def test_offers_sent_from_one_task_get_different_ids(self, signaling_client):
        """id(current_task()) is the same for every offer a task sends."""
        sent = _capture_sends(signaling_client)

        async def ack_soon(session_id):
            await asyncio.sleep(0.01)
            await signaling_client._handle_message({"type": "ack", "status": "ok", "session_id": session_id})

        for session_id in ("s1", "s2"):
            acker = asyncio.create_task(ack_soon(session_id))
            assert await signaling_client.send_offer(device_id=MOCK_BRIDGE_ID, sdp="v=0") == session_id
            await acker

        assert sent[0]["correlation_id"] != sent[1]["correlation_id"]
