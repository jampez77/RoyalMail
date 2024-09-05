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
    CONF_MAILPIECES,
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
    REMOVE_MAILPIECE_URL,
    CONF_MP_DETAILS,
    CONF_SUMMARY,
    CONF_PRODUCT_NAME
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
            return new_tokens

    async def _persist_tokens(self):
        entries = self.hass.config_entries.async_entries(DOMAIN)
        for entry in entries:
            updated_data = entry.data.copy()
            updated_data.update(self.data)
            self.hass.config_entries.async_update_entry(
                entry, data=updated_data)


class RoyalMailRemoveMailPieceCoordinator(DataUpdateCoordinator):
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
        self.refresh_token = data[CONF_REFRESH_TOKEN]
        self.mail_piece_id = mail_piece_id
        self.guid = data[CONF_GUID]
        self.device_id = str(uuid.uuid4().hex.upper()[0:6])
        self.data = data

    async def _async_update_data(self):
        """Fetch data from API endpoint."""
        try:

            mail_piece = await self.session.request(
                method="GET",
                url=MAILPIECE_URL.format(mailPieceId=self.mail_piece_id),
                headers={
                    CONF_IBM_CLIENT_ID: IBM_CLIENT_ID,
                    CONF_ORIGIN: ORIGIN,
                    "Authorization": f"Bearer {self.access_token}"
                },
            )

            mailPiece = await mail_piece.json()

            product_name = mailPiece[CONF_MAILPIECES][CONF_SUMMARY][CONF_PRODUCT_NAME]

            push_notification = await self.session.request(
                method="DELETE",
                url=PUSH_NOTIFICATION_URL.format(
                    guid=self.guid, mailPieceId=self.mail_piece_id),
                headers={
                    ACCESS_TOKEN: self.access_token
                },
                json={
                    PRODUCT_NAME: product_name
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
            mail_piece = await self.session.request(
                method="GET",
                url=MAILPIECE_URL.format(mailPieceId=self.mail_piece_id),
                headers={
                    CONF_IBM_CLIENT_ID: IBM_CLIENT_ID,
                    CONF_ORIGIN: ORIGIN,
                    "Authorization": f"Bearer {self.access_token}"
                },
            )

            mailPiece = await mail_piece.json()

            product_name = mailPiece[CONF_MAILPIECES][CONF_SUMMARY][CONF_PRODUCT_NAME]

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
                        PRODUCT_NAME: product_name
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


class RoyalMaiMailPiecesCoordinator(DataUpdateCoordinator):
    """ RoyalMaiMailPiecesCoordinator """

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
        self.authenticating = False
        self.session = session
        self.access_token = data.get(CONF_ACCESS_TOKEN, None)
        self.refresh_token = data.get(CONF_REFRESH_TOKEN, None)
        self.guid = data.get(CONF_GUID, None)
        self.device_id = str(uuid.uuid4().hex.upper()[0:6])
        self.data = data
        self.token_manager = TokenManager(hass, session, data)

    async def _async_update_data(self):
        """Fetch data from API endpoint."""
        if self.authenticating:
            # Return early or set a pending state instead of making an API call
            return {"status": "pending"}

        if not self.access_token or not self.guid:
            self.authenticating = True
            updated_tokens = await self.token_manager.refresh_tokens()
            self.authenticating = False

            if updated_tokens:
                self.access_token = updated_tokens.get(CONF_ACCESS_TOKEN)
                self.guid = updated_tokens.get(CONF_GUID)
            else:
                raise UpdateFailed(
                    "Failed to refresh tokens and missing essential data.")

        try:
            respAllMailPieces = await self._make_request_all_mailpieces()
            if respAllMailPieces.status in [401, 429]:
                self.authenticating = True
                await self.token_manager.refresh_tokens()
                self.authenticating = False
                respAllMailPieces = await self._make_request_all_mailpieces()

            all_mailpieces = await respAllMailPieces.json()
            # Validate response structure
            if not isinstance(all_mailpieces, dict):
                raise ValueError("Unexpected response format")

            mail_pieces = {
                CONF_MAILPIECES: 0,
                CONF_MP_DETAILS: {}
            }
            total_mail_pieces = 0
            for mail_piece in all_mailpieces.get(CONF_MP_DETAILS):
                mail_piece_id = mail_piece[CONF_MAILPIECE_ID]
                respMailPiece = await self._make_request_mailpiece(mail_piece_id)
                mail_piece = await respMailPiece.json()

                if 'errors' not in mail_piece:
                    total_mail_pieces += 1
                    mail_pieces[CONF_MP_DETAILS][mail_piece_id] = mail_piece.get(
                        CONF_MAILPIECES)

            mail_pieces[CONF_MAILPIECES] = total_mail_pieces
            return mail_pieces

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

    async def _make_request_all_mailpieces(self):
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

    async def _make_request_mailpiece(self, mail_piece_id: str):
        """Make the API request."""
        return await self.session.request(
            method="GET",
            url=MAILPIECE_URL.format(mailPieceId=mail_piece_id),
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

                self.data[CONF_ACCESS_TOKEN] = body.get(
                    CONF_ACCESS_TOKEN, None)
                self.data[CONF_REFRESH_TOKEN] = body.get(
                    CONF_REFRESH_TOKEN, None)
                self.data[CONF_GUID] = body.get(CONF_GUID, None)
                self.data[CONF_FIRST_NAME] = body.get(CONF_FIRST_NAME, None)

                # Validate response structure
                if not isinstance(body, dict):
                    raise ValueError("Unexpected response format")

                # Persist the updated tokens
                entries = self.hass.config_entries.async_entries(DOMAIN)
                for entry in entries:
                    # Update specific data in the entry
                    updated_data = entry.data.copy()
                    # Merge the import_data into the entry_data
                    updated_data.update(body)
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
