"""Shared fixtures for pybticino tests."""

import pytest

from pybticino import AuthHandler
from pybticino.const import BASE_URL, GETEVENTS_ENDPOINT, HOMESDATA_ENDPOINT, HOMESTATUS_ENDPOINT, SETSTATE_ENDPOINT

# --- Test data ---

MOCK_USERNAME = "user@example.com"
MOCK_PASSWORD = "secret123"
MOCK_ACCESS_TOKEN = "mock-access-token-abc123"
MOCK_REFRESH_TOKEN = "mock-refresh-token-xyz789"
MOCK_HOME_ID = "home_test_001"
MOCK_HOME_NAME = "Casa Test"
MOCK_BRIDGE_ID = "AA:BB:CC:DD:EE:FF"
MOCK_LOCK_ID = "module_lock_1"
MOCK_LIGHT_ID = "module_light_1"

TOKEN_URL = BASE_URL + "/oauth2/token"
HOMESDATA_URL = BASE_URL + HOMESDATA_ENDPOINT
HOMESTATUS_URL = BASE_URL + HOMESTATUS_ENDPOINT
SETSTATE_URL = BASE_URL + SETSTATE_ENDPOINT
GETEVENTS_URL = BASE_URL + GETEVENTS_ENDPOINT


def build_token_response(
    access_token=MOCK_ACCESS_TOKEN,
    refresh_token=MOCK_REFRESH_TOKEN,
    expires_in=3600,
):
    """Build a mock OAuth2 token response."""
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": expires_in,
        "token_type": "Bearer",
        "scope": "security_scopes",
    }


def build_homesdata_response():
    """Build a mock /api/homesdata response."""
    return {
        "body": {
            "user": {"email": MOCK_USERNAME},
            "homes": [
                {
                    "id": MOCK_HOME_ID,
                    "name": MOCK_HOME_NAME,
                    "modules": [
                        {
                            "id": MOCK_BRIDGE_ID,
                            "name": "Bridge",
                            "type": "BNCX",
                            "firmware_name": "2.1.0",
                        },
                        {
                            "id": MOCK_LOCK_ID,
                            "name": "Front Door Lock",
                            "type": "BNDL",
                            "variant": "xxx:bndl_doorlock",
                            "bridge": MOCK_BRIDGE_ID,
                        },
                        {
                            "id": MOCK_LIGHT_ID,
                            "name": "Staircase Light",
                            "type": "BNSL",
                            "variant": "xxx:bnsl_staircase_light",
                            "bridge": MOCK_BRIDGE_ID,
                        },
                    ],
                },
            ],
        },
        "status": "ok",
    }


def build_homestatus_response():
    """Build a mock /syncapi/v1/homestatus response."""
    return {
        "body": {
            "home": {
                "id": MOCK_HOME_ID,
                "modules": [
                    {"id": MOCK_LOCK_ID, "lock": True, "reachable": True},
                    {"id": MOCK_LIGHT_ID, "status": "off", "reachable": True},
                    {"id": MOCK_BRIDGE_ID, "wifi_strength": 65, "uptime": 86400},
                ],
            },
        },
        "status": "ok",
    }


def build_events_response():
    """Build a mock /api/getevents response."""
    return {
        "body": {
            "home": {
                "id": MOCK_HOME_ID,
                "events": [
                    {
                        "id": "evt_1",
                        "type": "call",
                        "module_id": "module_ext_unit_1",
                        "time": 1700000000,
                        "subevents": [
                            {
                                "type": "missed_call",
                                "time": 1700000050,
                            }
                        ],
                    },
                ],
            },
        },
        "status": "ok",
    }


@pytest.fixture
def auth_handler():
    """Create an AuthHandler instance for testing."""
    return AuthHandler(MOCK_USERNAME, MOCK_PASSWORD)
