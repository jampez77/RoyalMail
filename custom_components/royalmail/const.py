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
CONF_STATUS_DESCRIPTION = "statusDescription"
CONF_DELIVERIES_TODAY = "deliveriesToday"
CONF_EVENTS = "events"
CONF_EVENTCODE = "eventCode"
CONF_EVENTNAME = "eventName"
CONF_EVENTDATETIME = "eventDateTime"
PARCEL_IN_TRANSIT = [
    "EVNSR",
    "EVODO",
    "EVORI",
    "EVOAC",
    "EVAIE",
    "EVAIP",
    "EVPPA",
    "EVDAV",
    "EVIMC",
    "EVDAC",
    "EVNRT",
    "EVOCO",
    "RSRXS",
    "RORXS",
    "EVNDA",
    "EVBAV",
    "EVKLS",
    "EVIAV",
]
PARCEL_DELIVERY_FAILED = ["EVKNR"]
PARCEL_DELIVERED = ["EVKSP", "EVKOP", "EVKSF"]
PARCEL_COLLECTED = "EVPLC"
PARCEL_AVAILABLE_FOR_COLLECTION = "EVPLA"
PARCEL_COLLECTION = [PARCEL_AVAILABLE_FOR_COLLECTION, PARCEL_COLLECTED]
PARCEL_DELIVERY_TODAY = ["EVGPD"]
CONF_PARCELS = "parcels"
CONF_OUT_FOR_DELIVERY = "out_for_delivery"
CONF_AVAILABLE_FOR_COLLECTION = "available_for_collection"
