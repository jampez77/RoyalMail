"""Fixtures for the Royal Mail tests."""

from collections.abc import Generator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, create_autospec, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from custom_components.royalmail.api import ApiConfig, Parcel, RoyalMailWebClient
from custom_components.royalmail.const import CONF_SESSION, DOMAIN

USERNAME = "user@example.com"
PASSWORD = "correct-horse"
USER_ID = "100000001"
SECOND_USERNAME = "other@example.com"
SECOND_USER_ID = "100000002"

API_CONFIG = ApiConfig(
    client_id="fake-client-id",
    base_url="https://api.example.test",
    mailpieces_path="/mailpieces/v3/",
    user_seg="user",
    history_seg="history",
    summary_seg="summary",
    events_seg="events",
    jwt_token_path="/user-data/jwt-token",
    language="en",
    timeout=15.0,
)
SESSION: dict[str, Any] = {
    "jwt": "saved-token",
    "cookies": [],
    "config": None,
    "config_fetched": 0.0,
    "login_retry_at": 0.0,
    "login_backoff": 1800.0,
}


def make_parcels() -> dict[str, Parcel]:
    """Return a history with one item in each kind of state."""
    when = datetime(2026, 10, 12, 9, 30, tzinfo=UTC)
    parcels = [
        Parcel(
            "AB123456789GB",
            alias="Kettle",
            product="Tracked 24",
            last_event="Delivered",
            last_event_code="EVKSP",
            last_event_time=when,
            last_event_location="Example Delivery Office",
            status_category="Delivered",
            status_description="Your item was delivered",
            summary_line="We delivered your item",
            carrier="Royal Mail",
            summary_ok=True,
        ),
        Parcel(
            "1B0000000000000000001",
            product="Tracked 48",
            last_event="Out for delivery",
            last_event_code="EVGPD",
            last_event_time=when,
            status_category="In Transit",
            summary_ok=True,
        ),
        Parcel(
            "CD987654321GB",
            alias="Shoes",
            last_event="Delivered to Your Collection Point",
            last_event_code="EVKLS",
            last_event_time=when,
            status_category="Ready for Delivery",
            summary_ok=True,
        ),
        Parcel("EF111111111GB", alias="Unknown item"),
    ]
    return {parcel.tracking_number: parcel for parcel in parcels}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load the integration from custom_components in every test."""


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a Royal Mail config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title=USERNAME,
        unique_id=USER_ID,
        version=1,
        minor_version=2,
        data={CONF_USERNAME: USERNAME, CONF_PASSWORD: PASSWORD, CONF_SESSION: SESSION},
    )


@pytest.fixture
def second_config_entry() -> MockConfigEntry:
    """Return a config entry for a second Royal Mail account."""
    return MockConfigEntry(
        domain=DOMAIN,
        title=SECOND_USERNAME,
        unique_id=SECOND_USER_ID,
        version=1,
        minor_version=2,
        data={
            CONF_USERNAME: SECOND_USERNAME,
            CONF_PASSWORD: PASSWORD,
            CONF_SESSION: SESSION,
        },
    )


def _set_up_client(client: MagicMock, user_id: str) -> None:
    """Make a mocked client sign in to an account that tracks make_parcels()."""
    client.user_id = user_id
    client.state = dict(SESSION)
    client.config = API_CONFIG
    client.async_get_parcels.return_value = make_parcels()
    client.async_track.return_value = {}


@pytest.fixture
def second_client() -> MagicMock:
    """Return the mocked web client for SECOND_USERNAME."""
    client: MagicMock = create_autospec(RoyalMailWebClient, instance=True)
    _set_up_client(client, SECOND_USER_ID)
    return client


@pytest.fixture
def mock_client_class(second_client: MagicMock) -> Generator[MagicMock]:
    """Replace the web client everywhere the integration creates one.

    SECOND_USERNAME gets second_client; any other username gets the
    class's return_value, signed in to USER_ID's account.
    """
    with (
        patch(
            "custom_components.royalmail.RoyalMailWebClient", autospec=True
        ) as client_class,
        patch(
            "custom_components.royalmail.config_flow.RoyalMailWebClient",
            new=client_class,
        ),
    ):
        _set_up_client(client_class.return_value, USER_ID)
        client_class.side_effect = lambda username, *args, **kwargs: (
            second_client if username == SECOND_USERNAME else client_class.return_value
        )
        yield client_class


@pytest.fixture
def mock_client(mock_client_class: MagicMock) -> MagicMock:
    """Return the mocked web client."""
    client: MagicMock = mock_client_class.return_value
    return client


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Skip setting up the entry in config flow tests."""
    with patch(
        "custom_components.royalmail.async_setup_entry", return_value=True
    ) as mock_setup:
        yield mock_setup


@pytest.fixture
async def init_integration(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> MockConfigEntry:
    """Set up the integration with the mocked client."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    return mock_config_entry
