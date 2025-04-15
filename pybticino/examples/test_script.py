#!/usr/bin/env python3

"""Example script to test the refactored async pybticino library."""

import asyncio
import asyncio
import logging
import json  # To pretty-print JSON output
import os  # Import os module to access environment variables
import aiohttp  # Needed for session management indirectly via AuthHandler
from typing import Optional  # Import Optional

# Import new async classes and exceptions
from pybticino import (
    AuthHandler,
    AsyncAccount,
    ApiError,
    AuthError,
    Home,  # Import models if needed for type hints or direct use
    Module,
)

# --- Configuration ---
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# Read credentials from environment variables, fallback to placeholders
USERNAME = os.getenv("BTICINOUSER", "YOUR_EMAIL@example.com")
PASSWORD = os.getenv("BTICINOPASSWORD", "YOUR_PASSWORD")

if USERNAME == "YOUR_EMAIL@example.com" or PASSWORD == "YOUR_PASSWORD":
    logging.error(
        "Please set BTICINOUSER and BTICINOPASSWORD environment variables or update placeholders in the script."
    )
    exit(1)

# Read optional target home ID from environment variable
TARGET_HOME_ID = os.getenv("BTICINOHOMEID", None)


# --- Main Async Function ---
async def main():
    """Run the example test using the async library."""
    logging.info("Starting async pybticino example script...")
    auth = None  # Initialize auth to None for finally block
    try:
        # 1. Create AuthHandler (session managed internally by default)
        logging.info("Creating AuthHandler...")
        auth = AuthHandler(USERNAME, PASSWORD)

        # 2. Create AsyncAccount Client
        # No need to explicitly get token here, get_access_token will be called internally
        account = AsyncAccount(auth)
        logging.info("AsyncAccount created.")

        # 3. Get Homes Data (now called async_update_topology)
        logging.info("Fetching homes data (async_update_topology)...")
        await account.async_update_topology()
        logging.info("Homes data received and processed.")

        # Access homes via the account object
        homes = account.homes  # Dictionary of Home objects keyed by ID
        logging.info(f"Found {len(homes)} homes:")
        i = 0
        for home_id, home_obj in homes.items():
            i += 1
            logging.info(f"  {i}. Name: '{home_obj.name}', ID: {home_id}")
            # You can also access modules directly: logging.info(f"    Modules: {[m.name for m in home_obj.modules]}")

        if not homes:
            logging.warning("No homes found for this account.")
            return

        selected_home_obj: Optional[Home] = None
        selected_home_id: Optional[str] = None

        if TARGET_HOME_ID:
            logging.info(f"Attempting to use specified Home ID: {TARGET_HOME_ID}")
            selected_home_obj = homes.get(TARGET_HOME_ID)
            if not selected_home_obj:
                logging.error(
                    f"Specified Home ID {TARGET_HOME_ID} not found in account."
                )
                logging.error(f"Valid Home IDs found: {list(homes.keys())}")
                return
            selected_home_id = TARGET_HOME_ID
        else:
            logging.info("No specific Home ID specified, using the first home found.")
            # Get the first home from the dictionary
            selected_home_id = next(iter(homes))
            selected_home_obj = homes[selected_home_id]

        home_name = selected_home_obj.name
        logging.info(f"Using Home: Name='{home_name}', ID='{selected_home_id}'")

        # Extract timezone and module names/bridge from the processed Home object
        # Note: timezone might not be directly on Home model yet, access raw_data if needed
        home_timezone = selected_home_obj.raw_data.get("timezone")
        bridge_id = None
        module_names = {}
        for module in selected_home_obj.modules:
            module_names[module.id] = module.name
            if module.type == "BNC1":  # Assuming BNC1 is the bridge
                bridge_id = module.id
                logging.debug(f"Found bridge module: ID={bridge_id}")

        logging.debug(f"Extracted module names: {module_names}")
        logging.debug(f"Extracted home timezone: {home_timezone}")

        # 4. Get Home Status
        logging.info(f"Fetching status for home ID: {selected_home_id}...")
        # Note: async_get_home_status currently returns raw data, needs processing
        home_status_raw = await account.async_get_home_status(home_id=selected_home_id)
        logging.info("Home status received.")
        # Process the raw status data (similar to before, but ideally update models)
        modules_status = (
            home_status_raw.get("body", {}).get("home", {}).get("modules", [])
        )
        logging.info(
            f"Found {len(modules_status)} modules in status for home '{home_name}':"
        )
        if modules_status:
            for module_status_data in modules_status:
                mod_id = module_status_data.get("id", "N/A")
                mod_name = module_names.get(
                    mod_id, "Unknown Name"
                )  # Use name from topology
                mod_type = module_status_data.get("type", "Unknown Type")
                logging.info(
                    f"  - Module Name: '{mod_name}', ID: {mod_id}, Type: {mod_type}"
                )
                # TODO: Update the corresponding Module object in selected_home_obj.modules
        else:
            logging.info("  (No modules listed in the status response for this home)")

        # 5. Get Events
        logging.info(f"Fetching latest 5 events for home ID: {selected_home_id}...")
        # Note: async_get_events currently returns raw data
        events_data_raw = await account.async_get_events(
            home_id=selected_home_id, size=5
        )
        logging.info("Events data received.")
        events_list = events_data_raw.get("body", {}).get("home", {}).get("events", [])
        logging.info(f"Retrieved {len(events_list)} events.")
        # TODO: Process events_list into Event objects

        # 6. Example: Set State (Demonstration - commented out by default)
        # module_to_control_id = None
        # module_type = None
        # # Find module in the status data or topology data
        # for module_status in modules_status: # Or iterate selected_home_obj.modules
        #     if module_status.get('type') == 'BNDL':
        #         module_to_control_id = module_status.get('id')
        #         module_type = 'BNDL'
        #         logging.info(f"Found example module to control (Door Lock): ID='{module_to_control_id}'")
        #         break
        #
        # if module_to_control_id and module_type == 'BNDL':
        #     try:
        #         logging.warning(f"Attempting to set state (lock=False) for module {module_to_control_id}. Ensure this is intended!")
        #         # Use the async method, provide timezone and bridge_id if known
        #         result = await account.async_set_module_state(
        #             selected_home_id,
        #             module_to_control_id,
        #             {'lock': False},
        #             timezone=home_timezone,
        #             bridge_id=bridge_id
        #         )
        #         logging.info(f"Set state result: {result}")
        #     except ApiError as e:
        #         logging.error(f"Error setting state for module {module_to_control_id}: {e}")
        # else:
        #     logging.info("No suitable module found for set_state example or example disabled.")

    except AuthError as e:
        logging.error(f"Authentication Error: {e}")
    except ApiError as e:
        logging.error(f"API Error: Status={e.status_code}, Message={e.error_message}")
    except Exception as e:
        logging.exception(f"An unexpected error occurred: {e}")  # Use logging.exception
    finally:
        # Ensure the session is closed if AuthHandler created it
        if auth:
            await auth.close_session()
            logging.info("Auth session closed.")


if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())
