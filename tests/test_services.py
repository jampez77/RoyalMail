"""Tests for the Royal Mail actions."""

from unittest.mock import MagicMock

import probatio
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.config_entries import SOURCE_REAUTH
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from custom_components.royalmail.api import (
    CannotConnect,
    CaptchaRequired,
    InvalidAuth,
    RateLimited,
)
from custom_components.royalmail.const import (
    ATTR_REFERENCE_NUMBER,
    DOMAIN,
    SERVICE_STOP_TRACKING_ITEM,
    SERVICE_TRACK_ITEM,
)

pytestmark = pytest.mark.usefixtures("init_integration")


async def _call(hass: HomeAssistant, service: str, reference: str) -> None:
    await hass.services.async_call(
        DOMAIN, service, {ATTR_REFERENCE_NUMBER: reference}, blocking=True
    )


async def test_track_item(hass: HomeAssistant, mock_client: MagicMock) -> None:
    """Test tracking an item looks it up and refreshes the history."""
    await _call(hass, SERVICE_TRACK_ITEM, " gh22 2222 222gb ")

    mock_client.async_track.assert_awaited_once_with("GH222222222GB")
    assert mock_client.async_get_parcels.await_count == 2


async def test_stop_tracking_item(hass: HomeAssistant, mock_client: MagicMock) -> None:
    """Test removing an item from the history."""
    await _call(hass, SERVICE_STOP_TRACKING_ITEM, "ab123456789gb")

    mock_client.async_remove.assert_awaited_once_with(["AB123456789GB"])
    assert mock_client.async_get_parcels.await_count == 2


async def test_stop_tracking_unknown_item(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    """Test removing an item that isn't tracked is refused."""
    with pytest.raises(ServiceValidationError) as err:
        await _call(hass, SERVICE_STOP_TRACKING_ITEM, "ZZ000000000GB")

    assert err.value.translation_key == "not_tracked"
    assert err.value.translation_placeholders == {"reference": "ZZ000000000GB"}
    mock_client.async_remove.assert_not_awaited()


@pytest.mark.parametrize("reference", ["", "abc", "AB-123456789GB", 12])
async def test_invalid_reference(
    hass: HomeAssistant, mock_client: MagicMock, reference: str
) -> None:
    """Test references that aren't Royal Mail ones are rejected."""
    with pytest.raises(probatio.Invalid):
        await _call(hass, SERVICE_TRACK_ITEM, reference)

    mock_client.async_track.assert_not_awaited()


@pytest.mark.parametrize(
    ("error", "translation_key"),
    [
        (CaptchaRequired("captcha"), "captcha_required"),
        (RateLimited("slow down"), "rate_limited"),
        (CannotConnect("boom"), "cannot_connect"),
    ],
)
async def test_track_item_errors(
    hass: HomeAssistant,
    mock_client: MagicMock,
    error: Exception,
    translation_key: str,
) -> None:
    """Test Royal Mail errors are raised as translated errors."""
    mock_client.async_track.side_effect = error

    with pytest.raises(HomeAssistantError) as err:
        await _call(hass, SERVICE_TRACK_ITEM, "GH222222222GB")

    assert err.value.translation_key == translation_key
    assert mock_client.async_get_parcels.await_count == 1


async def test_track_item_auth_failed(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Test a rejected password during an action starts reauthentication."""
    mock_client.async_remove.side_effect = InvalidAuth("nope")

    with pytest.raises(HomeAssistantError) as err:
        await _call(hass, SERVICE_STOP_TRACKING_ITEM, "AB123456789GB")

    assert err.value.translation_key == "invalid_auth"
    await hass.async_block_till_done()
    flows = hass.config_entries.flow.async_progress()
    assert [flow["context"]["source"] for flow in flows] == [SOURCE_REAUTH]
    assert flows[0]["context"]["entry_id"] == mock_config_entry.entry_id


async def test_entry_not_loaded(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Test actions explain that the integration isn't running."""
    await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    with pytest.raises(ServiceValidationError) as err:
        await _call(hass, SERVICE_TRACK_ITEM, "GH222222222GB")

    assert err.value.translation_key == "service_config_entry_not_loaded"
    mock_client.async_track.assert_not_awaited()
