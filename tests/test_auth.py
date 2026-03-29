"""Tests for AuthHandler authentication and token management."""

import time

from aioresponses import aioresponses
import pytest

from pybticino import AuthHandler
from pybticino.exceptions import AuthError

from .conftest import (
    MOCK_ACCESS_TOKEN,
    MOCK_PASSWORD,
    MOCK_REFRESH_TOKEN,
    MOCK_USERNAME,
    TOKEN_URL,
    build_token_response,
)

# --- Authentication ---


async def test_authenticate_success():
    """Test successful authentication with username/password."""
    handler = AuthHandler(MOCK_USERNAME, MOCK_PASSWORD)

    with aioresponses() as m:
        m.post(TOKEN_URL, payload=build_token_response())

        token = await handler.get_access_token()

        assert token == MOCK_ACCESS_TOKEN
        assert handler._refresh_token == MOCK_REFRESH_TOKEN
        assert handler._token_expires_at is not None
        assert not handler._is_token_expired()

    await handler.close_session()


async def test_authenticate_invalid_credentials():
    """Test authentication failure with invalid credentials."""
    handler = AuthHandler(MOCK_USERNAME, "wrong_password")

    with aioresponses() as m:
        m.post(
            TOKEN_URL,
            status=400,
            payload={"error": "invalid_grant", "error_description": "Bad credentials"},
        )

        with pytest.raises(AuthError, match="Invalid credentials"):
            await handler.get_access_token()

    await handler.close_session()


async def test_authenticate_server_error():
    """Test authentication failure on server error."""
    handler = AuthHandler(MOCK_USERNAME, MOCK_PASSWORD)

    with aioresponses() as m:
        m.post(TOKEN_URL, status=500, body="Internal Server Error")

        with pytest.raises(AuthError):
            await handler.get_access_token()

    await handler.close_session()


async def test_authenticate_missing_tokens_in_response():
    """Test authentication failure when response lacks tokens."""
    handler = AuthHandler(MOCK_USERNAME, MOCK_PASSWORD)

    with aioresponses() as m:
        m.post(TOKEN_URL, payload={"status": "ok"})

        with pytest.raises(AuthError, match="Missing tokens"):
            await handler.get_access_token()

    await handler.close_session()


async def test_authenticate_network_error():
    """Test authentication failure on network error."""
    handler = AuthHandler(MOCK_USERNAME, MOCK_PASSWORD)

    with aioresponses() as m:
        from aiohttp import ClientConnectionError

        m.post(TOKEN_URL, exception=ClientConnectionError("Connection refused"))

        with pytest.raises(AuthError, match="Request error"):
            await handler.get_access_token()

    await handler.close_session()


# --- Token Refresh ---


async def test_token_refresh_on_expiry():
    """Test that expired token triggers a refresh."""
    handler = AuthHandler(MOCK_USERNAME, MOCK_PASSWORD)

    with aioresponses() as m:
        # Initial auth
        m.post(TOKEN_URL, payload=build_token_response())
        await handler.get_access_token()

        # Simulate token expiry
        handler._token_expires_at = time.time() - 10

        # Refresh
        new_token = "refreshed-token-new"
        m.post(
            TOKEN_URL,
            payload=build_token_response(access_token=new_token),
        )
        token = await handler.get_access_token()

        assert token == new_token

    await handler.close_session()


async def test_token_refresh_failure_falls_back_to_full_auth():
    """Test that refresh failure triggers full re-authentication."""
    handler = AuthHandler(MOCK_USERNAME, MOCK_PASSWORD)

    with aioresponses() as m:
        # Initial auth
        m.post(TOKEN_URL, payload=build_token_response())
        await handler.get_access_token()

        # Simulate token expiry
        handler._token_expires_at = time.time() - 10

        # Refresh fails
        m.post(TOKEN_URL, status=400, payload={"error": "invalid_grant"})

        # Full re-auth succeeds
        reauth_token = "reauth-token"
        m.post(TOKEN_URL, payload=build_token_response(access_token=reauth_token))

        token = await handler.get_access_token()
        assert token == reauth_token

    await handler.close_session()


async def test_token_not_expired_returns_cached():
    """Test that a valid token is returned without re-authenticating."""
    handler = AuthHandler(MOCK_USERNAME, MOCK_PASSWORD)

    with aioresponses() as m:
        m.post(TOKEN_URL, payload=build_token_response())
        token1 = await handler.get_access_token()

        # Second call should NOT make another HTTP request
        token2 = await handler.get_access_token()
        assert token1 == token2

    await handler.close_session()


# --- Token Expiry Check ---


def test_is_token_expired_no_expiry():
    """Test token is considered expired when no expiry is set."""
    handler = AuthHandler(MOCK_USERNAME, MOCK_PASSWORD)
    assert handler._is_token_expired() is True


def test_is_token_expired_within_buffer():
    """Test token is considered expired within 60s buffer."""
    handler = AuthHandler(MOCK_USERNAME, MOCK_PASSWORD)
    handler._token_expires_at = time.time() + 30  # Expires in 30s (within 60s buffer)
    assert handler._is_token_expired() is True


def test_is_token_not_expired():
    """Test token is valid when well within expiry."""
    handler = AuthHandler(MOCK_USERNAME, MOCK_PASSWORD)
    handler._token_expires_at = time.time() + 3600
    assert handler._is_token_expired() is False


# --- Session Management ---


async def test_close_managed_session():
    """Test closing an internally managed session."""
    handler = AuthHandler(MOCK_USERNAME, MOCK_PASSWORD)

    with aioresponses() as m:
        m.post(TOKEN_URL, payload=build_token_response())
        await handler.get_access_token()

    assert handler._managed_session is True
    await handler.close_session()
    assert handler._session is None


async def test_external_session_not_closed():
    """Test that externally provided session is not closed by handler."""
    import aiohttp

    external_session = aiohttp.ClientSession()
    handler = AuthHandler(MOCK_USERNAME, MOCK_PASSWORD, session=external_session)

    assert handler._managed_session is False
    await handler.close_session()
    # Session should still be open
    assert not external_session.closed
    await external_session.close()
