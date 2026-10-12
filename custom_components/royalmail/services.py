"""Actions for the Royal Mail integration."""

import re
from typing import Any

import probatio

from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv, service

from .const import (
    ATTR_REFERENCE_NUMBER,
    DOMAIN,
    SERVICE_STOP_TRACKING_ITEM,
    SERVICE_TRACK_ITEM,
)
from .coordinator import RoyalMailConfigEntry, RoyalMailCoordinator

_REFERENCE = re.compile(r"[A-Z0-9]{8,40}")


def _reference_number(value: Any) -> str:
    """Normalise a tracking reference the way the website does."""
    reference = re.sub(r"\s+", "", cv.string(value)).upper()
    if not _REFERENCE.fullmatch(reference):
        raise probatio.Invalid("Not a Royal Mail reference number")
    return reference


SERVICE_SCHEMA = probatio.Schema(
    {probatio.Required(ATTR_REFERENCE_NUMBER): _reference_number}
)


def _coordinator(call: ServiceCall) -> RoyalMailCoordinator:
    entry: RoyalMailConfigEntry = service.async_get_config_entry(
        call.hass, DOMAIN, None
    )
    return entry.runtime_data


async def _async_track_item(call: ServiceCall) -> None:
    """Add an item to the account's tracked items."""
    await _coordinator(call).async_track(call.data[ATTR_REFERENCE_NUMBER])


async def _async_stop_tracking_item(call: ServiceCall) -> None:
    """Remove an item from the account's tracked items."""
    coordinator = _coordinator(call)
    reference: str = call.data[ATTR_REFERENCE_NUMBER]
    if reference not in coordinator.data:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="not_tracked",
            translation_placeholders={"reference": reference},
        )
    await coordinator.async_remove(reference)


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the Royal Mail actions."""
    hass.services.async_register(
        DOMAIN, SERVICE_TRACK_ITEM, _async_track_item, schema=SERVICE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_STOP_TRACKING_ITEM,
        _async_stop_tracking_item,
        schema=SERVICE_SCHEMA,
    )
