"""Tests for AsyncAccount API interactions."""

from aioresponses import aioresponses
import pytest

from pybticino import AsyncAccount, AuthHandler
from pybticino.exceptions import ApiError

from .conftest import (
    GETEVENTS_URL,
    HOMESDATA_URL,
    HOMESTATUS_URL,
    MOCK_BRIDGE_ID,
    MOCK_HOME_ID,
    MOCK_HOME_NAME,
    MOCK_LIGHT_ID,
    MOCK_LOCK_ID,
    MOCK_PASSWORD,
    MOCK_USERNAME,
    SETSTATE_URL,
    TOKEN_URL,
    build_events_response,
    build_homesdata_response,
    build_homestatus_response,
    build_token_response,
)


@pytest.fixture
async def authenticated_account():
    """Create an authenticated AsyncAccount with mocked token."""
    handler = AuthHandler(MOCK_USERNAME, MOCK_PASSWORD)
    handler._access_token = "mock-token"
    handler._token_expires_at = 9999999999.0  # Far future
    handler._refresh_token = "mock-refresh"
    account = AsyncAccount(handler)
    yield account
    await handler.close_session()


# --- Instantiation ---


def test_account_requires_auth_handler():
    """Test AsyncAccount rejects non-AuthHandler arguments."""
    with pytest.raises(TypeError, match="must be an instance of AuthHandler"):
        AsyncAccount("not_an_auth_handler")


def test_account_instantiation():
    """Test AsyncAccount can be instantiated with a valid AuthHandler."""
    handler = AuthHandler(MOCK_USERNAME, MOCK_PASSWORD)
    account = AsyncAccount(handler)
    assert account.auth_handler is handler
    assert account.homes == {}
    assert account.user is None


# --- Topology ---


async def test_update_topology(authenticated_account):
    """Test fetching and parsing home topology."""
    account = authenticated_account

    with aioresponses() as m:
        m.post(HOMESDATA_URL, payload=build_homesdata_response())

        await account.async_update_topology()

    assert account.user == MOCK_USERNAME
    assert len(account.homes) == 1
    assert MOCK_HOME_ID in account.homes

    home = account.homes[MOCK_HOME_ID]
    assert home.name == MOCK_HOME_NAME
    assert len(home.modules) == 3

    # Check module types
    module_ids = {m.id for m in home.modules}
    assert MOCK_BRIDGE_ID in module_ids
    assert MOCK_LOCK_ID in module_ids
    assert MOCK_LIGHT_ID in module_ids


async def test_update_topology_empty_homes(authenticated_account):
    """Test topology update when no homes are returned."""
    account = authenticated_account

    with aioresponses() as m:
        m.post(HOMESDATA_URL, payload={"body": {"user": {"email": MOCK_USERNAME}, "homes": []}})

        await account.async_update_topology()

    assert account.user == MOCK_USERNAME
    assert len(account.homes) == 0


async def test_update_topology_api_error(authenticated_account):
    """Test topology update handles API errors."""
    account = authenticated_account

    with aioresponses() as m:
        m.post(HOMESDATA_URL, status=500, body="Internal Server Error")

        with pytest.raises(ApiError):
            await account.async_update_topology()


async def test_update_topology_clears_previous_homes(authenticated_account):
    """Test that topology update replaces previous home data."""
    account = authenticated_account

    with aioresponses() as m:
        # First call
        m.post(HOMESDATA_URL, payload=build_homesdata_response())
        await account.async_update_topology()
        assert len(account.homes) == 1

        # Second call with empty homes
        m.post(HOMESDATA_URL, payload={"body": {"user": {"email": MOCK_USERNAME}, "homes": []}})
        await account.async_update_topology()
        assert len(account.homes) == 0


# --- Home Status ---


async def test_get_home_status(authenticated_account):
    """Test fetching home status."""
    account = authenticated_account

    # First populate homes
    with aioresponses() as m:
        m.post(HOMESDATA_URL, payload=build_homesdata_response())
        await account.async_update_topology()

    with aioresponses() as m:
        m.post(HOMESTATUS_URL, payload=build_homestatus_response())

        status = await account.async_get_home_status(MOCK_HOME_ID)

    assert "body" in status
    modules = status["body"]["home"]["modules"]
    assert len(modules) == 3


