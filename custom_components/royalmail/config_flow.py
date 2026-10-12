"""Config flow for the Royal Mail integration."""

from collections.abc import Mapping
from typing import Any

import probatio

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import InvalidAuth, RateLimited, RoyalMailError, RoyalMailWebClient
from .const import CONF_SESSION, DOMAIN, LOGGER
from .coordinator import async_get_login_throttle

PASSWORD_SELECTOR = TextSelector(
    TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="current-password")
)
STEP_USER_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_USERNAME): TextSelector(
            TextSelectorConfig(type=TextSelectorType.EMAIL, autocomplete="username")
        ),
        probatio.Required(CONF_PASSWORD): PASSWORD_SELECTOR,
    }
)
STEP_REAUTH_SCHEMA = probatio.Schema(
    {probatio.Required(CONF_PASSWORD): PASSWORD_SELECTOR}
)


async def _async_sign_in(
    hass: HomeAssistant, username: str, password: str, errors: dict[str, str]
) -> tuple[dict[str, Any], str] | None:
    """Sign in to royalmail.com, returning the session and account number.

    On failure, fill in errors and return None.
    """
    client = RoyalMailWebClient(
        username, password, login_throttle=async_get_login_throttle(hass)
    )
    try:
        await client.async_login()
        await client.async_ensure_token()
    except InvalidAuth:
        errors["base"] = "invalid_auth"
    except RateLimited:
        errors["base"] = "rate_limited"
    except RoyalMailError:
        errors["base"] = "cannot_connect"
    except Exception:
        LOGGER.exception("Unexpected error signing in to Royal Mail")
        errors["base"] = "unknown"
    else:
        return client.state, client.user_id
    finally:
        await client.async_close()
    return None


class RoyalMailConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Royal Mail."""

    VERSION = 1
    MINOR_VERSION = 2

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the royalmail.com account details."""
        errors: dict[str, str] = {}
        if user_input is not None:
            username = user_input[CONF_USERNAME].strip()
            password = user_input[CONF_PASSWORD]
            # Keep the session so setting up doesn't sign in a second time;
            # Royal Mail blocks logins that come in quick succession.
            signed_in = await _async_sign_in(self.hass, username, password, errors)
            if signed_in is not None:
                session, user_id = signed_in
                # The account number stays the same if the email changes.
                await self.async_set_unique_id(user_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=username,
                    data={
                        CONF_USERNAME: username,
                        CONF_PASSWORD: password,
                        CONF_SESSION: session,
                    },
                )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_SCHEMA,
                {CONF_USERNAME: user_input[CONF_USERNAME]} if user_input else None,
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle the saved password no longer working."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the password again."""
        entry = self._get_reauth_entry()
        username: str = entry.data[CONF_USERNAME]
        errors: dict[str, str] = {}
        if user_input is not None:
            password = user_input[CONF_PASSWORD]
            signed_in = await _async_sign_in(self.hass, username, password, errors)
            if signed_in is not None:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={CONF_PASSWORD: password, CONF_SESSION: signed_in[0]},
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_REAUTH_SCHEMA,
            errors=errors,
            description_placeholders={CONF_USERNAME: username},
        )
