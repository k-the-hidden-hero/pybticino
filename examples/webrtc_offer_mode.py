#!/usr/bin/env python3
"""Example: Connect to BTicino intercom via WebRTC offer mode.

This script demonstrates the complete WebRTC signaling flow for on-demand
video viewing (offer mode). It connects to the device, exchanges SDP
offer/answer, handles ICE candidates, and prints the session state.

This is a signaling-only example -- it does NOT render video. To actually
view the video stream, you would need a WebRTC stack (like aiortc) to
create a real PeerConnection. This script uses a minimal synthetic SDP
to demonstrate the signaling protocol.

Usage:
    export BTICINO_USERNAME=your@email.com
    export BTICINO_PASSWORD=yourpassword
    python webrtc_offer_mode.py

Optional environment variables:
    BTICINO_HOME_ID     - Specific home ID (uses first found if not set)
    BTICINO_MODULE_ID   - Specific external unit module ID to call
"""

import asyncio
import logging
import os
import signal
import sys

from pybticino import AsyncAccount, AuthHandler, SignalingClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - [%(name)s] %(message)s",
)
_LOGGER = logging.getLogger(__name__)

# Read credentials from environment
USERNAME = os.getenv("BTICINO_USERNAME")
PASSWORD = os.getenv("BTICINO_PASSWORD")
HOME_ID = os.getenv("BTICINO_HOME_ID")
MODULE_ID = os.getenv("BTICINO_MODULE_ID")

# Minimal SDP offer for signaling demonstration.
# In a real application, this would come from a PeerConnection.createOffer().
# This SDP requests audio (sendrecv) and video (recvonly) using codecs
# the BTicino device supports.
MINIMAL_SDP_OFFER = (
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
    "a=setup:actpass\r\n"
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
    "a=setup:actpass\r\n"
)

# Global shutdown event
shutdown_event = asyncio.Event()


def signal_handler() -> None:
    """Handle shutdown signals."""
    _LOGGER.info("Shutdown signal received")
    shutdown_event.set()


async def main() -> None:
    """Run the offer mode example."""
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

    try:
        # Step 1: Authenticate and fetch topology
        _LOGGER.info("Authenticating and fetching home topology...")
        await account.async_update_topology()

        if not account.homes:
            _LOGGER.error("No homes found for this account")
            return

        # Select home
        home_id = HOME_ID
        if not home_id:
            home_id = next(iter(account.homes))
        home = account.homes.get(home_id)
        if not home:
            _LOGGER.error("Home ID %s not found. Available: %s", home_id, list(account.homes.keys()))
            return

        _LOGGER.info("Using home: %s (%s)", home.name, home_id)

        # Find bridge device (BNC1 type, identified by MAC address format)
        bridge_id = None
        external_units = []
        for module in home.modules:
            if module.type == "BNC1":
                bridge_id = module.id
                _LOGGER.info("Found bridge: %s (%s)", module.name, module.id)
            # External units have BNEU type
            variant = module.raw_data.get("variant_type", "")
            if "bneu" in variant.lower() or module.type == "BNEU":
                external_units.append(module)
                _LOGGER.info("Found external unit: %s (%s)", module.name, module.id)

        if not bridge_id:
            _LOGGER.error("No bridge device (BNC1) found in this home")
            return

        # Select module to call
        module_id = MODULE_ID
        if not module_id and external_units:
            module_id = external_units[0].id
            _LOGGER.info("Using first external unit: %s", module_id)

        # Step 2: Fetch TURN servers (optional, needed for NAT traversal)
        _LOGGER.info("Fetching TURN/STUN server credentials...")
        try:
            ice_servers = await account.async_get_turn_servers()
            _LOGGER.info("Got %d ICE servers:", len(ice_servers))
            for server in ice_servers:
                urls = server.get("urls", server.get("url", []))
                _LOGGER.info("  %s", urls)
        except Exception:
            _LOGGER.warning("Failed to fetch TURN servers (WebRTC may not work behind NAT)")

        # Step 3: Set up signaling callbacks
        answer_received = asyncio.Event()
        answer_sdp = ""

        async def on_answer(session_id: str, sdp: str) -> None:
            nonlocal answer_sdp
            _LOGGER.info("Received answer SDP from device (session=%s)", session_id)
            _LOGGER.info("Answer SDP length: %d bytes", len(sdp))
            # Log audio/video directions from the answer
            for line in sdp.split("\r\n"):
                if line.startswith("m=") or line.startswith("a=sendrecv") or \
                   line.startswith("a=sendonly") or line.startswith("a=recvonly"):
                    _LOGGER.info("  SDP: %s", line)
            answer_sdp = sdp
            answer_received.set()

        async def on_candidate(session_id: str, ice: dict) -> None:
            candidate = ice.get("candidate", "")
            m_line = ice.get("sdp_m_line_index", 0)
            _LOGGER.info("Received ICE candidate (m=%d): %s", m_line, candidate[:80])

        async def on_event(session_id: str, event_type: str, data: dict) -> None:
            _LOGGER.info("Signaling event: %s (session=%s)", event_type, session_id)
            error = data.get("data", {}).get("error", {})
            if error:
                _LOGGER.warning("  Error: code=%s, message=%s",
                                error.get("code"), error.get("message"))

        # Step 4: Connect signaling and send offer
        _LOGGER.info("Connecting to signaling WebSocket...")
        signaling = SignalingClient(
            auth_handler=auth,
            on_answer=on_answer,
            on_candidate=on_candidate,
            on_event=on_event,
        )
        await signaling.connect()
        _LOGGER.info("Signaling connected and subscribed")

        _LOGGER.info("Sending SDP offer to device %s...", bridge_id)
        session_id = await signaling.send_offer(
            device_id=bridge_id,
            sdp=MINIMAL_SDP_OFFER,
            module_id=module_id,
        )
        _LOGGER.info("Offer sent, session_id=%s", session_id)

        # Step 5: Wait for answer or timeout/terminate
        _LOGGER.info("Waiting for device answer (timeout: 30s)...")
        try:
            await asyncio.wait_for(answer_received.wait(), timeout=30)
            _LOGGER.info("WebRTC session established successfully!")
            _LOGGER.info("Session ID: %s", signaling.session_id)

            # In a real application, you would now:
            # 1. Call peerConnection.setRemoteDescription(answer_sdp)
            # 2. Exchange ICE candidates
            # 3. Wait for media to flow
            # 4. Display video

            _LOGGER.info("Press Ctrl+C to terminate the session...")
            await shutdown_event.wait()

        except TimeoutError:
            _LOGGER.warning("Timeout waiting for device answer")
            _LOGGER.info("The device may be busy or unreachable")

        # Step 6: Terminate session
        _LOGGER.info("Terminating session...")
        await signaling.send_terminate()
        _LOGGER.info("Session terminated")

    except Exception:
        _LOGGER.exception("Error during WebRTC offer mode example")
    finally:
        if signaling:
            await signaling.disconnect()
        await auth.close_session()
        _LOGGER.info("Cleanup complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        _LOGGER.info("Interrupted by user")
