"""Tests for the royalmail.com web client.

The client runs against a fake HTTP session that answers with synthetic
responses, so these tests never talk to Royal Mail.
"""

import base64
from collections.abc import Callable
import copy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
import json
import time
from typing import Any

from curl_cffi import CurlError
from curl_cffi.requests import Cookies
from freezegun.api import FrozenDateTimeFactory
import pytest

from custom_components.royalmail.api import (
    LOGIN_BACKOFF,
    LOGIN_BACKOFF_MAX,
    ApiConfig,
    CannotConnect,
    CaptchaRequired,
    InvalidAuth,
    Parcel,
    RateLimited,
    RoyalMailWebClient,
)

WEB = "https://www.royalmail.com"
LOGIN_URL = f"{WEB}/login"
CONFIG_URL = f"{WEB}/spalp/rml_track_and_trace/json"
JWT_URL = f"{WEB}/user-data/jwt-token"
API = "https://api.example.test/mailpieces/v3"
HISTORY_URL = f"{API}/user/user-guid/history/fake-client-id"
NEW_HISTORY_URL = f"{API}/user/user-guid/history/new-client-id"
SUMMARY_URL = f"{API}/summary"
EVENTS_URL = f"{API}/AB123456789GB/events"

LOGIN_PAGE = (
    '<form action="/search" id="search-form"><input name="q"></form>'
    '<form class="user-login-form" id="user_login_form" method="post">'
    '<input type="hidden" name="form_build_id" value="form-abc123">'
    "</form>"
)
CONFIG: dict[str, Any] = {
    "appConfig": {
        "epsApiConfig": {
            "ibmClientId": "fake-client-id",
            "baseUrl": "https://api.example.test/",
            "mailpieces": "/mailpieces/v3/",
            "user": "user",
            "history": "history/",
            "summary": "summary",
            "events": "events",
            "jwtToken": "user-data/jwt-token",
            "networkTimeOut(in_seconds)": 15,
        }
    },
    "appText": {"localisation": {"apiLanguage": "en"}},
}
HISTORY: dict[str, Any] = {
    "jwt": "history-token",
    "mpDetails": [
        {"mailPieceId": "AB123456789GB", "alias": " **Kettle** "},
        {"mailPieceId": "CD987654321GB", "alias": ""},
        {"alias": "no reference"},
        "junk",
    ],
}
SUMMARY: dict[str, Any] = {
    "mailPieces": [
        {
            "mailPieceId": "AB123456789GB",
            "status": "200",
            "carrierShortName": "RM",
            "summary": {
                "productName": "Tracked 24",
                "lastEventName": "**Delivered**",
                "lastEventCode": "EVKSP",
                "lastEventDateTime": "2026-10-12T09:30:00+01:00",
                "lastEventLocationName": "Example Delivery Office",
                "statusCategory": "Delivered",
                "statusDescription": "We delivered your item",
                "summaryLine": "Delivered on Monday",
            },
        },
        {
            "mailPieceId": "CD987654321GB",
            "status": "404",
            "summary": {"productName": "ignored"},
        },
        {"status": "200"},
    ]
}


def make_jwt(expires_in: float = 7200, sub: str = "user-guid") -> str:
    """Make an unsigned JWT; the client only reads its claims."""
    claims = json.dumps({"sub": sub, "exp": time.time() + expires_in}).encode()
    return f"header.{base64.urlsafe_b64encode(claims).rstrip(b'=').decode()}.sig"


@dataclass
class FakeResponse:
    """The parts of a curl_cffi response the client reads."""

    status_code: int = 200
    text: str = ""
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)


def ok(payload: Any, **kwargs: Any) -> FakeResponse:
    """Return a JSON response."""
    return FakeResponse(200, json.dumps(payload), **kwargs)


@dataclass
class Request:
    """A request the client made."""

    method: str
    url: str
    params: dict[str, str] | None
    data: dict[str, str] | None
    headers: dict[str, str]


type Responder = FakeResponse | Exception | Callable[[FakeSession], FakeResponse]


