"""Tests for the Royal Mail sensors."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    async_mock_restore_state_shutdown_restart,
    mock_restore_cache_with_extra_data,
    snapshot_platform,
)
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er

from custom_components.royalmail.api import CannotConnect, Parcel
from custom_components.royalmail.const import DOMAIN, MAX_EVENTS, UPDATE_INTERVAL
from custom_components.royalmail.sensor import parcel_state

from .conftest import USER_ID, USERNAME, make_parcels

TOTAL = f"sensor.{USER_ID}_tracked_parcels"
KETTLE = f"sensor.{USER_ID}_kettle"
BOOKS = f"sensor.{USER_ID}_books"
SHOES = f"sensor.{USER_ID}_shoes"
LAMP_REF = "1B0000000000000000001"
LAMP = f"sensor.{USER_ID}_{LAMP_REF.lower()}"
WHEN = datetime(2026, 10, 12, 9, 30, tzinfo=UTC)
OUT_FOR_DELIVERY = {
    "code": "EVGPD",
    "event": "Out for delivery",
    "time": WHEN,
    "location": None,
}


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
    assert hass.states.get(BOOKS).state == "unknown"
    assert hass.states.get(TOTAL).state == "4"

    # An item that comes back gets a sensor again.
    mock_client.async_get_parcels.return_value = make_parcels()
    await _poll(hass, freezer)

    assert hass.states.get(KETTLE).state == "delivered"
    assert hass.states.get(BOOKS) is None


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
        last_event="Delivery attempted",
        last_event_code="EVKNR",
        status_category="Delivery Attempted",
    )
    mock_client.async_get_parcels.return_value = parcels
    await _poll(hass, freezer)

    state = hass.states.get(f"sensor.{USER_ID}_1b0000000000000000001")
    assert state.state == "delivery_attempted"
    assert state.attributes["friendly_name"] == f"{USER_ID} Lamp"
    assert state.attributes["last_event"] == "Delivery attempted"
    total = hass.states.get(TOTAL).attributes
    assert total["out_for_delivery"] == []
    assert total["delivery_attempted"] == ["1B0000000000000000001"]


@pytest.mark.usefixtures("init_integration")
async def test_events_build_up(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, mock_client: MagicMock
) -> None:
    """Test each item's sensor keeps a timeline of the events it has seen."""
    assert hass.states.get(LAMP).attributes["events"] == [OUT_FOR_DELIVERY]
    assert hass.states.get(f"sensor.{USER_ID}_unknown_item").attributes["events"] == []
    # The recorder keeps each latest event; the timeline stays out of it.
    assert "events" in hass.states.get(LAMP).state_info["unrecorded_attributes"]

    parcels = make_parcels()
    attempted = replace(
        parcels[LAMP_REF],
        last_event="Delivery attempted",
        last_event_code="EVKNR",
        last_event_time=WHEN + timedelta(hours=3),
        last_event_location="Example Delivery Office",
        status_category="Delivery Attempted",
    )
    parcels[LAMP_REF] = attempted
    mock_client.async_get_parcels.return_value = parcels
    await _poll(hass, freezer)
    # Seeing the same event again doesn't repeat it.
    await _poll(hass, freezer)

    attempted_event = {
        "code": "EVKNR",
        "event": "Delivery attempted",
        "time": WHEN + timedelta(hours=3),
        "location": "Example Delivery Office",
    }
    assert hass.states.get(LAMP).attributes["events"] == [
        attempted_event,
        OUT_FOR_DELIVERY,
    ]

    # Royal Mail rewording an event updates it rather than adding another.
    mock_client.async_get_parcels.return_value = {
        **parcels,
        LAMP_REF: replace(attempted, last_event_location="Example Office"),
    }
    await _poll(hass, freezer)

    assert hass.states.get(LAMP).attributes["events"] == [
        {**attempted_event, "location": "Example Office"},
        OUT_FOR_DELIVERY,
    ]


async def test_events_kept_across_restart(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    mock_client: MagicMock,
    init_integration: MockConfigEntry,
) -> None:
    """Test the timeline survives Home Assistant restarting."""
    parcels = make_parcels()
    parcels[LAMP_REF] = replace(
        parcels[LAMP_REF],
        last_event="Delivery attempted",
        last_event_code="EVKNR",
        last_event_time=WHEN + timedelta(hours=3),
    )
    mock_client.async_get_parcels.return_value = parcels
    await _poll(hass, freezer)

    assert await hass.config_entries.async_unload(init_integration.entry_id)
    await async_mock_restore_state_shutdown_restart(hass)
    assert await hass.config_entries.async_setup(init_integration.entry_id)
    await hass.async_block_till_done()

    events = hass.states.get(LAMP).attributes["events"]
    assert [event["code"] for event in events] == ["EVKNR", "EVGPD"]
    assert events[1] == OUT_FOR_DELIVERY


