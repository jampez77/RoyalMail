"""The Royal Mail integration."""

from typing import Any, Final

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import (
    config_validation as cv,
    device_registry as dr,
    entity_registry as er,
)
from homeassistant.helpers.typing import ConfigType

from .api import RoyalMailWebClient
from .const import CONF_SESSION, DOMAIN, LOGGER
from .coordinator import (
    RoyalMailConfigEntry,
    RoyalMailCoordinator,
    async_get_login_throttle,
)
from .entity import account_id
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
    # The account number comes from the token, which the refresh made sure of.
    await _async_adopt_account_id(hass, entry, client.user_id)
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


async def _async_adopt_account_id(
    hass: HomeAssistant, entry: RoyalMailConfigEntry, user_id: str
) -> None:
    """Identify an entry by its Royal Mail account number.

    Earlier versions used the email address. The entities and the device keep
    their registry IDs, so entity IDs, history and customisations carry over.
    """
    old_id = account_id(entry)
    if old_id == user_id:
        return
    if other := hass.config_entries.async_entry_for_domain_unique_id(DOMAIN, user_id):
        raise ConfigEntryError(
            translation_domain=DOMAIN,
            translation_key="duplicate_account",
            translation_placeholders={"title": other.title},
        )
    old_prefix = f"{DOMAIN}-{old_id}-".lower()
    new_prefix = f"{DOMAIN}-{user_id}-".lower()

    @callback
    def _new_unique_id(entity: er.RegistryEntry) -> dict[str, Any] | None:
        if not entity.unique_id.startswith(old_prefix):
            return None
        key = entity.unique_id.removeprefix(old_prefix)
        return {"new_unique_id": new_prefix + key}

    await er.async_migrate_entries(hass, entry.entry_id, _new_unique_id)
    device_registry = dr.async_get(hass)
    if device := device_registry.async_get_device(identifiers={(DOMAIN, old_id)}):
        device_registry.async_update_device(
            device.id, new_identifiers={(DOMAIN, user_id)}
        )
    hass.config_entries.async_update_entry(entry, unique_id=user_id)
    LOGGER.debug("Now identifying %s by its Royal Mail account number", entry.title)
