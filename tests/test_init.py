"""Tests for setting up the Royal Mail integration."""

from unittest.mock import MagicMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.royalmail.api import (
    CannotConnect,
    CaptchaRequired,
    InvalidAuth,
    RateLimited,
)
from custom_components.royalmail.const import CONF_SESSION, DATA_LOGIN_THROTTLE, DOMAIN

from .conftest import PASSWORD, SESSION, USER_ID, USERNAME


def legacy_entry(email: str) -> MockConfigEntry:
    """Return an entry from a version that identified accounts by email."""
    return MockConfigEntry(
        domain=DOMAIN,
        title=email,
        unique_id=email,
        version=1,
        minor_version=2,
        data={CONF_USERNAME: email, CONF_PASSWORD: PASSWORD, CONF_SESSION: SESSION},
    )


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
    mock_client_class.assert_called_once_with(
        USERNAME, PASSWORD, SESSION, login_throttle=hass.data[DATA_LOGIN_THROTTLE]
    )
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
    assert entry.unique_id == USER_ID
    # Setting up then saved the new website session alongside the login.
    assert entry.data == {
        CONF_USERNAME: USERNAME,
        CONF_PASSWORD: PASSWORD,
        CONF_SESSION: mock_client.state,
    }
    mock_client_class.assert_called_once_with(
        USERNAME, PASSWORD, None, login_throttle=hass.data[DATA_LOGIN_THROTTLE]
    )


async def test_adopt_account_number(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    device_registry: dr.DeviceRegistry,
    mock_client: MagicMock,
) -> None:
    """Test an entry identified by email moves to the account number in place."""
    entry = legacy_entry("User@Example.com")
    entry.add_to_hass(hass)
    device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "User@Example.com")},
        name="Royal Mail",
    )
    device_registry.async_update_device(device.id, name_by_user="Front door")

    def register(unique_id: str, object_id: str) -> er.RegistryEntry:
        return entity_registry.async_get_or_create(
            SENSOR_DOMAIN,
            DOMAIN,
            unique_id,
            suggested_object_id=object_id,
            config_entry=entry,
            device_id=device.id,
        )

    total = register("royalmail-user@example.com-tracked_parcels", "parcels")
    kettle = register("royalmail-user@example.com-ab123456789gb", "kettle")
    stray = register("something-else", "stray")

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert entry.unique_id == USER_ID
    assert entry.title == "User@Example.com"
    total_entry = entity_registry.async_get(total.entity_id)
    assert total_entry is not None
    assert total_entry.unique_id == f"royalmail-{USER_ID}-tracked_parcels"
    kettle_entry = entity_registry.async_get(kettle.entity_id)
    assert kettle_entry is not None
    assert kettle_entry.unique_id == f"royalmail-{USER_ID}-ab123456789gb"
    assert hass.states.get(kettle.entity_id).state == "delivered"
    # Only the integration's own unique IDs are rewritten; this one is pruned.
    assert entity_registry.async_get(stray.entity_id) is None
    moved = device_registry.async_get(device.id)
    assert moved is not None
    assert moved.identifiers == {(DOMAIN, USER_ID)}
    assert moved.name_by_user == "Front door"
    assert dr.async_entries_for_config_entry(device_registry, entry.entry_id) == [moved]


async def test_duplicate_account(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Test an old entry for an account that's already set up isn't merged."""
    mock_config_entry.add_to_hass(hass)
    entry = legacy_entry("old-address@example.com")
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert entry.error_reason_translation_key == "duplicate_account"
    assert entry.unique_id == "old-address@example.com"


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
