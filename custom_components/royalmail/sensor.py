"""Royal Mail sensor platform."""

from datetime import date, datetime
from typing import Any

from aiohttp import ClientSession

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
from homeassistant.util import dt as dt_util

from .const import (
    CONF_AVAILABLE_FOR_COLLECTION,
    CONF_EVENTCODE,
    CONF_EVENTDATETIME,
    CONF_EVENTNAME,
    CONF_EVENTS,
    CONF_MAILPIECE_ID,
    CONF_MP_DETAILS,
    CONF_OUT_FOR_DELIVERY,
    CONF_PARCELS,
    CONF_STATUS_DESCRIPTION,
    CONF_SUMMARY,
    DOMAIN,
    PARCEL_AVAILABLE_FOR_COLLECTION,
    PARCEL_COLLECTED,
    PARCEL_COLLECTION,
    PARCEL_DELIVERED,
    PARCEL_DELIVERY_TODAY,
    PARCEL_IN_TRANSIT,
)
from .coordinator import (
    RoyalMailRemoveMailPieceCoordinator,
    RoyalMaiMailPiecesCoordinator,
)


def hasMailPieceExpired(hass: HomeAssistant, expiry_date_raw: str) -> bool:
    """Check if booking has expired."""

    user_timezone = dt_util.get_time_zone(hass.config.time_zone)

    dt_utc = datetime.strptime(expiry_date_raw, "%Y-%m-%dT%H:%M:%S%z").replace(
        tzinfo=user_timezone
    )
    # Convert the datetime to the default timezone
    expiry_date = dt_utc.astimezone(user_timezone)
    return (datetime.today().timestamp() - expiry_date.timestamp()) >= 86400


async def removeMailPiece(hass: HomeAssistant, mail_piece_id: str):
    """Remove expired booking."""
    entry = next(
        (
            entry
            for entry in hass.config_entries.async_entries(DOMAIN)
            if entry.data.get(CONF_MAILPIECE_ID) == mail_piece_id
        ),
        None,
    )

    if entry is not None:
        # Remove the config entry
        await hass.config_entries.async_remove(entry.entry_id)


def is_mailpiece_id_present(mp_details: list[dict], mailpiece_id: str) -> bool:
    """Check if the given mailPieceId is in the mpDetails array."""
    return any(item[CONF_MAILPIECE_ID] == mailpiece_id for item in mp_details)


