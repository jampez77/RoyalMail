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

STATE_IN_TRANSIT: Final = "in_transit"
STATE_OUT_FOR_DELIVERY: Final = "out_for_delivery"
STATE_READY_FOR_COLLECTION: Final = "ready_for_collection"
STATE_DELIVERED: Final = "delivered"
STATE_COLLECTED: Final = "collected"
PARCEL_STATES: Final = [
    STATE_IN_TRANSIT,
    STATE_OUT_FOR_DELIVERY,
    STATE_READY_FOR_COLLECTION,
    STATE_DELIVERED,
    STATE_COLLECTED,
]

# Royal Mail tracking event codes. Anything not listed counts as in transit,
# including failed delivery attempts (EVKNR, EVKNA, EVNDA).
EVENT_STATES: Final = {
    "EVGPD": STATE_OUT_FOR_DELIVERY,
    "EVKPD": STATE_OUT_FOR_DELIVERY,
    "EVKLS": STATE_READY_FOR_COLLECTION,
    "EVPLA": STATE_READY_FOR_COLLECTION,
    "EVKOP": STATE_DELIVERED,
    "EVKSF": STATE_DELIVERED,
    "EVKSP": STATE_DELIVERED,
    "EVPLC": STATE_COLLECTED,
    "EVPLF": STATE_COLLECTED,
}
# Fallback for unknown event codes, keyed by the website's status category.
CATEGORY_STATES: Final = {
    "delivered": STATE_DELIVERED,
    "collected": STATE_COLLECTED,
}