class FakeSession:
    """Answers requests from canned responses, one route at a time."""

    def __init__(self) -> None:
        """Start with no routes and an empty cookie jar."""
        self.cookies = Cookies()
        self.routes: dict[tuple[str, str], list[Responder]] = {}
        self.requests: list[Request] = []
        self.closed = False

    def route(self, method: str, url: str, *responses: Responder) -> None:
        """Answer with each response in turn, repeating the last one."""
        self.routes[(method, url)] = list(responses)

    @property
    def urls(self) -> list[str]:
        """Return the requests made so far."""
        return [f"{request.method} {request.url}" for request in self.requests]

    def last(self, method: str, url: str) -> Request:
        """Return the latest request to a URL."""
        return next(
            request
            for request in reversed(self.requests)
            if (request.method, request.url) == (method, url)
        )

    async def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, str] | None = None,
        data: dict[str, str] | None = None,
        headers: dict[str, str],
        timeout: float,
    ) -> FakeResponse:
        """Answer a request."""
        self.requests.append(Request(method, url, params, data, headers))
        responses = self.routes.get((method, url))
        if not responses:
            raise AssertionError(f"Unexpected request: {method} {url}")
        response = responses.pop(0) if len(responses) > 1 else responses[0]
        if isinstance(response, Exception):
            raise response
        if callable(response):
            return response(self)
        return response

    async def close(self) -> None:
        """Close the session."""
        self.closed = True


def signed_in(session: FakeSession) -> FakeResponse:
    """Answer the login form the way a successful login does."""
    session.cookies.set("SSESSabc", "drupal-session", domain=".royalmail.com")
    return FakeResponse(200, "<html>Welcome</html>", url=f"{WEB}/?check_logged_in=1")


def refused(text: str) -> Callable[[FakeSession], FakeResponse]:
    """Answer the login form by showing it again."""
    return lambda session: FakeResponse(200, LOGIN_PAGE + text, url=LOGIN_URL)


def saved_state(
    *, token: str | None = None, cookie: bool = True, config_age: float = 0
) -> dict[str, Any]:
    """Return a session saved by an earlier run."""
    return {
        "jwt": token or make_jwt(),
        "cookies": [
            {
                "name": "SSESSabc",
                "value": "drupal-session",
                "domain": ".royalmail.com",
                "path": "/",
                "secure": True,
                "expires": None,
            }
        ]
        if cookie
        else [],
        "config": asdict(ApiConfig.from_website(CONFIG)),
        "config_fetched": time.time() - config_age,
        "login_retry_at": 0.0,
        "login_backoff": LOGIN_BACKOFF,
    }


def make_client(
    session: FakeSession, state: dict[str, Any] | None = None
) -> RoyalMailWebClient:
    """Create a client that talks to the fake session."""
    return RoyalMailWebClient(
        "user@example.com",
        "correct-horse",
        state,
        session=session,  # type: ignore[arg-type]
    )


@pytest.fixture
def token() -> str:
    """Return the token the website mints."""
    return make_jwt()


@pytest.fixture
def session(token: str) -> FakeSession:
    """Return a fake royalmail.com that accepts the login."""
    session = FakeSession()
    session.route("GET", LOGIN_URL, FakeResponse(200, LOGIN_PAGE, url=LOGIN_URL))
    session.route("POST", LOGIN_URL, signed_in)
    session.route("GET", CONFIG_URL, ok(CONFIG))
    session.route("GET", JWT_URL, ok({"jwt_token": token}))
    session.route("GET", HISTORY_URL, ok(HISTORY))
    session.route("GET", SUMMARY_URL, ok(SUMMARY))
    return session


SIGN_IN = [
    f"GET {LOGIN_URL}",
    f"POST {LOGIN_URL}",
    f"GET {CONFIG_URL}",
    f"GET {JWT_URL}",
]
READ_HISTORY = [f"GET {HISTORY_URL}", f"GET {SUMMARY_URL}"]


def test_config_from_website() -> None:
    """Test the website's runtime config is used for every API detail."""
    config = ApiConfig.from_website(CONFIG)

    assert config == ApiConfig(
        client_id="fake-client-id",
        base_url="https://api.example.test",
        mailpieces_path="/mailpieces/v3/",
        user_seg="user",
        history_seg="history",
        summary_seg="summary",
        events_seg="events",
        jwt_token_path="/user-data/jwt-token",
        language="en",
        timeout=15.0,
    )
    assert config.history_url("a/b c") == (
        f"{API}/user/a%2Fb%20c/history/fake-client-id"
    )


