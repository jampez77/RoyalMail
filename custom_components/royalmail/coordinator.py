"""Royal Mail Coordinator."""
from datetime import timedelta
import logging
from homeassistant.const import CONTENT_TYPE_JSON
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
import uuid
import hashlib
from .const import (
    TOKENS_URL,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_DEVICE_ID,
    CONF_GRANT_TYPE,
    CONF_IBM_CLIENT_ID,
    IBM_CLIENT_ID,
    CONF_REFRESH_TOKEN,
    PENDING_ITEMS_URL,
    CONF_ORIGIN,
    ORIGIN,
    CONF_ACCESS_TOKEN,
    CONF_GUID,
    CONF_FIRST_NAME,
    MAILPIECES_URL,
    MAILPIECE_URL,
    SUBSCRIPTION_URL,
    CONF_CONTENT_TYPE,
    CONTENT_TYPE,
    PUSH_NOTIFICATION_URL,
    ACCESS_TOKEN,
    TRACKING_ALIAS_URL,
    CONF_USER_ID,
    CONF_MAILPIECE_ID,
    PRODUCT_NAME,
    REMOVE_MAILPIECE_URL
)

_LOGGER = logging.getLogger(__name__)


class RoyalMailRemoveMailPieceCoordinator(DataUpdateCoordinator):
    """ Pending items coordinator"""

    def __init__(self, hass: HomeAssistant, session, data: dict, mail_piece_id: str, product_name: str) -> None:
        """Initialize coordinator."""

        super().__init__(
            hass,
            _LOGGER,
            # Name of the data. For logging purposes.
            name="Royal Mail",
            # Polling interval. Will only be polled if there are subscribers.
            update_interval=timedelta(seconds=300),
        )
        self.session = session
        self.access_token = data[CONF_ACCESS_TOKEN]
        self.refresh_token = data[CONF_REFRESH_TOKEN]
        self.mail_piece_id = mail_piece_id
        self.product_name = product_name
        self.guid = data[CONF_GUID]
        unique_id = hashlib.md5(
            data[CONF_USERNAME].encode("UTF-8")).hexdigest()
        self.device_id = str(uuid.UUID(hex=unique_id))
        self.data = data

    async def _async_update_data(self):
        """Fetch data from API endpoint."""
        try:

            print("subscribed delete item")
            print(PUSH_NOTIFICATION_URL.format(
                guid=self.guid, mailPieceId=self.mail_piece_id))
            push_notification = await self.session.request(
                method="DELETE",
                url=PUSH_NOTIFICATION_URL.format(
                    guid=self.guid, mailPieceId=self.mail_piece_id),
                headers={
                    ACCESS_TOKEN: self.access_token
                },
                json={
                    PRODUCT_NAME: self.product_name
                }
            )
            print(push_notification.status)
            if push_notification.status == 201:
                removeMailPiece = await self.session.request(
                    method="DELETE",
                    url=REMOVE_MAILPIECE_URL.format(
                        guid=self.guid, ibmClientId=IBM_CLIENT_ID, mailPieceId=self.mail_piece_id),
                    headers={
                        CONF_IBM_CLIENT_ID: IBM_CLIENT_ID,
                        CONF_ORIGIN: ORIGIN,
                        "Authorization": f"Bearer {self.access_token}"
                    },
                )

                body = await removeMailPiece.json()
                print("remove item")
                print(body)
                return body

        except InvalidAuth as err:
            raise ConfigEntryAuthFailed from err
        except RoyalMailError as err:
            raise UpdateFailed(str(err)) from err
        except ValueError as err:
            _LOGGER.exception("Value error occurred: %s", err)
            raise UpdateFailed(f"Unexpected response: {err}") from err
        except Exception as err:
            _LOGGER.exception("Unexpected exception: %s", err)
            raise UnknownError from err


