==========
API Client
==========

The :class:`~pybticino.account.AsyncAccount` class is the primary interface for interacting with the BTicino API after authentication. It provides methods to retrieve information about homes, modules, status, events, and to control devices.

Initialization
--------------

You initialize `AsyncAccount` by passing it an authenticated :class:`~pybticino.auth.AuthHandler` instance:

.. code-block:: python

    from pybticino import AsyncAccount, AuthHandler

    # Assume auth_handler is an initialized AuthHandler instance
    auth_handler = AuthHandler("user@example.com", "password")

    account = AsyncAccount(auth_handler)

Fetching Home Topology
----------------------

Before interacting with specific homes or modules, you need to fetch the account's topology using :meth:`~pybticino.account.AsyncAccount.async_update_topology`:

.. code-block:: python

    await account.async_update_topology()

    # After this call, account.homes and account.user are populated
    print(f"User: {account.user}")
    for home_id, home in account.homes.items():
        print(f"Home: {home.name} ({home_id})")
        for module in home.modules:
            print(f"  Module: {module.name} ({module.id}, Type: {module.type})")

The `account.homes` attribute becomes a dictionary mapping home IDs to :class:`~pybticino.models.Home` objects. Each `Home` object contains a list of :class:`~pybticino.models.Module` objects.

Getting Home Status
-------------------

To get the current status of devices within a specific home, use :meth:`~pybticino.account.AsyncAccount.async_get_home_status`:

.. code-block:: python

    home_id = list(account.homes.keys())[0] # Get an example home ID
    status_data = await account.async_get_home_status(home_id)
    print(status_data) # Note: Returns raw API response currently

This method currently returns the raw dictionary response from the API.

Setting Module State
--------------------

You can control devices using :meth:`~pybticino.account.AsyncAccount.async_set_module_state`.

.. warning::
   Use this method with caution. Ensure you know the correct `module_id`, state keys (e.g., `'lock'`, `'on'`), and value types (e.g., `bool`, `int`) for the specific device you are controlling. Providing incorrect parameters might lead to unexpected behavior or errors. You may also need to provide the `bridge_id` for certain modules.

.. code-block:: python

    home_id = "..."
    module_id = "..." # e.g., the ID of a door lock module
    bridge_id = "..." # Optional: ID of the bridge if needed

    try:
        # Example: Unlock a door lock (BNDL module type)
        result = await account.async_set_module_state(
            home_id=home_id,
            module_id=module_id,
            state={'lock': False},
            # bridge_id=bridge_id # Uncomment if required
        )
        print(f"Set state result: {result}")
    except (ApiError, ValueError) as e:
        print(f"Error setting state: {e}")

Getting Events
--------------

Retrieve recent events for a home using :meth:`~pybticino.account.AsyncAccount.async_get_events`:

.. code-block:: python

    home_id = "..."
    events_data = await account.async_get_events(home_id=home_id, size=10) # Get last 10 events
    print(events_data) # Note: Returns raw API response currently

This method also currently returns the raw dictionary response from the API.

API Reference
-------------

For detailed information on the class and its methods, see the API reference:

*   :class:`~pybticino.account.AsyncAccount`
*   :class:`~pybticino.models.Home`
*   :class:`~pybticino.models.Module`
*   :class:`~pybticino.exceptions.ApiError` (Exception raised on API call failures)
