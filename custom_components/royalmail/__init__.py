"""The Royal Mail integration."""

from typing import Final

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .api import RoyalMailWebClient
from .const import CONF_SESSION, DOMAIN, LOGGER
from .coordinator import (
    RoyalMailConfigEntry,
    RoyalMailCoordinator,
    async_get_login_throttle,
)
from .services import async_setup_services

PLATFORMS: Final = [Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Royal Mail actions."""
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: RoyalMailConfigEntry) -> bool:
    """Set up Royal Mail from a config entry."""
    client = RoyalMailWebClient(
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        entry.data.get(CONF_SESSION),
        login_throttle=async_get_login_throttle(hass),
    )
    entry.async_on_unload(client.async_close)
    coordinator = RoyalMailCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: RoyalMailConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_migrate_entry(hass: HomeAssistant, entry: RoyalMailConfigEntry) -> bool:
    """Migrate entries created by earlier versions."""
    if entry.version > 1:
        return False
    if entry.minor_version < 2:
        # 1.1 kept app API tokens that no longer work; only the login is reused.
        username: str = entry.data[CONF_USERNAME]
        hass.config_entries.async_update_entry(
            entry,
            data={CONF_USERNAME: username, CONF_PASSWORD: entry.data[CONF_PASSWORD]},
            unique_id=entry.unique_id or username,
            minor_version=2,
        )
    LOGGER.debug("Migrated to version %s.%s", entry.version, entry.minor_version)
    return True
