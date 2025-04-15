"""WebSocket client for receiving push notifications."""

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
import json
import logging
import ssl
from typing import Any

import websockets
from websockets.protocol import State  # Added for state checking

from .auth import AuthHandler
from .const import DEFAULT_APP_VERSION, DEFAULT_PLATFORM, PUSH_WS_URL
from .exceptions import AuthError, PyBticinoException

_LOGGER = logging.getLogger(__name__)


class WebsocketClient:
    """Handles the WebSocket connection for receiving real-time push notifications.

    This client connects to the BTicino WebSocket endpoint, authenticates using
    an `AuthHandler`, subscribes to updates, and invokes a user-provided
    asynchronous callback function for each received message. It includes
    automatic reconnection logic.

    Attributes:
        _auth_handler (AuthHandler): Instance used for authentication.
        _message_callback (Callable): Async function called with received messages.
        _app_version (str): Application version string.
        _platform (str): Platform identifier string.
        _websocket (Optional[websockets.ClientConnection]): The active WebSocket connection.
        _listener_task (Optional[asyncio.Task]): The task running the message listener loop.
        _is_running (bool): Flag indicating if the client is actively running/connecting.
        _connection_lock (asyncio.Lock): Lock to prevent race conditions during
                                         connect/disconnect operations.

    """

    def __init__(
        self,
        auth_handler: AuthHandler,
        message_callback: Callable[[dict[str, Any]], Awaitable[None]],
        app_version: str = DEFAULT_APP_VERSION,
        platform: str = DEFAULT_PLATFORM,
    ) -> None:
        """Initialize the WebSocket client.

        Args:
            auth_handler (AuthHandler): An initialized and authenticated
                                        `AuthHandler` instance.
            message_callback (Callable[[dict[str, Any]], Awaitable[None]]):
                An asynchronous function that will be called with each decoded
                JSON message received from the WebSocket.
            app_version (str): The application version string. Defaults to
                               `DEFAULT_APP_VERSION`.
            platform (str): The platform identifier string. Defaults to
                            `DEFAULT_PLATFORM`.

        Raises:
            TypeError: If `auth_handler` is not an instance of `AuthHandler` or
                       if `message_callback` is not an async function.

        """
        if not isinstance(auth_handler, AuthHandler):
            err_msg = "auth_handler must be an instance of AuthHandler"
            raise TypeError(err_msg)
        if not asyncio.iscoroutinefunction(message_callback):
            err_msg = "message_callback must be an async function"
            raise TypeError(err_msg)

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

    async def _subscribe(self) -> None:
        """Send the subscription message after connecting to the WebSocket.

        This method constructs and sends the JSON payload required to start
        receiving push notifications. It waits for an 'ok' status response.

        Raises:
            PyBticinoException: If the WebSocket is not connected, if the
                                subscription payload cannot be sent, if a timeout
                                occurs waiting for the response, or if the
                                server returns a non-ok status.
            AuthError: If obtaining an access token fails during subscription.
            websockets.exceptions.ConnectionClosed: If the connection closes
                                                    during subscription.

        """
        if not self._websocket:
            err_msg = "WebSocket connection not established."
            raise PyBticinoException(err_msg)

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
                err_msg = f"WebSocket subscription failed: {response}"
                raise PyBticinoException(err_msg)  # noqa: TRY301
        except AuthError:
            _LOGGER.exception("Authentication error during WebSocket subscription")
            raise  # Re-raise AuthError to be handled by connect/run_forever
        except websockets.exceptions.ConnectionClosed:
            _LOGGER.warning("WebSocket connection closed during subscription.")
            raise  # Re-raise to trigger reconnection logic
        except TimeoutError:
            _LOGGER.exception("Timeout waiting for WebSocket subscription response.")
            err_msg = "Timeout waiting for WebSocket subscription response."
            raise PyBticinoException(err_msg) from None
        except Exception as e:  # Added 'as e' back
            _LOGGER.exception("Error during WebSocket subscription")
            err_msg = f"Error during WebSocket subscription: {e}"
            raise PyBticinoException(err_msg) from e

    async def _listen(self) -> None:
        """Continuously listen for incoming messages on the WebSocket connection.

        This method runs an `async for` loop over the WebSocket connection.
        For each received message, it attempts to decode it as JSON and passes
        it to the `_message_callback` provided during initialization.

        It handles JSON decoding errors and exceptions raised by the callback.
        The loop terminates when the WebSocket connection is closed.

        Raises:
            websockets.exceptions.ConnectionClosedError: If the connection closes
                                                         unexpectedly with an error.
                                                         (ConnectionClosedOK is handled gracefully).
            asyncio.CancelledError: If the listening task is cancelled.
            Exception: Any other unexpected error during the listening loop.

        """
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
                        "Received non-JSON WebSocket message: %s",
                        message_raw,
                    )
                except Exception:  # Catches errors in the callback
                    _LOGGER.exception(
                        "Error processing WebSocket message in callback",
                    )
            # End of the async for loop

        # Specific handling for connection closure exceptions or other errors during iteration.
        # These except/else/finally blocks belong to the try block wrapping the async for loop.
        except websockets.exceptions.ConnectionClosedOK as e:
            _LOGGER.info(
                "WebSocket connection closed normally (code=%s, reason='%s').",
                e.code,
                e.reason or "No reason given",
            )
            # Don't re-raise, this is a clean closure
        except websockets.exceptions.ConnectionClosedError as e:
            _LOGGER.warning(
                "WebSocket connection closed with error (code=%s, reason='%s').",
                e.code,
                e.reason or "No reason given",
            )
            raise  # Re-raise ConnectionClosedError to trigger reconnection in run_forever
        except asyncio.CancelledError:
            _LOGGER.info("WebSocket listener task cancelled.")
            raise  # Propagate cancellation
        except Exception:
            # Catch any other unexpected error during the listener loop or its finalization
            _LOGGER.exception("Unexpected error caught in listener loop")
            raise  # Re-raise other exceptions to trigger reconnection
        else:
            _LOGGER.info(
                "_listen: Async for loop finished without exceptions.",
            )  # Log normal loop exit
        finally:
            _LOGGER.info("WebSocket listener loop finished.")
            # Do not set self._is_running = False here

    async def connect(self) -> None:
        """Establish the WebSocket connection, subscribe, and start listening.

        Connects to the WebSocket server, sends the subscription message,
        and creates a background task to listen for incoming messages.
        Uses a lock to prevent concurrent connection attempts.

        Raises:
            PyBticinoException: If connection or subscription fails.
                                Wraps underlying exceptions like `websockets.exceptions`,
                                `AuthError`, `TimeoutError`.

        """
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
                    "WebSocket state: %s",
                    self._websocket.state,
                )  # Log state after connect

                # Subscribe after connecting
                await self._subscribe()

                # Start the listener task
                self._listener_task = asyncio.create_task(self._listen())
                _LOGGER.info("WebSocket listener task started.")

            except Exception as e:
                _LOGGER.exception(
                    "Failed to connect or subscribe to WebSocket",
                )  # Use exception
                self._is_running = False  # Reset running state on failure
                if (
                    self._websocket
                    and self._websocket.state != State.CLOSED  # Use state check
                ):  # Check if not closed before trying to close
                    # Use contextlib.suppress for cleaner error ignoring
                    with suppress(websockets.exceptions.WebSocketException):
                        await self._websocket.close()
                self._websocket = None
                self._listener_task = None  # Ensure task is cleared
                # Re-raise as a specific exception for run_forever to catch
                err_msg = f"WebSocket connection/subscription failed: {e}"
                raise PyBticinoException(err_msg) from e

    async def disconnect(self) -> None:
        """Disconnect the WebSocket client gracefully.

        Cancels the listener task and closes the WebSocket connection.
        Uses a lock to prevent concurrent disconnect operations.
        """
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
                except Exception:
                    _LOGGER.exception(
                        "Error waiting for listener task cancellation",
                    )
            self._listener_task = None

            ws = self._websocket  # Keep a local reference
            self._websocket = None  # Clear instance reference immediately

            # Check if the local reference exists and use the 'closed' property
            if ws and ws.state != State.CLOSED:  # Use state check
                try:
                    await ws.close()
                    _LOGGER.info("WebSocket connection closed.")
                    _LOGGER.debug("WebSocket state after close: %s", ws.state)
                except websockets.exceptions.WebSocketException as e:
                    _LOGGER.warning("Error closing WebSocket connection: %s", e)
            elif ws:
                _LOGGER.debug(
                    "WebSocket connection was already closed (state: %s).",
                    ws.state,
                )
            else:
                _LOGGER.debug("No active WebSocket connection object to close.")

    async def run_forever(self, reconnect_delay: int = 30) -> None:
        """Connect and maintain the WebSocket connection indefinitely.

        This method runs a loop that attempts to `connect()`. If the connection
        drops (indicated by the listener task ending or an error during connection),
        it waits for `reconnect_delay` seconds before attempting to `disconnect()`
        cleanly and then `connect()` again.

        This method typically runs forever until the client is explicitly stopped
        (e.g., by cancelling the task running this method or calling `disconnect`
        from another task).

        Args:
            reconnect_delay (int): The number of seconds to wait before attempting
                                   to reconnect after a disconnection. Defaults to 30.

        """
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
                                    "run_forever: Listener task finished with exception: %r",
                                    listener_exception,
                                )
                                # Exception occurred, will trigger reconnect below
                    except asyncio.CancelledError:
                        _LOGGER.info(
                            "run_forever: Listener task was cancelled during shutdown.",
                        )
                        # If cancellation was triggered by disconnect(), _is_running will be False
                        if not self._is_running:
                            break  # Exit loop cleanly
                        # If cancelled externally but not via disconnect(), still attempt reconnect?
                        _LOGGER.warning(
                            "Listener task cancelled externally, attempting reconnect.",
                        )
                    except (
                        Exception
                    ) as e:  # Catch blind exception is okay here for loop robustness
                        # Catch any error during the await self._listener_task itself (less likely)
                        _LOGGER.exception("run_forever: Error awaiting listener task")
                        listener_exception = (
                            e  # Treat this also as a reason to reconnect
                        )

                # --- Reconnection Logic ---
                # If we are still supposed to be running...
                if self._is_running:
                    if listener_exception:
                        _LOGGER.warning(
                            "Listener task stopped due to error. Attempting reconnect.",
                        )
                    elif self._listener_task and self._listener_task.done():
                        # Listener finished without CancelledError or logged exception from await
                        _LOGGER.warning(
                            "Listener task stopped unexpectedly (e.g. server closed connection or loop finished cleanly). Attempting reconnect.",
                        )
                    # else: The task might still be running if connect() failed before starting it
                else:
                    # _is_running is False, means disconnect() was called or shutdown initiated
                    _LOGGER.info(
                        "run_forever: Shutdown initiated or disconnect called. Exiting loop.",
                    )
                    break

            except PyBticinoException:
                # Errors during connect() or _subscribe()
                _LOGGER.exception(
                    "WebSocket connection/subscription error. Retrying in %d seconds...",
                    reconnect_delay,
                )
            except Exception:
                # Catch-all for other unexpected errors in the main loop
                _LOGGER.exception(
                    "Unexpected error in run_forever loop. Retrying in %d seconds...",
                    reconnect_delay,
                )

            # If the loop didn't break, attempt reconnect after delay
            _LOGGER.info("Attempting WebSocket reconnection...")
            await self.disconnect()  # Ensure clean state before retry
            _LOGGER.info(
                "Waiting %d seconds before reconnect attempt...",
                reconnect_delay,
            )
            await asyncio.sleep(reconnect_delay)
