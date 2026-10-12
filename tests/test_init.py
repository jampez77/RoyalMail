"""Tests for setting up the Royal Mail integration."""

from unittest.mock import MagicMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from custom_components.royalmail.api import (
    CannotConnect,
    CaptchaRequired,
    InvalidAuth,
    RateLimited,
)
from custom_components.royalmail.const import CONF_SESSION, DOMAIN

from .conftest import PASSWORD, SESSION, USERNAME


async def test_setup_and_unload(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client_class: MagicMock,
    mock_client: MagicMock,
) -> None:
    """Test the entry resumes the saved session and closes it on unload."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED
    mock_client_class.assert_called_once_with(USERNAME, PASSWORD, SESSION)
    mock_client.async_get_parcels.assert_awaited_once()

    await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED
    mock_client.async_close.assert_awaited_once()


@pytest.mark.parametrize(
    "error", [CannotConnect("boom"), CaptchaRequired("captcha"), RateLimited("slow")]
)
async def test_setup_retry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: MagicMock,
    error: Exception,
) -> None:
    """Test setup is retried when Royal Mail can't be read."""
    mock_client.async_get_parcels.side_effect = error
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY
    # The failed attempt still closes its HTTP session.
    mock_client.async_close.assert_awaited_once()


async def test_setup_auth_failed(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Test a rejected password starts reauthentication."""
    mock_client.async_get_parcels.side_effect = InvalidAuth("nope")
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert len(flows) == 1
    assert flows[0]["context"]["source"] == SOURCE_REAUTH
    assert flows[0]["context"]["entry_id"] == mock_config_entry.entry_id


async def test_session_saved_when_it_changes(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Test a new token is written back to the entry, and nothing else is."""
    mock_client.state = {**SESSION, "jwt": "new-token", "cookies": [{"name": "a"}]}
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.data == {
        CONF_USERNAME: USERNAME,
        CONF_PASSWORD: PASSWORD,
        CONF_SESSION: mock_client.state,
    }


async def test_cookie_refresh_alone_is_not_saved(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Test cookie churn doesn't rewrite the config entry on every poll."""
    mock_client.state = {**SESSION, "cookies": [{"name": "a"}]}
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.data[CONF_SESSION] == SESSION


@pytest.mark.parametrize("unique_id", [None, USERNAME])
async def test_migrate_from_app_api(
    hass: HomeAssistant,
    mock_client_class: MagicMock,
    mock_client: MagicMock,
    unique_id: str | None,
) -> None:
    """Test 1.1 entries drop the app API tokens and keep the login."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=USERNAME,
        unique_id=unique_id,
        version=1,
        minor_version=1,
        data={
            CONF_USERNAME: USERNAME,
            CONF_PASSWORD: PASSWORD,
            "access_token": "old",
            "refresh_token": "old",
            "guid": "old",
        },
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert entry.minor_version == 2
    assert entry.unique_id == USERNAME
    # Setting up then saved the new website session alongside the login.
    assert entry.data == {
        CONF_USERNAME: USERNAME,
        CONF_PASSWORD: PASSWORD,
        CONF_SESSION: mock_client.state,
    }
    mock_client_class.assert_called_once_with(USERNAME, PASSWORD, None)


async def test_migrate_from_future_version(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    """Test entries from a newer version are left alone."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=USERNAME,
        version=2,
        data={CONF_USERNAME: USERNAME, CONF_PASSWORD: PASSWORD},
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.MIGRATION_ERROR
