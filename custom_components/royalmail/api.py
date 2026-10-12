"""Async client for the Royal Mail consumer website.

The client signs in to www.royalmail.com the way a browser does, mints the
short-lived token the website's track page uses, and reads the account's
tracked-items history from Royal Mail's web API. Every web API detail (client
id, base URL, paths, language) comes from the website's own runtime config, so
nothing about the API is hardcoded here.

This module has no Home Assistant imports so it can be published on its own.
"""

from __future__ import annotations

import base64
from dataclasses import asdict, dataclass
from datetime import datetime
import json
import logging
import re
import time
from typing import TYPE_CHECKING, Any
from urllib.parse import quote, urlsplit

from curl_cffi import CurlError
from curl_cffi.requests import AsyncSession, Response

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from curl_cffi.requests.session import HttpMethod

_LOGGER = logging.getLogger(__name__)

WEB_URL = "https://www.royalmail.com"
LOGIN_URL = f"{WEB_URL}/login"
CONFIG_URL = f"{WEB_URL}/spalp/rml_track_and_trace/json"
TRACK_PAGE_URL = f"{WEB_URL}/track-your-item"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36"
)
# Akamai fronts www.royalmail.com and only lets real browser TLS through.
IMPERSONATE = "chrome"

WEB_TIMEOUT = 30
TOKEN_REFRESH_MARGIN = 300
CONFIG_MAX_AGE = 24 * 3600
CONFIG_RETRY_AFTER = 3600
API_SESSION_HEADER = "x-rmg-api-session"
API_SESSION_FALLBACK_TTL = 110
# Royal Mail blocks logins after a few attempts in quick succession, so after a
# refusal we wait before trying again, doubling the wait each time.
LOGIN_BACKOFF = 30 * 60
LOGIN_BACKOFF_MAX = 4 * 3600

_FORM_BUILD_ID = re.compile(r'name="form_build_id"\s+value="([^"]+)"')
_RATE_LIMIT_MARKERS = ("experiencing technical issues", "temporarily blocked")
_CLIENT_ID_MARKERS = ("client id", "not registered to plan")
_CAPTCHA_MARKERS = ("captcha", "api-session", "api session")


class RoyalMailError(Exception):
    """Base error for the Royal Mail client."""


class CannotConnect(RoyalMailError):
    """Royal Mail could not be reached or answered unexpectedly."""


class InvalidAuth(RoyalMailError):
    """Royal Mail rejected the username or password."""


class RateLimited(RoyalMailError):
    """Royal Mail is refusing logins for a while."""


class CaptchaRequired(RoyalMailError):
    """Royal Mail wants a captcha before it accepts this request."""


class _SessionExpired(RoyalMailError):
    """The saved website session can no longer mint tokens."""


@dataclass(frozen=True, slots=True)
class ApiConfig:
    """Web API settings published in the website's runtime config."""

    client_id: str
    base_url: str
    mailpieces_path: str
    user_seg: str
    history_seg: str
    summary_seg: str
    events_seg: str
    jwt_token_path: str
    language: str
    timeout: float

    @classmethod
    def from_website(cls, payload: Any) -> ApiConfig:
        """Parse the JSON served at CONFIG_URL."""
        try:
            eps = payload["appConfig"]["epsApiConfig"]
            base_url = _text(eps["baseUrl"]).rstrip("/")
            if urlsplit(base_url).scheme != "https":
                raise ValueError("insecure base URL")
            return cls(
                client_id=_text(eps["ibmClientId"]),
                base_url=base_url,
                mailpieces_path=f"/{_text(eps['mailpieces']).strip('/')}/",
                user_seg=_text(eps["user"]).strip("/"),
                history_seg=_text(eps["history"]).strip("/"),
                summary_seg=_text(eps["summary"]).strip("/"),
                events_seg=_text(eps["events"]).strip("/"),
                jwt_token_path=f"/{_text(eps['jwtToken']).lstrip('/')}",
                language=_text(payload["appText"]["localisation"]["apiLanguage"]),
                timeout=float(eps.get("networkTimeOut(in_seconds)") or 20),
            )
        except (KeyError, TypeError, ValueError, AttributeError) as err:
            raise CannotConnect("Unexpected Royal Mail config format") from err

    def mailpieces_url(self, *segments: str) -> str:
        """Build a URL under the mailpieces API."""
        path = "/".join(quote(segment, safe="") for segment in segments)
        return f"{self.base_url}{self.mailpieces_path}{path}"

    def history_url(self, user_id: str) -> str:
        """URL of the account's tracked-items history."""
        return self.mailpieces_url(
            self.user_seg, user_id, self.history_seg, self.client_id
        )


