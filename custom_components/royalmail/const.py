"""Constants for the Royal Mail integration."""

from datetime import timedelta
import logging
from typing import Final

from homeassistant.util.hass_dict import HassKey

from .api import LoginThrottle

DOMAIN: Final = "royalmail"
LOGGER = logging.getLogger(__package__)

# Shared by every account, so their logins are spaced out.
DATA_LOGIN_THROTTLE: Final[HassKey[LoginThrottle]] = HassKey(f"{DOMAIN}_login_throttle")

CONF_SESSION: Final = "session"

UPDATE_INTERVAL: Final = timedelta(minutes=15)

SERVICE_TRACK_ITEM: Final = "track_your_item"
SERVICE_STOP_TRACKING_ITEM: Final = "stop_tracking_item"
ATTR_REFERENCE_NUMBER: Final = "reference_number"

STATE_EXPECTED: Final = "expected"
STATE_IN_TRANSIT: Final = "in_transit"
STATE_IN_CUSTOMS: Final = "in_customs"
STATE_OUT_FOR_DELIVERY: Final = "out_for_delivery"
STATE_DELIVERY_ATTEMPTED: Final = "delivery_attempted"
STATE_READY_FOR_COLLECTION: Final = "ready_for_collection"
STATE_DELIVERED: Final = "delivered"
STATE_COLLECTED: Final = "collected"
STATE_RETURNED_TO_SENDER: Final = "returned_to_sender"
STATE_PROBLEM: Final = "problem"
PARCEL_STATES: Final = [
    STATE_EXPECTED,
    STATE_IN_TRANSIT,
    STATE_IN_CUSTOMS,
    STATE_OUT_FOR_DELIVERY,
    STATE_DELIVERY_ATTEMPTED,
    STATE_READY_FOR_COLLECTION,
    STATE_DELIVERED,
    STATE_COLLECTED,
    STATE_RETURNED_TO_SENDER,
    STATE_PROBLEM,
]

# The website's status categories, lowercased, that win over the event code:
# an item returned to its sender ends with "Delivered by" like any other.
PRIORITY_CATEGORY_STATES: Final = {
    "returned to sender": STATE_RETURNED_TO_SENDER,
    "duplicate identified": STATE_PROBLEM,
    "restricted or prohibited contents": STATE_PROBLEM,
}
# Royal Mail tracking event codes.
EVENT_STATES: Final = {
    "EVAIE": STATE_EXPECTED,
    "EVAIP": STATE_EXPECTED,
    "EVJIC": STATE_IN_CUSTOMS,
    "EVGPD": STATE_OUT_FOR_DELIVERY,
    "EVKPD": STATE_OUT_FOR_DELIVERY,
    "EVKNA": STATE_DELIVERY_ATTEMPTED,
    "EVKNR": STATE_DELIVERY_ATTEMPTED,
    "EVNDA": STATE_DELIVERY_ATTEMPTED,
    "EVKLS": STATE_READY_FOR_COLLECTION,
    "EVPLA": STATE_READY_FOR_COLLECTION,
    "EVKOP": STATE_DELIVERED,
    "EVKSF": STATE_DELIVERED,
    "EVKSP": STATE_DELIVERED,
    "EVPLC": STATE_COLLECTED,
    "EVPLF": STATE_COLLECTED,
}
# For other event codes, the status category; anything not listed, including
# "Pending", counts as in transit. "No Status" means Royal Mail has nothing yet.
CATEGORY_STATES: Final[dict[str, str | None]] = {
    "we're expecting it": STATE_EXPECTED,
    "in customs": STATE_IN_CUSTOMS,
    "delivery attempted": STATE_DELIVERY_ATTEMPTED,
    "delivered": STATE_DELIVERED,
    "collected": STATE_COLLECTED,
    "no status": None,
}