def test_config_default_timeout() -> None:
    """Test the timeout is optional."""
    payload = copy.deepcopy(CONFIG)
    del payload["appConfig"]["epsApiConfig"]["networkTimeOut(in_seconds)"]

    assert ApiConfig.from_website(payload).timeout == 20


@pytest.mark.parametrize(
    "change",
    [
        lambda c: c["appConfig"]["epsApiConfig"].pop("ibmClientId"),
        lambda c: c["appConfig"]["epsApiConfig"].update(ibmClientId="  "),
        lambda c: c["appConfig"]["epsApiConfig"].update(ibmClientId=123),
        lambda c: c["appConfig"]["epsApiConfig"].update(baseUrl="http://plain.test"),
        lambda c: c["appConfig"]["epsApiConfig"].update(
            {"networkTimeOut(in_seconds)": "soon"}
        ),
        lambda c: c["appText"].pop("localisation"),
        lambda c: c.update(appConfig=[]),
    ],
)
def test_config_unexpected_format(change: Callable[[dict[str, Any]], Any]) -> None:
    """Test a config the client doesn't understand is refused, not guessed."""
    payload = copy.deepcopy(CONFIG)
    change(payload)

    with pytest.raises(CannotConnect, match="config format"):
        ApiConfig.from_website(payload)


async def test_sign_in_and_read_history(session: FakeSession, token: str) -> None:
    """Test a fresh client signs in once and merges history with summaries."""
    client = make_client(session)

    parcels = await client.async_get_parcels()

    assert session.urls == SIGN_IN + READ_HISTORY
    assert session.last("POST", LOGIN_URL).data == {
        "name": "user@example.com",
        "pass": "correct-horse",
        "form_build_id": "form-abc123",
        "form_id": "user_login_form",
        "op": "Log in",
    }
    assert session.last("GET", JWT_URL).headers["X-Requested-With"] == "XMLHttpRequest"
    headers = session.last("GET", HISTORY_URL).headers
    assert headers["x-ibm-client-id"] == "fake-client-id"
    assert headers["x-rmg-auth-token"] == f"Bearer {token}"
    assert headers["x-rmg-language"] == "en"
    assert "x-rmg-api-session" not in headers
    assert session.last("GET", SUMMARY_URL).params == {"mailPieceId": "history-token"}
    assert client.config == ApiConfig.from_website(CONFIG)
    assert parcels == {
        "AB123456789GB": Parcel(
            tracking_number="AB123456789GB",
            alias="Kettle",
            product="Tracked 24",
            last_event="Delivered",
            last_event_code="EVKSP",
            last_event_time=datetime(
                2026, 10, 12, 9, 30, tzinfo=timezone(timedelta(hours=1))
            ),
            last_event_location="Example Delivery Office",
            status_category="Delivered",
            status_description="We delivered your item",
            summary_line="Delivered on Monday",
            carrier="RM",
            summary_ok=True,
        ),
        # Royal Mail had no summary for this one, so only the history is used.
        "CD987654321GB": Parcel("CD987654321GB"),
    }

    # The token is reused until it nears expiry.
    await client.async_get_parcels()
    assert session.urls == SIGN_IN + READ_HISTORY * 2


async def test_resume_saved_session(session: FakeSession) -> None:
    """Test a saved session reads the history without signing in again."""
    client = make_client(session)
    await client.async_get_parcels()
    state = client.state
    json.dumps(state)  # Config entries need it JSON serialisable.

    resumed = FakeSession()
    resumed.route("GET", HISTORY_URL, ok(HISTORY))
    resumed.route("GET", SUMMARY_URL, ok(SUMMARY))
    parcels = await make_client(resumed, state).async_get_parcels()

    assert resumed.urls == READ_HISTORY
    assert set(parcels) == {"AB123456789GB", "CD987654321GB"}
    assert resumed.cookies.get("SSESSabc") == "drupal-session"