@dataclass(frozen=True, slots=True)
class Parcel:
    """One item from the account's tracked-items history."""

    tracking_number: str
    alias: str | None = None
    product: str | None = None
    last_event: str | None = None
    last_event_code: str | None = None
    last_event_time: datetime | None = None
    last_event_location: str | None = None
    status_category: str | None = None
    status_description: str | None = None
    summary_line: str | None = None
    carrier: str | None = None
    summary_ok: bool = False

    @classmethod
    def from_api(cls, detail: dict[str, Any], item: dict[str, Any] | None) -> Parcel:
        """Merge a history entry with its summary, as the website does."""
        tracking_number = str(detail["mailPieceId"])
        alias = _clean(detail.get("alias"))
        summary = item.get("summary") if item else None
        if item is None or str(item.get("status")) != "200":
            return cls(tracking_number, alias)
        if not isinstance(summary, dict):
            return cls(tracking_number, alias)
        return cls(
            tracking_number=tracking_number,
            alias=alias,
            product=_clean(summary.get("productName")),
            last_event=_clean(summary.get("lastEventName")),
            last_event_code=_clean(summary.get("lastEventCode")),
            last_event_time=_parse_time(summary.get("lastEventDateTime")),
            last_event_location=_clean(summary.get("lastEventLocationName")),
            status_category=_clean(summary.get("statusCategory")),
            status_description=_clean(summary.get("statusDescription")),
            summary_line=_clean(summary.get("summaryLine")),
            carrier=_clean(item.get("carrierFullName") or item.get("carrierShortName")),
            summary_ok=True,
        )


