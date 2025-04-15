"""Async Authentication handler for pybticino."""

import logging
import time
from typing import Optional

import aiohttp

from .const import (
    BASE_URL,
    DEFAULT_APP_VERSION,
    DEFAULT_SCOPE,
    TOKEN_ENDPOINT,
    get_client_id,
    get_client_secret,
)
from .exceptions import ApiError, AuthError

_LOGGER = logging.getLogger(__name__)


class AuthHandler:
    """Handles async authentication and token management using aiohttp."""

    def __init__(
        self,
        username: str,
        password: str,
        scope: str = DEFAULT_SCOPE,
        app_version: str = DEFAULT_APP_VERSION,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> None:
        """Initialize the authentication handler."""
        self._username = username
        self._password = password
        self._client_id = get_client_id()
        self._client_secret = get_client_secret()
        self._scope = scope
        self._app_version = app_version
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._token_expires_at: Optional[float] = None
        # Use provided session or create a new one
        self._session = session
        self._managed_session = (
            session is None
        )  # Flag to know if we should close the session

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create the aiohttp session."""
        if self._session is None or self._session.closed:
            _LOGGER.debug("Creating new aiohttp ClientSession for AuthHandler.")
            self._session = aiohttp.ClientSession()
            self._managed_session = True  # We created it, so we manage it
        return self._session

    async def close_session(self) -> None:
        """Close the aiohttp session if it's managed by this instance."""
        if self._session and not self._session.closed and self._managed_session:
            await self._session.close()
            self._session = None
            _LOGGER.debug("Managed aiohttp session closed by AuthHandler.")
        elif self._session and not self._managed_session:
            _LOGGER.debug("Session provided externally, not closing.")

    def _is_token_expired(self) -> bool:
        """Check if the access token is expired or close to expiring."""
        if not self._token_expires_at:
            return True
        return time.time() >= (self._token_expires_at - 60)

    async def get_access_token(self) -> str:
        """Return the current access token, refreshing if necessary."""
        if self._is_token_expired():
            _LOGGER.debug("Token is expired or nearing expiration.")
            if self._refresh_token:
                try:
                    await self._refresh_access_token()
                except AuthError:
                    _LOGGER.warning(
                        "Token refresh failed, attempting full authentication.",
                    )
                    await self.authenticate()  # Fallback to full auth
            else:
                _LOGGER.debug(
                    "No refresh token available, performing full authentication.",
                )
                await self.authenticate()
        elif not self._access_token:
            _LOGGER.debug("No access token found, performing full authentication.")
            await self.authenticate()

        if not self._access_token:
            # Should not happen if authenticate/refresh worked, but safety check
            err_msg = "Failed to obtain a valid access token."
            raise AuthError(err_msg)

        return self._access_token

    async def authenticate(self) -> None:
        """Perform authentication to get access and refresh tokens."""
        url = BASE_URL + TOKEN_ENDPOINT
        payload = {
            "grant_type": "password",
            "username": self._username,
            "password": self._password,
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "scope": self._scope,
            "app_version": self._app_version,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        session = await self._get_session()

        try:
            _LOGGER.debug("Requesting token from %s", url)
            async with session.post(
                url,
                data=payload,
                headers=headers,
                timeout=10,
            ) as response:
                if response.status >= 400:
                    error_text = await response.text()
                    _LOGGER.error(
                        "HTTP error %s during authentication: %s",
                        response.status,
                        error_text,
                    )
                    try:
                        error_data = await response.json()
                        if (
                            response.status == 400
                            and error_data.get("error") == "invalid_grant"
                        ):
                            err_msg = (
                                "Authentication failed: Invalid credentials or grant"
                            )
                            raise AuthError(err_msg)
                        # Raise generic ApiError for other 4xx/5xx based on JSON if possible
                        raise ApiError(
                            response.status,
                            error_data.get("error", error_text),
                        )
                    except (
                        aiohttp.ContentTypeError,
                        ValueError,
                    ) as parse_err:  # Handle non-JSON errors
                        raise ApiError(response.status, error_text) from parse_err

                token_data = await response.json()
                _LOGGER.debug("Token response received: %s", token_data)

                if (
                    "access_token" not in token_data
                    or "refresh_token" not in token_data
                ):
                    err_msg = "Authentication failed: Missing tokens in response"
                    raise AuthError(err_msg)  # noqa: TRY301

                self._access_token = token_data["access_token"]
                self._refresh_token = token_data["refresh_token"]
                expires_in = token_data.get("expires_in")
                if expires_in:
                    self._token_expires_at = time.time() + int(expires_in)
                    _LOGGER.debug("Token expires at: %s", self._token_expires_at)
                else:
                    self._token_expires_at = None
                    _LOGGER.warning("No 'expires_in' found in token response.")
                _LOGGER.info("Authentication successful. Access token obtained.")

        except aiohttp.ClientError as req_err:
            _LOGGER.exception("Request error during authentication")
            err_msg = f"Authentication failed: Request error - {req_err}"
            raise AuthError(err_msg) from req_err
        except TimeoutError as timeout_err:
            _LOGGER.exception("Timeout during authentication request")
            err_msg = "Authentication failed: Request timed out"
            raise AuthError(err_msg) from timeout_err
        except Exception as e:
            _LOGGER.exception("Unexpected error during authentication")
            err_msg = f"Authentication failed: Unexpected error - {e}"
            raise AuthError(err_msg) from e

    async def _refresh_access_token(self) -> None:
        """Refresh the access token using the refresh token."""
        if not self._refresh_token:
            err_msg = "Cannot refresh token: No refresh token available."
            raise AuthError(err_msg)

        url = BASE_URL + TOKEN_ENDPOINT
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": self._refresh_token,
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        session = await self._get_session()

        try:
            _LOGGER.info("Refreshing access token...")
            async with session.post(
                url,
                data=payload,
                headers=headers,
                timeout=10,
            ) as response:
                if response.status >= 400:
                    error_text = await response.text()
                    _LOGGER.error(
                        "HTTP error %s during token refresh: %s",
                        response.status,
                        error_text,
                    )
                    # Clear tokens on persistent refresh failure (like invalid grant)
                    self._access_token = None
                    self._refresh_token = None
                    self._token_expires_at = None
                    try:
                        error_data = await response.json()
                        if response.status == 400 and error_data.get("error") in [
                            "invalid_grant",
                            "invalid_request",
                        ]:
                            err_msg = f"Token refresh failed: {error_data.get('error')}"
                            raise AuthError(err_msg)
                        raise ApiError(
                            response.status,
                            error_data.get("error", error_text),
                        )
                    except (aiohttp.ContentTypeError, ValueError) as parse_err:
                        err_msg = f"Token refresh failed: HTTP {response.status} - {error_text}"
                        # Distinguish parsing error from original HTTP error
                        raise AuthError(err_msg) from parse_err

                token_data = await response.json()
                _LOGGER.debug("Token refresh response received: %s", token_data)

                if "access_token" not in token_data:
                    self._access_token = None
                    self._refresh_token = None
                    self._token_expires_at = None
                    err_msg = "Token refresh failed: Missing access token in response"
                    raise AuthError(err_msg)  # noqa: TRY301

                self._access_token = token_data["access_token"]
                self._refresh_token = token_data.get(
                    "refresh_token",
                    self._refresh_token,
                )
                expires_in = token_data.get("expires_in")
                if expires_in:
                    self._token_expires_at = time.time() + int(expires_in)
                    _LOGGER.debug(
                        "Refreshed token expires at: %s",
                        self._token_expires_at,
                    )
                else:
                    self._token_expires_at = None
                    _LOGGER.warning("No 'expires_in' found in token refresh response.")
                _LOGGER.info("Access token refreshed successfully.")

        except aiohttp.ClientError as req_err:
            _LOGGER.exception("Request error during token refresh")
            # Don't clear tokens on temporary network errors
            err_msg = f"Token refresh failed: Request error - {req_err}"
            raise AuthError(err_msg) from req_err
        except TimeoutError as timeout_err:
            _LOGGER.exception("Timeout during token refresh request")
            err_msg = "Token refresh failed: Request timed out"
            raise AuthError(err_msg) from timeout_err
        except Exception as e:
            _LOGGER.exception("Unexpected error during token refresh")
            # Don't clear tokens on unknown errors
            err_msg = f"Token refresh failed: Unexpected error - {e}"
            raise AuthError(err_msg) from e
