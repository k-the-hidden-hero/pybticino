"""WebSocket client for receiving push notifications."""

import asyncio
import json
import logging
import websockets
import ssl
from typing import Callable, Awaitable, Any
from websockets.protocol import State  # Added for state checking

from .auth import AuthHandler
from .const import PUSH_WS_URL, DEFAULT_APP_VERSION, DEFAULT_PLATFORM
from .exceptions import AuthError, PyBticinoException

_LOGGER = logging.getLogger(__name__)


class WebsocketClient:
    """Handles WebSocket connection and push notifications."""

    def __init__(
        self,
        auth_handler: AuthHandler,
        message_callback: Callable[[dict[str, Any]], Awaitable[None]],
        app_version: str = DEFAULT_APP_VERSION,
        platform: str = DEFAULT_PLATFORM,
    ):
        """
        Initialize the WebSocket client.

        Args:
            auth_handler: Authenticated AuthHandler instance.
            message_callback: Async function to call when a message is received.
                              It will be called with the decoded JSON message.
            app_version: The application version string.
            platform: The platform string (e.g., 'Android').
        """
        if not isinstance(auth_handler, AuthHandler):
            raise TypeError("auth_handler must be an instance of AuthHandler")
        if not asyncio.iscoroutinefunction(message_callback):
            raise TypeError("message_callback must be an async function")

        self._auth_handler = auth_handler
        self._message_callback = message_callback
        self._app_version = app_version
        self._platform = platform
        self._websocket: websockets.ClientConnection | None = None  # Updated type hint
        self._listener_task: asyncio.Task | None = None
        self._is_running = False
        self._connection_lock = (
            asyncio.Lock()
        )  # Lock to prevent concurrent connect/disconnect

    async def _subscribe(self):
        """Send the subscription message to the WebSocket server."""
        if not self._websocket:
            raise PyBticinoException("WebSocket connection not established.")

        try:
            # Ensure token is valid before subscribing (using async getter)
            access_token = await self._auth_handler.get_access_token()  # Added await
            subscribe_message = {
                "filter": "silent",  # As seen in logs for PUSH_WS_URL
                "access_token": access_token,
                "app_type": "app_camera",  # As seen in logs for PUSH_WS_URL
                "action": "Subscribe",
                "version": self._app_version,
                "platform": self._platform,
            }
            _LOGGER.info("Sending WebSocket subscription message...")
            _LOGGER.debug("Subscribe payload: %s", subscribe_message)
            await self._websocket.send(json.dumps(subscribe_message))

            # Wait for the confirmation message (simple 'ok' status)
            response_raw = await asyncio.wait_for(self._websocket.recv(), timeout=10)
            response = json.loads(response_raw)
            _LOGGER.debug("Subscription response: %s", response)
            if response.get("status") == "ok":
                _LOGGER.info("WebSocket subscription successful.")
            else:
                # Handle potential errors like expired token etc. if server sends specific codes
                raise PyBticinoException(f"WebSocket subscription failed: {response}")
        except AuthError as e:
            _LOGGER.error("Authentication error during WebSocket subscription: %s", e)
            raise  # Re-raise AuthError to be handled by connect/run_forever
        except websockets.exceptions.ConnectionClosed:
            _LOGGER.warning("WebSocket connection closed during subscription.")
            raise  # Re-raise to trigger reconnection logic
        except asyncio.TimeoutError:
            _LOGGER.error("Timeout waiting for WebSocket subscription response.")
            raise PyBticinoException(
                "Timeout waiting for WebSocket subscription response."
            )
        except Exception as e:
            _LOGGER.error("Error during WebSocket subscription: %s", e)
            raise PyBticinoException(f"Error during WebSocket subscription: {e}") from e

    async def _listen(self):
        """Listen for messages on the WebSocket."""
        # Ensure connection exists and is not closed before starting to listen
        if (
            not self._websocket or self._websocket.state == State.CLOSED
        ):  # Use state check
            _LOGGER.error("Cannot listen, WebSocket is not connected or is closed.")
            return

        _LOGGER.info("Starting WebSocket listener loop...")
        # Rely on the async for loop raising ConnectionClosed* exceptions
        # when the connection terminates, instead of explicit .closed checks.
        try:
            _LOGGER.debug("_listen: Entering async for message loop...")
            async for message_raw in self._websocket:
                # Inner try/except handles errors *during* processing of a single message
                try:
                    message = json.loads(message_raw)
                    _LOGGER.debug("Received WebSocket message: %s", message)
                    # Process the message - Call the user-provided callback
                    # We assume the callback handles different message types if needed
                    await self._message_callback(message)
                except json.JSONDecodeError:
                    _LOGGER.warning(
                        "Received non-JSON WebSocket message: %s", message_raw
                    )
                except Exception as e:  # Catches errors in the callback
                    _LOGGER.exception(
                        "Error processing WebSocket message in callback: %s", e
                    )
            # End of the async for loop

        # Specific handling for connection closure exceptions or other errors during iteration.
        # These except/else/finally blocks belong to the try block wrapping the async for loop.
        except websockets.exceptions.ConnectionClosedOK as e:
            _LOGGER.info(
                f"WebSocket connection closed normally (code={e.code}, reason='{e.reason or 'No reason given'}')."
            )
            # Don't re-raise, this is a clean closure
        except websockets.exceptions.ConnectionClosedError as e:
            _LOGGER.warning(
                f"WebSocket connection closed with error (code={e.code}, reason='{e.reason or 'No reason given'}')."
            )
            raise  # Re-raise ConnectionClosedError to trigger reconnection in run_forever
        except asyncio.CancelledError:
            _LOGGER.info("WebSocket listener task cancelled.")
            raise  # Propagate cancellation
        except Exception as e:
            # Catch any other unexpected error during the listener loop or its finalization
            _LOGGER.exception("Unexpected error caught in listener loop: %s", e)
            raise  # Re-raise other exceptions to trigger reconnection
        else:
            _LOGGER.info(
                "_listen: Async for loop finished without exceptions."
            )  # Log normal loop exit
        finally:
            _LOGGER.info("WebSocket listener loop finished.")
            # Do not set self._is_running = False here

    async def connect(self):
        """Establish WebSocket connection and start listening."""
        async with self._connection_lock:
            if self._is_running:
                _LOGGER.warning("WebSocket client is already running or connecting.")
                return

            self._is_running = True  # Mark as attempting to run
            _LOGGER.info("Connecting to WebSocket: %s", PUSH_WS_URL)
            try:
                # Use default SSL context for wss
                ssl_context = ssl.create_default_context()
                # Increase timeout for connection establishment and add keepalive pings
                self._websocket = await websockets.connect(
                    PUSH_WS_URL,
                    ssl=ssl_context,
                    open_timeout=20,
                    close_timeout=10,
                    ping_interval=20,  # Send a ping every 20 seconds
                    ping_timeout=20,  # Wait up to 20 seconds for pong response
                )
                _LOGGER.info("WebSocket connection established.")
                _LOGGER.debug(
                    f"WebSocket state: {self._websocket.state}"
                )  # Log state after connect

                # Subscribe after connecting
                await self._subscribe()

                # Start the listener task
                self._listener_task = asyncio.create_task(self._listen())
                _LOGGER.info("WebSocket listener task started.")

            except Exception as e:
                _LOGGER.error("Failed to connect or subscribe to WebSocket: %s", e)
                self._is_running = False  # Reset running state on failure
                if (
                    self._websocket
                    and self._websocket.state != State.CLOSED  # Use state check
                ):  # Check if not closed before trying to close
                    try:
                        await self._websocket.close()
                    except websockets.exceptions.WebSocketException:
                        pass  # Ignore errors during cleanup close
                self._websocket = None
                self._listener_task = None  # Ensure task is cleared
                # Re-raise as a specific exception for run_forever to catch
                raise PyBticinoException(
                    f"WebSocket connection/subscription failed: {e}"
                ) from e

    async def disconnect(self):
        """Disconnect the WebSocket client."""
        async with self._connection_lock:
            if not self._is_running and not self._websocket:
                _LOGGER.info("WebSocket client already disconnected.")
                return

            _LOGGER.info("Disconnecting WebSocket client...")
            self._is_running = False  # Signal intent to stop

            if self._listener_task and not self._listener_task.done():
                self._listener_task.cancel()
                try:
                    await self._listener_task
                except asyncio.CancelledError:
                    _LOGGER.debug("Listener task successfully cancelled.")
                except Exception as e:
                    _LOGGER.exception(
                        "Error waiting for listener task cancellation: %s", e
                    )
            self._listener_task = None

            ws = self._websocket  # Keep a local reference
            self._websocket = None  # Clear instance reference immediately

            # Check if the local reference exists and use the 'closed' property
            if ws and ws.state != State.CLOSED:  # Use state check
                try:
                    await ws.close()
                    _LOGGER.info("WebSocket connection closed.")
                    _LOGGER.debug(f"WebSocket state after close: {ws.state}")
                except websockets.exceptions.WebSocketException as e:
                    _LOGGER.warning("Error closing WebSocket connection: %s", e)
            elif ws:
                _LOGGER.debug(
                    f"WebSocket connection was already closed (state: {ws.state})."
                )
            else:
                _LOGGER.debug("No active WebSocket connection object to close.")

    async def run_forever(self, reconnect_delay: int = 30):
        """Connect and keep running, attempting to reconnect on failure."""
        _LOGGER.info("Starting WebSocket client run_forever loop...")
        while True:
            listener_exception = None  # Track exception from listener task
            try:
                # Attempt to connect (includes subscription and starting listener)
                await self.connect()

                # Wait for the listener task to complete (indicates disconnection or error)
                if self._listener_task:
                    try:
                        # Wait for the task to complete
                        await self._listener_task
                        # After awaiting, check if it finished with an exception
                        if self._listener_task.done():  # Check if task is actually done
                            listener_exception = (
                                self._listener_task.exception()
                            )  # Get exception if any
                            if listener_exception:
                                _LOGGER.error(
                                    f"run_forever: Listener task finished with exception: {listener_exception!r}"
                                )
                                # Exception occurred, will trigger reconnect below
                    except asyncio.CancelledError:
                        _LOGGER.info(
                            "run_forever: Listener task was cancelled during shutdown."
                        )
                        # If cancellation was triggered by disconnect(), _is_running will be False
                        if not self._is_running:
                            break  # Exit loop cleanly
                        else:
                            # If cancelled externally but not via disconnect(), still attempt reconnect?
                            _LOGGER.warning(
                                "Listener task cancelled externally, attempting reconnect."
                            )
                    except Exception as e:
                        # Catch any error during the await self._listener_task itself (less likely)
                        _LOGGER.error(
                            f"run_forever: Error awaiting listener task: {e!r}"
                        )
                        listener_exception = (
                            e  # Treat this also as a reason to reconnect
                        )

                # --- Reconnection Logic ---
                # If we are still supposed to be running...
                if self._is_running:
                    if listener_exception:
                        _LOGGER.warning(
                            "Listener task stopped due to error. Attempting reconnect."
                        )
                    elif self._listener_task and self._listener_task.done():
                        # Listener finished without CancelledError or logged exception from await
                        _LOGGER.warning(
                            "Listener task stopped unexpectedly (e.g. server closed connection or loop finished cleanly). Attempting reconnect."
                        )
                    # else: The task might still be running if connect() failed before starting it
                else:
                    # _is_running is False, means disconnect() was called or shutdown initiated
                    _LOGGER.info(
                        "run_forever: Shutdown initiated or disconnect called. Exiting loop."
                    )
                    break

            except PyBticinoException as e:
                # Errors during connect() or _subscribe()
                _LOGGER.error(
                    "WebSocket connection/subscription error: %s. Retrying in %d seconds...",
                    e,
                    reconnect_delay,
                )
            except Exception as e:
                # Catch-all for other unexpected errors in the main loop
                _LOGGER.exception(
                    "Unexpected error in run_forever loop: %s. Retrying in %d seconds...",
                    e,
                    reconnect_delay,
                )

            # If the loop didn't break, attempt reconnect after delay
            _LOGGER.info("Attempting WebSocket reconnection...")
            await self.disconnect()  # Ensure clean state before retry
            _LOGGER.info(
                "Waiting %d seconds before reconnect attempt...", reconnect_delay
            )
            await asyncio.sleep(reconnect_delay)
