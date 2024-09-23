"""Royal Mail sensor platform."""

from datetime import date, datetime
from typing import Any

from aiohttp import ClientSession

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
from homeassistant.util import dt as dt_util

from .const import (
    CONF_DELIVERIES_TODAY,
    CONF_LAST_EVENT_CODE,
    CONF_LAST_EVENT_DATE_TIME,
    CONF_MAILPIECE_ID,
    CONF_MP_DETAILS,
    CONF_SUMMARY,
    DELIVERY_DELIVERED_EVENTS,
    DELIVERY_TODAY_EVENTS,
    DELIVERY_TRANSIT_EVENTS,
    DOMAIN,
)
from .coordinator import (
    RoyalMailRemoveMailPieceCoordinator,
    RoyalMaiMailPiecesCoordinator,
)

MAILPIECES_SENSORS = [
    SensorEntityDescription(
        key=CONF_MP_DETAILS, name="Mail Pieces", icon="mdi:package-variant-closed"
    ),
    SensorEntityDescription(
        key=CONF_DELIVERIES_TODAY, name="Deliveries Today", icon="mdi:truck-delivery"
    ),
]


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

    totalMailPieces = len(rmData[CONF_MP_DETAILS])

    for key, value in rmData[CONF_MP_DETAILS].items():
        if CONF_SUMMARY in value and CONF_LAST_EVENT_CODE in value[CONF_SUMMARY]:
            lastEventCode = value[CONF_SUMMARY][CONF_LAST_EVENT_CODE]
            lastEventDateTime = value[CONF_SUMMARY][CONF_LAST_EVENT_DATE_TIME]
            if lastEventCode in DELIVERY_DELIVERED_EVENTS:
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

                else:
                    mailPieceSensors.append(
                        RoyalMailSensor(
                            coordinator=rmCoordinator,
                            name=name,
                            value=None,
                            description=SensorEntityDescription(
                                key=CONF_MAILPIECE_ID,
                                name=key,
                                icon="mdi:package-variant-closed-remove",
                            ),
                        )
                    )

    mailPiecesSensors = [
        RoyalMailSensor(rmCoordinator, totalMailPieces, name, description)
        for description in MAILPIECES_SENSORS
    ]

    return mailPiecesSensors + mailPieceSensors


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


class RoyalMailSensor(CoordinatorEntity[DataUpdateCoordinator], SensorEntity):
    """Define an Royal Mail sensor."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        value: int,
        name: str,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self.coordinator = coordinator
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{name}")},
            manufacturer="Royal Mail",
            model="Item Tracker",
            name=name,
            configuration_url="https://github.com/jampez77/RoyalMail/",
        )

        if description.key == CONF_MAILPIECE_ID:
            self.data = coordinator.data.get(CONF_MP_DETAILS)[description.name]
            sensor_id = f"{DOMAIN}_{description.name}".lower()
        else:
            self.data = value
            sensor_id = f"{DOMAIN}_{description.key}".lower()
        # Set the unique ID based on domain, name, and sensor type
        self._attr_unique_id = f"{DOMAIN}-{name}-{sensor_id}".lower()
        self.entity_id = f"sensor.{sensor_id}".lower()
        self.entity_description = description
        self._name = name
        self._sensor_id = sensor_id
        self._state = None
        self.attrs: dict[str, Any] = {}
        self._available = True
        self._state = None
        self._attr_icon = self.entity_description.icon

    def update_from_coordinator(self):
        """Update sensor state and attributes from coordinator data."""

        if (
            isinstance(self.data, (dict, list))
            and CONF_SUMMARY in self.data
            and CONF_LAST_EVENT_CODE in self.data[CONF_SUMMARY]
        ):
            lastEventCode = self.data[CONF_SUMMARY][CONF_LAST_EVENT_CODE]
            lastEventDateTime = self.data[CONF_SUMMARY][CONF_LAST_EVENT_DATE_TIME]
            if lastEventCode in DELIVERY_DELIVERED_EVENTS:
                if hasMailPieceExpired(self.hass, lastEventDateTime):
                    session = async_get_clientsession(self.hass)

                    removeMailPieceCoordinator = RoyalMailRemoveMailPieceCoordinator(
                        self.hass, session, self.data, self._sensor_id
                    )

                    self.hass.async_add_job(removeMailPieceCoordinator.async_refresh())
                    self.hass.async_add_job(removeMailPiece(self.hass, self._sensor_id))
                    return
        if self.entity_description.key == CONF_MP_DETAILS:
            value = self.data
        elif self.entity_description.key == CONF_DELIVERIES_TODAY:
            deliveries_today = []
            for key, value in self.coordinator.data.get(CONF_MP_DETAILS).items():
                lastEventCode = value[CONF_SUMMARY][CONF_LAST_EVENT_CODE]
                if lastEventCode in DELIVERY_TODAY_EVENTS:
                    deliveries_today.append(key)
            value = len(deliveries_today)
        else:
            value = self.data.get(self.entity_description.key)

            if self.entity_description.key == CONF_MAILPIECE_ID:
                if (
                    CONF_SUMMARY in self.data
                    and "statusDescription" in self.data[CONF_SUMMARY]
                ):
                    value = self.data[CONF_SUMMARY]["statusDescription"]
            else:
                if isinstance(value, dict):
                    value = next(iter(value.values()))

                if isinstance(value, list):
                    value = str(len(value))

                if (
                    value
                    and self.entity_description.device_class
                    == SensorDeviceClass.TIMESTAMP
                ):
                    user_timezone = dt_util.get_time_zone(self.hass.config.time_zone)

                    dt_utc = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S").replace(
                        tzinfo=user_timezone
                    )
                    # Convert the datetime to the default timezone
                    value = dt_utc.astimezone(user_timezone)

        self._state = value

        attributes = {}

        if self.entity_description.key == CONF_MAILPIECE_ID:
            mail_piece_data = self.data
            if mail_piece_data:
                for key, value in mail_piece_data.items():
                    if isinstance(value, dict):
                        attributes.update({f"{key}_{k}": v for k, v in value.items()})
                    else:
                        attributes[key] = value

        if self.entity_description.key == CONF_DELIVERIES_TODAY:
            deliveries_today = []
            for key, value in self.coordinator.data.get(CONF_MP_DETAILS).items():
                lastEventCode = value[CONF_SUMMARY][CONF_LAST_EVENT_CODE]
                if lastEventCode in DELIVERY_TODAY_EVENTS:
                    deliveries_today.append(key)
            if len(deliveries_today) > 0:
                attributes[CONF_DELIVERIES_TODAY] = deliveries_today

        self.attrs = attributes

        if self.entity_description.key == CONF_MAILPIECE_ID:
            if (
                CONF_SUMMARY in self.data
                and CONF_LAST_EVENT_CODE in self.data[CONF_SUMMARY]
            ):
                lastEventCode = self.data[CONF_SUMMARY][CONF_LAST_EVENT_CODE]
                if lastEventCode in DELIVERY_DELIVERED_EVENTS:
                    self._attr_icon = "mdi:package-variant-closed-check"
                if lastEventCode in DELIVERY_TODAY_EVENTS:
                    self._attr_icon = "mdi:truck-delivery-outline"
                if lastEventCode in DELIVERY_TRANSIT_EVENTS:
                    self._attr_icon = "mdi:transit-connection-variant"

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

    @property
    def available(self) -> bool:
        """Return if the entity is available."""
        if self.entity_description.key == CONF_MP_DETAILS:
            return self._available and self.data is not None

        return self.coordinator.last_update_success and self.data is not None

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
