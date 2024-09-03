"""Royal Mail sensor platform."""
from datetime import datetime, date
from homeassistant.util import dt as dt_util
import time
from aiohttp import ClientSession
from homeassistant.util.dt import DEFAULT_TIME_ZONE
from homeassistant.core import HomeAssistant
from typing import Any
from aiohttp import ClientError
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from .const import (
    DOMAIN,
    CONF_USERNAME,
    CONF_MAILPIECE_ID,
    CONF_MAILPIECES,
    CONF_MP_DETAILS,
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
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator
)
from .coordinator import (
    RoyalMailMailPiecesCoordinator,
    RoyalMailMailPieceCoordinator,
)

MAILPIECES_SENSORS = [
    SensorEntityDescription(
        key=CONF_MP_DETAILS,
        name="Mail Pieces",
        icon="mdi:package-variant-closed"
    )
]


async def get_sensors(
    name: str,
    hass: HomeAssistant,
    entry: ConfigEntry,
    session: ClientSession
) -> list:

    data = dict(entry.data)

    mailPiecesCoordinator = RoyalMailMailPiecesCoordinator(
        hass, session, data)

    await mailPiecesCoordinator.async_refresh()

    mailPieceSensors = []
    if CONF_MP_DETAILS in mailPiecesCoordinator.data and len(mailPiecesCoordinator.data[CONF_MP_DETAILS]) > 0:

        for mail_piece in mailPiecesCoordinator.data[CONF_MP_DETAILS]:
            mail_piece_id = mail_piece[CONF_MAILPIECE_ID]

            mailPieceCoordinator = RoyalMailMailPieceCoordinator(
                hass, session, data, mail_piece_id)

            await mailPieceCoordinator.async_refresh()

            if mailPieceCoordinator.data is not None:
                mailPieceSensors.append(
                    RoyalMailSensor(
                        coordinator=mailPieceCoordinator,
                        name=name,
                        value=None,
                        description=SensorEntityDescription(
                            key=CONF_MAILPIECE_ID,
                            name=mail_piece_id,
                            icon="mdi:package-variant-plus"
                        )
                    )
                )

    mailPiecesSensors = [RoyalMailSensor(mailPiecesCoordinator, len(mailPieceSensors), name, description)
                         for description in MAILPIECES_SENSORS]

    return mailPiecesSensors + mailPieceSensors


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

        sensors = await get_sensors(entry.title, hass, entry, session)

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
        value: int,
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
            self.data = coordinator.data.get(CONF_MAILPIECES, {})
            sensor_id = description.name.lower()
        else:
            self.data = value
            sensor_id = description.key.lower()

        # Set the unique ID based on domain, name, and sensor type
        self._attr_unique_id = f"{DOMAIN}-{name}-{sensor_id}".lower()
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
        else:
            return self.coordinator.last_update_success and self.data is not None

    @property
    def icon(self) -> str:
        """Return a representative icon of the timer."""
        if self.entity_description.key == CONF_MAILPIECE_ID:
            if 'summary' in self.data and 'statusCategory' in self.data['summary']:
                status_category = self.data['summary']['statusCategory']
                if status_category == "Delivered":
                    return "mdi:package-variant-closed-check"
                elif status_category == "We've got it":
                    return "mdi:truck-delivery-outline"
        return self.entity_description.icon

    async def async_update(self) -> None:
        """Update the entity.

        Only used by the generic entity update service.
        """
        print(f"Updating sensor {self._attr_unique_id} - Starting update")
        try:
            self._available = True

            # Check if the data is available before processing it
            if not self.data:
                self._state = "Loading..."
                return

            if self.entity_description.key == CONF_MP_DETAILS:
                value = self.data
            else:
                value = self.data.get(self.entity_description.key)

                if self.entity_description.key == CONF_MAILPIECE_ID:
                    if 'summary' in self.data and 'statusDescription' in self.data['summary']:
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

            self._state = value
            print(
                f"Updating sensor {self._attr_unique_id} - Update successful")
        except ClientError:
            self._available = False
            self._state = "Pending"
            print("Error retrieving data from RoyalMail for sensor %s", self.name)

    @property
    def native_value(self) -> str | date | None:
        if self._state is None:
            return "Loading..."  # or some other indicator
        return self._state

    @ property
    def extra_state_attributes(self) -> dict[str, Any]:
        attributes = {}

        if self.entity_description.key == CONF_MAILPIECE_ID:
            mail_piece_data = self.data
            if mail_piece_data:
                for key, value in mail_piece_data.items():
                    if isinstance(value, dict):
                        attributes.update(
                            {f"{key}_{k}": v for k, v in value.items()})
                    else:
                        attributes[key] = value

        return attributes
