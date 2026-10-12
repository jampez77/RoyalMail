"""Diagnostics support for the Royal Mail integration."""

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .const import CONF_SESSION
from .coordinator import RoyalMailConfigEntry
from .sensor import parcel_state

TO_REDACT = {
    CONF_PASSWORD,
    CONF_SESSION,
    CONF_USERNAME,
    "title",
    "unique_id",
    # Parcel details that identify the item or where it is going.
    "alias",
    "last_event_location",
    "summary_line",
    "tracking_number",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: RoyalMailConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    config = coordinator.client.config
    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "api_config": asdict(config) if config else None,
        "parcels": [
            async_redact_data(
                {**asdict(parcel), "state": parcel_state(parcel)}, TO_REDACT
            )
            for parcel in coordinator.data.values()
        ],
    }
