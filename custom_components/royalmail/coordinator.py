"""Data update coordinator for the Royal Mail integration."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, override

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    CannotConnect,
    CaptchaRequired,
    InvalidAuth,
    Parcel,
    RateLimited,
    RoyalMailWebClient,
)
from .const import CONF_SESSION, DOMAIN, LOGGER, UPDATE_INTERVAL

type RoyalMailConfigEntry = ConfigEntry[RoyalMailCoordinator]

# Saving the session rewrites the config entry, so only do it when something
# that matters for resuming changed, not on every cookie refresh.
_SESSION_KEYS = ("jwt", "config_fetched", "login_retry_at")


class RoyalMailCoordinator(DataUpdateCoordinator[dict[str, Parcel]]):
    """Polls the account's tracked-items history."""

    config_entry: RoyalMailConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: RoyalMailConfigEntry,
        client: RoyalMailWebClient,
    ) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
            always_update=False,
        )
        self.client = client
        # Services and polling share one website session, so take turns.
        self._lock = asyncio.Lock()

    @override
    async def _async_update_data(self) -> dict[str, Parcel]:
        """Fetch the tracked items."""
        try:
            async with self._lock:
                return await self.client.async_get_parcels()
        except InvalidAuth as err:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="invalid_auth"
            ) from err
        except RateLimited as err:
            raise UpdateFailed(
                translation_domain=DOMAIN, translation_key="rate_limited"
            ) from err
        except (CannotConnect, CaptchaRequired) as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="cannot_connect",
                translation_placeholders={"error": str(err)},
            ) from err
        finally:
            self._async_save_session()

    async def async_track(self, reference: str) -> None:
        """Add an item to the account's tracked items."""
        await self._async_call(lambda: self.client.async_track(reference))
        await self.async_request_refresh()

    async def async_remove(self, reference: str) -> None:
        """Remove an item from the account's tracked items."""
        await self._async_call(lambda: self.client.async_remove([reference]))
        await self.async_request_refresh()

    async def _async_call(self, call: Callable[[], Awaitable[Any]]) -> None:
        """Run a client call for a service and translate its errors."""
        try:
            async with self._lock:
                await call()
        except InvalidAuth as err:
            self.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="invalid_auth"
            ) from err
        except CaptchaRequired as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="captcha_required"
            ) from err
        except RateLimited as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="rate_limited"
            ) from err
        except CannotConnect as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="cannot_connect",
                translation_placeholders={"error": str(err)},
            ) from err
        finally:
            self._async_save_session()

    @callback
    def _async_save_session(self) -> None:
        """Persist the website session so restarts don't need a new login."""
        state = self.client.state
        saved = self.config_entry.data.get(CONF_SESSION) or {}
        if all(state.get(key) == saved.get(key) for key in _SESSION_KEYS):
            return
        self.hass.config_entries.async_update_entry(
            self.config_entry, data={**self.config_entry.data, CONF_SESSION: state}
        )
