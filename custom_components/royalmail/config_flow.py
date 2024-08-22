"""Config flow for Royal Mail integration."""
from __future__ import annotations

import logging
from typing import Any
from collections.abc import Mapping
from homeassistant.core import callback
from homeassistant.config_entries import ConfigEntryState
import voluptuous as vol
from .coordinator import RoyalMailTokensCoordinator
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import device_registry as dr
from .const import (
    DOMAIN,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_REFRESH_TOKEN,
    CONF_GUID,
    CONF_USER_ID,
    CONF_RESULTS,
    CONF_ACCESS_TOKEN
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


@callback
def async_get_options_flow(config_entry):
    return RoyalMailFlowHandler(config_entry)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""

    session = async_get_clientsession(hass)
    coordinator = RoyalMailTokensCoordinator(
        hass, session, data, CONF_PASSWORD)

    await coordinator.async_refresh()

    if coordinator.last_exception is not None and data is not None:
        raise InvalidAuth

    return {"title": str(data[CONF_USERNAME])}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Royal Mail."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""

        existing_entries = self._async_current_entries()
        if existing_entries:
            return self.async_abort(reason="already_configured")

        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_import(self, import_data=None) -> FlowResult:
        """Handle the import step for the service call."""
        print("async_step_import")
        if import_data is not None:
            try:

                # Debugging: Print existing entries
                existing_entries = self.hass.config_entries.async_entries(
                    DOMAIN)
                print("Existing entries: %s", existing_entries[0].data)

                # Check if an entry already exists with the same username
                existing_entry = next(
                    (entry for entry in existing_entries
                     if entry.data.get(CONF_GUID) == import_data.get(CONF_RESULTS)[0][CONF_USER_ID]),
                    None
                )

                if existing_entry is not None:
                    entry_data = existing_entry.data
                    print(f"entry_data: {entry_data}")
                    import_data[CONF_USERNAME] = entry_data[CONF_USERNAME]
                    print(f"import_data: {import_data}")

                    # Update specific data in the entry
                    updated_data = existing_entry.data.copy()
                    # Merge the import_data into the entry_data
                    updated_data.update(import_data)

                    # Update the entry with the new data
                    self.hass.config_entries.async_update_entry(
                        existing_entry,
                        data=updated_data
                    )

                for entry in self._async_current_entries():
                    self.hass.config_entries.async_update_entry(
                        entry,
                        data=entry_data
                    )
                    # Ensure that the config entry is fully set up before attempting a reload
                    if entry.state == ConfigEntryState.LOADED:
                        self.hass.async_create_task(
                            self.hass.config_entries.async_reload(
                                entry.entry_id)
                        )
                    else:
                        # If the entry is not yet fully loaded, you might want to log a message or handle it accordingly
                        print("Config entry is not fully loaded; cannot reload yet.")

                return self.async_abort(reason="entry_updated")

            except Exception as e:  # pylint: disable=broad-except
                _LOGGER.error(f"Failed to import booking: {e}")
                return self.async_abort(reason="import_failed")

    async def async_step_reauth(self, user_input: Mapping[str, Any]) -> FlowResult:
        """Handle reauth step."""
        print("async_step_reauth")
        print(user_input)

        session = async_get_clientsession(self.hass)
        coordinator = RoyalMailTokensCoordinator(
            self.hass, session, user_input, CONF_REFRESH_TOKEN)

        await coordinator.async_refresh()
        print(coordinator.data)
        if coordinator.last_exception is not None and user_input is not None:
            print("reauth failed")
            raise InvalidAuth
        print("reauth success")

        existing_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        print(existing_entry.data)
        user_input[CONF_ACCESS_TOKEN] = coordinator.data[CONF_ACCESS_TOKEN]
        self.hass.config_entries.async_update_entry(
            existing_entry, data=user_input)
        # Ensure that the config entry is fully set up before attempting a reload
        if existing_entry.state == ConfigEntryState.LOADED:
            await self.hass.config_entries.async_reload(existing_entry.entry_id)
        else:
            # If the entry is not yet fully loaded, you might want to log a message or handle it accordingly
            print("Config entry is not fully loaded; cannot reload yet.")
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the re-auth step."""
        print("async_step_reauth_confirm")
        print(user_input)
        if user_input is not None:
            # Here you would handle any form submission from the user
            return self.async_create_entry(title="Re-authenticated", data=self.context["data"])

        # Show a confirmation form or return directly depending on your flow
        return self.async_show_form(
            step_id="reauth_confirm",
            errors=None,
        )


class RoyalMailFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None) -> FlowResult:
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({}),
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
