#!/usr/bin/env python3
"""Example: Answer an incoming call from BTicino intercom via WebRTC.

This script demonstrates the answer mode WebRTC flow. It connects to the
push WebSocket and waits for a doorbell ring (BNC1-rtc offer). When a call
arrives, it answers via the signaling WebSocket using the session details
from the push event.

Flow:
    1. Connect to push WS and wait for BNC1-rtc offer event
    2. Extract session_id, tag_id, correlation_id, device_id, and SDP from the event
    3. Connect to signaling WS
    4. Call set_session_from_push() to inject session state
    5. Call send_answer() with a local SDP answer
    6. Exchange ICE candidates
    7. WebRTC media flows (signaling only -- no actual video rendering)

Usage:
    export BTICINO_USERNAME=your@email.com
    export BTICINO_PASSWORD=yourpassword
    python webrtc_answer_mode.py

This is a signaling-only example -- it demonstrates the protocol but does
not render video. For actual video, you would need a WebRTC stack (aiortc)
to create a real PeerConnection and generate a proper SDP answer.
"""

import asyncio
import logging
import os
import signal
import sys
from typing import Any

from pybticino import AsyncAccount, AuthHandler, SignalingClient, WebsocketClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - [%(name)s] %(message)s",
)
_LOGGER = logging.getLogger(__name__)

# Read credentials from environment
USERNAME = os.getenv("BTICINO_USERNAME")
PASSWORD = os.getenv("BTICINO_PASSWORD")

# Global shutdown event
shutdown_event = asyncio.Event()

# Minimal SDP answer for signaling demonstration.
# In a real application, this would come from PeerConnection.createOffer()
# with the DTLS setup changed from actpass to active.
MINIMAL_SDP_ANSWER = (
    "v=0\r\n"
    "o=- 1234567890 2 IN IP4 127.0.0.1\r\n"
    "s=-\r\n"
    "t=0 0\r\n"
    "a=group:BUNDLE 0 1\r\n"
    "a=msid-semantic: WMS\r\n"
    "m=audio 9 UDP/TLS/RTP/SAVPF 111\r\n"
    "c=IN IP4 0.0.0.0\r\n"
    "a=rtcp:9 IN IP4 0.0.0.0\r\n"
    "a=mid:0\r\n"
    "a=sendrecv\r\n"
    "a=rtpmap:111 opus/48000/2\r\n"
    "a=fmtp:111 minptime=10;useinbandfec=1\r\n"
    "a=ssrc:1000 cname:pybticino-example\r\n"
    "a=ssrc:1000 msid:pybticino audio0\r\n"
    "a=ice-ufrag:example\r\n"
    "a=ice-pwd:examplepasswordexamplepassword\r\n"
    "a=fingerprint:sha-256 00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00"
    ":00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00\r\n"
    "a=setup:active\r\n"  # Note: "active" not "actpass" -- we are the answerer
    "m=video 9 UDP/TLS/RTP/SAVPF 103\r\n"
    "c=IN IP4 0.0.0.0\r\n"
    "a=rtcp:9 IN IP4 0.0.0.0\r\n"
    "a=mid:1\r\n"
    "a=recvonly\r\n"
    "a=rtpmap:103 H264/90000\r\n"
    "a=fmtp:103 level-asymmetry-allowed=1;packetization-mode=1;"
    "profile-level-id=42001f\r\n"
    "a=rtcp-fb:103 nack pli\r\n"
    "a=rtcp-fb:103 ccm fir\r\n"
    "a=ice-ufrag:example\r\n"
    "a=ice-pwd:examplepasswordexamplepassword\r\n"
    "a=fingerprint:sha-256 00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00"
    ":00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00\r\n"
    "a=setup:active\r\n"
)


def signal_handler() -> None:
    """Handle shutdown signals."""
    _LOGGER.info("Shutdown signal received")
    shutdown_event.set()


