# WebRTC Signaling Protocol

This document describes the WebRTC signaling protocol used by BTicino Classe 100X/300X video intercoms via the Netatmo cloud infrastructure. All details were discovered through reverse engineering of the official BTicino/Netatmo Android app (com.netatmo.camera).

## WebSocket Endpoints

The system uses **two separate WebSocket connections** for different purposes:

| Purpose | URL | `app_type` | Description |
|---------|-----|-----------|-------------|
| **Push WS** | `wss://app-ws.netatmo.net/ws/` | `app_camera` | Persistent connection for real-time event notifications (doorbell rings, call offers, connection status) |
| **Signaling WS** | `wss://app-ws.netatmo.net/appws/` | `app_security` | On-demand connection for WebRTC signaling (SDP exchange, ICE candidates, session management) |

!!! important "URL distinction"
    Note the different paths: `/ws/` for push notifications and `/appws/` for signaling. The signaling endpoint is at `app-ws.netatmo.net`, NOT `app.netatmo.net` (which redirects and does not work).

## Subscribe Messages

Both WebSocket connections require a subscribe message after connecting.

### Push WS Subscribe

```json
{
    "action": "Subscribe",
    "access_token": "<oauth_token>",
    "app_type": "app_camera",
    "platform": "Android",
    "version": "4.1.1.3"
}
```

!!! warning "No filter field"
    Do **not** include a `filter` field in the push WS subscribe message. The official app does not send one. Including `filter=silent` or similar will cause real-time call notifications to be suppressed.

### Signaling WS Subscribe

```json
{
    "action": "subscribe",
    "access_token": "<oauth_token>",
    "app_type": "app_security",
    "version": "1.0",
    "platform": "android"
}
```

Both endpoints respond with:

```json
{
    "status": "ok"
}
```

## Session State

Every signaling session tracks four identifiers:

| Field | Type | Description |
|-------|------|-------------|
| `session_id` | UUID string | Unique session identifier, assigned by the server in the offer ack |
| `tag_id` | Base64 string | Session tag, assigned by the server in the offer ack |
| `correlation_id` | Number/string | Client-generated identifier to correlate requests with acks |
| `device_id` | MAC address | The bridge device MAC (e.g., `00:03:50:xx:xx:xx`) |

These values must be included in every subsequent signaling message (answer, candidate, terminate) after the session is established.

## Two Call Modes

### Offer Mode (On-Demand Viewing)

The client initiates a call to view the intercom camera on demand. The client sends an SDP offer, and the device responds with an SDP answer.

```
Client (pybticino)           Netatmo Server           BTicino Device
      |                            |                        |
      |-- subscribe -------------->|                        |
      |<-- {status: "ok"} --------|                        |
      |                            |                        |
      |-- offer (SDP) ----------->|-- forward offer ------>|
      |<-- ack (session_id, -------|                        |
      |    tag_id)                 |                        |
      |                            |<-- answer (SDP) ------|
      |<-- answer (SDP) ----------|                        |
      |                            |                        |
      |-- candidate (ICE) ------->|-- forward candidate -->|
      |<-- candidate (ICE) -------|<-- candidate (ICE) ----|
      |                            |                        |
      |========= WebRTC media flows directly ===============|
      |                            |                        |
      |-- terminate -------------->|-- forward terminate -->|
```

### Answer Mode (Incoming Call)

The device initiates a call (doorbell ring). The call offer arrives via the **push WS**, but the answer is sent via the **signaling WS**.

```
Push WS                    Client (pybticino)         Signaling WS         Device
   |                             |                         |                  |
   |<-- BNC1-rtc (offer SDP) ---|<-- doorbell ring --------|<-- ring ---------|
   |                             |                         |                  |
   |                             |-- connect + subscribe ->|                  |
   |                             |<-- {status: "ok"} ------|                  |
   |                             |                         |                  |
   |                             |-- set_session_from_push |                  |
   |                             |   (session_id, tag_id,  |                  |
   |                             |    correlation_id,      |                  |
   |                             |    device_id)           |                  |
   |                             |                         |                  |
   |                             |-- answer (SDP) -------->|-- forward ------>|
   |                             |                         |                  |
   |                             |-- candidate (ICE) ----->|-- forward ------>|
   |                             |                         |                  |
   |                             |========= WebRTC media =================== |
```

