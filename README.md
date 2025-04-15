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
import logging
from pybticino import AuthHandler, ApiClient, ApiError, AuthError

# Configure logging (optional)
logging.basicConfig(level=logging.INFO)

# Replace with your actual credentials
USERNAME = "your_email@example.com"
PASSWORD = "your_password"

try:
    # 1. Authenticate
    auth = AuthHandler(USERNAME, PASSWORD)
    # The first call to auth.access_token will trigger authentication
    print(f"Access Token obtained: {auth.access_token[:10]}...") # Print truncated token

    # 2. Create API Client
    client = ApiClient(auth)

    # 3. Get Homes Data
    print("\nFetching homes data...")
    homes_data = client.get_homes_data()
    print(f"Found {len(homes_data.get('body', {}).get('homes', []))} homes.")

    # Example: Get the first home ID
    home_id = None
    if homes_data.get('body', {}).get('homes'):
        home_id = homes_data['body']['homes'][0]['id']
        print(f"Using Home ID: {home_id}")

        # 4. Get Home Status (if home_id found)
        print(f"\nFetching status for home {home_id}...")
        home_status = client.get_home_status(home_id)
        print(f"Home status retrieved. Found {len(home_status.get('body', {}).get('home', {}).get('modules', []))} modules.")
        # print(home_status) # Uncomment to see full status

        # 5. Get Events (if home_id found)
        print(f"\nFetching events for home {home_id}...")
        events = client.get_events(home_id=home_id, size=5) # Get last 5 events
        print(f"Retrieved {len(events.get('body', {}).get('home', {}).get('events', []))} events.")
        # print(events) # Uncomment to see full events

        # 6. Example: Set State (Use with caution!)
        # Find a module ID to control (e.g., a door lock 'BNDL')
        # module_to_unlock_id = None
        # if home_status.get('body', {}).get('home', {}).get('modules'):
        #     for module in home_status['body']['home']['modules']:
        #         if module.get('type') == 'BNDL': # Example: Find a door lock
        #              module_to_unlock_id = module.get('id')
        #              print(f"\nFound door lock module: {module_to_unlock_id}")
        #              break
        #
        # if module_to_unlock_id:
        #     try:
        #         print(f"Attempting to unlock module {module_to_unlock_id}...")
        #         # Ensure you know the correct state key (e.g., 'lock')
        #         result = client.set_module_state(home_id, module_to_unlock_id, {'lock': False})
        #         print(f"Set state result: {result}")
        #     except ApiError as e:
        #         print(f"Error setting state: {e}")


except AuthError as e:
    print(f"Authentication Error: {e}")
except ApiError as e:
    print(f"API Error: Status={e.status_code}, Message={e.error_message}")
except Exception as e:
    print(f"An unexpected error occurred: {e}")

```

## Features

*   Authentication via username/password (OAuth2 Password Grant)
*   Get Homes Data (`/api/homesdata`)
*   Get Home Status (`/syncapi/v1/homestatus`)
*   Set Module State (`/syncapi/v1/setstate`)
*   Get Events (`/api/getevents`)

## TODO

*   Implement token refresh logic.
*   Implement handling for WebSocket connections.
*   Add methods for remaining API endpoints found in logs.
*   Implement proper data models (`models.py`).
*   Add comprehensive unit tests.
*   Improve error handling and documentation.
*   Refine `set_module_state` to handle bridge IDs reliably.

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.
