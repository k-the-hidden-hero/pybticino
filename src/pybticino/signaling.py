"""WebRTC signaling client for BTicino intercom devices.

Connects to the Netatmo signaling WebSocket (wss://app.netatmo.net/appws/)
to exchange SDP offers/answers and ICE candidates with BTicino devices.

This is separate from the push WebSocket (WebsocketClient) which receives
event notifications. The signaling WS uses app_type "app_security" and
handles the RTC call setup/teardown.

Browser compatibility note:
    The BTicino BNC1 firmware uses hardcoded Chrome-compatible RTP payload
    type numbers (PT=111 for Opus, PT=109 for H264) regardless of what is
    negotiated in the SDP answer. This makes WebRTC streaming Chrome-only.
    Firefox uses different PT assignments and silently drops the mismatched
    packets. The signaling layer works correctly with all browsers — the
    incompatibility is at the RTP payload type level in the device firmware.
"""

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
import json
import logging
import ssl
from typing import Any

import websockets
from websockets.protocol import State

from .auth import AuthHandler
from .const import RTC_WS_URL
from .exceptions import PyBticinoException

_LOGGER = logging.getLogger(__name__)

# Type aliases for callbacks
OnAnswerCallback = Callable[[str, str], Awaitable[None]]  # (session_id, sdp)
OnCandidateCallback = Callable[[str, dict], Awaitable[None]]  # (session_id, ice_candidate)
OnEventCallback = Callable[[str, str, dict], Awaitable[None]]  # (session_id, event_type, data)