async def test_remint_token_from_session(session: FakeSession) -> None:
    """Test an expiring token is re-minted from the website session."""
    client = make_client(session, saved_state(token=make_jwt(expires_in=60)))

    await client.async_get_parcels()

    assert session.urls == [f"GET {JWT_URL}", *READ_HISTORY]


async def test_expired_session_signs_in(session: FakeSession, token: str) -> None:
    """Test a website session that can't mint tokens leads to a new login."""
    session.route(
        "GET", JWT_URL, FakeResponse(403, "Forbidden"), ok({"jwt_token": token})
    )
    client = make_client(session, saved_state(token=make_jwt(expires_in=60)))

    await client.async_get_parcels()

    assert session.urls == [f"GET {JWT_URL}", *SIGN_IN, *READ_HISTORY]


@pytest.mark.parametrize(
    "payload",
    [
        {"error": "nope"},
        {"jwt_token": "not-a-jwt"},
        {"jwt_token": f"h.{base64.urlsafe_b64encode(b'[1]').decode()}.s"},
        {"jwt_token": make_jwt(sub="")},
    ],
)
async def test_signed_in_without_token(
    session: FakeSession, payload: dict[str, Any]
) -> None:
    """Test a login that doesn't lead to a usable token."""
    session.route("GET", JWT_URL, ok(payload))

    with pytest.raises(CannotConnect, match="could not get an API token"):
        await make_client(session).async_get_parcels()


@pytest.mark.parametrize(
    "responder",
    [
        refused("Unrecognized username or password."),
        # A session cookie alone isn't enough if we land back on the form.
        lambda session: (
            signed_in(session),
            FakeResponse(200, LOGIN_PAGE, url=f"{LOGIN_URL}/"),
        )[1],
    ],
)
async def test_wrong_password(session: FakeSession, responder: Responder) -> None:
    """Test a refused login is reported as bad credentials."""
    session.route("POST", LOGIN_URL, responder)
    client = make_client(session)

    with pytest.raises(InvalidAuth):
        await client.async_login()

    assert client.state["login_retry_at"] == 0


async def test_login_rate_limited(
    session: FakeSession, freezer: FrozenDateTimeFactory
) -> None:
    """Test refused logins back off, doubling, and reset after a success."""
    session.route(
        "POST",
        LOGIN_URL,
        refused("We are experiencing technical issues. Please try later."),
        refused("Sorry, this IP is temporarily blocked."),
        signed_in,
    )
    client = make_client(session)

    with pytest.raises(RateLimited):
        await client.async_login()
    assert client.state["login_retry_at"] == time.time() + LOGIN_BACKOFF
    assert client.state["login_backoff"] == LOGIN_BACKOFF * 2

    # Neither this client nor one resumed from its state tries again yet.
    attempts = len(session.requests)
    with pytest.raises(RateLimited, match="Not retrying"):
        await client.async_login()
    with pytest.raises(RateLimited, match="Not retrying"):
        await make_client(session, client.state).async_ensure_token()
    assert len(session.requests) == attempts

    freezer.tick(LOGIN_BACKOFF + 1)
    with pytest.raises(RateLimited):
        await client.async_login()
    assert client.state["login_retry_at"] == time.time() + LOGIN_BACKOFF * 2
    assert client.state["login_backoff"] == LOGIN_BACKOFF * 4

    freezer.tick(LOGIN_BACKOFF * 2 + 1)
    await client.async_login()
    assert client.state["login_retry_at"] == 0
    assert client.state["login_backoff"] == LOGIN_BACKOFF


async def test_login_backoff_capped(session: FakeSession) -> None:
    """Test the login backoff never grows past its cap."""
    session.route("POST", LOGIN_URL, refused("temporarily blocked"))
    state = {"login_backoff": LOGIN_BACKOFF_MAX * 10}
    client = make_client(session, state)

    with pytest.raises(RateLimited):
        await client.async_login()

    assert client.state["login_retry_at"] == pytest.approx(
        time.time() + LOGIN_BACKOFF_MAX, abs=5
    )
    assert client.state["login_backoff"] == LOGIN_BACKOFF_MAX