class RoyalMailWebClient:
    """Talks to royalmail.com the way the website's track page does."""

    def __init__(
        self,
        username: str,
        password: str,
        state: dict[str, Any] | None = None,
        *,
        session: AsyncSession[Response] | None = None,
    ) -> None:
        """Create a client, optionally resuming a saved session."""
        self._username = username
        self._password = password
        self._session: AsyncSession[Response] = session or AsyncSession(
            impersonate=IMPERSONATE
        )
        self._jwt: str | None = None
        self._jwt_claims: dict[str, Any] = {}
        self._config: ApiConfig | None = None
        self._config_fetched = 0.0
        self._api_session: str | None = None
        self._api_session_expiry = 0.0
        self._login_retry_at = 0.0
        self._login_backoff: float = LOGIN_BACKOFF
        if state:
            self._restore(state)

    @property
    def config(self) -> ApiConfig | None:
        """The web API config currently in use."""
        return self._config

    @property
    def state(self) -> dict[str, Any]:
        """Everything needed to resume without logging in again."""
        return {
            "jwt": self._jwt,
            "cookies": [
                {
                    "name": cookie.name,
                    "value": cookie.value,
                    "domain": cookie.domain,
                    "path": cookie.path,
                    "secure": cookie.secure,
                    "expires": cookie.expires,
                }
                for cookie in self._session.cookies.jar
                if cookie.value is not None
            ],
            "config": asdict(self._config) if self._config else None,
            "config_fetched": self._config_fetched,
            "login_retry_at": self._login_retry_at,
            "login_backoff": self._login_backoff,
        }

    async def async_close(self) -> None:
        """Close the HTTP session."""
        await self._session.close()

    async def async_load_config(self, *, force: bool = False) -> ApiConfig:
        """Return the web API config, fetching it from the website if stale."""
        if (
            self._config is not None
            and not force
            and time.time() - self._config_fetched < CONFIG_MAX_AGE
        ):
            return self._config
        try:
            response = await self._request(
                "GET",
                CONFIG_URL,
                headers={
                    "Accept": "application/json, text/plain, */*",
                    "Referer": TRACK_PAGE_URL,
                },
            )
            if response.status_code != 200:
                raise CannotConnect(
                    f"Royal Mail config returned HTTP {response.status_code}"
                )
            config = ApiConfig.from_website(_json(response))
        except CannotConnect as err:
            if self._config is None:
                raise
            _LOGGER.debug("Keeping cached Royal Mail config: %s", err)
            self._config_fetched = time.time() - CONFIG_MAX_AGE + CONFIG_RETRY_AFTER
            return self._config
        if self._config is not None and config.client_id != self._config.client_id:
            _LOGGER.info("Royal Mail published a new web API client id")
        self._config = config
        self._config_fetched = time.time()
        return config

    async def async_login(self) -> None:
        """Sign in to www.royalmail.com with the username and password."""
        if (wait := self._login_retry_at - time.time()) > 0:
            raise RateLimited(f"Not retrying the login for another {wait:.0f}s")
        self._session.cookies.clear()
        self._jwt = None
        self._jwt_claims = {}
        page = await self._request("GET", LOGIN_URL, headers=_page_headers())
        if page.status_code != 200:
            raise CannotConnect(f"Login page returned HTTP {page.status_code}")
        form = next(
            (chunk for chunk in page.text.split("<form") if "user_login_form" in chunk),
            "",
        )
        if (match := _FORM_BUILD_ID.search(form)) is None:
            raise CannotConnect("Login form not found")

        response = await self._request(
            "POST",
            LOGIN_URL,
            data={
                "name": self._username,
                "pass": self._password,
                "form_build_id": match.group(1),
                "form_id": "user_login_form",
                "op": "Log in",
            },
            headers={
                **_page_headers(),
                "Origin": WEB_URL,
                "Referer": LOGIN_URL,
            },
        )
        back_on_form = urlsplit(str(response.url)).path.rstrip("/").endswith("/login")
        if response.status_code >= 400:
            raise CannotConnect(f"Login returned HTTP {response.status_code}")
        if not self._has_web_session() or back_on_form:
            if _rate_limited(response.text):
                self._login_retry_at = time.time() + self._login_backoff
                self._login_backoff = min(self._login_backoff * 2, LOGIN_BACKOFF_MAX)
                raise RateLimited("Royal Mail is temporarily refusing logins")
            raise InvalidAuth("Royal Mail rejected the username or password")
        _LOGGER.debug("Signed in to royalmail.com")
        self._login_retry_at = 0.0
        self._login_backoff = LOGIN_BACKOFF
        await self.async_load_config(force=True)

    async def async_ensure_token(self) -> str:
        """Return a valid API token, re-minting or logging in only when needed."""
        if self._jwt and self._jwt_claims.get("exp", 0) - time.time() > (
            TOKEN_REFRESH_MARGIN
        ):
            return self._jwt
        if self._has_web_session():
            try:
                return await self._mint_token()
            except _SessionExpired:
                _LOGGER.debug("Saved royalmail.com session expired, logging in")
        await self.async_login()
        try:
            return await self._mint_token()
        except _SessionExpired as err:
            raise CannotConnect("Signed in but could not get an API token") from err

    async def async_get_parcels(self) -> dict[str, Parcel]:
        """Return every item in the account's tracked-items history."""
        for attempt in range(2):
            history = _json(
                await self._api("GET", lambda c: c.history_url(self._user_id))
            )
            details = [
                detail
                for detail in history.get("mpDetails") or []
                if isinstance(detail, dict) and detail.get("mailPieceId")
            ]
            if not details:
                return {}
            # The history token expires within a minute, so ask straight away.
            response = await self._api(
                "GET",
                lambda c: c.mailpieces_url(c.summary_seg),
                params={"mailPieceId": history.get("jwt", "")},
                passthrough=(400, 401),
            )
            if response.status_code in (400, 401):
                _LOGGER.debug(
                    "Summary rejected the history token (attempt %s)", attempt + 1
                )
                continue
            items = {
                str(item["mailPieceId"]): item
                for item in _json(response).get("mailPieces") or []
                if isinstance(item, dict) and item.get("mailPieceId")
            }
            return {
                str(detail["mailPieceId"]): Parcel.from_api(
                    detail, items.get(str(detail["mailPieceId"]))
                )
                for detail in details
            }
        raise CannotConnect("Royal Mail kept rejecting the summary request")

    async def async_track(self, reference: str) -> dict[str, Any]:
        """Look up an item, which also adds it to the account's history."""
        response = await self._api(
            "GET", lambda c: c.mailpieces_url(reference, c.events_seg)
        )
        return _json(response)

    async def async_remove(self, references: Iterable[str]) -> None:
        """Remove items from the account's tracked-items history."""
        ids = ",".join(quote(reference, safe="") for reference in references)
        await self._api(
            "DELETE", lambda c: f"{c.history_url(self._user_id)}?mailPieceId={ids}"
        )

    @property
    def _user_id(self) -> str:
        return str(self._jwt_claims.get("sub", ""))

    def _has_web_session(self) -> bool:
        return any(
            cookie.name.startswith("SSESS") for cookie in self._session.cookies.jar
        )

    async def _mint_token(self) -> str:
        config = await self.async_load_config()
        response = await self._request(
            "GET",
            WEB_URL + config.jwt_token_path,
            headers={
                "Accept": "application/json, text/plain, */*",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": TRACK_PAGE_URL,
            },
        )
        if response.status_code != 200:
            raise _SessionExpired(
                f"Token endpoint returned HTTP {response.status_code}"
            )
        try:
            token = json.loads(response.text)["jwt_token"]
            claims = _jwt_claims(token)
        except (ValueError, KeyError, TypeError) as err:
            raise _SessionExpired("Token endpoint returned no token") from err
        if not claims.get("sub"):
            raise _SessionExpired("Token has no user id")
        self._jwt = str(token)
        self._jwt_claims = claims
        return self._jwt

    async def _api(
        self,
        method: HttpMethod,
        url: Callable[[ApiConfig], str],
        *,
        params: dict[str, str] | None = None,
        passthrough: tuple[int, ...] = (),
        retry_auth: bool = True,
        retry_config: bool = True,
    ) -> Response:
        # Logging in refreshes the config, so read it after the token.
        token = await self.async_ensure_token()
        config = await self.async_load_config()
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Origin": WEB_URL,
            "Referer": f"{WEB_URL}/",
            "x-ibm-client-id": config.client_id,
            "x-rmg-auth-token": f"Bearer {token}",
            "x-rmg-language": config.language,
        }
        if self._api_session and self._api_session_expiry > time.time():
            headers[API_SESSION_HEADER] = self._api_session
        response = await self._request(
            method, url(config), params=params, headers=headers, timeout=config.timeout
        )
        self._remember_api_session(response)
        status = response.status_code
        if status in passthrough or status < 400:
            return response

        body = response.text.lower()
        if status in (401, 403) and any(m in body for m in _CLIENT_ID_MARKERS):
            if retry_config:
                _LOGGER.debug("Web API rejected the client id, refreshing config")
                await self.async_load_config(force=True)
                return await self._api(
                    method,
                    url,
                    params=params,
                    passthrough=passthrough,
                    retry_auth=retry_auth,
                    retry_config=False,
                )
            raise CannotConnect("Royal Mail rejected the published client id")
        if status in (401, 403) and any(m in body for m in _CAPTCHA_MARKERS):
            raise CaptchaRequired("Royal Mail wants a captcha for this request")
        if status == 401:
            if retry_auth:
                self._jwt = None
                self._jwt_claims = {}
                return await self._api(
                    method,
                    url,
                    params=params,
                    passthrough=passthrough,
                    retry_auth=False,
                    retry_config=retry_config,
                )
            raise CannotConnect("Royal Mail rejected a freshly issued token")
        if status == 429:
            raise RateLimited("Royal Mail is rate limiting requests")
        raise CannotConnect(
            f"Royal Mail returned HTTP {status}: {_error_message(response)}"
        )

    def _remember_api_session(self, response: Response) -> None:
        if not (value := response.headers.get(API_SESSION_HEADER)):
            return
        self._api_session = value
        try:
            self._api_session_expiry = float(_jwt_claims(value)["exp"])
        except (ValueError, KeyError, TypeError):
            self._api_session_expiry = time.time() + API_SESSION_FALLBACK_TTL

    async def _request(
        self,
        method: HttpMethod,
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, str] | None = None,
        data: dict[str, str] | None = None,
        timeout: float = WEB_TIMEOUT,
    ) -> Response:
        try:
            return await self._session.request(
                method,
                url,
                params=params,
                data=data,
                headers={"User-Agent": USER_AGENT, **headers},
                timeout=timeout,
            )
        except CurlError as err:
            raise CannotConnect(f"Error talking to Royal Mail: {err}") from err

    def _restore(self, state: dict[str, Any]) -> None:
        now = time.time()
        try:
            for cookie in state.get("cookies") or []:
                if cookie.get("expires") and cookie["expires"] < now:
                    continue
                self._session.cookies.set(
                    cookie["name"],
                    cookie["value"],
                    domain=cookie.get("domain") or "",
                    path=cookie.get("path") or "/",
                    secure=bool(cookie.get("secure")),
                )
            if config := state.get("config"):
                self._config = ApiConfig(**config)
                self._config_fetched = float(state.get("config_fetched") or 0)
            if token := state.get("jwt"):
                self._jwt_claims = _jwt_claims(token)
                self._jwt = token
            self._login_retry_at = float(state.get("login_retry_at") or 0)
            self._login_backoff = min(
                max(float(state.get("login_backoff") or 0), LOGIN_BACKOFF),
                LOGIN_BACKOFF_MAX,
            )
        except (KeyError, TypeError, ValueError, AttributeError) as err:
            _LOGGER.debug("Ignoring unusable saved Royal Mail session: %s", err)
            self._session.cookies.clear()
            self._jwt = None
            self._jwt_claims = {}
            self._config = None
            self._config_fetched = 0.0


