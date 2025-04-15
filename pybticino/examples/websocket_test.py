#!/usr/bin/env python3

"""
Example script to test the pybticino WebSocket client for push notifications (async version).

Reads credentials (BTICINOUSER, BTICINOPASSWORD) from environment variables.
Connects to the push notification WebSocket and prints received messages.
Press Ctrl+C to stop.
"""

import asyncio
import json
import logging
import os
import signal  # To handle graceful shutdown
import sys
import argparse
import time
import functools
from typing import Optional, Callable, Awaitable, Any, Dict  # Added Dict

# Import new async classes
from pybticino import (
    AuthHandler,
    AsyncAccount,  # Use AsyncAccount
    WebsocketClient,
    ApiError,
    AuthError,
    PyBticinoException,
)

# --- Configuration ---
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - [%(name)s] %(message)s"
)
# Enable more detailed logging for debugging:
# logging.getLogger("pybticino.websocket").setLevel(logging.DEBUG)
# logging.getLogger("pybticino.auth").setLevel(logging.DEBUG)
# logging.getLogger("pybticino.account").setLevel(logging.DEBUG)
# logging.getLogger("websockets").setLevel(logging.DEBUG)


# --- Fake Data for Simulation ---
FAKE_HOME_ID = "FAKE_HOME_ID_123"
FAKE_MODULE_ID = "00:03:50:d9:a6:3b"
FAKE_USER_ID = "FAKE_USER_ID_456"

# Use current time for fake events
current_time = int(time.time())

FAKE_WEBSOCKET_TRIGGER_MESSAGE = {
    "type": "Websocket",
    "push_type": "BNC1-websocket_connection",
    "extra_params": {
        "event_type": "websocket_connection",
        "device_id": FAKE_MODULE_ID,
        "home_id": FAKE_HOME_ID,
        "camera_id": FAKE_MODULE_ID,
        "home_name": "Fake Home",
    },
    "app_type": "app_camera",
    "user_id": FAKE_USER_ID,
    "Timestamp": {"sec": current_time, "usec": 0},
}

FAKE_GET_EVENTS_RESPONSE_WITH_CALL = {
    "body": {
        "home": {
            "id": FAKE_HOME_ID,
            "events": [
                {
                    "id": "fake_event_id_1",
                    "type": "connection",
                    "time": current_time - 60,
                    "module_id": FAKE_MODULE_ID,
                    "message": "Fake connection event",
                },
                {
                    "id": "fake_call_event_id",
                    "type": "outdoor",
                    "time": current_time - 5,
                    "module_id": FAKE_MODULE_ID,
                    "subevents": [
                        {
                            "id": "fake_subevent_id",
                            "type": "incoming_call",
                            "time": current_time - 5,
                            "verified": True,
                            "session_id": "fake_session_id_abc",
                            "offset": 0,
                            "snapshot": {
                                "url": "fake_snapshot_url",
                                "expires_at": current_time + 3600,
                            },
                            "vignette": {
                                "url": "fake_vignette_url",
                                "expires_at": current_time + 3600,
                            },
                            "message": f"Incoming call from Fake Module {FAKE_MODULE_ID}",
                        }
                    ],
                    "video_status": "available",
                },
            ],
        }
    },
    "status": "ok",
}

FAKE_GET_EVENTS_RESPONSE_WITHOUT_CALL = {
    "body": {
        "home": {
            "id": FAKE_HOME_ID,
            "events": [
                {
                    "id": "fake_event_id_2",
                    "type": "connection",
                    "time": current_time - 30,
                    "module_id": FAKE_MODULE_ID,
                    "message": "Another fake connection event",
                },
                {
                    "id": "fake_event_id_3",
                    "type": "disconnection",
                    "time": current_time - 15,
                    "module_id": FAKE_MODULE_ID,
                    "message": "Fake disconnection event",
                },
            ],
        }
    },
    "status": "ok",
}