@pytest.mark.parametrize(
    ("method", "responder", "message"),
    [
        ("GET", FakeResponse(503, "Down"), "Login page returned HTTP 503"),
        ("GET", FakeResponse(200, "<html>No form here</html>"), "Login form not found"),
        ("GET", CurlError("TLS handshake failed"), "TLS handshake failed"),
        ("POST", FakeResponse(500, "Error"), "Login returned HTTP 500"),
    ],
)
async def test_login_cannot_connect(
    session: FakeSession, method: str, responder: Responder, message: str
) -> None:
    """Test login failures that say nothing about the credentials."""
    session.route(method, LOGIN_URL, responder)

    with pytest.raises(CannotConnect, match=message):
        await make_client(session).async_login()


async def test_config_refreshed_daily(session: FakeSession) -> None:
    """Test a day-old config is fetched again, picking up a new client id."""
    new_config = copy.deepcopy(CONFIG)
    new_config["appConfig"]["epsApiConfig"]["ibmClientId"] = "new-client-id"
    session.route("GET", CONFIG_URL, ok(new_config))
    session.route("GET", NEW_HISTORY_URL, ok(HISTORY))
    client = make_client(session, saved_state(config_age=25 * 3600))

    await client.async_get_parcels()

    assert session.urls == [
        f"GET {CONFIG_URL}",
        f"GET {NEW_HISTORY_URL}",
        f"GET {SUMMARY_URL}",
    ]
    headers = session.last("GET", NEW_HISTORY_URL).headers
    assert headers["x-ibm-client-id"] == "new-client-id"
    assert client.config is not None
    assert client.config.client_id == "new-client-id"


@pytest.mark.parametrize(
    "response",
    [
        FakeResponse(500, "Error"),
        FakeResponse(200, "<html>Maintenance</html>"),
        ok({"appConfig": {}}),
    ],
)
async def test_config_refresh_failure_keeps_cache(
    session: FakeSession, freezer: FrozenDateTimeFactory, response: FakeResponse
) -> None:
    """Test the cached config is used, and retried hourly, when a refresh fails."""
    session.route("GET", CONFIG_URL, response)
    client = make_client(session, saved_state(config_age=25 * 3600))

    await client.async_get_parcels()
    await client.async_get_parcels()

    assert session.urls == [f"GET {CONFIG_URL}", *READ_HISTORY, *READ_HISTORY]

    freezer.tick(3601)
    await client.async_get_parcels()

    assert session.urls[-3:] == [f"GET {CONFIG_URL}", *READ_HISTORY]


async def test_config_unavailable(session: FakeSession) -> None:
    """Test nothing is guessed when there's no config at all."""
    session.route("GET", CONFIG_URL, FakeResponse(500, "Error"))

    with pytest.raises(CannotConnect, match="config returned HTTP 500"):
        await make_client(session).async_get_parcels()


async def test_client_id_rejected(session: FakeSession) -> None:
    """Test a rejected client id refreshes the config and retries."""
    new_config = copy.deepcopy(CONFIG)
    new_config["appConfig"]["epsApiConfig"]["ibmClientId"] = "new-client-id"
    session.route("GET", CONFIG_URL, ok(new_config))
    session.route(
        "GET",
        HISTORY_URL,
        FakeResponse(
            401, '{"httpCode":"401","moreInformation":"Client id not registered."}'
        ),
    )
    session.route("GET", NEW_HISTORY_URL, ok(HISTORY))
    client = make_client(session, saved_state())

    await client.async_get_parcels()

    assert session.urls == [
        f"GET {HISTORY_URL}",
        f"GET {CONFIG_URL}",
        f"GET {NEW_HISTORY_URL}",
        f"GET {SUMMARY_URL}",
    ]
    headers = session.last("GET", NEW_HISTORY_URL).headers
    assert headers["x-ibm-client-id"] == "new-client-id"


async def test_client_id_still_rejected(session: FakeSession) -> None:
    """Test the client gives up if the published client id is rejected too."""
    session.route(
        "GET",
        HISTORY_URL,
        FakeResponse(403, '{"moreInformation":"Client id not registered to plan"}'),
    )

    with pytest.raises(CannotConnect, match="published client id"):
        await make_client(session, saved_state()).async_get_parcels()

    assert session.urls == [
        f"GET {HISTORY_URL}",
        f"GET {CONFIG_URL}",
        f"GET {HISTORY_URL}",
    ]


