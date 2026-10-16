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
| `sub` | The account's user ID, used in history URLs. It stays the same if the account's email address changes, so the integration uses it as the account number that identifies a config entry and names its device. |
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
        "uniqueItemId": "<ID>",
        "oneDBarcode": "AB123456789GB",
        "productId": "TO4",
        "productName": "Royal Mail Tracked 48",
        "productDescription": "Aims to deliver within 2-3 days with online tracking",
        "productCategory": "NON-INTERNATIONAL",
        "originCountryCode": "GB",
        "originCountryName": "United Kingdom",
        "destinationCountryCode": "GB",
        "destinationCountryName": "United Kingdom",
        "lastEventCode": "EVKOP",
        "lastEventName": "Delivered by",
        "lastEventDateTime": "2026-10-12T10:30:00+01:00",
        "lastEventLocationName": "Example Delivery Office",
        "statusCategory": "Delivered",
        "statusDescription": "Delivered",
        "statusHelpText": " ",
        "summaryLine": "Your item was delivered on 12-10-2026.",
        "detailedStatusCategory": "Delivered"
      },
      "greenCredentials": {
        "totalCO2e": 205,
        "dataAccuracy": "Average"
      },
      "preadvice": {
        "senderName": null,
        "senderLogo": null
      },
      "links": {
        "events": {
          "href": "/mailpieces/v3/AB123456789GB/events",
          "title": "Events",
          "description": "Get events"
        }
      }
    }
  ]
}
```

Only use `summary` when the item's `status` is `"200"`; otherwise Royal Mail has no tracking for it yet. Text fields can contain `**bold**` markers, which the website renders and the integration strips.

Fields can be missing: `destinationCountry*` isn't always sent, and `greenCredentials` has no `totalCO2e` while `dataAccuracy` is `Calculating`. `totalCO2e` is in grams of CO2e. `dataAccuracy: Average` seems to mean the figure is an average for the service rather than one worked out for the item. `preadvice` names the sender only when the sender told Royal Mail about the item in advance.

`statusCategory` is one of the progress steps the track page has an icon for: `We're expecting it`, `We've got it`, `Left Origin Country`, `In Customs`, `Released from Customs`, `Left the UK`, `In Transit`, `Ready for Delivery`, `Delivery Attempted`, `Pending`, `Returned to Sender`, `Delivered`, `Collected`, `Duplicate Identified`, `Restricted or Prohibited Contents` and `No Status` (from `appText.trackingInformation.statusCategoryIcon` in the runtime config).

The integration reads the product, countries, latest event, status, summary line, carrier, sender and carbon footprint. It ignores the IDs, `statusHelpText` and `detailedStatusCategory` (so far the same as `statusCategory`).

`links.events.href` doesn't always use the item's reference. For some items it names another ID Royal Mail has for the item, such as a 21-character `1B…` ID or a short hexadecimal one.

An item's page on royalmail.com is `https://www.royalmail.com/track-your-item#/tracking-results/<reference>`.

A 400 or 401 response means the history `jwt` expired: fetch the history again and retry.

### Events

**GET** `{api}{reference}/events`

The full tracking history of one item. Looking an item up while signed in also adds it to the account's tracked items, which is how the **Track your item** action works.

This response hasn't been captured from the web API, because Royal Mail only answers it after a captcha (see [Captcha](#captcha)). The app API's equivalent, `/mailpieces/v3.1/{reference}/events`, returned the item's `summary` as above, plus an `events` list, newest first:

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

Looking an item up (events) needs a captcha, and removing items probably does too. With those requests the website sends one of:

- `x-rmg-api-session`: a token valid for about two minutes. Web API responses can carry it as a response header. The website stores the latest one and sends it back on the next requests, and so does the integration.
- `x-rmg-recaptcha`: an hCaptcha token, after the user solves a captcha.