async def test_restored_events_checked(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Test restored timelines are capped, sorted, and dropped when unreadable."""
    older = [
        {
            "code": "EVNRT",
            "event": "We've got it",
            "time": (WHEN - timedelta(hours=hours)).isoformat(),
            "location": None,
        }
        for hours in range(1, MAX_EVENTS + 1)
    ]
    untimed = {"code": "EVAIP", "event": "Expected", "time": None, "location": None}
    mock_restore_cache_with_extra_data(
        hass,
        [
            (State(LAMP, "in_transit"), {"events": older}),
            (State(KETTLE, "delivered"), {"events": "unreadable"}),
            (State(SHOES, "ready_for_collection"), {"events": [untimed]}),
        ],
    )
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    lamp = hass.states.get(LAMP).attributes["events"]
    assert len(lamp) == MAX_EVENTS
    assert lamp[0] == OUT_FOR_DELIVERY
    assert lamp[-1]["time"] == WHEN - timedelta(hours=MAX_EVENTS - 1)
    kettle = hass.states.get(KETTLE).attributes["events"]
    assert [event["code"] for event in kettle] == ["EVKSP"]
    # An event without a time goes after those with one.
    shoes = hass.states.get(SHOES).attributes["events"]
    assert [event["code"] for event in shoes] == ["EVKLS", "EVAIP"]


async def test_legacy_entities_pruned(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_config_entry: MockConfigEntry,
    mock_client: MagicMock,
) -> None:
    """Test sensors from earlier versions are kept or removed by unique ID."""
    mock_config_entry.add_to_hass(hass)
    # Earlier versions identified the account by its email.
    hass.config_entries.async_update_entry(mock_config_entry, unique_id=USERNAME)
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
        (Parcel("A", last_event_code="EVKPD", summary_ok=True), "out_for_delivery"),
        (Parcel("A", last_event_code="EVAIP", summary_ok=True), "expected"),
        (Parcel("A", last_event_code="EVJIC", summary_ok=True), "in_customs"),
        (Parcel("A", last_event_code="EVPLA", summary_ok=True), "ready_for_collection"),
        (Parcel("A", last_event_code="EVPLC", summary_ok=True), "collected"),
        (Parcel("A", last_event_code="EVKNR", summary_ok=True), "delivery_attempted"),
        (Parcel("A", last_event_code="EVNDA", summary_ok=True), "delivery_attempted"),
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
            Parcel("A", status_category="We're expecting it", summary_ok=True),
            "expected",
        ),
        (
            Parcel("A", status_category="We\u2019re expecting it", summary_ok=True),
            "expected",
        ),
        (Parcel("A", status_category="In Customs", summary_ok=True), "in_customs"),
        (
            Parcel("A", status_category="Delivery Attempted", summary_ok=True),
            "delivery_attempted",
        ),
        (Parcel("A", status_category="Pending", summary_ok=True), "in_transit"),
        (Parcel("A", status_category="Left the UK", summary_ok=True), "in_transit"),
        (Parcel("A", status_category="No Status", summary_ok=True), None),
        # The event code wins over an ordinary category...
        (
            Parcel(
                "A",
                last_event_code="EVGPD",
                status_category="Ready for Delivery",
                summary_ok=True,
            ),
            "out_for_delivery",
        ),
        # ...but not over one that says something went wrong.
        (
            Parcel(
                "A",
                last_event_code="EVKOP",
                status_category="Returned to Sender",
                summary_ok=True,
            ),
            "returned_to_sender",
        ),
        (
            Parcel("A", status_category="Duplicate Identified", summary_ok=True),
            "problem",
        ),
        (
            Parcel(
                "A",
                last_event_code="EVORI",
                status_category="Restricted or Prohibited Contents",
                summary_ok=True,
            ),
            "problem",
        ),
    ],
)
def test_parcel_state(parcel: Parcel, expected: str | None) -> None:
    """Test tracking events map to sensor states."""
    assert parcel_state(parcel) == expected
