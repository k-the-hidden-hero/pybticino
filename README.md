# pybticino

[![PyPI](https://img.shields.io/pypi/v/pybticino)](https://pypi.org/project/pybticino/)
[![CI](https://github.com/k-the-hidden-hero/pybticino/actions/workflows/ci.yaml/badge.svg)](https://github.com/k-the-hidden-hero/pybticino/actions/workflows/ci.yaml)
[![Python](https://img.shields.io/pypi/pyversions/pybticino)](https://pypi.org/project/pybticino/)
[![License](https://img.shields.io/github/license/k-the-hidden-hero/pybticino)](LICENSE.txt)

Async Python library for the BTicino/Netatmo API. Controls BTicino Classe 100X/300X video intercom systems via the Netatmo cloud.

Used by the [bticino_intercom](https://github.com/k-the-hidden-hero/bticino_intercom) Home Assistant integration.

## Installation

```bash
pip install pybticino
```

Requires Python 3.13 or later.

## Features

- **Authentication**: OAuth2 password grant with automatic token refresh and persistence support
- **Home topology**: fetch homes, modules, and their configuration
- **Device control**: lock/unlock doors, turn lights on/off
- **Events**: fetch call history with snapshots and vignettes
- **WebSocket**: real-time push notifications (call events, connection status, state changes)
- **Re-subscribe**: refresh OAuth token on existing connection without reconnecting
- **WebRTC signaling**: offer/answer/ICE exchange for live video calls (experimental)

## Quick start

```python
import asyncio
from pybticino import AuthHandler, AsyncAccount

async def main():
    auth = AuthHandler("your_email@example.com", "your_password")
    account = AsyncAccount(auth)

    await account.async_update_topology()
    for home_id, home in account.homes.items():
        print(f"Home: {home.name} ({len(home.modules)} modules)")

        status = await account.async_get_home_status(home_id)
        events = await account.async_get_events(home_id, size=5)

    await auth.close_session()

asyncio.run(main())
```

## WebSocket (real-time events)

```python
import asyncio
from pybticino import AuthHandler, WebsocketClient

async def on_message(message):
    print(f"Event: {message.get('push_type')} - {message}")

async def main():
    auth = AuthHandler("your_email@example.com", "your_password")
    ws = WebsocketClient(auth, on_message)

    await ws.connect()
    # Listen for events (doorbell rings, connection changes, etc.)
    task = ws.get_listener_task()
    if task:
        await task

    await ws.disconnect()
    await auth.close_session()

asyncio.run(main())
```

### Re-subscribe (keep connection alive)

```python
# Refresh token on existing connection without disconnecting
await ws.resubscribe()
```

## API endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `async_update_topology()` | `/api/homesdata` | Fetch homes and modules |
| `async_get_home_status(home_id)` | `/syncapi/v1/homestatus` | Get module status |
| `async_set_module_state(home_id, module_id, state)` | `/syncapi/v1/setstate` | Control devices |
| `async_get_events(home_id, size)` | `/api/getevents` | Get event history |

## WebSocket event types

Events are delivered with `push_type` in format `{DEVICE_TYPE}-{EVENT_TYPE}`:

| push_type | Description |
|-----------|-------------|
| `BNC1-rtc` | Incoming WebRTC call (with SDP offer) |
| `BNC1-incoming_call` | Doorbell ring (with snapshot URL) |
| `BNC1-missed_call` | Unanswered call |
| `BNC1-accepted_call` | Call answered |
| `BNC1-connection` | Bridge connected |
| `BNC1-disconnection` | Bridge disconnected |

## Documentation

Full documentation at **[k-the-hidden-hero.github.io/pybticino](https://k-the-hidden-hero.github.io/pybticino/)**

Key guides from reverse engineering:

- **[WebRTC Signaling Protocol](https://k-the-hidden-hero.github.io/pybticino/webrtc-signaling/)** — complete offer/answer/ICE flow, message formats, session state, two call modes
- **[WebRTC Audio Mechanism](https://k-the-hidden-hero.github.io/pybticino/webrtc-audio/)** — how to activate the device microphone (requires real RTP audio packets)
- **[WebSocket Events](https://k-the-hidden-hero.github.io/pybticino/websocket-events/)** — all push notification types and their JSON structures
- **[Reverse Engineering Notes](https://k-the-hidden-hero.github.io/pybticino/reverse-engineering-notes/)** — findings from decompiling the official BTicino/Netatmo app

### Examples

Working example scripts in [`examples/`](examples/):

| Script | Description |
|--------|-------------|
| [`webrtc_offer_mode.py`](examples/webrtc_offer_mode.py) | On-demand video: send offer → receive answer → ICE → connected |
| [`webrtc_answer_mode.py`](examples/webrtc_answer_mode.py) | Answer incoming call: wait for doorbell → answer via signaling |
| [`webrtc_audio_test.html`](examples/webrtc_audio_test.html) | Browser-based audio test with silence oscillator |
| [`websocket_test.py`](examples/websocket_test.py) | Real-time push notification listener |

## Related projects

- [bticino_intercom](https://github.com/k-the-hidden-hero/bticino_intercom) — Home Assistant custom integration
- [bticino_ha_extras](https://github.com/k-the-hidden-hero/bticino_ha_extras) — Blueprints, Lovelace cards, and companion resources

## Contributing

```bash
pip install -e ".[test,dev]"
pytest tests/ -v
ruff check src/ tests/
```

## License

MIT