async def get_sensors(
    name: str, hass: HomeAssistant, entry: ConfigEntry, session: ClientSession
) -> list:
    """Get sensors."""

    data = dict(entry.data)

    rmCoordinator = RoyalMaiMailPiecesCoordinator(hass, session, data)

    await rmCoordinator.async_config_entry_first_refresh()

    rmData = rmCoordinator.data

    mailPieceSensors = []

    parcels = rmData[CONF_MP_DETAILS]

    totalMailPieces = len(parcels)

    for key, value in parcels.items():
        if value is not None and CONF_EVENTS in value:
            lastEventCode = value[CONF_EVENTS][0][CONF_EVENTCODE]

            if lastEventCode in PARCEL_DELIVERED or lastEventCode == PARCEL_COLLECTED:
                lastEventDateTime = value[CONF_EVENTS][0][CONF_EVENTDATETIME]
                if hasMailPieceExpired(hass, lastEventDateTime):
                    removeMailPieceCoordinator = RoyalMailRemoveMailPieceCoordinator(
                        hass, session, data, key
                    )

                    await removeMailPieceCoordinator.async_refresh()

                    remainingMailPieces = removeMailPieceCoordinator.data.get(
                        CONF_MP_DETAILS
                    )

                    if is_mailpiece_id_present(remainingMailPieces, key) is False:
                        await removeMailPiece(hass, key)
                        totalMailPieces -= 1

            mailPieceSensors.append(
                RoyalMailSensor(
                    hass=hass,
                    name=name,
                    data=rmCoordinator.data.get(CONF_MP_DETAILS)[key],
                    description=SensorEntityDescription(
                        key=CONF_MAILPIECE_ID,
                        name=key,
                        icon="mdi:package-variant-closed-remove",
                    ),
                )
            )

    total_sensor = [
        TotalParcelsSensor(
            rmCoordinator,
            name,
        )
    ]

    return total_sensor + mailPieceSensors


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors from a config entry created in the integrations UI."""
    config = hass.data[DOMAIN][entry.entry_id]
    if entry.options:
        config.update(entry.options)

    if entry.data:
        session = async_get_clientsession(hass)

        sensors = await get_sensors(entry.title, hass, entry, session)

        async_add_entities(sensors, update_before_add=True)


async def remove_unavailable_entities(hass: HomeAssistant):
    """Remove entities no longer provided by the integration."""
    # Access the entity registry
    registry = er.async_get(hass)

    # Loop through all registered entities
    for entity_id in list(registry.entities):
        entity = registry.entities[entity_id]
        # Check if the entity belongs to your integration (by checking domain)
        if entity.platform == DOMAIN:
            # Check if the entity is not available in `hass.states`
            state = hass.states.get(entity_id)

            # If the entity's state is unavailable or not in `hass.states`
            if state is None or state.state == "unavailable":
                registry.async_remove(entity_id)


class TotalParcelsSensor(CoordinatorEntity[DataUpdateCoordinator], SensorEntity):
    """Sensor to track the total number of parcels."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        name: str,
    ) -> None:
        """Init."""
        super().__init__(coordinator)
        self.coordinator = coordinator
        self.total_parcels = self.coordinator.data[CONF_MP_DETAILS]
        self._state = self.get_state()
        self._name = "Royal Mail Parcels"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{name}")},
            manufacturer="Royal Mail",
            model="Item Tracker",
            name=name,
            configuration_url="https://github.com/jampez77/RoyalMail/",
        )
        self._attr_unique_id = f"{DOMAIN}-{name}-tracked_parcels".lower()
        self.entity_id = f"sensor.{DOMAIN}_tracked_parcels".lower()
        self._attr_icon = "mdi:package-variant-closed"
        self.attrs: dict[str, Any] = {}

    @property
    def name(self) -> None:
        """Name."""
        return self._name

    @property
    def state(self) -> None:
        """State."""
        return self._state

    def get_state(self) -> int:
        """Update the state based on the number of tracked parcels."""
        return len(self.total_parcels)

    def update_from_coordinator(self):
        """Update sensor state and attributes from coordinator data."""

        parcels_out_for_delivery = []
        parcels_available_for_collection = []
        for parcel in self.total_parcels.values():
            if self.is_parcel_delivery_today(parcel):
                parcels_out_for_delivery.append(parcel)

            if self.is_parcel_available_for_collection(parcel):
                parcels_available_for_collection.append(parcel)

            for entity in self.hass.data[DOMAIN].values():
                if (
                    isinstance(entity, RoyalMailSensor)
                    and str(parcel[CONF_MAILPIECE_ID]).lower() in entity.unique_id
                ):
                    entity.update_parcel_data(parcel)

        if self.total_parcels is not None:
            self.attrs[CONF_PARCELS] = [
                parcel[CONF_MAILPIECE_ID] for parcel in self.total_parcels.values()
            ]

        self.attrs[CONF_OUT_FOR_DELIVERY] = [
            parcel[CONF_MAILPIECE_ID] for parcel in parcels_out_for_delivery
        ]

        self.attrs[CONF_AVAILABLE_FOR_COLLECTION] = [
            parcel[CONF_MAILPIECE_ID] for parcel in parcels_available_for_collection
        ]

        self._state = self.get_state()

        self.async_write_ha_state()

        self.hass.add_job(remove_unavailable_entities(self.hass))

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.update_from_coordinator()
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Handle adding to Home Assistant."""
        await super().async_added_to_hass()
        await self.async_update()

    async def async_remove(self) -> None:
        """Handle the removal of the entity."""
        # If you have any specific cleanup logic, add it here
        if self.hass is not None:
            await super().async_remove()

    def is_parcel_delivery_today(self, parcel: dict) -> bool:
        """Check if the parcel has been delivered."""
        lastEventCode = parcel[CONF_EVENTS][0][CONF_EVENTCODE]
        return lastEventCode in PARCEL_DELIVERY_TODAY

    def is_parcel_available_for_collection(self, parcel: dict) -> bool:
        """Check if parcel is available for collection."""
        lastEventCode = parcel[CONF_EVENTS][0][CONF_EVENTCODE]
        return lastEventCode in PARCEL_AVAILABLE_FOR_COLLECTION

    @property
    def icon(self) -> str:
        """Return a representative icon of the timer."""
        return self._attr_icon

    @property
    def native_value(self) -> str | date | None:
        """Native value."""
        return self._state

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Define entity attributes."""
        return self.attrs