The key difference is that in answer mode:

1. The session identifiers (`session_id`, `tag_id`, `correlation_id`, `device_id`) come from the push WS event's `extra_params`, not from an offer ack
2. The client calls `set_session_from_push()` to inject these values into the `SignalingClient` before sending the answer
3. The client sends `send_answer()` instead of `send_offer()`
4. The DTLS setup role in the browser's SDP must be changed from `actpass` to `active` (since the client is now the answerer, not the offerer)

## Signaling Message Types

### Offer

Sent by the client (offer mode) or received from the device (answer mode via push WS).

**Client sends offer (offer mode):**

```json
{
    "action": "rtc",
    "data": {
        "type": "offer",
        "session_description": {
            "type": "call",
            "sdp": "v=0\r\no=- 123456 2 IN IP4 127.0.0.1\r\n...",
            "module_id": "optional_external_unit_id"
        }
    },
    "device_id": "00:03:50:xx:xx:xx",
    "correlation_id": "12345"
}
```

The `module_id` field is optional and specifies which external unit to call when there are multiple units.

**Device sends offer (answer mode, via push WS):**

```json
{
    "type": "Websocket",
    "push_type": "BNC1-rtc",
    "category": "rtc",
    "voip_call": true,
    "expiry": 30,
    "extra_params": {
        "session_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
        "tag_id": "base64_encoded_tag",
        "correlation_id": 12345,
        "device_id": "00:03:50:xx:xx:xx",
        "home_id": "home_id_string",
        "data": {
            "type": "offer",
            "session_description": {
                "type": "call",
                "sdp": "v=0\r\no=- 123456 2 IN IP4 127.0.0.1\r\n...",
                "module_id": "calling_unit_id",
                "modules": ["module_id_1", "module_id_2"]
            }
        }
    }
}
```

### Offer Ack

The server responds to an offer with an acknowledgement containing the session identifiers.

```json
{
    "type": "ack",
    "session_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "tag_id": "base64_encoded_tag"
}
```

!!! warning "Ack handling"
    Only the offer ack contains `session_id` and `tag_id`. Subsequent acks (for ICE candidates, terminate, etc.) return `null` for both fields. The client **must not** overwrite the session state with null values, or the terminate message will fail with `data/tag_id must be string`.

### Answer

Received from the device (offer mode) or sent by the client (answer mode).

**Device answer (received in offer mode):**

```json
{
    "session_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "data": {
        "type": "answer",
        "session_description": {
            "type": "call",
            "sdp": "v=0\r\no=- 789012 2 IN IP4 127.0.0.1\r\n..."
        }
    }
}
```

**Client answer (sent in answer mode):**

```json
{
    "action": "rtc",
    "data": {
        "type": "answer",
        "session_description": {
            "type": "call",
            "sdp": "v=0\r\n..."
        }
    },
    "session_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "tag_id": "base64_encoded_tag",
    "device_id": "00:03:50:xx:xx:xx",
    "correlation_id": "12345"
}
```

### ICE Candidate

Exchanged bidirectionally for trickle ICE.

**Send candidate:**

```json
{
    "action": "rtc",
    "data": {
        "type": "candidate",
        "ice_candidate": {
            "sdp_m_line_index": 0,
            "candidate": "candidate:1 1 udp 2122260223 192.168.1.100 54321 typ host ..."
        }
    },
    "session_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "tag_id": "base64_encoded_tag",
    "device_id": "00:03:50:xx:xx:xx",
    "correlation_id": "12345"
}
```

**Receive candidate:**

```json
{
    "session_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "data": {
        "type": "candidate",
        "ice_candidate": {
            "sdp_m_line_index": 0,
            "candidate": "candidate:1 1 udp 2122260223 10.0.0.50 12345 typ host ..."
        }
    }
}
```

### Terminate

Ends the session. Can be sent by either side.

**Send terminate:**

