===============
Getting Started
===============

This guide provides a basic walkthrough of using `pybticino` to interact with your BTicino/Netatmo devices.

Core Concepts
-------------

1.  **Authentication (`AuthHandler`)**: You first need to authenticate with your BTicino/Netatmo account credentials to obtain API tokens. The `AuthHandler` class manages this process, including token refreshing.
2.  **Account Interaction (`AsyncAccount`)**: Once authenticated, you use the `AsyncAccount` class, passing it the `AuthHandler` instance. This class provides methods to fetch information about your homes and modules, get their status, and control them.
3.  **Asynchronous Operations**: The library is built using `asyncio` and `aiohttp`, meaning most operations (API calls) are asynchronous and need to be awaited.

Basic Example
-------------

The following example demonstrates the fundamental workflow:

.. code-block:: python

    import asyncio
    import logging
    import os
    from pybticino import AuthHandler, AsyncAccount, ApiError, AuthError

    # Configure logging (optional but helpful for debugging)
    logging.basicConfig(level=logging.INFO)
    _LOGGER = logging.getLogger(__name__)

    async def main():
        # Replace with your actual credentials (consider using environment variables)
        USERNAME = os.environ.get("BTICINO_USERNAME", "your_email@example.com")
        PASSWORD = os.environ.get("BTICINO_PASSWORD", "your_password")

        if USERNAME == "your_email@example.com" or PASSWORD == "your_password":
            _LOGGER.error("Please set BTICINO_USERNAME and BTICINO_PASSWORD environment variables or replace placeholders.")
            return

        auth_handler = None
        try:
            # 1. Initialize Authentication Handler
            # It's recommended to manage the session externally if making multiple calls
            # or using the WebsocketClient simultaneously.
            # For simplicity here, AuthHandler manages its own session.
            auth_handler = AuthHandler(USERNAME, PASSWORD)

            # 2. Initialize Account Client
            account = AsyncAccount(auth_handler)

            # 3. Fetch Home Topology (Homes and Modules)
            _LOGGER.info("Fetching topology...")
            await account.async_update_topology()
            _LOGGER.info(f"User: {account.user}")
            _LOGGER.info(f"Found {len(account.homes)} homes.")

            if not account.homes:
                _LOGGER.warning("No homes found for this account.")
                return

            # Get the first home ID (replace with specific ID if needed)
            home_id = list(account.homes.keys())[0]
            home = account.homes[home_id]
            _LOGGER.info(f"Using Home: {home.name} ({home.id})")
            _LOGGER.info(f"Modules in this home: {[m.name for m in home.modules]}")

            # 4. Get Home Status
            _LOGGER.info(f"Fetching status for home {home_id}...")
            # Note: This currently returns raw data. You might need to parse it.
            home_status = await account.async_get_home_status(home_id)
            _LOGGER.info(f"Home status retrieved. Found {len(home_status.get('body', {}).get('home', {}).get('modules', []))} modules in status.")
            # print(home_status) # Uncomment to see full status

            # 5. Get Events
            _LOGGER.info(f"Fetching events for home {home_id}...")
            # Note: This currently returns raw data.
            events = await account.async_get_events(home_id=home_id, size=5) # Get last 5 events
            _LOGGER.info(f"Retrieved {len(events.get('body', {}).get('home', {}).get('events', []))} events.")
            # print(events) # Uncomment to see full events

            # 6. Example: Set State (Use with extreme caution!)
            # Find a module ID to control (e.g., a door lock 'BNDL')
            # module_to_unlock = None
            # for module in home.modules:
            #     if module.type == 'BNDL': # Example: Find a door lock
            #         module_to_unlock = module
            #         _LOGGER.info(f"Found door lock module: {module_to_unlock.name} ({module_to_unlock.id})")
            #         break
            #
            # if module_to_unlock:
            #     try:
            #         _LOGGER.info(f"Attempting to unlock module {module_to_unlock.id}...")
            #         # Ensure you know the correct state key (e.g., 'lock') and value type
            #         # The 'bridge' parameter might be needed depending on the module
            #         result = await account.async_set_module_state(
            #             home_id=home_id,
            #             module_id=module_to_unlock.id,
            #             state={'lock': False}, # Example state
            #             # bridge_id=module_to_unlock.bridge # May be required
            #         )
            #         _LOGGER.info(f"Set state result: {result}")
            #     except ApiError as e:
            #         _LOGGER.error(f"Error setting state: {e}")
            #     except ValueError as e:
            #          _LOGGER.error(f"Value error setting state: {e}")


        except AuthError as e:
            _LOGGER.error(f"Authentication Error: {e}")
        except ApiError as e:
            _LOGGER.error(f"API Error: Status={e.status_code}, Message={e.error_message}")
        except Exception as e:
            _LOGGER.exception(f"An unexpected error occurred: {e}")
        finally:
            # Clean up the session if AuthHandler created it
            if auth_handler:
                await auth_handler.close_session()
                _LOGGER.info("AuthHandler session closed.")

    if __name__ == "__main__":
        asyncio.run(main())

Next Steps
----------

*   Explore the :doc:`authentication` guide for more details on `AuthHandler`.
*   Dive deeper into the :doc:`api_client` guide to understand `AsyncAccount` methods.
*   Learn about real-time updates in the :doc:`websockets` guide.
*   Consult the :doc:`api_reference` for detailed class and method signatures.
