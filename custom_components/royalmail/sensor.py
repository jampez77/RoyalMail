"""Sensors for the Royal Mail integration."""

from typing import Any, override

from homeassistant.components.sensor import (
    DOMAIN as SENSOR_DOMAIN,
    SensorDeviceClass,
    SensorEntity,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import Parcel
from .const import (
    CATEGORY_STATES,
    DOMAIN,
    EVENT_STATES,
    PARCEL_STATES,
    PRIORITY_CATEGORY_STATES,
    STATE_DELIVERY_ATTEMPTED,
    STATE_IN_TRANSIT,
    STATE_OUT_FOR_DELIVERY,
    STATE_READY_FOR_COLLECTION,
)
from .coordinator import RoyalMailConfigEntry, RoyalMailCoordinator
from .entity import RoyalMailEntity, entity_unique_id

PARALLEL_UPDATES = 0

TRACKED_PARCELS_KEY = "tracked_parcels"


def parcel_state(parcel: Parcel) -> str | None:
    """Map a parcel's status category and latest tracking event to a sensor state."""
    if not parcel.summary_ok:
        return None
    # Match "We're expecting it" whichever apostrophe it comes with.
    category = (parcel.status_category or "").lower().replace("\u2019", "'")
    if state := PRIORITY_CATEGORY_STATES.get(category):
        return state
    if parcel.last_event_code and (
        state := EVENT_STATES.get(parcel.last_event_code.upper())
    ):
        return state
    return CATEGORY_STATES.get(category, STATE_IN_TRANSIT)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RoyalMailConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Royal Mail sensors."""
    coordinator = entry.runtime_data
    registry = er.async_get(hass)
    known: set[str] = set()

    # Drop entities for items no longer in the history, including leftovers
    # from earlier versions of the integration.
    wanted = {
        entity_unique_id(entry, key) for key in (TRACKED_PARCELS_KEY, *coordinator.data)
    }
    for registry_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if (
            registry_entry.domain == SENSOR_DOMAIN
            and registry_entry.unique_id not in wanted
        ):
            registry.async_remove(registry_entry.entity_id)

    @callback
    def async_sync_parcels() -> None:
        if not coordinator.last_update_success:
            return
        current = set(coordinator.data)
        for tracking_number in known - current:
            if entity_id := registry.async_get_entity_id(
                SENSOR_DOMAIN, DOMAIN, entity_unique_id(entry, tracking_number)
            ):
                registry.async_remove(entity_id)
        if new := current - known:
            async_add_entities(
                RoyalMailParcelSensor(coordinator, tracking_number)
                for tracking_number in sorted(new)
            )
        known.clear()
        known.update(current)

    async_add_entities([RoyalMailTrackedParcelsSensor(coordinator)])
    async_sync_parcels()
    entry.async_on_unload(coordinator.async_add_listener(async_sync_parcels))


class RoyalMailParcelSensor(RoyalMailEntity, SensorEntity):
    """The delivery status of one tracked item."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = PARCEL_STATES
    _attr_translation_key = "parcel"

    def __init__(self, coordinator: RoyalMailCoordinator, tracking_number: str) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, tracking_number)
        self._tracking_number = tracking_number
        self._parcel = coordinator.data[tracking_number]
        self._attr_name = self._parcel.alias or tracking_number

    @property
    @override
    def available(self) -> bool:
        """Return whether the item is still in the history."""
        return super().available and self._tracking_number in self.coordinator.data

    @property
    @override
    def native_value(self) -> str | None:
        """Return the delivery status."""
        return parcel_state(self._parcel)

    @property
    @override
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return details of the item and its latest tracking event."""
        parcel = self._parcel
        return {
            "tracking_number": parcel.tracking_number,
            "alias": parcel.alias,
            "product": parcel.product,
            "product_description": parcel.product_description,
            "carrier": parcel.carrier,
            "sender": parcel.sender,
            "origin_country": parcel.origin_country,
            "destination_country": parcel.destination_country,
            "last_event": parcel.last_event,
            "last_event_code": parcel.last_event_code,
            "last_event_time": parcel.last_event_time,
            "last_event_location": parcel.last_event_location,
            "status_category": parcel.status_category,
            "status_description": parcel.status_description,
            "summary_line": parcel.summary_line,
            "co2e_grams": parcel.co2e_grams,
            "tracking_url": parcel.tracking_url,
        }

    @callback
    @override
    def _handle_coordinator_update(self) -> None:
        """Pick up the item's new details, including a changed alias."""
        if parcel := self.coordinator.data.get(self._tracking_number):
            self._parcel = parcel
            self._attr_name = parcel.alias or self._tracking_number
        super()._handle_coordinator_update()


class RoyalMailTrackedParcelsSensor(RoyalMailEntity, SensorEntity):
    """How many items the account is tracking."""

    _attr_translation_key = TRACKED_PARCELS_KEY

    def __init__(self, coordinator: RoyalMailCoordinator) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, TRACKED_PARCELS_KEY)

    @property
    @override
    def native_value(self) -> int:
        """Return the number of tracked items."""
        return len(self.coordinator.data)

    @property
    @override
    def extra_state_attributes(self) -> dict[str, Any]:
        """List the tracked items, and those that need you today."""
        states = {
            tracking_number: parcel_state(parcel)
            for tracking_number, parcel in self.coordinator.data.items()
        }
        return {
            "parcels": list(states),
            **{
                wanted: [number for number, state in states.items() if state == wanted]
                for wanted in (
                    STATE_OUT_FOR_DELIVERY,
                    STATE_DELIVERY_ATTEMPTED,
                    STATE_READY_FOR_COLLECTION,
                )
            },
        }