async def main() -> None:
    """Run the answer mode example."""
    if not USERNAME or not PASSWORD:
        _LOGGER.error(
            "Set BTICINO_USERNAME and BTICINO_PASSWORD environment variables"
        )
        sys.exit(1)

    # Set up signal handlers
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    auth = AuthHandler(USERNAME, PASSWORD)
    account = AsyncAccount(auth)
    signaling: SignalingClient | None = None
    ws_client: WebsocketClient | None = None

    try:
        # Step 1: Authenticate and fetch topology
        _LOGGER.info("Authenticating and fetching home topology...")
        await account.async_update_topology()

        if not account.homes:
            _LOGGER.error("No homes found for this account")
            return

        home_id = next(iter(account.homes))
        home = account.homes[home_id]
        _LOGGER.info("Using home: %s (%s)", home.name, home_id)

        # Step 2: Set up the signaling client (not connected yet)
        call_received = asyncio.Event()
        call_data: dict[str, Any] = {}

        async def on_candidate(session_id: str, ice: dict) -> None:
            candidate = ice.get("candidate", "")
            m_line = ice.get("sdp_m_line_index", 0)
            _LOGGER.info("Received ICE candidate (m=%d): %s", m_line, candidate[:80])

        async def on_event(session_id: str, event_type: str, data: dict) -> None:
            _LOGGER.info("Signaling event: %s (session=%s)", event_type, session_id)
            if event_type in ("terminate", "rescind"):
                _LOGGER.info("Call ended (%s)", event_type)
                shutdown_event.set()

        signaling = SignalingClient(
            auth_handler=auth,
            on_candidate=on_candidate,
            on_event=on_event,
        )

        # Step 3: Set up push WS to listen for incoming calls
        async def on_push_message(message: dict[str, Any]) -> None:
            push_type = message.get("push_type", "")
            _LOGGER.info("Push event: %s", push_type)

            if push_type == "BNC1-rtc":
                extra = message.get("extra_params", {})
                data = extra.get("data", {})

                if data.get("type") == "offer":
                    _LOGGER.info("Incoming call detected!")
                    session_desc = data.get("session_description", {})
                    calling_module = session_desc.get("module_id", "unknown")
                    _LOGGER.info("  Calling module: %s", calling_module)
                    _LOGGER.info("  Session ID: %s", extra.get("session_id"))

                    call_data.update({
                        "session_id": extra.get("session_id"),
                        "tag_id": extra.get("tag_id"),
                        "correlation_id": str(extra.get("correlation_id", "")),
                        "device_id": extra.get("device_id"),
                        "sdp": session_desc.get("sdp"),
                        "module_id": calling_module,
                    })
                    call_received.set()

                elif data.get("type") in ("terminate", "rescind"):
                    _LOGGER.info("Call %s via push WS", data.get("type"))

            elif push_type == "BNC1-incoming_call":
                extra = message.get("extra_params", {})
                _LOGGER.info("Doorbell ring! Snapshot: %s", extra.get("snapshot_url", "none"))

        ws_client = WebsocketClient(auth_handler=auth, message_callback=on_push_message)

        _LOGGER.info("Connecting to push WebSocket...")
        await ws_client.connect()
        _LOGGER.info("Push WebSocket connected. Waiting for doorbell ring...")
        _LOGGER.info("(Press the doorbell or Ctrl+C to exit)")

        # Step 4: Wait for an incoming call
        try:
            # Wait for either a call or shutdown
            done, _ = await asyncio.wait(
                [
                    asyncio.create_task(call_received.wait()),
                    asyncio.create_task(shutdown_event.wait()),
                ],
                return_when=asyncio.FIRST_COMPLETED,
            )

            if shutdown_event.is_set():
                _LOGGER.info("Shutting down without answering")
                return

        except asyncio.CancelledError:
            _LOGGER.info("Cancelled while waiting for call")
            return

        # Step 5: Answer the call via signaling WS
        _LOGGER.info("Answering call...")
        _LOGGER.info("  Session: %s", call_data.get("session_id"))
        _LOGGER.info("  Device: %s", call_data.get("device_id"))
        _LOGGER.info("  Module: %s", call_data.get("module_id"))

        # Connect signaling WS if not already connected
        if not signaling.is_connected:
            _LOGGER.info("Connecting to signaling WebSocket...")
            await signaling.connect()

        # Set session state from the push event
        signaling.set_session_from_push(
            session_id=call_data["session_id"],
            tag_id=call_data["tag_id"],
            correlation_id=call_data["correlation_id"],
            device_id=call_data["device_id"],
        )
        _LOGGER.info("Session state set from push event")

        # Send answer
        # In a real application, you would:
        # 1. Create a PeerConnection
        # 2. Set the device's offer as remoteDescription
        # 3. Create an answer with createAnswer()
        # 4. Set localDescription
        # 5. Send the local SDP as the answer
        #
        # For this demo, we use a minimal synthetic SDP.
        _LOGGER.info("Sending SDP answer to device...")
        await signaling.send_answer(MINIMAL_SDP_ANSWER)
        _LOGGER.info("Answer sent! Session is active.")

        # Log the device's offer SDP summary
        device_sdp = call_data.get("sdp", "")
        if device_sdp:
            _LOGGER.info("Device offer SDP summary:")
            for line in device_sdp.split("\r\n"):
                if line.startswith("m=") or line.startswith("a=sendrecv") or \
                   line.startswith("a=sendonly") or line.startswith("a=recvonly") or \
                   line.startswith("a=rtpmap:"):
                    _LOGGER.info("  %s", line)

        # Step 6: Wait for session to end
        _LOGGER.info("Call active. Waiting for terminate or Ctrl+C...")
        await shutdown_event.wait()

        # Step 7: Terminate
        _LOGGER.info("Terminating session...")
        await signaling.send_terminate()
        _LOGGER.info("Session terminated")

    except Exception:
        _LOGGER.exception("Error during WebRTC answer mode example")
    finally:
        if signaling:
            await signaling.disconnect()
        if ws_client:
            await ws_client.disconnect()
        await auth.close_session()
        _LOGGER.info("Cleanup complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        _LOGGER.info("Interrupted by user")
