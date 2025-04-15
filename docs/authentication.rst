==============
Authentication
==============

Authentication with the BTicino/Netatmo API is handled by the :class:`~pybticino.auth.AuthHandler` class. It manages the OAuth2 "password" grant type flow to obtain and automatically refresh API access tokens.

Initialization
--------------

You need to initialize `AuthHandler` with your BTicino/Netatmo account username (email) and password:

.. code-block:: python

    from pybticino import AuthHandler

    USERNAME = "your_email@example.com"
    PASSWORD = "your_password"

    auth_handler = AuthHandler(USERNAME, PASSWORD)

    # You can optionally provide an existing aiohttp.ClientSession
    # import aiohttp
    # async with aiohttp.ClientSession() as session:
    #     auth_handler_shared_session = AuthHandler(USERNAME, PASSWORD, session=session)

Obtaining Tokens
----------------

The `AuthHandler` obtains tokens lazily. The first time an access token is needed (e.g., when :meth:`~pybticino.auth.AuthHandler.get_access_token` is called, either directly or indirectly by :class:`~pybticino.account.AsyncAccount` or :class:`~pybticino.websocket.WebsocketClient`), the handler will perform the full authentication flow.

Token Refreshing
----------------

The handler automatically checks if the current access token is expired or close to expiring before returning it via :meth:`~pybticino.auth.AuthHandler.get_access_token`. If necessary, it will use the stored refresh token to obtain a new access token automatically. If refreshing fails, it will attempt a full re-authentication.

Session Management
------------------

By default, `AuthHandler` creates and manages its own `aiohttp.ClientSession`. You can close this internally managed session by calling:

.. code-block:: python

    await auth_handler.close_session()

If you provide an `aiohttp.ClientSession` during initialization, `AuthHandler` will use that session, and `close_session()` will *not* close the provided session. This is useful if you want to share a single session across multiple handlers or other parts of your application.

API Reference
-------------

For detailed information on the class and its methods, see the API reference:

*   :class:`~pybticino.auth.AuthHandler`
*   :class:`~pybticino.exceptions.AuthError` (Exception raised on authentication failures)
