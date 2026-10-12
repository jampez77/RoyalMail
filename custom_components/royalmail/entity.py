"""Base entity for the Royal Mail integration."""

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import TRACK_PAGE_URL
from .const import DOMAIN
from .coordinator import RoyalMailConfigEntry, RoyalMailCoordinator


def account_id(entry: RoyalMailConfigEntry) -> str:
    """Return the identifier of the Royal Mail account behind an entry."""
    return entry.unique_id or entry.entry_id


def entity_unique_id(entry: RoyalMailConfigEntry, key: str) -> str:
    """Return the unique ID of one of the account's entities."""
    # Matches the unique IDs earlier versions created, so entities carry over.
    return f"{DOMAIN}-{account_id(entry)}-{key}".lower()


class RoyalMailEntity(CoordinatorEntity[RoyalMailCoordinator]):
    """An entity on the Royal Mail account's device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: RoyalMailCoordinator, key: str) -> None:
        """Initialise the entity."""
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = entity_unique_id(entry, key)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, account_id(entry))},
            name="Royal Mail",
            manufacturer="Royal Mail",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=TRACK_PAGE_URL,
        )