```json
{
    "action": "rtc",
    "data": {
        "type": "terminate"
    },
    "session_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "tag_id": "base64_encoded_tag",
    "device_id": "00:03:50:xx:xx:xx",
    "correlation_id": "12345"
}
```

**Receive terminate (normal):**

```json
{
    "session_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "data": {
        "type": "terminate"
    }
}
```

**Receive terminate (with error):**

```json
{
    "session_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "data": {
        "type": "terminate",
        "error": {
            "code": 1,
            "message": "Max number of peers reached"
        }
    }
}
```

### Rescind

Received when the call is answered by another device (e.g., the physical handset or another app instance).

```json
{
    "session_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "data": {
        "type": "rescind"
    }
}
```

## Session Lifecycle

### Offer Mode Lifecycle

```
1. DISCONNECTED
   └─ connect() → signaling WS
2. CONNECTED
   └─ subscribe (app_security)
3. SUBSCRIBED
   └─ send_offer(device_id, sdp)
4. OFFER_SENT
   └─ receive ack (session_id, tag_id stored)
5. ACK_RECEIVED
   └─ receive answer (SDP)
6. ANSWER_RECEIVED
   ├─ exchange ICE candidates
   └─ WebRTC media flowing
7. CONNECTED (media)
   └─ send_terminate() or receive terminate
8. TERMINATED
   └─ session_id cleared
```

### Answer Mode Lifecycle

```
1. Push WS receives BNC1-rtc offer
   └─ extract session_id, tag_id, correlation_id, device_id, SDP
2. connect() → signaling WS (if not already connected)
   └─ subscribe (app_security)
3. set_session_from_push(session_id, tag_id, correlation_id, device_id)
4. send_answer(sdp)
   ├─ exchange ICE candidates
   └─ WebRTC media flowing
5. CONNECTED (media)
   └─ send_terminate() or receive terminate
6. TERMINATED
```

## Device Timeout

In offer mode, the device has an approximately **30-second timeout**. If the WebRTC connection is not fully established within this window, the device sends a terminate message. The official app uses a 20-second per-transition timeout in its internal state machine.

## Keepalive

There are **no application-level keepalive messages** during active WebRTC sessions. The official app does not send ping/pong or any heartbeat during calls. TCP keepalive handles the WebSocket connection.

For the push WS connection (which is long-lived), tokens expire approximately every hour. Use `resubscribe()` to send a fresh token without disconnecting.

## TURN/STUN Servers

ICE server credentials for NAT traversal are obtained from the `/turn` endpoint:

```
POST https://app.netatmo.net/turn
Authorization: Bearer <access_token>
Content-Type: application/x-www-form-urlencoded

client_type=user
```

The response contains ICE server configurations:

```json
{
    "iceServers": [
        {
            "urls": ["turn:turn.netatmo.net:443?transport=tcp"],
            "username": "temporary_username",
            "credential": "temporary_password",
            "credentialType": "password"
        },
        {
            "urls": ["stun:stun.netatmo.net:3478"]
        }
    ]
}
```

## pybticino API Reference

The `SignalingClient` class provides the following methods for WebRTC signaling:

| Method | Description |
|--------|-------------|
| `connect()` | Connect and subscribe to the signaling WS |
| `disconnect()` | Disconnect and clean up session state |
| `send_offer(device_id, sdp, module_id=None)` | Send an SDP offer (offer mode). Returns `session_id` |
| `send_answer(sdp)` | Send an SDP answer (answer mode). Requires prior `set_session_from_push()` |
| `send_candidate(candidate, sdp_m_line_index)` | Send an ICE candidate |
| `send_terminate()` | Terminate the current session |
| `set_session_from_push(session_id, tag_id, correlation_id, device_id)` | Set session state from a push WS event for answer mode |

### Callbacks

```python
SignalingClient(
    auth_handler=auth,
    on_answer=async_callback,     # (session_id: str, sdp: str) -> None
    on_candidate=async_callback,  # (session_id: str, ice_candidate: dict) -> None
    on_event=async_callback,      # (session_id: str, event_type: str, data: dict) -> None
)
```