class RoyalMailTrackNewItemCoordinator(DataUpdateCoordinator):
    """ Pending items coordinator"""

    def __init__(self, hass: HomeAssistant, session, data: dict, mail_piece_id: str, product_name: str) -> None:
        """Initialize coordinator."""

        super().__init__(
            hass,
            _LOGGER,
            # Name of the data. For logging purposes.
            name="Royal Mail",
            # Polling interval. Will only be polled if there are subscribers.
            update_interval=timedelta(seconds=300),
        )
        self.session = session
        self.access_token = data[CONF_ACCESS_TOKEN]
        self.guid = data[CONF_GUID]
        self.mail_piece_id = mail_piece_id
        self.product_name = product_name

    async def _async_update_data(self):
        """Fetch data from API endpoint."""
        try:
            print(SUBSCRIPTION_URL.format(mailPieceId=self.mail_piece_id))
            create_subscription = await self.session.request(
                method="POST",
                url=SUBSCRIPTION_URL.format(mailPieceId=self.mail_piece_id),
                headers={
                    CONF_IBM_CLIENT_ID: IBM_CLIENT_ID,
                    CONF_ORIGIN: ORIGIN,
                    CONF_CONTENT_TYPE: CONTENT_TYPE,
                    "Authorization": f"Bearer {self.access_token}"
                },
            )

            print(create_subscription.status)
            if create_subscription.status == 200:
                print("subscribed new item")
                print(PUSH_NOTIFICATION_URL.format(
                    guid=self.guid, mailPieceId=self.mail_piece_id))
                push_notification = await self.session.request(
                    method="PUT",
                    url=PUSH_NOTIFICATION_URL.format(
                        guid=self.guid, mailPieceId=self.mail_piece_id),
                    headers={
                        ACCESS_TOKEN: self.access_token
                    },
                    json={
                        PRODUCT_NAME: self.product_name
                    }
                )
                print(push_notification.status)
                if push_notification.status == 201:
                    print("notify new item")

                    tracking_alias = await self.session.request(
                        method="GET",
                        url=TRACKING_ALIAS_URL,
                        headers={
                            CONF_IBM_CLIENT_ID: IBM_CLIENT_ID,
                            CONF_ORIGIN: ORIGIN,
                            CONF_CONTENT_TYPE: CONTENT_TYPE,
                            CONF_USER_ID: self.guid,
                            CONF_MAILPIECE_ID: self.mail_piece_id,
                            "Authorization": f"Bearer {self.access_token}"
                        },
                    )
                    body = await tracking_alias.json()
                    print("track new item")
                    print(body)
                    return body

            else:
                raise NotFoundError(
                    f"New item: Unable to track {self.mail_piece_id}")

        except InvalidAuth as err:
            raise ConfigEntryAuthFailed from err
        except RoyalMailError as err:
            raise UpdateFailed(str(err)) from err
        except ValueError as err:
            _LOGGER.exception("Value error occurred: %s", err)
            raise UpdateFailed(f"Unexpected response: {err}") from err
        except Exception as err:
            _LOGGER.exception("Unexpected exception: %s", err)
            raise UnknownError from err


class RoyalMailMailPieceCoordinator(DataUpdateCoordinator):
    """ Pending items coordinator"""

    def __init__(self, hass: HomeAssistant, session, data: dict, mail_piece_id: str) -> None:
        """Initialize coordinator."""

        super().__init__(
            hass,
            _LOGGER,
            # Name of the data. For logging purposes.
            name="Royal Mail",
            # Polling interval. Will only be polled if there are subscribers.
            update_interval=timedelta(seconds=300),
        )
        self.session = session
        self.access_token = data[CONF_ACCESS_TOKEN]
        self.guid = data[CONF_GUID]
        self.mail_piece_id = mail_piece_id

    async def _async_update_data(self):
        """Fetch data from API endpoint."""
        try:
            resp = await self.session.request(
                method="GET",
                url=MAILPIECE_URL.format(mailPieceId=self.mail_piece_id),
                headers={
                    CONF_IBM_CLIENT_ID: IBM_CLIENT_ID,
                    CONF_ORIGIN: ORIGIN,
                    "Authorization": f"Bearer {self.access_token}"
                },
            )

            if resp.status == 200:
                body = await resp.json()
                # Validate response structure
                if not isinstance(body, dict):
                    raise ValueError("Unexpected response format")

                return body

            elif resp.status == 401:
                raise InvalidAuth("Invalid authentication credentials")
            elif resp.status == 429:
                raise APIRatelimitExceeded("API rate limit exceeded.")
            else:
                raise NotFoundError(f"Unable to track {self.mail_piece_id}")

        except InvalidAuth as err:
            raise ConfigEntryAuthFailed from err
        except RoyalMailError as err:
            raise UpdateFailed(str(err)) from err
        except ValueError as err:
            _LOGGER.exception("Value error occurred: %s", err)
            raise UpdateFailed(f"Unexpected response: {err}") from err
        except Exception as err:
            _LOGGER.exception("Unexpected exception: %s", err)
            raise UnknownError from err


