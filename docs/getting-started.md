# Getting Started

## Installation

```bash
pip install pybticino
```

## Basic usage

```python
import asyncio
from pybticino import AuthHandler, AsyncAccount

async def main():
    auth = AuthHandler("your_email@example.com", "your_password")
    account = AsyncAccount(auth)

    # Fetch home topology
    await account.async_update_topology()

    for home_id, home in account.homes.items():
        print(f"Home: {home.name} ({len(home.modules)} modules)")

        # Get module status
        status = await account.async_get_home_status(home_id)

        # Get recent events
        events = await account.async_get_events(home_id, size=5)

        # Control a door lock
        for module in home.modules:
            if module.type == "BNDL":
                await account.async_set_module_state(
                    home_id=home_id,
                    module_id=module.id,
                    bridge_id=module.bridge,
                    state={"lock": False},
                    timezone="Europe/Rome",
                )
                break

    await auth.close_session()

asyncio.run(main())
```

## WebSocket (real-time events)

```python
import asyncio
from pybticino import AuthHandler, WebsocketClient

async def on_message(message):
    push_type = message.get("push_type", "unknown")
    print(f"Event: {push_type}")

async def main():
    auth = AuthHandler("your_email@example.com", "your_password")
    ws = WebsocketClient(auth, on_message)

    await ws.connect()

    # Listen until interrupted
    task = ws.get_listener_task()
    if task:
        try:
            await task
        except KeyboardInterrupt:
            pass

    await ws.disconnect()
    await auth.close_session()

asyncio.run(main())
```

## Token persistence

Save and restore tokens to avoid re-authenticating on every startup:

```python
def on_token_change(token_data):
    # Save to file, database, etc.
    save_tokens(token_data)

auth = AuthHandler(
    "email@example.com",
    "password",
    token_callback=on_token_change,
)

# Restore saved tokens
saved = load_tokens()
if saved:
    auth.set_tokens(
        access_token=saved["access_token"],
        refresh_token=saved["refresh_token"],
        expires_at=saved["expires_at"],
    )
```