# Read credentials from environment variables
USERNAME = os.getenv("BTICINOUSER")
PASSWORD = os.getenv("BTICINOPASSWORD")
# Optionally, specify a Home ID, otherwise the first one found will be used
HOME_ID_ENV = os.getenv("BTICINO_HOME_ID")

# Global variable to signal shutdown
shutdown_event = asyncio.Event()


# Modified to be async and accept AsyncAccount
async def handle_message(
    message: Dict[str, Any],
    account: Optional[AsyncAccount],  # Accept AsyncAccount or None (for simulation)
    home_id: str,
    simulate: bool,
    fake_event_data: Optional[Dict[str, Any]] = None,
):
    """Callback function to process received WebSocket messages."""
    logging.info("Received Message: %s", message)
    push_type = message.get("push_type")

    if push_type:
        logging.info(f"--> Push Type: {push_type}")
        extra_params = message.get("extra_params", {})
        logging.info(f"--> Extra Params: {extra_params}")

        # Check for the specific trigger message
        if push_type == "BNC1-websocket_connection":
            logging.info(
                "Trigger 'BNC1-websocket_connection' received. Checking for recent call events..."
            )
            events_data = None
            try:
                if simulate:
                    logging.info("[SIMULATION] Using fake event data.")
                    events_data = fake_event_data
                    await asyncio.sleep(0.5)  # Simulate delay
                elif account:  # Check if account object exists (real mode)
                    logging.info("Calling real async_get_events API...")
                    # Call the async method directly
                    events_data = await account.async_get_events(
                        home_id=home_id,
                        size=5,
                    )
                else:
                    logging.error(
                        "Cannot fetch events: Account object is None and not in simulation mode."
                    )
                    return

                # Process the events_data (either real or fake)
                if events_data and events_data.get("body", {}).get("home", {}).get(
                    "events"
                ):
                    logging.debug("Recent events fetched: %s", events_data)
                    call_found = False
                    for event in events_data["body"]["home"]["events"]:
                        if event.get("type") == "outdoor":
                            for subevent in event.get("subevents", []):
                                if subevent.get("type") == "incoming_call":
                                    logging.warning(
                                        ">>> INCOMING CALL DETECTED! <<< (Event ID: %s, Time: %s)",
                                        event.get("id"),
                                        event.get("time"),
                                    )
                                    logging.info("Full call event details: %s", event)
                                    call_found = True
                                    break
                            if call_found:
                                break
                    if not call_found:
                        logging.info(
                            "No 'incoming_call' event found in the last 5 events."
                        )
                else:
                    logging.warning(
                        "Could not retrieve recent events or events list is empty."
                    )

            except (ApiError, PyBticinoException) as e:
                logging.error(f"Error fetching events after trigger: {e}")
            except Exception as e:
                logging.exception("Unexpected error fetching events after trigger.")


def signal_handler():
    """Handle Ctrl+C or termination signals."""
    logging.info("Shutdown signal received, stopping...")
    shutdown_event.set()


async def run_simulation():
    """Runs the simulation loop."""
    logging.info("Starting simulation loop (Press Ctrl+C to stop)...")
    fake_response_toggle = True
    while not shutdown_event.is_set():
        logging.info("-----------------------------------------------------")
        logging.info("[SIMULATION] Triggering fake WebSocket message...")

        fake_response = (
            FAKE_GET_EVENTS_RESPONSE_WITH_CALL
            if fake_response_toggle
            else FAKE_GET_EVENTS_RESPONSE_WITHOUT_CALL
        )
        fake_response_toggle = not fake_response_toggle

        # Prepare the callback with simulation context (account=None)
        callback_with_sim_context = functools.partial(
            handle_message,
            account=None,  # Pass None for account in simulation
            home_id=FAKE_HOME_ID,
            simulate=True,
            fake_event_data=fake_response,
        )

        # Call the handler directly (it's now async)
        await callback_with_sim_context(FAKE_WEBSOCKET_TRIGGER_MESSAGE)

        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=10.0)
        except asyncio.TimeoutError:
            continue
        except asyncio.CancelledError:
            logging.info("[SIMULATION] Loop cancelled.")
            break


