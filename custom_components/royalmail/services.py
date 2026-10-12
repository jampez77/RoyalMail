"""Actions for the Royal Mail integration."""

import re
from typing import Any

import probatio

from homeassistant.const import ATTR_CONFIG_ENTRY_ID
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
    {
        probatio.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        probatio.Required(ATTR_REFERENCE_NUMBER): _reference_number,
    }
)


def _coordinator(call: ServiceCall) -> RoyalMailCoordinator:
    """Return the chosen account, or the only one if none was chosen."""
    entry: RoyalMailConfigEntry = service.async_get_config_entry(
        call.hass, DOMAIN, call.data.get(ATTR_CONFIG_ENTRY_ID)
    )
    return entry.runtime_data


def _coordinator_tracking(call: ServiceCall, reference: str) -> RoyalMailCoordinator:
    """Return the account that tracks an item.

    With several accounts and none chosen, look for the item in each of them.
    """
    config_entries = call.hass.config_entries
    accounts = config_entries.async_entries(
        DOMAIN, include_ignore=False, include_disabled=False
    )
    if ATTR_CONFIG_ENTRY_ID in call.data or len(accounts) <= 1:
        candidates = [_coordinator(call)]
    else:
        candidates = [
            entry.runtime_data for entry in config_entries.async_loaded_entries(DOMAIN)
        ]
    matches = [c for c in candidates if reference in c.data]
    if not matches:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="not_tracked",
            translation_placeholders={"reference": reference},
        )
    if len(matches) > 1:
        # Never remove an item from more than one account at once.
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="tracked_in_several_accounts",
            translation_placeholders={
                "reference": reference,
                "accounts": ", ".join(c.config_entry.title for c in matches),
            },
        )
    return matches[0]


async def _async_track_item(call: ServiceCall) -> None:
    """Add an item to the account's tracked items."""
    await _coordinator(call).async_track(call.data[ATTR_REFERENCE_NUMBER])


async def _async_stop_tracking_item(call: ServiceCall) -> None:
    """Remove an item from the account's tracked items."""
    reference: str = call.data[ATTR_REFERENCE_NUMBER]
    await _coordinator_tracking(call, reference).async_remove(reference)


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
