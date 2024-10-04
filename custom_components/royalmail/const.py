"""Constants for the Royal Mail integration."""

DOMAIN = "royalmail"
CONF_IBM_CLIENT_ID = "x-ibm-client-id"
IBM_CLIENT_ID = "e83f49c439b0ebc0b130692bcb8b1cde"
TOKENS_URL = "https://api.royalmail.net/login/v1/tokens"
IMAGE_URL = "https://api.royalmail.net{image}"
PENDING_ITEMS_URL = "https://api.royalmail.net/track/v2/pending/items"
MAILPIECES_URL = "https://api.royalmail.net/mailpieces/v3.1/user/{guid}/history/{ibmClientId}?limit=6"
MAILPIECE_URL = "https://api.royalmail.net/mailpieces/v3.1/{mailPieceId}/events"
SUBSCRIPTION_URL = (
    "https://api.royalmail.net/pushapi/app/v2/subscription/track/{mailPieceId}"
)
PUSH_NOTIFICATION_URL = "https://rmappgateway.dockethub.com/rmpushnotification/api/v3/user/{guid}/trackedmailpieces/{mailPieceId}"
TRACKING_ALIAS_URL = "https://api.royalmail.net/trackingalias"
REMOVE_MAILPIECE_URL = "https://api.royalmail.net/mailpieces/v3.1/user/{guid}/history/{ibmClientId}?mailPieceId={mailPieceId}"
CONF_TRACK_ITEM = "track_your_item"
CONF_STOP_TRACKING_ITEM = "stop_tracking_item"
CONF_REFERENCE_NUMBER = "reference_number"
CONF_DEVICE_ID = "device_id"
CONF_GRANT_TYPE = "grant_type"
CONF_RESULTS = "results"
CONF_PASSWORD = "password"
CONF_USERNAME = "username"
CONF_ACCESS_TOKEN = "access_token"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_TOKEN_TYPE = "token_type"
CONF_EXPIRES_IN = "expires_in"
CONF_GUID = "guid"
CONF_FIRST_NAME = "first_name"
CONF_MAILPIECES = "mailPieces"
CONF_MP_DETAILS = "mpDetails"
CONF_LAST_ACCESSED = "lastAccessedTimestamp"
CONF_MAILPIECE_ID = "mailPieceId"
CONF_JWT = "jwt"
CONF_ORIGIN = "origin"
ORIGIN = "consumermobile.royalmail.com"
CONF_CONTENT_TYPE = "content-type"
CONTENT_TYPE = "application/json; charset=utf-8"
ACCESS_TOKEN = "accessToken"
CONF_USER_ID = "userId"
CONF_PRODUCT_NAME = "productName"
PRODUCT_NAME = "ProductName"
CONF_SUMMARY = "summary"
CONF_DELIVERIES_TODAY = "deliveriesToday"
CONF_LAST_EVENT_CODE = "lastEventCode"
CONF_LAST_EVENT_DATE_TIME = "lastEventDateTime"
DELIVERY_TRANSIT_EVENTS = [
    "EVNSR",
    "EVODO",
    "EVORI",
    "EVOAC",
    "EVAIE",
    "EVPPA",
    "EVDAV",
    "EVIMC",
    "EVDAC",
    "EVNRT",
    "EVOCO",
]
DELIVERY_DELIVERED_EVENTS = ["EVKSP", "EVKOP", "EVKSF"]
DELIVERY_TODAY_EVENTS = ["EVGPD"]
CONF_PARCELS = "parcels"
CONF_OUT_FOR_DELIVERY = "out_for_delivery"
