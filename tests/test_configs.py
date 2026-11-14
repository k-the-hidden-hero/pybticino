"""Tests for module config endpoints."""

from unittest.mock import AsyncMock

import pytest

from pybticino.account import AsyncAccount
from pybticino.const import GETCONFIGS_ENDPOINT, SETCONFIGS_ENDPOINT


@pytest.mark.asyncio
async def test_async_get_module_configs_builds_payload(auth_handler):
    """Test getconfigs payload."""
    account = AsyncAccount(auth_handler)
    account.homes = {"home-1": object()}

    account._async_post_api_request = AsyncMock(return_value={"status": "ok"})

    result = await account.async_get_module_configs(
        home_id="home-1",
        module_ids=["module-1"],
    )

    assert result == {"status": "ok"}
    account._async_post_api_request.assert_awaited_once_with(
        endpoint=GETCONFIGS_ENDPOINT,
        json_data={
            "module_ids": ["module-1"],
            "home_id": "home-1",
            "app_identifier": "app_camera",
        },
    )


@pytest.mark.asyncio
async def test_async_set_module_configs_builds_payload(auth_handler, monkeypatch):
    """Test setconfigs payload."""
    account = AsyncAccount(auth_handler)
    account.homes = {"home-1": object()}

    account._async_post_api_request = AsyncMock(return_value={"status": "ok"})

    monkeypatch.setattr("pybticino.account.time.time", lambda: 1234.567)

    result = await account.async_set_module_configs(
        home_id="home-1",
        module_id="module-1",
        module_type="BNC3",
        configs={
            "do_not_disturb": {
                "dnd_mode": 3,
                "dnd_enabled": True,
            }
        },
    )

    assert result == {"status": "ok"}
    account._async_post_api_request.assert_awaited_once_with(
        endpoint=SETCONFIGS_ENDPOINT,
        json_data={
            "app_identifier": "app_camera",
            "home": {
                "id": "home-1",
                "modules": [
                    {
                        "id": "module-1",
                        "type": "BNC3",
                        "last_configs_update": 1234567,
                        "do_not_disturb": {
                            "dnd_mode": 3,
                            "dnd_enabled": True,
                        },
                    }
                ],
            },
        },
    )


@pytest.mark.asyncio
async def test_async_get_do_not_disturb_config_returns_config(auth_handler):
    """Test extracting do_not_disturb config."""
    account = AsyncAccount(auth_handler)
    account.homes = {"home-1": object()}

    account.async_get_module_configs = AsyncMock(
        return_value={
            "status": "ok",
            "body": {
                "home": {
                    "modules": [
                        {
                            "id": "module-1",
                            "do_not_disturb": {
                                "dnd_enabled": True,
                                "dnd_mode": 2,
                            },
                        }
                    ]
                }
            },
        }
    )

    result = await account.async_get_do_not_disturb_config(
        home_id="home-1",
        module_id="module-1",
    )

    assert result == {
        "dnd_enabled": True,
        "dnd_mode": 2,
    }


@pytest.mark.asyncio
async def test_async_set_do_not_disturb_config_wraps_config(auth_handler):
    """Test setting do_not_disturb config."""
    account = AsyncAccount(auth_handler)

    account.async_set_module_configs = AsyncMock(return_value={"status": "ok"})

    result = await account.async_set_do_not_disturb_config(
        home_id="home-1",
        module_id="module-1",
        module_type="BNC3",
        dnd_config={
            "dnd_enabled": True,
            "dnd_mode": 3,
        },
    )

    assert result == {"status": "ok"}
    account.async_set_module_configs.assert_awaited_once_with(
        home_id="home-1",
        module_id="module-1",
        module_type="BNC3",
        configs={
            "do_not_disturb": {
                "dnd_enabled": True,
                "dnd_mode": 3,
            },
        },
    )
