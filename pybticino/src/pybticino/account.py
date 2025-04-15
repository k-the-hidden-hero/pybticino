"""Represents a pybticino account."""

from __future__ import annotations

import asyncio  # Ensure asyncio is imported
import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import aiohttp

from .const import (
    BASE_URL,
    DEFAULT_APP_VERSION,
    DEFAULT_BUILD_NUMBER,
    DEFAULT_ANDROID_VERSION,
    DEFAULT_DEVICE_INFO,
    HOMESDATA_ENDPOINT,
    HOMESTATUS_ENDPOINT,
    SETSTATE_ENDPOINT,
    GETEVENTS_ENDPOINT,
    # Add other endpoints as needed
    build_user_agent,
)
from .exceptions import ApiError, AuthError
from .models import Home, Module  # Import basic models

# Import AuthHandler for runtime checks like isinstance
from .auth import AuthHandler

if TYPE_CHECKING:
    # Keep this for type hinting purposes
    from .auth import AuthHandler

LOG = logging.getLogger(__name__)

# Define default device types here or import from const if moved
DEFAULT_DEVICE_TYPES = [
    "BNMH",
    "BNCX",
    "BFII",
    "BPAC",
    "BPVC",
    "BNC1",
    "BDIY",
    "BNHY",
    "NACamera",
    "NOC",
    "NDB",
    "NSD",
    "NCO",
    "NDL",
]