async def test_get_home_status_unknown_home(authenticated_account):
    """Test fetching status for unknown home returns empty dict."""
    account = authenticated_account
    result = await account.async_get_home_status("unknown_home_id")
    assert result == {}


async def test_get_home_status_api_error(authenticated_account):
    """Test home status handles API errors."""
    account = authenticated_account

    with aioresponses() as m:
        m.post(HOMESDATA_URL, payload=build_homesdata_response())
        await account.async_update_topology()

    with aioresponses() as m:
        m.post(HOMESTATUS_URL, status=503, body="Service Unavailable")

        with pytest.raises(ApiError):
            await account.async_get_home_status(MOCK_HOME_ID)


# --- Set Module State ---


async def test_set_module_state(authenticated_account):
    """Test setting module state (e.g., unlock door)."""
    account = authenticated_account

    with aioresponses() as m:
        m.post(HOMESDATA_URL, payload=build_homesdata_response())
        await account.async_update_topology()

    with aioresponses() as m:
        m.post(SETSTATE_URL, payload={"status": "ok"})

        result = await account.async_set_module_state(
            home_id=MOCK_HOME_ID,
            module_id=MOCK_LOCK_ID,
            bridge_id=MOCK_BRIDGE_ID,
            state={"lock": False},
            timezone="Europe/Rome",
        )

    assert result["status"] == "ok"


async def test_set_module_state_unknown_home(authenticated_account):
    """Test setting state for unknown home raises ValueError."""
    account = authenticated_account

    with pytest.raises(ValueError, match="not found"):
        await account.async_set_module_state(
            home_id="unknown",
            module_id=MOCK_LOCK_ID,
            state={"lock": False},
        )


async def test_set_module_state_api_error(authenticated_account):
    """Test setting state handles API errors."""
    account = authenticated_account

    with aioresponses() as m:
        m.post(HOMESDATA_URL, payload=build_homesdata_response())
        await account.async_update_topology()

    with aioresponses() as m:
        m.post(SETSTATE_URL, status=500, body="Error")

        with pytest.raises(ApiError):
            await account.async_set_module_state(
                home_id=MOCK_HOME_ID,
                module_id=MOCK_LOCK_ID,
                state={"lock": False},
            )


# --- Get Events ---


async def test_get_events(authenticated_account):
    """Test fetching events for a home."""
    account = authenticated_account

    with aioresponses() as m:
        m.post(HOMESDATA_URL, payload=build_homesdata_response())
        await account.async_update_topology()

    with aioresponses() as m:
        m.post(GETEVENTS_URL, payload=build_events_response())

        events = await account.async_get_events(MOCK_HOME_ID, size=20)

    assert "body" in events
    event_list = events["body"]["home"]["events"]
    assert len(event_list) == 1
    assert event_list[0]["type"] == "call"


async def test_get_events_unknown_home(authenticated_account):
    """Test fetching events for unknown home returns empty dict."""
    account = authenticated_account
    result = await account.async_get_events("unknown_home_id")
    assert result == {}


# --- Integration: Full flow ---


async def test_full_auth_topology_status_flow():
    """Test the full flow: authenticate → topology → status."""
    handler = AuthHandler(MOCK_USERNAME, MOCK_PASSWORD)

    with aioresponses() as m:
        # Auth
        m.post(TOKEN_URL, payload=build_token_response())

        # Topology
        m.post(HOMESDATA_URL, payload=build_homesdata_response())

        # Status
        m.post(HOMESTATUS_URL, payload=build_homestatus_response())

        # Events
        m.post(GETEVENTS_URL, payload=build_events_response())

        # Execute full flow
        account = AsyncAccount(handler)
        await account.async_update_topology()

        assert len(account.homes) == 1
        assert account.user == MOCK_USERNAME

        status = await account.async_get_home_status(MOCK_HOME_ID)
        assert len(status["body"]["home"]["modules"]) == 3

        events = await account.async_get_events(MOCK_HOME_ID)
        assert len(events["body"]["home"]["events"]) == 1

    await handler.close_session()
