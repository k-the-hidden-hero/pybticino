#!/usr/bin/env python3

"""Example script to test the refactored async pybticino library."""

import asyncio
import logging
import os  # Import os module to access environment variables
import sys  # Import sys for sys.exit
from typing import Optional  # Import Optional

# Import new async classes and exceptions
from pybticino import (
    ApiError,
    AsyncAccount,
    AuthError,
    AuthHandler,
    Home,  # Import models if needed for type hints or direct use
)

# --- Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

# Read credentials from environment variables, fallback to placeholders
USERNAME = os.getenv("BTICINOUSER", "YOUR_EMAIL@example.com")
PASSWORD = os.getenv("BTICINOPASSWORD", "YOUR_PASSWORD")

if USERNAME == "YOUR_EMAIL@example.com" or PASSWORD == "YOUR_PASSWORD":  # nosec B105
    logging.error(
        "Please set BTICINOUSER and BTICINOPASSWORD environment variables or update placeholders in the script.",
    )
    sys.exit(1)

# Read optional target home ID from environment variable
TARGET_HOME_ID = os.getenv("BTICINOHOMEID", None)


# --- Main Async Function ---
async def main() -> None:
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
        logging.info("Found %d homes:", len(homes))
        for i, (home_id, home_obj) in enumerate(homes.items(), 1):
            logging.info("  %d. Name: '%s', ID: %s", i, home_obj.name, home_id)
            # You can also access modules directly: logging.info(f"    Modules: {[m.name for m in home_obj.modules]}")

        if not homes:
            logging.warning("No homes found for this account.")
            return

        selected_home_obj: Optional[Home] = None
        selected_home_id: Optional[str] = None

        if TARGET_HOME_ID:
            logging.info("Attempting to use specified Home ID: %s", TARGET_HOME_ID)
            selected_home_obj = homes.get(TARGET_HOME_ID)
            if not selected_home_obj:
                logging.error(
                    "Specified Home ID %s not found in account.",
                    TARGET_HOME_ID,
                )
                logging.error("Valid Home IDs found: %s", list(homes.keys()))
                return
            selected_home_id = TARGET_HOME_ID
        else:
            logging.info("No specific Home ID specified, using the first home found.")
            # Get the first home from the dictionary
            selected_home_id = next(iter(homes))
            selected_home_obj = homes[selected_home_id]

        home_name = selected_home_obj.name
        logging.info("Using Home: Name='%s', ID='%s'", home_name, selected_home_id)

        # Extract timezone and module names/bridge from the processed Home object
        # Note: timezone might not be directly on Home model yet, access raw_data if needed
        home_timezone = selected_home_obj.raw_data.get("timezone")
        bridge_id = None
        module_names = {}
        for module in selected_home_obj.modules:
            module_names[module.id] = module.name
            if module.type == "BNC1":  # Assuming BNC1 is the bridge
                bridge_id = module.id
                logging.debug("Found bridge module: ID=%s", bridge_id)

        logging.debug("Extracted module names: %s", module_names)
        logging.debug("Extracted home timezone: %s", home_timezone)

        # 4. Get Home Status
        logging.info("Fetching status for home ID: %s...", selected_home_id)
        # Note: async_get_home_status currently returns raw data, needs processing
        home_status_raw = await account.async_get_home_status(home_id=selected_home_id)
        logging.info("Home status received.")
        # Process the raw status data (similar to before, but ideally update models)
        modules_status = (
            home_status_raw.get("body", {}).get("home", {}).get("modules", [])
        )
        logging.info(
            "Found %d modules in status for home '%s':",
            len(modules_status),
            home_name,
        )
        if modules_status:
            for module_status_data in modules_status:
                mod_id = module_status_data.get("id", "N/A")
                mod_name = module_names.get(
                    mod_id,
                    "Unknown Name",
                )  # Use name from topology
                mod_type = module_status_data.get("type", "Unknown Type")
                logging.info(
                    "  - Module Name: '%s', ID: %s, Type: %s",
                    mod_name,
                    mod_id,
                    mod_type,
                )
                # Module object update would happen here if implemented
        else:
            logging.info("  (No modules listed in the status response for this home)")

        # 5. Get Events
        logging.info("Fetching latest 5 events for home ID: %s...", selected_home_id)
        # Note: async_get_events currently returns raw data
        events_data_raw = await account.async_get_events(
            home_id=selected_home_id,
            size=5,
        )
        logging.info("Events data received.")
        events_list = events_data_raw.get("body", {}).get("home", {}).get("events", [])
        logging.info("Retrieved %d events.", len(events_list))
        # Event object processing would happen here if implemented

        # 6. Example: Set State (Demonstration - commented out by default)

    except AuthError:
        logging.exception("Authentication Error")
    except ApiError as e:
        logging.exception(
            "API Error: Status=%s, Message=%s",
            e.status_code,
            e.error_message,
        )
    except Exception:
        logging.exception("An unexpected error occurred")
    finally:
        # Ensure the session is closed if AuthHandler created it
        if auth:
            await auth.close_session()
            logging.info("Auth session closed.")


if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())