class AsyncAccount:
    """Async class of a pybticino account, mirroring pyatmo structure."""

    def __init__(
        self,
        auth_handler: AuthHandler,
        app_version: str = DEFAULT_APP_VERSION,
        build_number: str = DEFAULT_BUILD_NUMBER,
        android_version: str = DEFAULT_ANDROID_VERSION,
        device_info: str = DEFAULT_DEVICE_INFO,
    ) -> None:
        """Initialize the account."""
        # Runtime check needs AuthHandler to be defined
        if not isinstance(auth_handler, AuthHandler):
            raise TypeError("auth_handler must be an instance of AuthHandler")
        self.auth_handler: AuthHandler = auth_handler
        self.user: Optional[str] = None  # Store user email if available
        self.homes: Dict[str, Home] = {}  # Store Home objects keyed by home_id
        self.raw_data: Dict[str, Any] = {}  # Store last raw homesdata response

        # Store User-Agent components
        self._app_version = app_version
        self._build_number = build_number
        self._android_version = android_version
        self._device_info = device_info

    async def _async_post_api_request(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        timeout: int = 15,
    ) -> Dict[str, Any]:
        """Make an authenticated async POST request."""
        try:
            access_token = await self.auth_handler.get_access_token()
        except AuthError as auth_err:
            LOG.error("Authentication required but failed: %s", auth_err)
            raise

        url = BASE_URL + endpoint
        user_agent = build_user_agent(
            app_version=self._app_version,
            build_number=self._build_number,
            android_version=self._android_version,
            device_info=self._device_info,
        )
        headers = {
            "Authorization": f"Bearer {access_token}",
            "User-Agent": user_agent,
            "Content-Type": "application/json; charset=utf-8",  # Assume JSON for POST
        }

        session = (
            await self.auth_handler._get_session()
        )  # Get session from auth handler

        LOG.debug("Making ASYNC POST request to %s", url)
        LOG.debug(
            "Headers: %s",
            {
                k: (v[:30] + "..." if k == "Authorization" else v)
                for k, v in headers.items()
            },
        )
        LOG.debug("Params: %s", params)
        LOG.debug("JSON Data: %s", json_data)

        try:
            async with session.post(
                url, headers=headers, params=params, json=json_data, timeout=timeout
            ) as response:
                LOG.debug("Response status code: %s", response.status)
                LOG.debug("Response headers: %s", response.headers)

                if response.status >= 400:
                    error_text = await response.text()
                    LOG.error(
                        "API Error Response (%s): %s", response.status, error_text
                    )
                    try:
                        # Try to parse specific error format
                        error_content = await response.json()
                        error_message = (
                            error_content.get("error", {}).get("message")
                            or error_content.get("error")
                            or error_text
                        )
                    except (aiohttp.ContentTypeError, ValueError):
                        error_message = error_text
                    raise ApiError(response.status, error_message)

                # Handle empty response body for certain status codes if necessary
                if response.status == 204:  # No Content
                    return {}  # Return empty dict for consistency

                # Assuming JSON response for successful calls
                return await response.json()

        except aiohttp.ClientResponseError as http_err:
            # This might be redundant if ApiError is raised above, but acts as a fallback
            LOG.error("HTTP error during API request: %s", http_err)
            if not isinstance(http_err, ApiError):
                raise ApiError(http_err.status, str(http_err)) from http_err
            else:
                raise  # Re-raise the original ApiError
        except asyncio.TimeoutError:
            LOG.error("Request timed out: POST %s", url)
            raise ApiError(408, "Request timed out")
        except aiohttp.ClientError as req_err:
            LOG.error("Request error during API request: %s", req_err)
            raise ApiError(0, f"Request error: {req_err}") from req_err
        except Exception as e:
            LOG.exception("Unexpected error during API request: %s", e)
            raise ApiError(0, f"Unexpected error: {e}") from e

    async def async_update_topology(
        self,
        device_types: Optional[List[str]] = None,
        # disabled_homes_ids: Optional[List[str]] = None, # Keep for future use?
    ) -> None:
        """Retrieve and process topology data from /homesdata."""
        if device_types is None:
            device_types = DEFAULT_DEVICE_TYPES

        payload = {
            "app_type": "app_camera",  # Keep this specific type for pybticino
            "app_version": self._app_version,
            "device_types": device_types,
            "sync_measurements": False,
        }

        homes_data = await self._async_post_api_request(
            endpoint=HOMESDATA_ENDPOINT, json_data=payload
        )

        # Basic processing similar to pyatmo
        self.raw_data = homes_data  # Store the raw response
        body = self.raw_data.get("body", {})
        self.user = body.get("user", {}).get("email")

        # Clear existing homes before processing new data
        self.homes.clear()

        for home_data in body.get("homes", []):
            home_id = home_data.get("id")
            if not home_id:
                LOG.warning("Skipping home with missing ID: %s", home_data.get("name"))
                continue

            # Create basic Module objects (can be refined later)
            modules = []
            for module_data in home_data.get("modules", []):
                mod_id = module_data.get("id")
                if not mod_id:
                    LOG.warning("Skipping module with missing ID in home %s", home_id)
                    continue
                modules.append(
                    Module(
                        id=mod_id,
                        name=module_data.get("name", "Unknown Module"),
                        type=module_data.get("type", "Unknown Type"),
                        bridge=module_data.get("bridge"),
                        raw_data=module_data,
                    )
                )

            # Create Home object
            self.homes[home_id] = Home(
                id=home_id,
                name=home_data.get("name", "Unknown Home"),
                modules=modules,
                raw_data=home_data,
            )
            LOG.debug("Processed home: %s (%s)", self.homes[home_id].name, home_id)

        LOG.info("Topology updated. Found %d homes.", len(self.homes))

    async def async_get_home_status(
        self, home_id: str, device_types: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Retrieve the status of modules for a specific home."""
        if home_id not in self.homes:
            LOG.error("Home ID %s not found in known homes.", home_id)
            # Or raise a specific error? For now, return empty dict.
            # raise ValueError(f"Home ID {home_id} not found.")
            return {}

        if device_types is None:
            device_types = DEFAULT_DEVICE_TYPES

        payload = {
            "app_type": "app_camera",  # Keep this specific type for pybticino
            "app_version": self._app_version,
            "home_id": home_id,
            "device_types": device_types,
        }

        # Note: Using the specific HOMESTATUS_ENDPOINT from pybticino's const.py
        status_data = await self._async_post_api_request(
            endpoint=HOMESTATUS_ENDPOINT, json_data=payload
        )

        # TODO: Process status_data and update self.homes[home_id].modules
        # For now, just return the raw data
        LOG.debug("Raw status data for home %s: %s", home_id, status_data)
        return status_data

    async def async_set_module_state(
        self,
        home_id: str,
        module_id: str,
        state: dict,
        timezone: str | None = None,  # Keep timezone optionality
        bridge_id: str | None = None,  # Keep bridge_id optionality
    ) -> Dict[str, Any]:
        """Set the state of a specific module (async version)."""
        # Basic validation
        if home_id not in self.homes:
            LOG.error("Home ID %s not found for setting state.", home_id)
            raise ValueError(f"Home ID {home_id} not found.")
        # We might not have the module object readily available without processing status first
        # For now, we proceed without checking module existence in self.homes[home_id].modules

        # Construct the module payload part (same logic as original)
        module_payload = {"id": module_id}
        module_payload.update(state)

        if bridge_id and module_id != bridge_id:
            module_payload["bridge"] = bridge_id
            LOG.debug(
                "Adding bridge ID %s to payload for module %s", bridge_id, module_id
            )
        elif bridge_id and module_id == bridge_id:
            LOG.debug(
                "Target module %s is the bridge, not adding bridge ID to payload.",
                module_id,
            )
        elif not bridge_id and "-" in module_id and ":" not in module_id:
            LOG.warning(
                "Setting state for potentially bridged module %s without explicit bridge ID. Call might fail.",
                module_id,
            )

        home_payload = {"id": home_id, "modules": [module_payload]}

        if timezone:
            home_payload["timezone"] = timezone
            LOG.debug("Adding timezone %s to home payload", timezone)
        else:
            # Keep the warning from original code
            LOG.warning(
                "Calling setstate without timezone. Call might fail based on logs."
            )

        payload = {
            "app_type": "app_camera",  # Keep this specific type for pybticino
            "app_version": self._app_version,
            "home": home_payload,
        }

        # Note: Using the specific SETSTATE_ENDPOINT from pybticino's const.py
        result = await self._async_post_api_request(
            endpoint=SETSTATE_ENDPOINT, json_data=payload
        )
        LOG.debug("Set state result: %s", result)
        return result

    async def async_get_events(self, home_id: str, size: int = 30) -> Dict[str, Any]:
        """Retrieve the event history for a specific home (async version)."""
        if home_id not in self.homes:
            LOG.error("Home ID %s not found for getting events.", home_id)
            # raise ValueError(f"Home ID {home_id} not found.")
            return {}  # Return empty dict or raise?

        payload = {
            "app_type": "app_camera",  # Keep this specific type for pybticino
            "app_version": self._app_version,
            "home_id": home_id,
            "size": size,
        }

        # Note: Using the specific GETEVENTS_ENDPOINT from pybticino's const.py
        events_data = await self._async_post_api_request(
            endpoint=GETEVENTS_ENDPOINT, json_data=payload
        )

        # TODO: Process events_data and potentially store in self.homes[home_id] or return Event objects
        # For now, just return the raw data
        LOG.debug("Raw events data for home %s: %s", home_id, events_data)
        return events_data

    # --- Add other account-level methods here ---
