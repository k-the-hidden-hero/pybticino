# pybticino

A Python library for interacting with the BTicino/Netatmo API (based on reverse-engineered logs).

**Disclaimer:** This library is based on unofficial observations of the Netatmo API used by BTicino devices. API endpoints, parameters, and responses may change without notice. Use at your own risk.

## Installation

```bash
# TODO: Add installation instructions once published or ready for local install
# pip install .
```

## Basic Usage

```python
import asyncio
import logging
from pybticino import AuthHandler, AsyncAccount, ApiError, AuthError

# Configure logging (optional)
logging.basicConfig(level=logging.INFO)

# Replace with your actual credentials
USERNAME = "your_email@example.com"
PASSWORD = "your_password"

async def main():
    auth = None
    try:
        # 1. Create AuthHandler
        auth = AuthHandler(USERNAME, PASSWORD)
        
        # 2. Create AsyncAccount (manages authentication automatically)
        account = AsyncAccount(auth)

        # 3. Get Homes Data and populate models
        print("Fetching homes data...")
        await account.async_update_topology()
        print(f"Found {len(account.homes)} homes.")
        
        # Access structured home data
        for home_id, home in account.homes.items():
            print(f"Home: {home.name} (ID: {home_id})")
            print(f"  Modules: {len(home.modules)}")
            
            # 4. Get Home Status
            print(f"\nFetching status for home {home_id}...")
            status = await account.async_get_home_status(home_id)
            
            # 5. Get Events
            print(f"Fetching recent events...")
            events = await account.async_get_events(home_id, size=5)
            
            # 6. Example: Control a device (Use with caution!)
            # for module in home.modules:
            #     if module.type == 'BNDL':  # Door lock
            #         print(f"Unlocking {module.name}...")
            #         result = await account.async_set_module_state(
            #             home_id, module.id, {'lock': False}
            #         )
            #         print(f"Result: {result}")
            #         break

    except AuthError as e:
        print(f"Authentication Error: {e}")
    except ApiError as e:
        print(f"API Error: Status={e.status_code}, Message={e.error_message}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    finally:
        # Clean up session
        if auth:
            await auth.close_session()

# Run the async main function
if __name__ == "__main__":
    asyncio.run(main())
```

### WebSocket Usage (Real-time notifications)

```python
import asyncio
from pybticino import AuthHandler, WebsocketClient

async def handle_message(message):
    """Handle incoming WebSocket messages"""
    print(f"Received: {message}")
    # Process different message types here

async def websocket_example():
    auth = AuthHandler("your_email@example.com", "your_password")
    
    # Create WebSocket client with message handler
    ws_client = WebsocketClient(auth, handle_message)
    
    try:
        # Connect and run forever (with auto-reconnection)
        await ws_client.run_forever(reconnect_delay=30)
    except KeyboardInterrupt:
        print("Stopping WebSocket client...")
    finally:
        await ws_client.disconnect()
        await auth.close_session()

if __name__ == "__main__":
    asyncio.run(websocket_example())
```

## Features

*   Authentication via username/password (OAuth2 Password Grant)
*   Get Homes Data (`/api/homesdata`)
*   Get Home Status (`/syncapi/v1/homestatus`)
*   Set Module State (`/syncapi/v1/setstate`)
*   Get Events (`/api/getevents`)

## TODO

*   ~~Implement token refresh logic.~~ ✅
*   ~~Implement handling for WebSocket connections.~~ ✅ 
*   ~~Implement proper data models (`models.py`).~~ ✅ 
*   ~~Refine `set_module_state` to handle bridge IDs reliably.~~ ✅ 
*   Enhance WebSocket integration with main API client for real-time state updates
*   Add event-driven model updates from WebSocket messages
*   Add methods for remaining API endpoints found in logs
*   Add comprehensive unit tests
*   Improve error handling and documentation

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.