async def run_real_connection():
    """Runs the real WebSocket client connection."""
    logging.info("Starting real WebSocket connection (Press Ctrl+C to stop)...")
    auth = None
    account = None
    ws_client = None
    home_id_to_use = HOME_ID_ENV

    if not all([USERNAME, PASSWORD]):
        logging.error(
            "Real mode requires BTICINOUSER and BTICINOPASSWORD environment variables."
        )
        return

    try:
        # 1. Create AuthHandler and AsyncAccount
        logging.info("Creating AuthHandler and AsyncAccount...")
        auth = AuthHandler(USERNAME, PASSWORD)
        account = AsyncAccount(auth)  # Pass the async auth handler

        # 2. Determine Home ID to use
        logging.info("Fetching topology to determine Home ID...")
        try:
            await account.async_update_topology()
        except (ApiError, PyBticinoException, AuthError) as e:
            logging.error(f"Error fetching homes data: {e}")
            return  # Exit if topology fails

        if not account.homes:
            logging.error("No homes found for this account.")
            return  # Exit if no homes

        if HOME_ID_ENV:
            logging.info(f"Attempting to use specified Home ID: {HOME_ID_ENV}")
            if HOME_ID_ENV in account.homes:
                home_id_to_use = HOME_ID_ENV
                logging.info(
                    f"Using specified Home: Name='{account.homes[home_id_to_use].name}', ID='{home_id_to_use}'"
                )
            else:
                logging.error(f"Specified Home ID {HOME_ID_ENV} not found in account.")
                logging.error(f"Valid Home IDs found: {list(account.homes.keys())}")
                return  # Exit if specified ID is invalid
        else:
            # Get the first home ID from the dictionary keys if none specified
            first_home_id = next(iter(account.homes))
            home_id_to_use = first_home_id
            logging.info(
                f"No specific Home ID specified. Using first found Home: Name='{account.homes[first_home_id].name}', ID='{home_id_to_use}'"
            )

        if not home_id_to_use:
            logging.error(
                "Could not determine Home ID to use. Set BTICINOHOMEID or ensure account has homes."
            )
            return

        # 3. Prepare callback with account and home_id
        callback_with_context = functools.partial(
            handle_message,
            account=account,  # Pass the real account object
            home_id=home_id_to_use,
            simulate=False,
        )

        # 4. Initialize WebSocket Client
        logging.info("Initializing WebSocket client...")
        # Pass the async AuthHandler instance
        ws_client = WebsocketClient(
            auth_handler=auth, message_callback=callback_with_context
        )

        # 5. Run the client until shutdown signal
        logging.info(
            f"Running WebSocket client for Home ID {home_id_to_use}, waiting for messages..."
        )
        run_task = asyncio.create_task(ws_client.run_forever())

        await shutdown_event.wait()

        logging.info("Initiating WebSocket disconnect...")
        await ws_client.disconnect()
        await run_task  # Wait for run_forever task to finish

    except (AuthError, ApiError, PyBticinoException) as e:
        logging.error(f"Client Error: {e}")
    except asyncio.CancelledError:
        logging.info("Real connection task cancelled.")
    except Exception as e:
        logging.exception(f"An unexpected error occurred during real connection: {e}")
    finally:
        logging.info("Cleaning up...")
        # Ensure the session is closed
        if auth:
            await auth.close_session()
            logging.info("Auth session closed.")
        logging.info("Real WebSocket connection finished.")


async def main_entry(args):  # Renamed to avoid conflict with module name
    """Main entry point, decides between simulation and real connection."""
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    if args.simulate:
        await run_simulation()
    else:
        await run_real_connection()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run pybticino WebSocket example, optionally in simulation mode."
    )
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="Run in simulation mode without connecting to the real API/WebSocket.",
    )
    cli_args = parser.parse_args()

    try:
        asyncio.run(main_entry(cli_args))  # Call renamed main entry
    except KeyboardInterrupt:
        logging.info("Script interrupted by user.")
    except asyncio.CancelledError:
        logging.info("Main task cancelled.")
