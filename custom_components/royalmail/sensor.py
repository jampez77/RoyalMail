"""Royal Mail sensor platform."""
from datetime import datetime, date
from homeassistant.util import dt as dt_util
import time
from aiohttp import ClientSession
from homeassistant.util.dt import DEFAULT_TIME_ZONE
from homeassistant.core import HomeAssistant
from typing import Any
from homeassistant.const import UnitOfMass
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from .const import DOMAIN, CONF_USERNAME, CONF_MAILPIECE_ID, CONF_MAILPIECES, CONF_MP_DETAILS, CONF_TOTAL_RECORDS
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
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator
)
from .coordinator import (
    RoyalMailPendingItemsCoordinator,
    RoyalMailMailPiecesCoordinator,
    RoyalMailMailPieceCoordinator
)

PENDING_ITEM_SENSORS = [
    SensorEntityDescription(
        key=CONF_TOTAL_RECORDS,
        name="Total Records",
        icon="mdi:package-variant-closed-check"
    ),
    SensorEntityDescription(
        key=CONF_MAILPIECES,
        name="Pending Mail Pieces",
        icon="mdi:package-variant-closed"
    )
]

MAILPIECES_SENSORS = [
    SensorEntityDescription(
        key=CONF_MP_DETAILS,
        name="Mail Pieces",
        icon="mdi:package-variant"
    )
]


async def get_sensors(
    name: str,
    hass: HomeAssistant,
    entry: ConfigEntry,
    session: ClientSession
) -> list:
    pendingItemsCoordinator = RoyalMailPendingItemsCoordinator(
        hass, session, entry.data)

    await pendingItemsCoordinator.async_refresh()

    pendingItemsSensors = [RoyalMailSensor(pendingItemsCoordinator, name, description)
                           for description in PENDING_ITEM_SENSORS]

    mailPiecesCoordinator = RoyalMailMailPiecesCoordinator(
        hass, session, entry.data)

    await mailPiecesCoordinator.async_refresh()

    mailPiecesSensors = [RoyalMailSensor(mailPiecesCoordinator, name, description)
                         for description in MAILPIECES_SENSORS]

    mailPieceSensors = []
    if CONF_MP_DETAILS in mailPiecesCoordinator.data and len(mailPiecesCoordinator.data[CONF_MP_DETAILS]) > 0:

        for mail_piece in mailPiecesCoordinator.data[CONF_MP_DETAILS]:
            mail_piece_id = mail_piece[CONF_MAILPIECE_ID]

            mailPieceCoordinator = RoyalMailMailPieceCoordinator(
                hass, session, entry.data, mail_piece_id)

            await mailPieceCoordinator.async_refresh()

            if mailPieceCoordinator.data is not None:
                mailPieceSensors.append(
                    RoyalMailSensor(
                        mailPieceCoordinator,
                        name,
                        SensorEntityDescription(
                            key=CONF_MAILPIECE_ID,
                            name=mail_piece_id,
                            icon="mdi:package-variant-plus"
                        )
                    )
                )

    return pendingItemsSensors + mailPiecesSensors + mailPieceSensors


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Setup sensors from a config entry created in the integrations UI."""
    config = hass.data[DOMAIN][entry.entry_id]
    print("async_setup_entry")
    if entry.options:
        config.update(entry.options)

    if entry.data:
        session = async_get_clientsession(hass)
        name = entry.data[CONF_USERNAME]

        sensors = await get_sensors(name, hass, entry, session)

        async_add_entities(sensors, update_before_add=True)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    _: DiscoveryInfoType | None = None,
) -> None:
    """Set up the sensor platform."""
    session = async_get_clientsession(hass)
    print("async_setup_platform")
    name = config[CONF_USERNAME]

    sensors = await get_sensors(name, hass, config, session)

    async_add_entities(sensors, update_before_add=True)


class RoyalMailSensor(CoordinatorEntity[DataUpdateCoordinator], SensorEntity):
    """Define an Royal Mail sensor."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        name: str,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{name}")},
            manufacturer='Royal Mail',
            name=name,
            configuration_url="https://github.com/jampez77/RoyalMail/",
        )

        if description.key == CONF_MAILPIECE_ID:
            self.data = coordinator.data[CONF_MAILPIECES]
            sensor_id = description.name.lower()
        else:
            self.data = coordinator.data
            sensor_id = description.key.lower()

        # Set the unique ID based on domain, name, and sensor type
        self._attr_unique_id = f"{DOMAIN}-{name}-{sensor_id}".lower()
        self.entity_description = description
        self._name = name
        self._sensor_id = sensor_id
        self.attrs: dict[str, Any] = {}

    @property
    def native_value(self) -> str | date | None:

        value = self.data.get(self.entity_description.key)

        if self.entity_description.key == CONF_MAILPIECE_ID:
            value = self.data['summary']['statusDescription']
        else:
            if isinstance(value, dict):
                value = next(iter(value.values()))

            if isinstance(value, list):
                value = str(len(value))

            if value and self.entity_description.device_class == SensorDeviceClass.TIMESTAMP:

                user_timezone = dt_util.get_time_zone(
                    self.hass.config.time_zone)

                dt_utc = datetime.strptime(
                    value, '%Y-%m-%dT%H:%M:%S').replace(tzinfo=user_timezone)
                # Convert the datetime to the default timezone
                value = dt_utc.astimezone(user_timezone)
        return value

    @ property
    def extra_state_attributes(self) -> dict[str, Any]:

        if self.entity_description.key == CONF_MAILPIECE_ID:
            self.data['links'] = None
            value = self.data
            if isinstance(value, dict) or isinstance(value, list):
                for attribute in value:
                    if isinstance(attribute, list) or isinstance(attribute, dict):
                        for attr in attribute:
                            self.attrs[attr] = attribute[attr]
                    else:
                        self.attrs[attribute] = value[attribute]
        else:
            value = self.data.get(self.entity_description.key)
            if isinstance(value, dict) or isinstance(value, list):
                self.attrs["Mail Pieces"] = value

        return self.attrs
