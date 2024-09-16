"""Royal Mail sensor platform."""

from datetime import datetime, date
from homeassistant.util import dt as dt_util
from aiohttp import ClientSession
from homeassistant.core import HomeAssistant
from typing import Any
from aiohttp import ClientError
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from .const import (
    DOMAIN,
    CONF_USERNAME,
    CONF_MAILPIECE_ID,
    CONF_DELIVERIES_TODAY,
    CONF_MP_DETAILS,
    CONF_SUMMARY,
    CONF_LAST_EVENT_CODE,
    DELIVERY_TRANSIT_EVENTS,
    DELIVERY_DELIVERED_EVENTS,
    DELIVERY_TODAY_EVENTS,
    CONF_LAST_EVENT_DATE_TIME,
)
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import device_registry as dr
from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorDeviceClass,
)
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from .coordinator import (
    RoyalMaiMailPiecesCoordinator,
    RoyalMailRemoveMailPieceCoordinator,
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

    @property
    def available(self) -> bool:
        """Return if the entity is available."""
        if self.entity_description.key == CONF_MP_DETAILS:
            return self._available and self.data is not None

        return self.coordinator.last_update_success and self.data is not None

    @property
    def icon(self) -> str:
        """Return a representative icon of the timer."""
        if self.entity_description.key == CONF_MAILPIECE_ID:
            if (
                CONF_SUMMARY in self.data
                and CONF_LAST_EVENT_CODE in self.data[CONF_SUMMARY]
            ):
                lastEventCode = self.data[CONF_SUMMARY][CONF_LAST_EVENT_CODE]
                if lastEventCode in DELIVERY_DELIVERED_EVENTS:
                    return "mdi:package-variant-closed-check"
                if lastEventCode in DELIVERY_TODAY_EVENTS:
                    return "mdi:truck-delivery-outline"
                if lastEventCode in DELIVERY_TRANSIT_EVENTS:
                    return "mdi:transit-connection-variant"
        return self.entity_description.icon

    async def async_update(self) -> None:
        """Update the entity.

        Only used by the generic entity update service.
        """
        try:
            self._available = True

            # Check if the data is available before processing it
            if not self.data:
                self._state = "Unable to Track"

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
                        "summary" in self.data
                        and "statusDescription" in self.data["summary"]
                    ):
                        value = self.data["summary"]["statusDescription"]
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
                        user_timezone = dt_util.get_time_zone(
                            self.hass.config.time_zone
                        )

                        dt_utc = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S").replace(
                            tzinfo=user_timezone
                        )
                        # Convert the datetime to the default timezone
                        value = dt_utc.astimezone(user_timezone)

            self._state = value
        except ClientError:
            self._available = False
            self._state = "Pending"

    @property
    def native_value(self) -> str | date | None:
        """Native value."""
        if self._state is None:
            return "Unable to Track"  # or some other indicator
        return self._state

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Define entity attributes."""
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

        return attributes
