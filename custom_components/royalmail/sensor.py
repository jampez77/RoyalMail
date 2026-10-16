"""Sensors for the Royal Mail integration."""

from dataclasses import dataclass
from datetime import datetime
import math
from typing import Any, Self, override

from homeassistant.components.sensor import (
    DOMAIN as SENSOR_DOMAIN,
    SensorDeviceClass,
    SensorEntity,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import ExtraStoredData, RestoreEntity
from homeassistant.util import dt as dt_util

from .api import Parcel
from .const import (
    CATEGORY_STATES,
    DOMAIN,
    EVENT_STATES,
    MAX_EVENTS,
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
ATTR_EVENTS = "events"


@dataclass(frozen=True)
class TrackingEvent:
    """One tracking event a parcel sensor has seen."""

    code: str | None
    event: str | None
    time: datetime | None
    location: str | None

    @classmethod
    def latest(cls, parcel: Parcel) -> Self | None:
        """Return the item's latest event, if Royal Mail has one."""
        if not parcel.summary_ok or not (parcel.last_event_code or parcel.last_event):
            return None
        return cls(
            parcel.last_event_code,
            parcel.last_event,
            parcel.last_event_time,
            parcel.last_event_location,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Read an event back from as_dict."""
        return cls(
            data["code"],
            data["event"],
            dt_util.parse_datetime(data["time"]) if data["time"] else None,
            data["location"],
        )

    def as_dict(self) -> dict[str, Any]:
        """Return the event as a state attribute."""
        return {
            "code": self.code,
            "event": self.event,
            "time": self.time,
            "location": self.location,
        }

    def newest_first(self) -> float:
        """Sort key: newest first, and events without a time last."""
        return -self.time.timestamp() if self.time else math.inf


@dataclass(frozen=True)
class ParcelEvents(ExtraStoredData):
    """The events a parcel sensor keeps across restarts."""

    events: tuple[TrackingEvent, ...]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Read events saved by an earlier run, dropping them if unreadable."""
        try:
            return cls(tuple(TrackingEvent.from_dict(item) for item in data["events"]))
        except (KeyError, TypeError, ValueError):
            return cls(())

    @override
    def as_dict(self) -> dict[str, Any]:
        """Return the events in a form Home Assistant can store."""
        return {
            "events": [
                {
                    **event.as_dict(),
                    "time": event.time.isoformat() if event.time else None,
                }
                for event in self.events
            ]
        }


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


class RoyalMailParcelSensor(RoyalMailEntity, SensorEntity, RestoreEntity):
    """The delivery status of one tracked item."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = PARCEL_STATES
    _attr_translation_key = "parcel"
    # The recorder already keeps each latest event; a growing list doesn't belong
    # in the database.
    _unrecorded_attributes = frozenset({ATTR_EVENTS})

    def __init__(self, coordinator: RoyalMailCoordinator, tracking_number: str) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, tracking_number)
        self._tracking_number = tracking_number
        self._parcel = coordinator.data[tracking_number]
        self._attr_name = self._parcel.alias or tracking_number
        self._events: tuple[TrackingEvent, ...] = ()

    @override
    async def async_added_to_hass(self) -> None:
        """Pick up the events seen before Home Assistant restarted."""
        await super().async_added_to_hass()
        if (data := await self.async_get_last_extra_data()) is not None:
            self._events = ParcelEvents.from_dict(data.as_dict()).events
        self._remember_latest_event()

    @property
    @override
    def extra_restore_state_data(self) -> ParcelEvents:
        """Return the events to keep across restarts."""
        return ParcelEvents(self._events)

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
            ATTR_EVENTS: [event.as_dict() for event in self._events],
        }

    @callback
    @override
    def _handle_coordinator_update(self) -> None:
        """Pick up the item's new details, including a changed alias."""
        if parcel := self.coordinator.data.get(self._tracking_number):
            self._parcel = parcel
            self._attr_name = parcel.alias or self._tracking_number
            self._remember_latest_event()
        super()._handle_coordinator_update()

    def _remember_latest_event(self) -> None:
        """Add the latest event to those seen, or update it if already seen."""
        if (latest := TrackingEvent.latest(self._parcel)) is None:
            return
        # Royal Mail can reword an event or its location; the code and time stay.
        others = (
            event
            for event in self._events
            if (event.code, event.time) != (latest.code, latest.time)
        )
        self._events = tuple(
            sorted((latest, *others), key=TrackingEvent.newest_first)[:MAX_EVENTS]
        )


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
