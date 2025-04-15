#!/usr/bin/env python3

"""
Example script to unlock a specific door lock (BNDL module) using the async pybticino library.

Reads credentials (BTICINOUSER, BTICINOPASSWORD) and the target home ID
(BTICINOHOMEID) from environment variables.

Requires the target door lock module ID as a command-line argument.

Usage:
  export BTICINOUSER="your_email"
  export BTICINOPASSWORD="your_password"
  export BTICINOHOMEID="your_home_id"
  python3 unlock_door.py <door_lock_module_id>
"""

import asyncio
import logging
import json
import os
import argparse
import sys
from typing import Optional  # Import Optional

# Import new async classes
from pybticino import (
    AuthHandler,
    AsyncAccount,
    ApiError,
    AuthError,
    Home,
    Module,
)

# --- Configuration ---
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# Read credentials and home ID from environment variables
USERNAME = os.getenv("BTICINOUSER")
PASSWORD = os.getenv("BTICINOPASSWORD")
HOME_ID = os.getenv("BTICINOHOMEID")

if not all([USERNAME, PASSWORD, HOME_ID]):
    logging.error(
        "Please set BTICINOUSER, BTICINOPASSWORD, and BTICINOHOMEID environment variables."
    )
    sys.exit(1)

# --- Argument Parsing ---
parser = argparse.ArgumentParser(description="Unlock a BTicino/Netatmo door lock.")
parser.add_argument(
    "module_id", help="The ID of the BNDL module (door lock) to unlock."
)
args = parser.parse_args()
MODULE_ID_TO_UNLOCK = args.module_id


# --- Main Async Function ---
async def main():
    """Run the async unlock script."""
    logging.info(
        f"Attempting to unlock module ID: {MODULE_ID_TO_UNLOCK} in home ID: {HOME_ID}"
    )
    auth = None  # Initialize for finally block
    try:
        # 1. Create AuthHandler and AsyncAccount
        logging.info("Creating AuthHandler and AsyncAccount...")
        auth = AuthHandler(USERNAME, PASSWORD)
        account = AsyncAccount(auth)
        logging.info("Authentication will occur on first API call.")

        # 2. Get Home Data to find timezone and bridge ID
        logging.info(
            f"Fetching topology for home {HOME_ID} to get timezone and bridge ID..."
        )
        # This call implicitly authenticates if needed
        await account.async_update_topology()

        home_obj = account.homes.get(HOME_ID)

        if not home_obj:
            logging.error(
                f"Could not find home with ID {HOME_ID} after topology update."
            )
            sys.exit(1)

        home_timezone = home_obj.raw_data.get("timezone")  # Access raw_data for now
        bridge_id = None
        module_details: Optional[Module] = None  # Use Module model

        for module in home_obj.modules:
            if module.type == "BNC1":  # Assuming BNC1 is the bridge
                bridge_id = module.id
            if module.id == MODULE_ID_TO_UNLOCK:
                module_details = module

        if not module_details:
            logging.error(f"Module {MODULE_ID_TO_UNLOCK} not found in home {HOME_ID}.")
            sys.exit(1)

        if module_details.type != "BNDL":
            logging.error(
                f"Module {MODULE_ID_TO_UNLOCK} is not a Door Lock (BNDL), it is type '{module_details.type}'. Aborting."
            )
            sys.exit(1)

        if not home_timezone:
            logging.warning(
                "Could not determine timezone for the home. Proceeding without it, but this might fail."
            )
        if not bridge_id:
            logging.error(
                "Could not determine bridge ID (BNC1) for the home. Cannot send command to bridged module."
            )
            sys.exit(1)

        logging.info(f"Found target module: Name='{module_details.name}', Type='BNDL'")
        logging.info(f"Using Bridge ID: {bridge_id}")
        logging.info(f"Using Timezone: {home_timezone}")

        # 3. Call async_set_module_state to unlock
        logging.info(
            f"Sending unlock command (lock=False) to module {MODULE_ID_TO_UNLOCK}..."
        )
        result = await account.async_set_module_state(
            home_id=HOME_ID,
            module_id=MODULE_ID_TO_UNLOCK,
            state={"lock": False},  # The command to unlock
            timezone=home_timezone,
            bridge_id=bridge_id,
        )
        logging.info(f"Set state command sent. Result: {result}")
        logging.info(
            f"Door lock {MODULE_ID_TO_UNLOCK} should be unlocked (it might re-lock automatically)."
        )

    except AuthError as e:
        logging.error(f"Authentication Error: {e}")
    except ApiError as e:
        logging.error(f"API Error: Status={e.status_code}, Message={e.error_message}")
    except Exception as e:
        logging.exception(f"An unexpected error occurred: {e}")
    finally:
        # Ensure the session is closed
        if auth:
            await auth.close_session()
            logging.info("Auth session closed.")


if __name__ == "__main__":
    asyncio.run(main())
