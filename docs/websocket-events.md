# WebSocket Events

The Netatmo push WebSocket delivers real-time events with `push_type` in the format `{DEVICE_TYPE}-{EVENT_TYPE}`.

## Two WebSocket Endpoints

The BTicino/Netatmo system uses **two separate WebSocket connections**:

| Endpoint | URL | `app_type` | Purpose |
|----------|-----|-----------|---------|
| **Push WS** | `wss://app-ws.netatmo.net/ws/` | `app_camera` | Persistent connection for real-time event notifications |
| **Signaling WS** | `wss://app-ws.netatmo.net/appws/` | `app_security` | On-demand connection for WebRTC signaling (SDP exchange) |

This page documents the **Push WS** events. For the signaling protocol, see [WebRTC Signaling](webrtc-signaling.md).

## Connection

Connect to `wss://app-ws.netatmo.net/ws/` and subscribe:

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
    Do not send a `filter` field in the subscribe message. Without it, you receive all events including real-time call notifications. Including `filter=silent` or similar will suppress call events.

## Event Types

### Call Events

| push_type | Description |
|-----------|-------------|
| `BNC1-rtc` | WebRTC call offer (contains SDP for video/audio) or terminate/rescind |
| `BNC1-incoming_call` | Doorbell ring notification (contains snapshot and vignette URLs) |
| `BNC1-accepted_call` | Call answered by a device |
| `BNC1-missed_call` | Call not answered (timeout, typically after ~30 seconds) |
| `BNC1-end_recording` | Call recording finished (video clip saved to cloud) |

### Connection Events

| push_type | Description |
|-----------|-------------|
| `BNC1-connection` | Bridge came online |
| `BNC1-disconnection` | Bridge went offline |

### Other Events

| push_type | Description |
|-----------|-------------|
| `new_user` | New user invited to the home |

## Event Structures

### RTC Offer (Incoming Call)

Received when the doorbell is pressed. Contains the device's SDP offer for WebRTC video/audio.

```json
{
    "type": "Websocket",
    "push_type": "BNC1-rtc",
    "category": "rtc",
    "voip_call": true,
    "expiry": 30,
    "extra_params": {
        "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "tag_id": "dGFnX2lkX2Jhc2U2NF9lbmNvZGVk",
        "correlation_id": 987654321,
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

The `extra_params` contain session identifiers needed for answering the call via the signaling WebSocket. See [WebRTC Signaling -- Answer Mode](webrtc-signaling.md#answer-mode-incoming-call) for the full flow.

### Incoming Call (with Snapshot)

Received alongside the RTC offer. Contains URLs for the snapshot and vignette images captured at the moment of the ring.

```json
{
    "type": "Websocket",
    "push_type": "BNC1-incoming_call",
    "category": "incoming_call",
    "extra_params": {
        "event_type": "incoming_call",
        "device_id": "00:03:50:xx:xx:xx",
        "home_id": "home_id_string",
        "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "snapshot_url": "https://netatmocameraimage.blob.core.windows.net/...",
        "vignette_url": "https://netatmocameraimage.blob.core.windows.net/..."
    }
}
```

The image URLs are time-limited (typically valid for several hours). The `snapshot_url` is a full-resolution image and `vignette_url` is a smaller thumbnail.

### Accepted Call

Received when the call is answered by any device (physical handset, app, or another client).

```json
{
    "type": "Websocket",
    "push_type": "BNC1-accepted_call",
    "category": "accepted_call",
    "extra_params": {
        "event_type": "accepted_call",
        "device_id": "00:03:50:xx:xx:xx",
        "home_id": "home_id_string",
        "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    }
}
```

### Missed Call

Received when the call times out without being answered (approximately 30 seconds after the ring).

```json
{
    "type": "Websocket",
    "push_type": "BNC1-missed_call",
    "category": "missed_call",
    "extra_params": {
        "event_type": "missed_call",
        "device_id": "00:03:50:xx:xx:xx",
        "home_id": "home_id_string",
        "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "snapshot_url": "https://netatmocameraimage.blob.core.windows.net/...",
        "vignette_url": "https://netatmocameraimage.blob.core.windows.net/..."
    }
}
```

### End Recording

Received when the device finishes recording a call video clip.

```json
{
    "type": "Websocket",
    "push_type": "BNC1-end_recording",
    "category": "end_recording",
    "extra_params": {
        "event_type": "end_recording",
        "device_id": "00:03:50:xx:xx:xx",
        "home_id": "home_id_string"
    }
}
```

### Terminate / Rescind

Terminate indicates the call session has ended. Rescind indicates the call was answered by another device (your client should stop ringing).

**Terminate:**

```json
{
    "type": "Websocket",
    "push_type": "BNC1-rtc",
    "extra_params": {
        "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "data": {
            "type": "terminate"
        }
    }
}
```

**Rescind:**

```json
{
    "type": "Websocket",
    "push_type": "BNC1-rtc",
    "extra_params": {
        "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "data": {
            "type": "rescind"
        }
    }
}
```

### Connection / Disconnection

```json
{
    "type": "Websocket",
    "push_type": "BNC1-connection",
    "extra_params": {
        "event_type": "connection",
        "device_id": "00:03:50:xx:xx:xx",
        "home_id": "home_id_string",
        "camera_id": "00:03:50:xx:xx:xx",
        "home_name": "My Home"
    }
}
```

Disconnection events have the same structure with `push_type: "BNC1-disconnection"` and `event_type: "disconnection"`.

## Keeping the Connection Alive

The connection may drop when the OAuth token expires (~1 hour). Use `resubscribe()` to send a fresh token without disconnecting:

```python
# Every hour
await ws_client.resubscribe()
```

The push WebSocket does **not** use application-level ping/pong messages. The official app relies on TCP keepalive. Sending WebSocket pings can cause the server to drop the connection after approximately 10 minutes.
