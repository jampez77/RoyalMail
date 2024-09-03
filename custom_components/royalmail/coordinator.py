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
from homeassistant.helpers.entity_registry import (
    async_get,
)
import uuid
from .const import (
    DOMAIN,
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
from asyncio import Lock
_LOGGER = logging.getLogger(__name__)


class TokenManager:
    def __init__(self, hass: HomeAssistant, session, data) -> None:
        self.hass = hass
        self.session = session
        self.data = data
        self.lock = Lock()

    async def refresh_tokens(self):
        async with self.lock:
            # Perform the refresh logic
            coordinator = RoyalMailTokensCoordinator(
                self.hass, self.session, self.data)
            new_tokens = await coordinator.refresh_tokens()
            if new_tokens:
                self.data.update(new_tokens)
                await self._persist_tokens()

    async def _persist_tokens(self):
        entries = self.hass.config_entries.async_entries(DOMAIN)
        for entry in entries:
            updated_data = entry.data.copy()
            updated_data.update(self.data)
            self.hass.config_entries.async_update_entry(
                entry, data=updated_data)


class RoyalMailRemoveMailPieceCoordinator(DataUpdateCoordinator):
    """ Pending items coordinator"""

    def __init__(self, hass: HomeAssistant, session, data: dict, mail_piece_id: str, product_name: str) -> None:
        """Initialize coordinator."""
        print("RoyalMailRemoveMailPieceCoordinator")
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
        self.device_id = str(uuid.uuid4().hex.upper()[0:6])
        self.data = data

    async def _async_update_data(self):
        """Fetch data from API endpoint."""
        try:

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
        print("RoyalMailTrackNewItemCoordinator")
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

            if create_subscription.status == 200:
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
                if push_notification.status == 201:

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
        print("RoyalMailMailPieceCoordinator")
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
        self.authenticating = False
        self.token_manager = TokenManager(hass, session, data)

    async def _async_update_data(self):
        """Fetch data from API endpoint."""
        if self.authenticating:
            # Return early or set a pending state instead of making an API call
            print("authenticating")
            return {"status": "pending"}
        try:

            resp = await self._make_request()
            if resp.status in [401, 429]:
                self.authenticating = True
                await self.token_manager.refresh_tokens()
                self.authenticating = False
                resp = await self._make_request()

            body = await resp.json()
            # Validate response structure
            if not isinstance(body, dict):
                raise ValueError("Unexpected response format")

            return body

        except InvalidAuth as err:
            raise ConfigEntryAuthFailed from err
        except RoyalMailError as err:
            raise UpdateFailed(str(err)) from err
        except ConfigEntryAuthFailed:
            print("Authentication failed; keeping entities as is until fixed")
            raise
        except ValueError as err:
            _LOGGER.exception("Value error occurred: %s", err)
            raise UpdateFailed(f"Unexpected response: {err}") from err
        except Exception as err:
            _LOGGER.exception("Unexpected exception: %s", err)
            raise UnknownError from err

    async def _make_request(self):
        """Make the API request."""
        return await self.session.request(
            method="GET",
            url=MAILPIECE_URL.format(mailPieceId=self.mail_piece_id),
            headers={
                CONF_IBM_CLIENT_ID: IBM_CLIENT_ID,
                CONF_ORIGIN: ORIGIN,
                "Authorization": f"Bearer {self.access_token}"
            },
        )


class RoyalMailMailPiecesCoordinator(DataUpdateCoordinator):
    """ Pending items coordinator"""

    def __init__(self, hass: HomeAssistant, session, data: dict) -> None:
        """Initialize coordinator."""
        print("RoyalMailMailPiecesCoordinator")
        super().__init__(
            hass,
            _LOGGER,
            # Name of the data. For logging purposes.
            name="Royal Mail",
            # Polling interval. Will only be polled if there are subscribers.
            update_interval=timedelta(seconds=300),
        )
        self.authenticating = False
        self.session = session
        self.access_token = None
        if CONF_ACCESS_TOKEN in data:
            self.access_token = data[CONF_ACCESS_TOKEN]
        if CONF_REFRESH_TOKEN in data:
            self.refresh_token = data[CONF_REFRESH_TOKEN]
        if CONF_GUID in data:
            self.guid = data[CONF_GUID]
        self.device_id = str(uuid.uuid4().hex.upper()[0:6])
        self.data = data
        self.token_manager = TokenManager(hass, session, data)

    async def _async_update_data(self):
        """Fetch data from API endpoint."""
        if self.authenticating:
            # Return early or set a pending state instead of making an API call
            print("authenticating")
            return {"status": "pending"}

        try:

            resp = await self._make_request()
            if resp.status in [401, 429]:
                self.authenticating = True
                await self.token_manager.refresh_tokens()
                self.authenticating = False
                resp = await self._make_request()

            body = await resp.json()
            print("have mail pieces")
            # Validate response structure
            if not isinstance(body, dict):
                raise ValueError("Unexpected response format")

            # Persist the updated tokens
            entries = self.hass.config_entries.async_entries(DOMAIN)
            for entry in entries:
                print(entry)
                # Update specific data in the entry
                updated_data = entry.data.copy()
                # Merge the import_data into the entry_data
                updated_data.update(body)
                print(updated_data)
                # Update the entry with the new data
                self.hass.config_entries.async_update_entry(
                    entry,
                    data=updated_data
                )

            return body

        except InvalidAuth as err:
            raise ConfigEntryAuthFailed from err
        except RoyalMailError as err:
            raise UpdateFailed(str(err)) from err
        except ConfigEntryAuthFailed:
            print("Authentication failed; keeping entities as is until fixed")
            raise
        except ValueError as err:
            _LOGGER.exception("Value error occurred: %s", err)
            raise UpdateFailed(f"Unexpected response: {err}") from err
        except Exception as err:
            _LOGGER.exception("Unexpected exception: %s", err)
            raise UnknownError from err

    async def _make_request(self):
        """Make the API request."""
        return await self.session.request(
            method="GET",
            url=MAILPIECES_URL.format(
                guid=self.guid, ibmClientId=IBM_CLIENT_ID),
            headers={
                CONF_IBM_CLIENT_ID: IBM_CLIENT_ID,
                CONF_ORIGIN: ORIGIN,
                "Authorization": f"Bearer {self.access_token}"
            },
        )


class RoyalMailTokensCoordinator(DataUpdateCoordinator):
    """Tokens coordinator."""

    def __init__(self, hass: HomeAssistant, session, data: dict) -> None:
        """Initialize coordinator."""
        print("RoyalMailTokensCoordinator")
        super().__init__(
            hass,
            _LOGGER,
            # Name of the data. For logging purposes.
            name="Royal Mail",
            # Polling interval. Will only be polled if there are subscribers.
            update_interval=timedelta(seconds=300),
        )
        self.session = session
        self.device_id = str(uuid.uuid4().hex.upper()[0:6])
        self.data = dict(data)
        self.body = None

        if CONF_USERNAME in data and CONF_PASSWORD in data:
            self.body = {
                CONF_USERNAME: data[CONF_USERNAME],
                CONF_PASSWORD: data[CONF_PASSWORD],
                CONF_GRANT_TYPE: CONF_PASSWORD,
                CONF_DEVICE_ID: self.device_id
            }
        elif CONF_REFRESH_TOKEN in data:
            self.body = {
                CONF_REFRESH_TOKEN: data[CONF_REFRESH_TOKEN],
                CONF_GRANT_TYPE: CONF_REFRESH_TOKEN,
                CONF_DEVICE_ID: self.device_id
            }

    async def _async_update_data(self):
        """Fetch data from API endpoint."""
        try:
            if self.body is not None:
                resp = await self._make_request()

                if resp.status == 401:
                    raise InvalidAuth("Invalid authentication credentials")
                if resp.status == 429:
                    raise APIRatelimitExceeded("API rate limit exceeded.")

                body = await resp.json()

                if CONF_ACCESS_TOKEN in body:
                    self.data[CONF_ACCESS_TOKEN] = body[CONF_ACCESS_TOKEN]

                if CONF_REFRESH_TOKEN in body:
                    self.data[CONF_REFRESH_TOKEN] = body[CONF_REFRESH_TOKEN]

                if CONF_GUID in body:
                    self.data[CONF_GUID] = body[CONF_GUID]

                if CONF_FIRST_NAME in body:
                    self.data[CONF_FIRST_NAME] = body[CONF_FIRST_NAME]

                # Validate response structure
                if not isinstance(body, dict):
                    raise ValueError("Unexpected response format")

                # Persist the updated tokens
                entries = self.hass.config_entries.async_entries(DOMAIN)
                for entry in entries:
                    print(entry)
                    # Update specific data in the entry
                    updated_data = entry.data.copy()
                    # Merge the import_data into the entry_data
                    updated_data.update(body)
                    print(updated_data)
                    # Update the entry with the new data
                    self.hass.config_entries.async_update_entry(
                        entry,
                        data=updated_data
                    )

                return body

        except InvalidAuth as err:
            raise ConfigEntryAuthFailed from err
        except RoyalMailError as err:
            raise UpdateFailed(str(err)) from err
        except ConfigEntryAuthFailed:
            print("Authentication failed; keeping entities as is until fixed")
            raise
        except ValueError as err:
            _LOGGER.exception("Value error occurred: %s", err)
            raise UpdateFailed(f"Unexpected response: {err}") from err
        except Exception as err:
            _LOGGER.exception("Unexpected exception: %s", err)
            raise UnknownError from err

    async def _make_request(self):
        """Make the API request."""
        return await self.session.request(
            method="POST",
            url=TOKENS_URL,
            json=self.body,
            headers={CONF_IBM_CLIENT_ID: IBM_CLIENT_ID},
        )

    async def refresh_tokens(self):
        """Public method to refresh tokens."""
        return await self._async_update_data()


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
