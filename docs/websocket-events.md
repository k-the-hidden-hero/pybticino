# WebSocket Events

The Netatmo push WebSocket delivers real-time events with `push_type` in the format `{DEVICE_TYPE}-{EVENT_TYPE}`.

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
    Do not send a `filter` field in the subscribe message. Without it, you receive all events including real-time call notifications.

## Event types

### Call events

| push_type | Description |
|-----------|-------------|
| `BNC1-rtc` | WebRTC call offer (contains SDP for video/audio) |
| `BNC1-incoming_call` | Doorbell ring notification (contains snapshot URL) |
| `BNC1-accepted_call` | Call answered by a device |
| `BNC1-missed_call` | Call not answered (timeout) |
| `BNC1-end_recording` | Call recording finished |

### Connection events

| push_type | Description |
|-----------|-------------|
| `BNC1-connection` | Bridge came online |
| `BNC1-disconnection` | Bridge went offline |

### Other events

| push_type | Description |
|-----------|-------------|
| `new_user` | New user invited to the home |

## Event structure

### RTC offer (call)

```json
{
    "type": "Websocket",
    "push_type": "BNC1-rtc",
    "category": "rtc",
    "voip_call": true,
    "expiry": 30,
    "extra_params": {
        "session_id": "uuid",
        "tag_id": "base64",
        "correlation_id": "number",
        "device_id": "00:03:50:xx:xx:xx",
        "home_id": "home_id",
        "data": {
            "type": "offer",
            "session_description": {
                "type": "call",
                "sdp": "v=0\r\n...",
                "module_id": "calling_unit_id",
                "modules": [...]
            }
        }
    }
}
```

### Incoming call (with snapshot)

```json
{
    "type": "Websocket",
    "push_type": "BNC1-incoming_call",
    "category": "incoming_call",
    "extra_params": {
        "event_type": "incoming_call",
        "device_id": "00:03:50:xx:xx:xx",
        "home_id": "home_id",
        "session_id": "uuid",
        "snapshot_url": "https://netatmocameraimage.blob.core.windows.net/...",
        "vignette_url": "https://netatmocameraimage.blob.core.windows.net/..."
    }
}
```

### Terminate / Rescind

```json
{
    "type": "Websocket",
    "push_type": "BNC1-rtc",
    "extra_params": {
        "session_id": "uuid",
        "data": {
            "type": "terminate"
        }
    }
}
```

`rescind` is sent when the call is answered by another device.

## Keeping the connection alive

The connection may drop when the OAuth token expires (~1 hour). Use `resubscribe()` to send a fresh token without disconnecting:

```python
# Every hour
await ws_client.resubscribe()
```
