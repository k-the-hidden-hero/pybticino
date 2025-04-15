==========
WebSockets
==========

The :class:`~pybticino.websocket.WebsocketClient` provides a way to receive real-time push notifications from the BTicino API. This is useful for getting immediate updates when device states change or events occur, without needing to poll the API repeatedly.

Initialization
--------------

To use the WebSocket client, you need an authenticated :class:`~pybticino.auth.AuthHandler` and an asynchronous callback function. The callback function will be executed every time a message is received from the WebSocket.

.. code-block:: python

    import asyncio
    import logging
    from pybticino import AuthHandler, WebsocketClient

    _LOGGER = logging.getLogger(__name__)

    async def my_message_callback(message: dict):
        """This function will be called for each WebSocket message."""
        _LOGGER.info(f"Received WebSocket message: {message}")
        # Add your logic here to process the message
        # e.g., update device states, trigger automations

    # Assume auth_handler is an initialized AuthHandler instance
    auth_handler = AuthHandler("user@example.com", "password")

    ws_client = WebsocketClient(auth_handler, my_message_callback)

Running the Client
------------------

There are two main ways to run the client:

1.  **Connect and Disconnect Manually:**
    You can manage the connection lifecycle yourself using `connect()` and `disconnect()`.

    .. code-block:: python

        try:
            await ws_client.connect() # Connects, subscribes, starts listener task
            # Keep your application running while the listener works
            # For example, wait indefinitely:
            await asyncio.Event().wait()
        except Exception as e:
            _LOGGER.error(f"WebSocket error: {e}")
        finally:
            await ws_client.disconnect()

2.  **Run Forever (Recommended for long-running applications):**
    The :meth:`~pybticino.websocket.WebsocketClient.run_forever` method handles connection and automatic reconnection in a loop. This is generally the preferred way for services that need a persistent connection.

    .. code-block:: python

        # This task will run indefinitely, attempting to stay connected
        try:
            await ws_client.run_forever(reconnect_delay=30) # Retry every 30s
        except asyncio.CancelledError:
            _LOGGER.info("WebSocket run_forever task cancelled.")
        finally:
            # Ensure disconnection if run_forever exits unexpectedly
            await ws_client.disconnect()

    You would typically run this `run_forever` coroutine as a background task in your application.

Message Format
--------------

The `message` dictionary passed to your callback function contains the raw JSON payload from the BTicino WebSocket. The exact structure depends on the type of event or update. You will need to inspect these messages to determine how to parse the information relevant to your application (e.g., identifying module IDs, state changes, event types).

API Reference
-------------

*   :class:`~pybticino.websocket.WebsocketClient`
*   :class:`~pybticino.exceptions.PyBticinoException` (Base exception, can be raised during connection/subscription)