class SignalingClient:
    """Handles the WebRTC signaling WebSocket for BTicino devices.

    This client connects to the Netatmo signaling endpoint, subscribes
    using the "app_security" app type, and provides methods to send/receive
    WebRTC signaling messages (offer, answer, ICE candidates, terminate).
    """

    def __init__(
        self,
        auth_handler: AuthHandler,
        on_answer: OnAnswerCallback | None = None,
        on_candidate: OnCandidateCallback | None = None,
        on_event: OnEventCallback | None = None,
    ) -> None:
        """Initialize the signaling client.

        Args:
            auth_handler: An authenticated AuthHandler instance.
            on_answer: Async callback invoked when an answer SDP is received.
                       Called with (session_id, sdp).
            on_candidate: Async callback invoked when an ICE candidate is received.
                          Called with (session_id, ice_candidate_dict).
            on_event: Async callback for other signaling events (rescind, terminate).
                      Called with (session_id, event_type, full_data).

        """
        self._auth_handler = auth_handler
        self._on_answer = on_answer
        self._on_candidate = on_candidate
        self._on_event = on_event
        self._websocket: websockets.ClientConnection | None = None
        self._listener_task: asyncio.Task | None = None
        self._connection_lock = asyncio.Lock()
        self._is_connected = False

        # Pending ack futures: correlation_id -> Future[dict]
        self._pending_acks: dict[str, asyncio.Future] = {}

        # Active session state (set after successful offer ack)
        self._session_id: str | None = None
        self._tag_id: str | None = None
        self._correlation_id: str | None = None
        self._device_id: str | None = None

    @property
    def is_connected(self) -> bool:
        """Return True if the signaling WS is connected and subscribed."""
        return self._is_connected

    @property
    def session_id(self) -> str | None:
        """Return the current signaling session ID."""
        return self._session_id

    async def connect(self) -> None:
        """Connect to the signaling WebSocket and subscribe."""
        async with self._connection_lock:
            if self._is_connected:
                _LOGGER.debug("Signaling client already connected")
                return

            _LOGGER.info("Connecting to signaling WS: %s", RTC_WS_URL)
            try:
                loop = asyncio.get_running_loop()
                ssl_context = await loop.run_in_executor(None, ssl.create_default_context)

                self._websocket = await websockets.connect(
                    RTC_WS_URL,
                    ssl=ssl_context,
                    open_timeout=30,
                    close_timeout=10,
                    ping_interval=None,
                    ping_timeout=None,
                )

                await self._subscribe()
                self._listener_task = asyncio.create_task(self._listen())
                self._is_connected = True
                _LOGGER.info("Signaling client connected and subscribed")

            except Exception as e:
                _LOGGER.exception("Failed to connect signaling WS")
                self._is_connected = False
                if self._websocket and self._websocket.state != State.CLOSED:
                    with suppress(websockets.exceptions.WebSocketException):
                        await self._websocket.close()
                self._websocket = None
                self._listener_task = None
                err_msg = f"Signaling connection failed: {e}"
                raise PyBticinoException(err_msg) from e

    async def disconnect(self) -> None:
        """Disconnect from the signaling WebSocket."""
        async with self._connection_lock:
            if not self._is_connected and not self._websocket:
                return

            _LOGGER.info("Disconnecting signaling client")
            self._is_connected = False

            # Cancel pending acks
            for fut in self._pending_acks.values():
                if not fut.done():
                    fut.cancel()
            self._pending_acks.clear()

            # Cancel listener
            if self._listener_task and not self._listener_task.done():
                self._listener_task.cancel()
                with suppress(asyncio.CancelledError):
                    await self._listener_task
            self._listener_task = None

            # Close WS
            ws = self._websocket
            self._websocket = None
            if ws and ws.state != State.CLOSED:
                with suppress(websockets.exceptions.WebSocketException):
                    await ws.close()

            # Clear session state
            self._session_id = None
            self._tag_id = None
            self._correlation_id = None
            self._device_id = None

            _LOGGER.info("Signaling client disconnected")

    async def _subscribe(self) -> None:
        """Subscribe to the signaling WS with app_security."""
        if not self._websocket:
            raise PyBticinoException("Signaling WS not connected")

        access_token = await self._auth_handler.get_access_token()
        subscribe_msg = {
            "action": "subscribe",
            "access_token": access_token,
            "app_type": "app_security",
            "version": "1.0",
            "platform": "android",
        }
        _LOGGER.debug("Signaling subscribe: %s", {**subscribe_msg, "access_token": "***"})
        await self._websocket.send(json.dumps(subscribe_msg))

        response_raw = await asyncio.wait_for(self._websocket.recv(), timeout=30)
        response = json.loads(response_raw)
        _LOGGER.debug("Signaling subscribe response: %s", response)

        if response.get("status") != "ok":
            err_msg = f"Signaling subscription failed: {response}"
            raise PyBticinoException(err_msg)

    async def _listen(self) -> None:
        """Listen for incoming signaling messages."""
        if not self._websocket:
            return

        _LOGGER.debug("Signaling listener started")
        try:
            async for message_raw in self._websocket:
                try:
                    message = json.loads(message_raw)
                    _LOGGER.debug("Signaling received: %s", message)
                    await self._handle_message(message)
                except json.JSONDecodeError:
                    _LOGGER.warning("Non-JSON signaling message: %s", message_raw)
                except Exception:
                    _LOGGER.exception("Error handling signaling message")

        except websockets.exceptions.ConnectionClosedOK as e:
            _LOGGER.info("Signaling WS closed normally (code=%s)", e.code)
        except websockets.exceptions.ConnectionClosedError as e:
            _LOGGER.warning("Signaling WS closed with error (code=%s)", e.code)
        except asyncio.CancelledError:
            _LOGGER.debug("Signaling listener cancelled")
            raise
        finally:
            self._is_connected = False
            _LOGGER.info("Signaling listener stopped")

    async def _handle_message(self, message: dict[str, Any]) -> None:
        """Route incoming signaling messages to appropriate handlers."""
        msg_top_type = message.get("type", "")

        # Ack responses: type=ack with session_id + tag_id
        if msg_top_type == "ack":
            await self._handle_ack(message)
            return

        data = message.get("data", {})
        msg_type = data.get("type", "")
        session_id = message.get("session_id", self._session_id)

        if msg_type == "answer":
            sdp = data.get("session_description", {}).get("sdp", "")
            if self._on_answer and sdp:
                await self._on_answer(session_id, sdp)

        elif msg_type == "candidate":
            ice = data.get("ice_candidate", {})
            if self._on_candidate and ice:
                await self._on_candidate(session_id, ice)

        elif msg_type in ("rescind", "terminate"):
            if self._on_event:
                await self._on_event(session_id, msg_type, message)

        else:
            _LOGGER.debug("Unhandled signaling message type: %s", msg_type)

    async def _handle_ack(self, message: dict[str, Any]) -> None:
        """Handle an ack response (session_id + tag_id) from the server.

        Only the offer ack contains session_id and tag_id. Subsequent acks
        (for ICE candidates, etc.) have None for both fields. We must NOT
        overwrite the session state with None, or terminate will fail with
        'data/tag_id must be string'.
        """
        session_id = message.get("session_id")
        tag_id = message.get("tag_id")
        _LOGGER.debug("Received ack: session_id=%s, tag_id=%s", session_id, tag_id)

        # Only update session state if the ack carries real values
        if session_id is not None:
            self._session_id = session_id
        if tag_id is not None:
            self._tag_id = tag_id

        # Resolve any pending ack future
        # The ack doesn't contain correlation_id, so resolve the most recent pending
        for corr_id, fut in list(self._pending_acks.items()):
            if not fut.done():
                fut.set_result(message)
                del self._pending_acks[corr_id]
                break

    async def _send(self, message: dict[str, Any]) -> None:
        """Send a JSON message on the signaling WS."""
        if not self._websocket or self._websocket.state == State.CLOSED:
            raise PyBticinoException("Signaling WS not connected")
        _LOGGER.debug("Signaling send: %s", message)
        await self._websocket.send(json.dumps(message))

    async def resubscribe(self) -> None:
        """Re-subscribe on the existing connection with a fresh token.

        Sends a new subscribe message with a refreshed OAuth token on the
        current WebSocket connection, keeping the session alive without
        disconnecting. Mirrors WebsocketClient.resubscribe().
        """
        if not self._websocket or not self._is_connected:
            raise PyBticinoException("Cannot resubscribe: no active signaling connection")

        access_token = await self._auth_handler.get_access_token()
        subscribe_msg = {
            "action": "subscribe",
            "access_token": access_token,
            "app_type": "app_security",
            "version": "1.0",
            "platform": "android",
        }
        _LOGGER.info("Re-subscribing signaling with fresh token")
        await self._websocket.send(json.dumps(subscribe_msg))

    async def ensure_connected(self) -> None:
        """Ensure the signaling WS is connected, reconnecting if needed."""
        if self._is_connected and self._websocket and self._websocket.state != State.CLOSED:
            return
        _LOGGER.info("Signaling not connected, reconnecting...")
        if self._is_connected:
            await self.disconnect()
        await self.connect()

    async def send_offer(
        self,
        device_id: str,
        sdp: str,
        module_id: str | None = None,
    ) -> str:
        """Send an SDP offer to initiate a call.

        Args:
            device_id: The bridge MAC address.
            sdp: The SDP offer string from the local PeerConnection.
            module_id: Optional module ID (external unit) to call.

        Returns:
            The session_id assigned by the server.

        Raises:
            PyBticinoException: If the offer fails or times out.

        """
        correlation_id = str(id(asyncio.current_task()))
        self._device_id = device_id
        self._correlation_id = correlation_id

        session_desc: dict[str, Any] = {"type": "call", "sdp": sdp}
        if module_id:
            session_desc["module_id"] = module_id

        message = {
            "action": "rtc",
            "data": {
                "type": "offer",
                "session_description": session_desc,
            },
            "device_id": device_id,
            "correlation_id": correlation_id,
        }

        # Create a future to wait for the ack
        loop = asyncio.get_running_loop()
        ack_future: asyncio.Future[dict] = loop.create_future()
        self._pending_acks[correlation_id] = ack_future

        await self._send(message)

        try:
            ack = await asyncio.wait_for(ack_future, timeout=30)
            session_id = ack.get("session_id", "")
            _LOGGER.info("Offer sent, session_id=%s", session_id)
            return session_id
        except TimeoutError as e:
            self._pending_acks.pop(correlation_id, None)
            err_msg = "Timeout waiting for offer ack"
            raise PyBticinoException(err_msg) from e

    async def send_answer(self, sdp: str) -> None:
        """Send an SDP answer (for incoming calls).

        Uses the session state (session_id, tag_id, device_id, correlation_id)
        set by the most recent offer or ack.

        Args:
            sdp: The SDP answer string.

        """
        if not self._session_id:
            raise PyBticinoException("No active session to send answer to")

        message = {
            "action": "rtc",
            "data": {
                "type": "answer",
                "session_description": {
                    "type": "call",
                    "sdp": sdp,
                },
            },
            "session_id": self._session_id,
            "tag_id": self._tag_id,
            "device_id": self._device_id,
            "correlation_id": self._correlation_id,
        }
        await self._send(message)
        _LOGGER.info("Answer sent for session %s", self._session_id)

    async def send_candidate(self, candidate: str, sdp_m_line_index: int) -> None:
        """Send an ICE candidate.

        Args:
            candidate: The ICE candidate string.
            sdp_m_line_index: The m-line index for the candidate.

        """
        if not self._session_id:
            raise PyBticinoException("No active session to send candidate to")

        message = {
            "action": "rtc",
            "data": {
                "type": "candidate",
                "ice_candidate": {
                    "sdp_m_line_index": sdp_m_line_index,
                    "candidate": candidate,
                },
            },
            "session_id": self._session_id,
            "tag_id": self._tag_id,
            "device_id": self._device_id,
            "correlation_id": self._correlation_id,
        }
        await self._send(message)

    async def send_terminate(self) -> None:
        """Terminate the current call session."""
        if not self._session_id:
            _LOGGER.debug("No active session to terminate")
            return

        message = {
            "action": "rtc",
            "data": {"type": "terminate"},
            "session_id": self._session_id,
            "tag_id": self._tag_id,
            "device_id": self._device_id,
            "correlation_id": self._correlation_id,
        }
        await self._send(message)
        _LOGGER.info("Terminate sent for session %s", self._session_id)
        self._session_id = None
        self._tag_id = None

    def set_session_from_push(
        self,
        session_id: str,
        tag_id: str,
        correlation_id: str,
        device_id: str,
    ) -> None:
        """Set session state from a push WS offer (incoming call).

        When a call comes in via the push WS, the session details are in
        the push event. This method sets them so send_answer/send_candidate
        can be used without first sending an offer.

        Args:
            session_id: From extra_params.session_id in the push event.
            tag_id: From extra_params.tag_id in the push event.
            correlation_id: From extra_params.correlation_id in the push event.
            device_id: The bridge MAC (extra_params.device_id).

        """
        self._session_id = session_id
        self._tag_id = tag_id
        self._correlation_id = correlation_id
        self._device_id = device_id
        _LOGGER.debug(
            "Session set from push: session_id=%s, device_id=%s",
            session_id,
            device_id,
        )
