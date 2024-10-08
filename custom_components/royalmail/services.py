"""Services for Royal Mail Integration."""

import functools

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_MAILPIECE_ID,
    CONF_MP_DETAILS,
    CONF_REFERENCE_NUMBER,
    CONF_STOP_TRACKING_ITEM,
    CONF_TRACK_ITEM,
    DOMAIN,
)
from .coordinator import (
    RoyalMailRemoveMailPieceCoordinator,
    RoyalMailTrackNewItemCoordinator,
)

SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_REFERENCE_NUMBER): cv.string,
    }
)


def async_cleanup_services(hass: HomeAssistant) -> None:
    """Cleanup Royal Mail services."""
    hass.services.async_remove(DOMAIN, CONF_TRACK_ITEM)
    hass.services.async_remove(DOMAIN, CONF_STOP_TRACKING_ITEM)


def async_setup_services(hass: HomeAssistant) -> None:
    """Set up Royal Mail services."""
    services = [
        (
            CONF_TRACK_ITEM,
            functools.partial(track_new_item, hass),
            SERVICE_SCHEMA,
        ),
        (
            CONF_STOP_TRACKING_ITEM,
            functools.partial(stop_tracking_item, hass),
            SERVICE_SCHEMA,
        ),
    ]
    for name, method, schema in services:
        if hass.services.has_service(DOMAIN, name):
            continue
        hass.services.async_register(DOMAIN, name, method, schema=schema)


async def track_new_item(hass: HomeAssistant, call: ServiceCall) -> None:
    """Track new item."""
    reference = call.data.get(CONF_REFERENCE_NUMBER)

    session = async_get_clientsession(hass)

    entries = hass.config_entries.async_entries(DOMAIN)

    if not entries:
        return False

    entry_data = entries[0].data

    coordinator = RoyalMailTrackNewItemCoordinator(hass, session, entry_data, reference)

    await coordinator.async_refresh()

    if coordinator.last_exception is not None:
        return HomeAssistantError(f"There was an unknown problem tracking {reference}")

    data = dict(coordinator.data)

    # Initiate the config flow with the "import" step
    await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "import"}, data=data
    )

    return True


async def stop_tracking_item(hass: HomeAssistant, call: ServiceCall) -> None:
    """Remove a booking, its device, and all related entities."""
    reference = call.data.get(CONF_REFERENCE_NUMBER)

    session = async_get_clientsession(hass)

    entries = hass.config_entries.async_entries(DOMAIN)

    if not entries:
        return

    entry_data = entries[0].data

    entity_registry = er.async_get(hass)

    entities = [
        entity_id
        for entity_id, entry in entity_registry.entities.items()
        if entry.platform == DOMAIN
        and str(reference).lower() in entry.entity_id.lower()
    ]

    for entity in entities:
        removeMailPieceCoordinator = RoyalMailRemoveMailPieceCoordinator(
            hass, session, entry_data, reference
        )

        await removeMailPieceCoordinator.async_refresh()

        remainingMailPieces = removeMailPieceCoordinator.data.get(CONF_MP_DETAILS)

        if is_mailpiece_id_present(remainingMailPieces, reference) is False:
            entity_registry.async_remove(entity)


def is_mailpiece_id_present(mp_details: list[dict], mailpiece_id: str) -> bool:
    """Check if the given mailPieceId is in the mpDetails array."""
    return any(item[CONF_MAILPIECE_ID] == mailpiece_id for item in mp_details)
