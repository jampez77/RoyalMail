"""Config flow for Royal Mail integration."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_ACCESS_TOKEN,
    CONF_GUID,
    CONF_PASSWORD,
    CONF_RESULTS,
    CONF_USER_ID,
    CONF_USERNAME,
    DOMAIN,
)
from .coordinator import RoyalMailTokensCoordinator

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


@callback
def async_get_options_flow(config_entry):
    """Async options flow."""
    return RoyalMailFlowHandler(config_entry)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""

    session = async_get_clientsession(hass)
    coordinator = RoyalMailTokensCoordinator(hass, session, data)

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

        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_USERNAME])
            self._abort_if_unique_id_configured()

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
                data = dict(user_input)

                existing_entries = self.hass.config_entries.async_entries(DOMAIN)

                # Check if an entry already exists with the same username
                existing_entry = next(
                    (
                        entry
                        for entry in existing_entries
                        if entry.data.get(CONF_USERNAME) == user_input[CONF_USERNAME]
                    ),
                    None,
                )

                if existing_entry is not None:
                    # Update specific data in the entry
                    updated_data = existing_entry.data.copy()
                    # Merge the import_data into the entry_data
                    updated_data.update(data)
                    # Update the entry with the new data
                    self.hass.config_entries.async_update_entry(
                        existing_entry, data=updated_data
                    )

                return self.async_create_entry(title=info["title"], data=data)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_import(self, import_data=None) -> FlowResult:
        """Handle the import step for the service call."""

        if import_data is not None:
            try:
                await self.async_set_unique_id(import_data[CONF_USERNAME])
                self._abort_if_unique_id_configured()

                existing_entries = self.hass.config_entries.async_entries(DOMAIN)

                # Check if an entry already exists with the same username
                existing_entry = next(
                    (
                        entry
                        for entry in existing_entries
                        if entry.data.get(CONF_GUID)
                        == import_data.get(CONF_RESULTS)[0][CONF_USER_ID]
                    ),
                    None,
                )

                if existing_entry is not None:
                    entry_data = existing_entry.data
                    import_data[CONF_USERNAME] = entry_data[CONF_USERNAME]

                    # Update specific data in the entry
                    updated_data = existing_entry.data.copy()
                    # Merge the import_data into the entry_data
                    updated_data.update(import_data)
                    # Update the entry with the new data
                    self.hass.config_entries.async_update_entry(
                        existing_entry, data=updated_data
                    )

                for entry in self._async_current_entries():
                    # Update specific data in the entry
                    updated_data = entry.data.copy()
                    # Merge the import_data into the entry_data
                    updated_data.update(entry_data)
                    self.hass.config_entries.async_update_entry(
                        entry, data=updated_data
                    )
                    # Ensure that the config entry is fully set up before attempting a reload
                    if entry.state == ConfigEntryState.LOADED:
                        self.hass.async_create_task(
                            self.hass.config_entries.async_reload(entry.entry_id)
                        )

                return self.async_abort(reason="entry_updated")

            except Exception as e:  # pylint: disable=broad-except
                _LOGGER.error("Failed to import booking: {e}")
                return self.async_abort(reason="import_failed")

                # Explicitly handle the case where import_data is None
        return self.async_abort(reason="no_import_data")

    async def async_step_reauth(self, user_input: Mapping[str, Any]) -> FlowResult:
        """Handle reauth step."""

        session = async_get_clientsession(self.hass)
        coordinator = RoyalMailTokensCoordinator(self.hass, session, user_input)

        await coordinator.async_refresh()
        if coordinator.last_exception is not None and user_input is not None:
            raise InvalidAuth

        existing_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        user_input[CONF_ACCESS_TOKEN] = coordinator.data[CONF_ACCESS_TOKEN]

        # Update specific data in the entry
        updated_data = existing_entry.data.copy()
        # Merge the import_data into the entry_data
        updated_data.update(user_input)
        # Update the entry with the new data
        self.hass.config_entries.async_update_entry(existing_entry, data=updated_data)
        # Ensure that the config entry is fully set up before attempting a reload
        if existing_entry.state == ConfigEntryState.LOADED:
            await self.hass.config_entries.async_reload(existing_entry.entry_id)

        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the re-auth step."""
        if user_input is not None:
            # Here you would handle any form submission from the user
            return self.async_create_entry(
                title="Re-authenticated", data=self.context["data"]
            )

        # Show a confirmation form or return directly depending on your flow
        return self.async_show_form(
            step_id="reauth_confirm",
            errors=None,
        )


class RoyalMailFlowHandler(config_entries.OptionsFlow):
    """Royal Mail flow handler."""

    def __init__(self, config_entry) -> None:
        """Init."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None) -> FlowResult:
        """Init."""
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({}),
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