def _page_headers() -> dict[str, str]:
    return {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-GB,en;q=0.9",
    }


def _rate_limited(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _RATE_LIMIT_MARKERS)


def _json(response: Response) -> dict[str, Any]:
    try:
        payload = json.loads(response.text)
    except ValueError as err:
        raise CannotConnect("Royal Mail returned something that is not JSON") from err
    if not isinstance(payload, dict):
        raise CannotConnect("Royal Mail returned an unexpected JSON shape")
    return payload


def _jwt_claims(token: Any) -> dict[str, Any]:
    """Decode a JWT payload without verifying it; only expiry and user are read."""
    if not isinstance(token, str) or token.count(".") != 2:
        raise ValueError("not a JWT")
    payload = token.split(".")[1]
    claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    if not isinstance(claims, dict):
        raise TypeError("JWT payload is not an object")
    return claims


def _error_message(response: Response) -> str:
    try:
        payload = json.loads(response.text)
    except ValueError:
        return response.text[:200]
    if isinstance(payload, dict):
        errors = payload.get("errors")
        if isinstance(errors, list) and errors and isinstance(errors[0], dict):
            for key in ("errorDescription", "errorCause", "errorCode"):
                if errors[0].get(key):
                    return str(errors[0][key])
        for key in ("moreInformation", "httpMessage", "message"):
            if payload.get(key):
                return str(payload[key])
    return response.text[:200]


def _text(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("expected a non-empty string")
    return value.strip()


def _clean(value: Any) -> str | None:
    """Strip the website's **bold** markup and blank values."""
    if not isinstance(value, str):
        return None
    return value.replace("**", "").strip() or None


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