async def test_token_rejected(session: FakeSession) -> None:
    """Test a rejected token is re-minted once."""
    session.route(
        "GET",
        HISTORY_URL,
        FakeResponse(401, '{"httpMessage":"Unauthorized"}'),
        ok(HISTORY),
    )

    await make_client(session, saved_state()).async_get_parcels()

    assert session.urls == [f"GET {HISTORY_URL}", f"GET {JWT_URL}", *READ_HISTORY]


async def test_token_still_rejected(session: FakeSession) -> None:
    """Test a freshly minted token being rejected isn't retried forever."""
    session.route(
        "GET", HISTORY_URL, FakeResponse(401, '{"httpMessage":"Unauthorized"}')
    )

    with pytest.raises(CannotConnect, match="freshly issued token"):
        await make_client(session, saved_state()).async_get_parcels()

    assert session.urls == [
        f"GET {HISTORY_URL}",
        f"GET {JWT_URL}",
        f"GET {HISTORY_URL}",
    ]


async def test_captcha_required(session: FakeSession) -> None:
    """Test a captcha challenge is reported as such."""
    session.route(
        "GET",
        EVENTS_URL,
        FakeResponse(
            403,
            '{"errors":[{"errorCode":"E0004","errorDescription":"Captcha validation failed"}]}',
        ),
    )

    with pytest.raises(CaptchaRequired):
        await make_client(session, saved_state()).async_track("AB123456789GB")


@pytest.mark.parametrize(
    ("response", "error", "message"),
    [
        (FakeResponse(429, "Too many"), RateLimited, "rate limiting"),
        (
            FakeResponse(500, '{"errors":[{"errorCause":"Mailpiece service down"}]}'),
            CannotConnect,
            "HTTP 500: Mailpiece service down",
        ),
        (
            FakeResponse(503, '{"moreInformation":"Backend unavailable"}'),
            CannotConnect,
            "HTTP 503: Backend unavailable",
        ),
        (FakeResponse(502, "Bad gateway"), CannotConnect, "HTTP 502: Bad gateway"),
        (FakeResponse(500, '["odd"]'), CannotConnect, r'HTTP 500: \["odd"\]'),
        (FakeResponse(404, "{}"), CannotConnect, "HTTP 404: {}"),
    ],
)
async def test_api_errors(
    session: FakeSession, response: FakeResponse, error: type[Exception], message: str
) -> None:
    """Test web API errors are classified and explained."""
    session.route("GET", HISTORY_URL, response)

    with pytest.raises(error, match=message):
        await make_client(session, saved_state()).async_get_parcels()


@pytest.mark.parametrize("text", ["<html>Oops</html>", '["not", "an", "object"]'])
async def test_unexpected_response(session: FakeSession, text: str) -> None:
    """Test responses that aren't the expected JSON."""
    session.route("GET", HISTORY_URL, FakeResponse(200, text))

    with pytest.raises(CannotConnect):
        await make_client(session, saved_state()).async_get_parcels()


async def test_history_token_expired(session: FakeSession) -> None:
    """Test the history is read again when its token expired before the summary."""
    session.route("GET", SUMMARY_URL, FakeResponse(400, "Expired"), ok(SUMMARY))

    parcels = await make_client(session, saved_state()).async_get_parcels()

    assert session.urls == READ_HISTORY * 2
    assert len(parcels) == 2


async def test_history_token_keeps_expiring(session: FakeSession) -> None:
    """Test the client gives up if the summary keeps refusing the history token."""
    session.route("GET", SUMMARY_URL, FakeResponse(401, "Expired"))

    with pytest.raises(CannotConnect, match="kept rejecting"):
        await make_client(session, saved_state()).async_get_parcels()

    assert session.urls == READ_HISTORY * 2


@pytest.mark.parametrize("details", [[], None])
async def test_empty_history(session: FakeSession, details: list[Any] | None) -> None:
    """Test an account tracking nothing."""
    session.route(
        "GET", HISTORY_URL, ok({"jwt": "history-token", "mpDetails": details})
    )

    assert await make_client(session, saved_state()).async_get_parcels() == {}
    assert session.urls == [f"GET {HISTORY_URL}"]


