"""Tests for the Royal Mail config flow."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    get_schema_suggested_value,
)

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.royalmail.api import (
    CannotConnect,
    CaptchaRequired,
    InvalidAuth,
    RateLimited,
)
from custom_components.royalmail.const import CONF_SESSION, DATA_LOGIN_THROTTLE, DOMAIN

from .conftest import (
    PASSWORD,
    SECOND_USER_ID,
    SECOND_USERNAME,
    SESSION,
    USER_ID,
    USERNAME,
)

pytestmark = pytest.mark.usefixtures("mock_setup_entry")

ERRORS = [
    (InvalidAuth("nope"), "invalid_auth"),
    (RateLimited("slow down"), "rate_limited"),
    (CannotConnect("boom"), "cannot_connect"),
    (CaptchaRequired("captcha"), "cannot_connect"),
    (RuntimeError("bug"), "unknown"),
]


async def test_user_flow(
    hass: HomeAssistant,
    mock_client_class: MagicMock,
    mock_client: MagicMock,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test signing in creates an entry that keeps the website session."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_USERNAME: f"  {USERNAME} ", CONF_PASSWORD: PASSWORD},
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == USERNAME
    assert result["data"] == {
        CONF_USERNAME: USERNAME,
        CONF_PASSWORD: PASSWORD,
        CONF_SESSION: SESSION,
    }
    assert result["result"].unique_id == USER_ID
    mock_client_class.assert_called_once_with(
        USERNAME, PASSWORD, login_throttle=hass.data[DATA_LOGIN_THROTTLE]
    )
    mock_client.async_login.assert_awaited_once()
    mock_client.async_ensure_token.assert_awaited_once()
    mock_client.async_close.assert_awaited_once()
    assert len(mock_setup_entry.mock_calls) == 1


@pytest.mark.parametrize(("error", "reason"), ERRORS)
async def test_user_flow_errors(
    hass: HomeAssistant, mock_client: MagicMock, error: Exception, reason: str
) -> None:
    """Test sign-in errors are shown and the flow can recover."""
    mock_client.async_login.side_effect = error
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_USERNAME: USERNAME, CONF_PASSWORD: "wrong"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": reason}
    assert (
        get_schema_suggested_value(result["data_schema"].schema, CONF_USERNAME)
        == USERNAME
    )
    mock_client.async_close.assert_awaited_once()

    mock_client.async_login.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_USERNAME: USERNAME, CONF_PASSWORD: PASSWORD}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_PASSWORD] == PASSWORD


async def test_second_account(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client_class: MagicMock,
    second_client: MagicMock,
) -> None:
    """Test another Royal Mail account can be added alongside the first."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_USERNAME: SECOND_USERNAME, CONF_PASSWORD: PASSWORD}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == SECOND_USERNAME
    assert result["result"].unique_id == SECOND_USER_ID
    second_client.async_login.assert_awaited_once()
    assert len(hass.config_entries.async_entries(DOMAIN)) == 2


async def test_same_email(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client_class: MagicMock,
) -> None:
    """Test an email that's already set up is turned away without a login."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_USERNAME: " User@Example.COM", CONF_PASSWORD: "x"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    mock_client_class.assert_not_called()


async def test_same_account(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Test an account that's set up under another email is turned away."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_USERNAME: "new-address@example.com", CONF_PASSWORD: PASSWORD},
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    mock_client.async_login.assert_awaited_once()
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


async def test_reauth(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client_class: MagicMock,
    mock_client: MagicMock,
) -> None:
    """Test entering a new password updates the entry."""
    mock_config_entry.add_to_hass(hass)
    mock_client.state = {**SESSION, "jwt": "fresh-token"}

    result = await mock_config_entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["description_placeholders"][CONF_USERNAME] == USERNAME

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "new-password"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert mock_config_entry.data == {
        CONF_USERNAME: USERNAME,
        CONF_PASSWORD: "new-password",
        CONF_SESSION: {**SESSION, "jwt": "fresh-token"},
    }
    mock_client_class.assert_called_once_with(
        USERNAME, "new-password", login_throttle=hass.data[DATA_LOGIN_THROTTLE]
    )


@pytest.mark.parametrize(("error", "reason"), ERRORS)
async def test_reauth_errors(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: MagicMock,
    error: Exception,
    reason: str,
) -> None:
    """Test reauthentication errors are shown and the flow can recover."""
    mock_config_entry.add_to_hass(hass)
    mock_client.async_ensure_token.side_effect = error

    result = await mock_config_entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "wrong"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": reason}
    assert mock_config_entry.data[CONF_PASSWORD] == PASSWORD

    mock_client.async_ensure_token.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "new-password"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert mock_config_entry.data[CONF_PASSWORD] == "new-password"