class RoyalMailMailPiecesCoordinator(DataUpdateCoordinator):
    """ Pending items coordinator"""

    def __init__(self, hass: HomeAssistant, session, data: dict) -> None:
        """Initialize coordinator."""

        super().__init__(
            hass,
            _LOGGER,
            # Name of the data. For logging purposes.
            name="Royal Mail",
            # Polling interval. Will only be polled if there are subscribers.
            update_interval=timedelta(seconds=300),
        )
        self.session = session
        self.access_token = data[CONF_ACCESS_TOKEN]
        self.refresh_token = data[CONF_REFRESH_TOKEN]
        self.guid = data[CONF_GUID]
        unique_id = hashlib.md5(
            data[CONF_USERNAME].encode("UTF-8")).hexdigest()
        self.device_id = str(uuid.UUID(hex=unique_id))
        self.data = data

    async def _async_update_data(self):
        """Fetch data from API endpoint."""
        try:
            resp = await self.session.request(
                method="GET",
                url=MAILPIECES_URL.format(
                    guid=self.guid, ibmClientId=IBM_CLIENT_ID),
                headers={
                    CONF_IBM_CLIENT_ID: IBM_CLIENT_ID,
                    CONF_ORIGIN: ORIGIN,
                    "Authorization": f"Bearer {self.access_token}"
                },
            )

            if resp.status == 401:
                raise InvalidAuth("Invalid authentication credentials")
            if resp.status == 429:
                raise APIRatelimitExceeded("API rate limit exceeded.")

            body = await resp.json()
            print("have mail pieces")
            # Validate response structure
            if not isinstance(body, dict):
                raise ValueError("Unexpected response format")

            return body

        except InvalidAuth as err:
            raise ConfigEntryAuthFailed from err
        except RoyalMailError as err:
            raise UpdateFailed(str(err)) from err
        except ValueError as err:
            _LOGGER.exception("Value error occurred: %s", err)
            raise UpdateFailed(f"Unexpected response: {err}") from err
        except Exception as err:
            _LOGGER.exception("Unexpected exception: %s", err)
            raise UnknownError from err


class RoyalMailPendingItemsCoordinator(DataUpdateCoordinator):
    """ Pending items coordinator"""

    def __init__(self, hass: HomeAssistant, session, data: dict) -> None:
        """Initialize coordinator."""

        super().__init__(
            hass,
            _LOGGER,
            # Name of the data. For logging purposes.
            name="Royal Mail",
            # Polling interval. Will only be polled if there are subscribers.
            update_interval=timedelta(seconds=300),
        )
        self.session = session
        self.access_token = data[CONF_ACCESS_TOKEN]

    async def _async_update_data(self):
        """Fetch data from API endpoint."""
        try:
            resp = await self.session.request(
                method="GET",
                url=PENDING_ITEMS_URL,
                headers={
                    CONF_IBM_CLIENT_ID: IBM_CLIENT_ID,
                    CONF_ORIGIN: ORIGIN,
                    "Authorization": f"Bearer {self.access_token}"
                },
            )

            if resp.status == 401:
                raise InvalidAuth("Invalid authentication credentials")
            if resp.status == 429:
                raise APIRatelimitExceeded("API rate limit exceeded.")

            body = await resp.json()

            # Validate response structure
            if not isinstance(body, dict):
                raise ValueError("Unexpected response format")

            return body

        except InvalidAuth as err:
            raise ConfigEntryAuthFailed from err
        except RoyalMailError as err:
            raise UpdateFailed(str(err)) from err
        except ValueError as err:
            _LOGGER.exception("Value error occurred: %s", err)
            raise UpdateFailed(f"Unexpected response: {err}") from err
        except Exception as err:
            _LOGGER.exception("Unexpected exception: %s", err)
            raise UnknownError from err