The track page runs an invisible hCaptcha (`appText.hCaptcha` in the runtime config, with `widget_size: invisible` and a site key) when you open an item. On 2026-10-14 it showed an image challenge.

Tested on 2026-10-14, signed in with a fresh JWT:

- History and summary worked without either header.
- Events without either header was never answered, even for items the account already tracked. Over HTTP/2 the server reset the stream (curl error 92). Over HTTP/1.1 it sent nothing until the request timed out (curl error 28).
- Removal wasn't tested, because it changes the account.
- Whether the `x-rmg-api-session` that comes back after a solved captcha lets later lookups through without another one hasn't been tested.

The integration reports that an action needs a captcha in two cases: Royal Mail answers 401 or 403 with a body that mentions a captcha or the API session, or it drops a lookup in one of the two ways above.

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
| No answer to a lookup: stream reset or timeout | A captcha is needed | Report it |
| Other 401 | The JWT expired | Get a new JWT and retry once |
| 429 | Too many requests | Wait for the next update |

## Event codes

Not a complete list. Codes with a sensor state set the state directly; for the others, marked "category", the summary's `statusCategory` decides:

| Code | Royal Mail's text | Sensor state |
| --- | --- | --- |
| EVAIE, EVAIP | Sender preparing/despatching item | `expected` |
| EVPPA | Accepted at Parcelshop | category |
| EVOCO | We've received your item and it's now being processed for delivery | category |
| EVDAV, EVIMC, EVDAC, EVBAV, EVIAV | Item received | category |
| EVOAC | Item received at | category |
| EVORI | Arrived at | category |
| EVODO | Item despatched to delivery office or mail centre | category |
| RSRXS, RORXS | Delivery request received | category |
| EVNRT | Item retention | category |
| EVKNA | Delivery attempted, no answer | `delivery_attempted` |
| EVKNR | Delivery attempted | `delivery_attempted` |
| EVNSR | Item prepared for redelivery | category |
| EVNDA | Available for redelivery or collection | `delivery_attempted` |
| EVHAC | Item Received by Royal Mail (international) | category |
| EVHOE | Item Leaving the UK (international) | category |
| EVJIC | With Customs in destination country (international) | `in_customs` |
| EVJOE | Item Received (international) | category |
| EVIIS | Item received at Sorting Office (international) | category |
| EVGID | Arrived at Delivery Office (international) | category |
| EVGPD | Due to be delivered today | `out_for_delivery` |
| EVKPD | Due to be delivered today (international) | `out_for_delivery` |
| EVKLS | Delivered to your collection point | `ready_for_collection` |
| EVPLA | Available for collection | `ready_for_collection` |
| EVKOP | Delivered by | `delivered` |
| EVKSF | Delivered to safeplace | `delivered` |
| EVKSP | Delivered and signed | `delivered` |
| EVPLC | Collected | `collected` |
| EVPLF | Not recorded | `collected` |

The integration works out an item's state in this order:

1. A `statusCategory` that says the item went wrong wins: `Returned to Sender` becomes `returned_to_sender`, and `Duplicate Identified` or `Restricted or Prohibited Contents` becomes `problem`. They come first because a returned item's last event is an ordinary one, such as `EVKOP` when it reaches the sender.
2. Otherwise, a code with a sensor state in the table above.
3. Otherwise, the `statusCategory`: `We're expecting it` becomes `expected`, `In Customs` becomes `in_customs`, `Delivery Attempted` becomes `delivery_attempted`, `Delivered` becomes `delivered`, `Collected` becomes `collected` and `No Status` becomes unknown. Anything else is `in_transit`, including `Pending`, which shares the customs icon on the track page but whose meaning isn't known.

## The app API

Earlier versions of the integration used the Royal Mail app's API on `api.royalmail.net`. Its sign-in now sits behind Akamai's mobile bot protection, which only the official app passes, and the client ID the integration used no longer works. The notes on it are in this file's git history.