class RoyalMailSensor(SensorEntity):
    """Define an Royal Mail sensor."""

    def __init__(
        self,
        hass: HomeAssistant,
        data: dict,
        name: str,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize."""
        self.hass = hass
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{name}")},
            manufacturer="Royal Mail",
            model="Item Tracker",
            name=name,
            configuration_url="https://github.com/jampez77/RoyalMail/",
        )

        self.data = data
        sensor_id = f"{DOMAIN}_parcel_{description.name}".lower()
        # Set the unique ID based on domain, name, and sensor type
        self._attr_unique_id = f"{DOMAIN}-{name}-{description.name}".lower()
        self.entity_id = f"sensor.{DOMAIN}_parcel_{description.name}".lower()
        self.entity_description = description
        self._name = name
        self._sensor_id = sensor_id
        self.attrs = self.update_attributes()
        self._available = self.update_available()
        self._state = self.update_state()
        self._attr_icon = self.update_icon()

    async def async_remove(self) -> None:
        """Handle the removal of the entity."""
        # If you have any specific cleanup logic, add it here
        if self.hass is not None:
            await super().async_remove()

    def update_state(self) -> str:
        """Update Name."""
        value = self.data.get(self.entity_description.key)

        if CONF_SUMMARY in self.data and CONF_EVENTS in self.data:
            lastEventCode = self.data[CONF_EVENTS][0][CONF_EVENTCODE]
            if lastEventCode in PARCEL_DELIVERED:
                value = self.data[CONF_SUMMARY][CONF_STATUS_DESCRIPTION]
            else:
                value = self.data[CONF_EVENTS][0][CONF_EVENTNAME]

        return value

    def update_available(self) -> bool:
        """Update Available."""
        return self.data is not None

    def update_icon(self) -> str:
        """Update Icon."""

        if CONF_EVENTS in self.data:
            lastEventCode = self.data[CONF_EVENTS][0][CONF_EVENTCODE]
            if lastEventCode in PARCEL_DELIVERED:
                return "mdi:package-variant-closed-check"
            if lastEventCode in PARCEL_DELIVERY_TODAY:
                return "mdi:truck-delivery-outline"
            if lastEventCode in PARCEL_IN_TRANSIT:
                return "mdi:transit-connection-variant"
            if lastEventCode in PARCEL_COLLECTION:
                return "mdi:human-dolly"

        return self.entity_description.icon

    def update_attributes(self) -> dict[str, Any]:
        """Update Attributes."""
        attributes = {}

        mail_piece_data = self.data
        if mail_piece_data:
            for key, value in mail_piece_data.items():
                if isinstance(value, dict):
                    attributes.update({f"{key}_{k}": v for k, v in value.items()})
                else:
                    attributes[key] = value
        return attributes

    def update_parcel_data(self, data):
        """Update parcel data."""
        self.data = data
        self._available = self.update_available()
        self._attr_icon = self.update_icon()
        self._state = self.update_state()
        self.attrs = self.update_attributes()

        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Return if the entity is available."""
        return self.update_available()

    @property
    def icon(self) -> str:
        """Return a representative icon of the timer."""
        return self.update_icon()

    @property
    def native_value(self) -> str | date | None:
        """Native value."""
        return self.update_state()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Define entity attributes."""
        return self.update_attributes()