class RoyalMailTokensCoordinator(DataUpdateCoordinator):
    """Tokens coordinator."""

    def __init__(self, hass: HomeAssistant, session, data: dict, grant_type: str) -> None:
        """Initialize coordinator."""

        super().__init__(
            hass,
            _LOGGER,
            # Name of the data. For logging purposes.
            name="Royal Mail",
            # Polling interval. Will only be polled if there are subscribers.
            update_interval=timedelta(seconds=300),
        )
        self.session = session
        self.username = data[CONF_USERNAME]
        self.password = data[CONF_PASSWORD]
        self.grant_type = grant_type
        unique_id = hashlib.md5(
            data[CONF_USERNAME].encode("UTF-8")).hexdigest()
        self.device_id = str(uuid.UUID(hex=unique_id))
        self.data = data
        self.body = {
            CONF_USERNAME: self.username,
            CONF_PASSWORD: self.password,
            CONF_GRANT_TYPE: self.grant_type,
            CONF_DEVICE_ID: self.device_id
        }

        if self.grant_type == CONF_REFRESH_TOKEN:
            self.body = {
                CONF_REFRESH_TOKEN: data[CONF_REFRESH_TOKEN],
                CONF_GRANT_TYPE: self.grant_type,
                CONF_DEVICE_ID: self.device_id
            }

    async def _async_update_data(self):
        """Fetch data from API endpoint."""
        try:
            resp = await self.session.request(
                method="POST",
                url=TOKENS_URL,
                json=self.body,
                headers={CONF_IBM_CLIENT_ID: IBM_CLIENT_ID},
            )

            if resp.status == 401:
                raise InvalidAuth("Invalid authentication credentials")
            if resp.status == 429:
                raise APIRatelimitExceeded("API rate limit exceeded.")

            body = await resp.json()
            self.data[CONF_ACCESS_TOKEN] = body[CONF_ACCESS_TOKEN]

            if CONF_REFRESH_TOKEN in body:
                self.data[CONF_REFRESH_TOKEN] = body[CONF_REFRESH_TOKEN]

            self.data[CONF_GUID] = body[CONF_GUID]
            self.data[CONF_FIRST_NAME] = body[CONF_FIRST_NAME]

            # Validate response structure
            if not isinstance(body, dict):
                raise ValueError("Unexpected response format")
            print(body)
            return body

        except InvalidAuth as err:
            raise ConfigEntryAuthFailed from err
        except RoyalMailError as err:
            raise UpdateFailed(str(err)) from err
        except ValueError as err:
            _LOGGER.exception("Value error occurred: %s", err)
            raise UpdateFailed(f"Unexpected response: {err}") from err
        except Exception as err:
            _LOGGER.exception("Unexpected exception: %s", err)
            raise UnknownError from err


class RoyalMailError(HomeAssistantError):
    """Base error."""


class InvalidAuth(RoyalMailError):
    """Raised when invalid authentication credentials are provided."""


class APIRatelimitExceeded(RoyalMailError):
    """Raised when the API rate limit is exceeded."""


class NotFoundError(RoyalMailError):
    """Raised when the API rate limit is exceeded."""


class UnknownError(RoyalMailError):
    """Raised when an unknown error occurs."""
