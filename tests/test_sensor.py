"""Tests for the Royal Mail sensors."""

from dataclasses import replace
from unittest.mock import MagicMock

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    snapshot_platform,
)
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.royalmail.api import CannotConnect, Parcel
from custom_components.royalmail.const import DOMAIN, UPDATE_INTERVAL
from custom_components.royalmail.sensor import parcel_state

from .conftest import USERNAME, make_parcels

TOTAL = "sensor.royal_mail_tracked_parcels"
KETTLE = "sensor.royal_mail_kettle"


async def _poll(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    freezer.tick(UPDATE_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


@pytest.mark.usefixtures("init_integration")
async def test_sensors(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test a sensor is created for every item in the history."""
    await snapshot_platform(hass, entity_registry, snapshot, mock_config_entry.entry_id)


@pytest.mark.usefixtures("init_integration")
async def test_items_added_and_removed(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    freezer: FrozenDateTimeFactory,
    mock_client: MagicMock,
) -> None:
    """Test sensors follow items as they enter and leave the history."""
    assert hass.states.get(TOTAL).state == "4"

    parcels = make_parcels()
    del parcels["AB123456789GB"]
    parcels["GH222222222GB"] = Parcel("GH222222222GB", alias="Books")
    mock_client.async_get_parcels.return_value = parcels
    await _poll(hass, freezer)

    assert hass.states.get(KETTLE) is None
    assert entity_registry.async_get(KETTLE) is None
    assert hass.states.get("sensor.royal_mail_books").state == "unknown"
    assert hass.states.get(TOTAL).state == "4"

    # An item that comes back gets a sensor again.
    mock_client.async_get_parcels.return_value = make_parcels()
    await _poll(hass, freezer)

    assert hass.states.get(KETTLE).state == "delivered"
    assert hass.states.get("sensor.royal_mail_books") is None


@pytest.mark.usefixtures("init_integration")
async def test_failed_update_keeps_sensors(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    freezer: FrozenDateTimeFactory,
    mock_client: MagicMock,
) -> None:
    """Test a failed poll marks sensors unavailable instead of removing them."""
    mock_client.async_get_parcels.side_effect = CannotConnect("boom")
    await _poll(hass, freezer)

    assert hass.states.get(KETTLE).state == STATE_UNAVAILABLE
    assert hass.states.get(TOTAL).state == STATE_UNAVAILABLE
    assert entity_registry.async_get(KETTLE) is not None

    mock_client.async_get_parcels.side_effect = None
    await _poll(hass, freezer)

    assert hass.states.get(KETTLE).state == "delivered"


@pytest.mark.usefixtures("init_integration")
async def test_item_details_update(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, mock_client: MagicMock
) -> None:
    """Test a sensor picks up new tracking events and a renamed alias."""
    parcels = make_parcels()
    parcels["1B0000000000000000001"] = replace(
        parcels["1B0000000000000000001"],
        alias="Lamp",
        last_event="Delivered",
        last_event_code="EVKOP",
    )
    mock_client.async_get_parcels.return_value = parcels
    await _poll(hass, freezer)

    state = hass.states.get("sensor.royal_mail_1b0000000000000000001")
    assert state.state == "delivered"
    assert state.attributes["friendly_name"] == "Royal Mail Lamp"
    assert state.attributes["last_event"] == "Delivered"
    assert hass.states.get(TOTAL).attributes["out_for_delivery"] == []


async def test_legacy_entities_pruned(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_config_entry: MockConfigEntry,
    mock_client: MagicMock,
) -> None:
    """Test sensors from earlier versions are kept or removed by unique ID."""
    mock_config_entry.add_to_hass(hass)
    total = entity_registry.async_get_or_create(
        SENSOR_DOMAIN,
        DOMAIN,
        f"royalmail-{USERNAME}-tracked_parcels",
        suggested_object_id="royalmail_tracked_parcels",
        config_entry=mock_config_entry,
    )
    kettle = entity_registry.async_get_or_create(
        SENSOR_DOMAIN,
        DOMAIN,
        f"royalmail-{USERNAME}-ab123456789gb",
        suggested_object_id="royalmail_parcel_ab123456789gb",
        config_entry=mock_config_entry,
    )
    gone = entity_registry.async_get_or_create(
        SENSOR_DOMAIN,
        DOMAIN,
        f"royalmail-{USERNAME}-zz000000000gb",
        suggested_object_id="royalmail_parcel_zz000000000gb",
        config_entry=mock_config_entry,
    )

    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(total.entity_id).state == "4"
    assert hass.states.get(kettle.entity_id).state == "delivered"
    assert entity_registry.async_get(gone.entity_id) is None


@pytest.mark.parametrize(
    ("parcel", "expected"),
    [
        (Parcel("A", last_event_code="EVKSP"), None),
        (Parcel("A", summary_ok=True), "in_transit"),
        (Parcel("A", last_event_code="evgpd", summary_ok=True), "out_for_delivery"),
        (Parcel("A", last_event_code="EVPLA", summary_ok=True), "ready_for_collection"),
        (Parcel("A", last_event_code="EVPLC", summary_ok=True), "collected"),
        (Parcel("A", last_event_code="EVNDA", summary_ok=True), "in_transit"),
        (
            Parcel(
                "A",
                last_event_code="EVXXX",
                status_category="Delivered",
                summary_ok=True,
            ),
            "delivered",
        ),
        (
            Parcel("A", status_category="Collected", summary_ok=True),
            "collected",
        ),
        (
            Parcel("A", status_category="In Customs", summary_ok=True),
            "in_transit",
        ),
    ],
)
def test_parcel_state(parcel: Parcel, expected: str | None) -> None:
    """Test tracking events map to sensor states."""
    assert parcel_state(parcel) == expected
