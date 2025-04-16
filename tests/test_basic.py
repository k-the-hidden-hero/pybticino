"""Basic structural and import tests for pybticino."""

import pytest


# 1. Test Main Imports
def test_main_imports():
    """Test that main components can be imported from the top level."""
    try:
        from pybticino import (  # noqa: F401
            ApiError,
            AsyncAccount,
            AuthError,
            AuthHandler,
            Event,
            Home,
            Module,
            PyBticinoException,
            WebsocketClient,
            __version__,
        )
    except ImportError as e:
        pytest.fail(f"Failed to import one or more main components: {e}")
    # Basic check on version format
    assert isinstance(__version__, str) and "." in __version__


# 2. Test Core Class Instantiation
def test_authhandler_instantiation():
    """Test that AuthHandler can be instantiated."""
    from pybticino import AuthHandler

    try:
        handler = AuthHandler("user", "pass")
        assert handler is not None
    except Exception as e:
        pytest.fail(f"Failed to instantiate AuthHandler: {e}")


def test_asyncaccount_instantiation():
    """Test that AsyncAccount can be instantiated with an AuthHandler."""
    from pybticino import AsyncAccount, AuthHandler

    try:
        # Use a real AuthHandler instance for the type check in AsyncAccount init
        handler = AuthHandler("user", "pass")
        account = AsyncAccount(handler)
        assert account is not None
    except Exception as e:
        pytest.fail(f"Failed to instantiate AsyncAccount: {e}")


async def dummy_callback(message: dict):
    """Dummy async callback for websocket test."""


def test_websocketclient_instantiation():
    """Test that WebsocketClient can be instantiated."""
    from pybticino import AuthHandler, WebsocketClient

    try:
        handler = AuthHandler("user", "pass")
        ws_client = WebsocketClient(handler, dummy_callback)
        assert ws_client is not None
    except Exception as e:
        pytest.fail(f"Failed to instantiate WebsocketClient: {e}")


# 3. Test Data Model Instantiation
def test_module_instantiation():
    """Test that Module dataclass can be instantiated."""
    from pybticino import Module

    try:
        module = Module(id="12:34", name="Test Module", type="BNDL")
        assert module.id == "12:34"
        assert module.name == "Test Module"
        assert module.type == "BNDL"
        assert module.bridge is None
        assert isinstance(module.raw_data, dict)
    except Exception as e:
        pytest.fail(f"Failed to instantiate Module: {e}")


def test_home_instantiation():
    """Test that Home dataclass can be instantiated."""
    from pybticino import Home, Module

    try:
        module1 = Module(id="1", name="Mod1", type="T1")
        home = Home(id="H1", name="Test Home", modules=[module1])
        assert home.id == "H1"
        assert home.name == "Test Home"
        assert len(home.modules) == 1
        assert home.modules[0] == module1
        assert isinstance(home.raw_data, dict)
    except Exception as e:
        pytest.fail(f"Failed to instantiate Home: {e}")


def test_event_instantiation():
    """Test that Event dataclass can be instantiated."""
    from pybticino import Event

    try:
        event = Event(id="E1", type="doorbell", time=1234567890)
        assert event.id == "E1"
        assert event.type == "doorbell"
        assert event.time == 1234567890
        assert isinstance(event.raw_data, dict)
    except Exception as e:
        pytest.fail(f"Failed to instantiate Event: {e}")


# 4. Test Utility Functions from const.py
def test_get_client_id():
    """Test the get_client_id function."""
    from pybticino.const import get_client_id

    client_id = get_client_id()
    assert isinstance(client_id, str)
    assert "na_client_" in client_id  # Check for expected substring


def test_build_user_agent():
    """Test the build_user_agent function."""
    from pybticino.const import build_user_agent

    ua = build_user_agent()
    assert isinstance(ua, str)
    assert "NetatmoApp" in ua
    assert "Android" in ua
    # Test with custom args
    custom_ua = build_user_agent(
        app_version="1.0",
        build_number="100",
        android_version="10",
        device_info="TestDevice",
    )
    assert "v1.0/100" in custom_ua
    assert "(10/TestDevice)" in custom_ua


# 5. Test Custom Exceptions
def test_custom_exceptions():
    """Test that custom exceptions can be raised and caught."""
    from pybticino import ApiError, AuthError, PyBticinoException

    with pytest.raises(PyBticinoException):
        raise PyBticinoException("Base exception test")

    with pytest.raises(AuthError):
        raise AuthError("Auth error test")

    with pytest.raises(ApiError) as excinfo:
        raise ApiError(404, "Not Found test")
    assert excinfo.value.status_code == 404
    assert "Not Found test" in str(excinfo.value)
    assert issubclass(AuthError, PyBticinoException)
    assert issubclass(ApiError, PyBticinoException)
