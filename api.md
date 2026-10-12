# Royal Mail web API

These are notes on the requests royalmail.com makes when you track items while signed in, which the integration repeats. Royal Mail doesn't document or support this API, so any of it can change. Tokens, IDs and personal details below are placeholders.

`custom_components/royalmail/api.py` implements everything here.

## Overview

1. Read the web API settings from the website's runtime config.
2. Sign in to www.royalmail.com with a form post, which sets a session cookie.
3. Use the session cookie to get a JWT for the web API. Repeat this step, not the sign-in, when the JWT expires.
4. Call the web API with the JWT: read the tracked-items history, then the summary of every item in it.

www.royalmail.com is behind Akamai, which only lets through clients that look like a real browser at the TLS level. The integration uses [curl_cffi](https://github.com/lexiforest/curl_cffi) with `impersonate="chrome"` for every request; plain Python HTTP clients are blocked. A fresh session is enough, with no JavaScript run: the cookies Akamai sets on the first page load are accepted for the sign-in.

The web API host itself (`api-web.royalmail.com`) needs no Akamai cookies.

## Runtime config

**GET** `https://www.royalmail.com/spalp/rml_track_and_trace/json`

No sign-in needed. The track page loads its settings from here, and so does the integration, so nothing about the web API is hardcoded. The JavaScript bundle also carries a copy of these settings, but it's out of date (it points at a test host with a different client ID), so use this endpoint.

The parts the integration reads:

```json
{
  "appConfig": {
    "epsApiConfig": {
      "baseUrl": "https://api-web.royalmail.com",
      "mailpieces": "/mailpieces/v3/",
      "user": "user",
      "history": "history",
      "summary": "summary",
      "events": "events",
      "jwtToken": "/user-data/jwt-token",
      "networkTimeOut(in_seconds)": 20,
      "ibmClientId": "<CLIENT_ID>"
    }
  },
  "appText": {
    "localisation": {
      "apiLanguage": "en_GB"
    }
  }
}
```

| Key | Used for |
| --- | --- |
| `ibmClientId` | The `x-ibm-client-id` header, and the last segment of the history URL. It's public: the website sends it to every visitor. |
| `baseUrl`, `mailpieces` | The start of every web API URL: `{baseUrl}{mailpieces}`, below written as `{api}`. |
| `user`, `history`, `summary`, `events` | Path segments. |
| `jwtToken` | The path, on www.royalmail.com, of the token endpoint. |
| `apiLanguage` | The `x-rmg-language` header. |
| `networkTimeOut(in_seconds)` | The request timeout. |

`epsApiConfig` has other keys, for features the integration doesn't use, such as customer-reference tracking.

The integration fetches the config on every sign-in and when its copy is a day old. If the web API rejects the client ID, it fetches the config again and retries once. If fetching fails, it keeps using the copy it has.

## Signing in

### 1. Load the sign-in page

**GET** `https://www.royalmail.com/login`

The page is a Drupal site. Find the `<form>` that contains `user_login_form` and take its hidden `form_build_id` value:

```html
<input type="hidden" name="form_build_id" value="form-<RANDOM>" />
```

This request also picks up the Akamai cookies.

### 2. Post the form

**POST** `https://www.royalmail.com/login`

Form-encoded body:

| Field | Value |
| --- | --- |
| `name` | Email address |
| `pass` | Password |
| `form_build_id` | From step 1 |
| `form_id` | `user_login_form` |
| `op` | `Log in` |

Send `Origin: https://www.royalmail.com` and `Referer: https://www.royalmail.com/login`.

**Success**: a redirect to `/?check_logged_in=1`, and an `SSESS<HASH>` session cookie, plus an `authToken` cookie.

**Failure**: you end up back on `/login` with no `SSESS` cookie.

- If the page says *experiencing technical issues* or *temporarily blocked*, Royal Mail is refusing sign-ins. That happens after about three sign-ins in a few minutes. Wait at least 30 minutes; the integration doubles the wait after each refusal, up to four hours.
- Otherwise the email address or password is wrong.

Because of the rate limit, sign in as rarely as possible: keep the session cookies and use them to get new tokens.

## Access token

**GET** `https://www.royalmail.com/user-data/jwt-token` (the `jwtToken` path from the config)

Needs the session cookies, and `X-Requested-With: XMLHttpRequest`.

```json
{
  "jwt_token": "<JWT>"
}
```

The JWT is valid for about two hours. Its payload carries:

| Claim | Meaning |
| --- | --- |
| `sub` | The account's user ID, used in history URLs. |
| `exp` | Expiry, in Unix seconds. |

A non-200 response, or a body without `jwt_token`, means the session has expired: sign in again.

## Web API requests

Every request to `{api}` sends:

| Header | Value |
| --- | --- |
| `x-ibm-client-id` | `ibmClientId` from the config |
| `x-rmg-auth-token` | `Bearer <JWT>` |
| `x-rmg-language` | `apiLanguage` from the config, for example `en_GB` |
| `Origin` | `https://www.royalmail.com` |
| `Referer` | `https://www.royalmail.com/` |
| `x-rmg-api-session` | Only if an earlier response sent one; see [Captcha](#captcha) |

### Tracked-items history

**GET** `{api}user/{sub}/history/{ibmClientId}`

Returns the account's tracked items: the list royalmail.com shows as *Recently tracked items*. It includes items tracked in the Royal Mail app, with the aliases set there.

```json
{
  "jwt": "<SHORT_LIVED_JWT>",
  "mpDetails": [
    {
      "mailPieceId": "AB123456789GB",
      "lastAccessedTimestamp": 1760259000000,
      "alias": "Kettle"
    },
    {
      "mailPieceId": "1B0000000000000000001",
      "lastAccessedTimestamp": 1760172600000
    }
  ]
}
```

`alias` is missing when the item has none. `mpDetails` is empty when the account tracks nothing.

`jwt` stands in for the list of items in the summary request below. It expires about a minute after it's issued, so make the summary request straight away.

### Summary

**GET** `{api}summary?mailPieceId=<SHORT_LIVED_JWT>`

`mailPieceId` is the `jwt` from the history response, not a tracking number.

```json
{
  "mailPieces": [
    {
      "mailPieceId": "AB123456789GB",
      "status": "200",
      "carrierShortName": "RM",
      "carrierFullName": "Royal Mail Group Ltd",
      "summary": {
        "productName": "Royal Mail Tracked 48",
        "lastEventCode": "EVKOP",
        "lastEventName": "Delivered by",
        "lastEventDateTime": "2026-10-12T10:30:00+01:00",
        "lastEventLocationName": "Example Delivery Office",
        "statusCategory": "Delivered",
        "statusDescription": "Delivered",
        "summaryLine": "Your item was delivered on 12-10-2026."
      }
    }
  ]
}
```

Only use `summary` when the item's `status` is `"200"`; otherwise Royal Mail has no tracking for it yet. Text fields can contain `**bold**` markers, which the website renders and the integration strips.

A 400 or 401 response means the history `jwt` expired: fetch the history again and retry.

### Events

**GET** `{api}{reference}/events`

The full tracking history of one item. Looking an item up while signed in also adds it to the account's tracked items, which is how the **Track your item** action works.

This response hasn't been captured from the web API yet. The app API's equivalent, `/mailpieces/v3.1/{reference}/events`, returned the item's `summary` as above, plus an `events` list, newest first:

```json
{
  "mailPieces": {
    "mailPieceId": "AB123456789GB",
    "carrierShortName": "RM",
    "carrierFullName": "Royal Mail Group Ltd",
    "summary": {
      "productName": "Royal Mail Tracked 48",
      "lastEventCode": "EVKOP",
      "lastEventName": "Delivered by",
      "statusCategory": "Delivered"
    },
    "events": [
      {
        "eventCode": "EVKOP",
        "eventName": "Delivered by",
        "eventDateTime": "2026-10-12T10:30:00+01:00",
        "locationName": "Example Delivery Office"
      },
      {
        "eventCode": "EVGPD",
        "eventName": "Due to be delivered today",
        "eventDateTime": "2026-10-12T06:15:00+01:00",
        "locationName": "Example Delivery Office"
      }
    ]
  }
}
```

### Removing items

**DELETE** `{api}user/{sub}/history/{ibmClientId}?mailPieceId=AB123456789GB,CD987654321GB`

Removes one or more items, separated by commas, from the account's tracked items. That removes them from the app too.

### Captcha

The website treats tracking a new item and removing items as protected by a captcha. It sends one of:

- `x-rmg-api-session`: a token valid for about two minutes. Web API responses can carry it as a response header. The website stores the latest one and sends it back on the next requests, and so does the integration.
- `x-rmg-recaptcha`: an hCaptcha token, after the user solves a captcha.

On 2026-10-12 the history and summary requests worked without either. Whether events and removal need one hasn't been tested yet. If Royal Mail answers 401 or 403 with a body that mentions a captcha or the API session, the integration reports that the action needs a captcha.

### Errors

The gateway answers with one of two JSON shapes:

```json
{
  "httpCode": "401",
  "httpMessage": "Unauthorized",
  "moreInformation": "Client id not registered."
}
```

```json
{
  "errors": [
    {
      "errorCode": "<CODE>",
      "errorDescription": "<DESCRIPTION>",
      "errorCause": "<CAUSE>"
    }
  ]
}
```

How the integration reacts:

| Response | Meaning | Reaction |
| --- | --- | --- |
| 401 or 403 mentioning `client id` or `not registered to plan` | The client ID changed | Fetch the config again and retry once |
| 401 or 403 mentioning a captcha or API session | A captcha is needed | Report it |
| Other 401 | The JWT expired | Get a new JWT and retry once |
| 429 | Too many requests | Wait for the next update |

## Event codes

Not a complete list. The integration maps the latest event's code to a sensor state:

| Code | Royal Mail's text | Sensor state |
| --- | --- | --- |
| EVAIE, EVAIP | Sender preparing/despatching item | `in_transit` |
| EVPPA | Accepted at Parcelshop | `in_transit` |
| EVOCO | We've received your item and it's now being processed for delivery | `in_transit` |
| EVDAV, EVIMC, EVDAC, EVBAV, EVIAV | Item received | `in_transit` |
| EVOAC | Item received at | `in_transit` |
| EVORI | Arrived at | `in_transit` |
| EVODO | Item despatched to delivery office or mail centre | `in_transit` |
| RSRXS, RORXS | Delivery request received | `in_transit` |
| EVNRT | Item retention | `in_transit` |
| EVKNA | Delivery attempted, no answer | `in_transit` |
| EVKNR | Delivery attempted | `in_transit` |
| EVNSR | Item prepared for redelivery | `in_transit` |
| EVNDA | Available for redelivery or collection | `in_transit` |
| EVGPD | Due to be delivered today | `out_for_delivery` |
| EVKLS | Delivered to your collection point | `ready_for_collection` |
| EVPLA | Available for collection | `ready_for_collection` |
| EVKOP | Delivered by | `delivered` |
| EVKSF | Delivered to safeplace | `delivered` |
| EVKSP | Delivered and signed | `delivered` |
| EVPLC | Collected | `collected` |
| EVPLF | Not recorded | `collected` |

For a code that isn't listed, the integration falls back to the summary's `statusCategory`: `Delivered` becomes `delivered`, `Collected` becomes `collected`, and anything else `in_transit`.

## The app API

Earlier versions of the integration used the Royal Mail app's API on `api.royalmail.net`. Its sign-in now sits behind Akamai's mobile bot protection, which only the official app passes, and the client ID the integration used no longer works. The notes on it are in this file's git history.