async def test_api_session_echoed(
    session: FakeSession, freezer: FrozenDateTimeFactory
) -> None:
    """Test the web API session header is sent back until it expires."""
    api_session = make_jwt(expires_in=120)
    session.route(
        "GET", HISTORY_URL, ok(HISTORY, headers={"x-rmg-api-session": api_session})
    )
    client = make_client(session, saved_state())

    await client.async_get_parcels()

    assert session.last("GET", SUMMARY_URL).headers["x-rmg-api-session"] == api_session

    freezer.tick(121)
    session.route("GET", HISTORY_URL, ok(HISTORY))
    await client.async_get_parcels()

    assert "x-rmg-api-session" not in session.last("GET", HISTORY_URL).headers


async def test_opaque_api_session(
    session: FakeSession, freezer: FrozenDateTimeFactory
) -> None:
    """Test an API session header that isn't a JWT gets a short lifetime."""
    session.route(
        "GET", HISTORY_URL, ok(HISTORY, headers={"x-rmg-api-session": "opaque"})
    )
    client = make_client(session, saved_state())

    await client.async_get_parcels()
    assert session.last("GET", SUMMARY_URL).headers["x-rmg-api-session"] == "opaque"

    freezer.tick(111)
    session.route("GET", HISTORY_URL, ok(HISTORY))
    await client.async_get_parcels()
    assert "x-rmg-api-session" not in session.last("GET", HISTORY_URL).headers


async def test_track_and_remove(session: FakeSession) -> None:
    """Test looking up and removing items."""
    session.route(
        "GET", EVENTS_URL, ok({"mailPieces": {"mailPieceId": "AB123456789GB"}})
    )
    remove_url = f"{HISTORY_URL}?mailPieceId=AB123456789GB,CD987654321GB"
    session.route("DELETE", remove_url, FakeResponse(200, ""))
    client = make_client(session, saved_state())

    assert await client.async_track("AB123456789GB") == {
        "mailPieces": {"mailPieceId": "AB123456789GB"}
    }
    await client.async_remove(["AB123456789GB", "CD987654321GB"])

    assert session.urls == [f"GET {EVENTS_URL}", f"DELETE {remove_url}"]
    assert (
        session.last("DELETE", remove_url).headers["x-ibm-client-id"]
        == "fake-client-id"
    )


async def test_unusable_saved_state(session: FakeSession) -> None:
    """Test a corrupt saved session is dropped and the client signs in."""
    client = make_client(session, {"config": {"unknown": 1}, "jwt": "garbage"})

    assert client.config is None
    await client.async_get_parcels()
    assert session.urls == SIGN_IN + READ_HISTORY


async def test_expired_cookies_not_restored(session: FakeSession) -> None:
    """Test cookies past their expiry are left behind."""
    state = saved_state()
    state["cookies"][0]["expires"] = time.time() - 1

    client = make_client(session, state)

    assert client.state["cookies"] == []


async def test_close(session: FakeSession) -> None:
    """Test closing the client closes its HTTP session."""
    await make_client(session).async_close()

    assert session.closed


@pytest.mark.parametrize(
    ("item", "expected"),
    [
        (None, Parcel("AB1")),
        ({"status": 200, "summary": "odd"}, Parcel("AB1")),
        (
            {
                "status": 200,
                "carrierFullName": "Parcelforce Worldwide",
                "carrierShortName": "PFW",
                "summary": {"lastEventDateTime": "yesterday", "summaryLine": "  "},
            },
            Parcel("AB1", carrier="Parcelforce Worldwide", summary_ok=True),
        ),
        (
            {"status": "200", "summary": {"lastEventDateTime": 1760261400}},
            Parcel("AB1", summary_ok=True),
        ),
    ],
)
def test_parcel_from_api(item: dict[str, Any] | None, expected: Parcel) -> None:
    """Test odd summaries are handled the way the website handles them."""
    assert Parcel.from_api({"mailPieceId": "AB1", "alias": 5}, item) == expected
