#!/usr/bin/env python3

"""Example script to unlock a specific door lock (BNDL module) using the async pybticino library.

Reads credentials (BTICINOUSER, BTICINOPASSWORD) and the target home ID
(BTICINOHOMEID) from environment variables.

Requires the target door lock module ID as a command-line argument.

Usage:
  export BTICINOUSER="your_email"
  export BTICINOPASSWORD="your_password"
  export BTICINOHOMEID="your_home_id"
  python3 unlock_door.py <door_lock_module_id>
"""

import argparse
import asyncio
import logging
import os
import sys
from typing import Optional  # Import Optional

# Import new async classes
from pybticino import ApiError, AsyncAccount, AuthError, AuthHandler, Module

# --- Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

# Read credentials and home ID from environment variables
USERNAME = os.getenv("BTICINOUSER")
PASSWORD = os.getenv("BTICINOPASSWORD")
HOME_ID = os.getenv("BTICINOHOMEID")

if not all([USERNAME, PASSWORD, HOME_ID]):
    logging.error(
        "Please set BTICINOUSER, BTICINOPASSWORD, and BTICINOHOMEID environment variables.",
    )
    sys.exit(1)

# --- Argument Parsing ---
parser = argparse.ArgumentParser(description="Unlock a BTicino/Netatmo door lock.")
parser.add_argument(
    "module_id",
    help="The ID of the BNDL module (door lock) to unlock.",
)
args = parser.parse_args()
MODULE_ID_TO_UNLOCK = args.module_id


# --- Main Async Function ---
async def main() -> None:
    """Run the async unlock script."""
    logging.info(
        "Attempting to unlock module ID: %s in home ID: %s",
        MODULE_ID_TO_UNLOCK,
        HOME_ID,
    )
    auth = None  # Initialize for finally block
    # Ensure credentials and HOME_ID are not None before proceeding
    if not USERNAME or not PASSWORD or not HOME_ID:
        logging.error(
            "USERNAME, PASSWORD, or HOME_ID is None. Check environment variables.",
        )
        sys.exit(1)
    try:
        # 1. Create AuthHandler and AsyncAccount
        logging.info("Creating AuthHandler and AsyncAccount...")
        auth = AuthHandler(USERNAME, PASSWORD)
        account = AsyncAccount(auth)
        logging.info("Authentication will occur on first API call.")

        # 2. Get Home Data to find timezone and bridge ID
        logging.info(
            "Fetching topology for home %s to get timezone and bridge ID...",
            HOME_ID,
        )
        # This call implicitly authenticates if needed
        await account.async_update_topology()

        home_obj = account.homes.get(HOME_ID)

        if not home_obj:
            logging.error(
                "Could not find home with ID %s after topology update.",
                HOME_ID,
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
            logging.error(
                "Module %s not found in home %s.",
                MODULE_ID_TO_UNLOCK,
                HOME_ID,
            )
            sys.exit(1)

        if module_details.type != "BNDL":
            logging.error(
                "Module %s is not a Door Lock (BNDL), it is type '%s'. Aborting.",
                MODULE_ID_TO_UNLOCK,
                module_details.type,
            )
            sys.exit(1)

        if not home_timezone:
            logging.warning(
                "Could not determine timezone for the home. Proceeding without it, but this might fail.",
            )
        if not bridge_id:
            logging.error(
                "Could not determine bridge ID (BNC1) for the home. Cannot send command to bridged module.",
            )
            sys.exit(1)

        logging.info("Found target module: Name='%s', Type='BNDL'", module_details.name)
        logging.info("Using Bridge ID: %s", bridge_id)
        logging.info("Using Timezone: %s", home_timezone)

        # 3. Call async_set_module_state to unlock
        logging.info(
            "Sending unlock command (lock=False) to module %s...",
            MODULE_ID_TO_UNLOCK,
        )
        result = await account.async_set_module_state(
            home_id=HOME_ID,
            module_id=MODULE_ID_TO_UNLOCK,
            state={"lock": False},  # The command to unlock
            timezone=home_timezone,
            bridge_id=bridge_id,
        )
        logging.info("Set state command sent. Result: %s", result)
        logging.info(
            "Door lock %s should be unlocked (it might re-lock automatically).",
            MODULE_ID_TO_UNLOCK,
        )

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
        # Ensure the session is closed
        if auth:
            await auth.close_session()
            logging.info("Auth session closed.")


if __name__ == "__main__":
    asyncio.run(main())
