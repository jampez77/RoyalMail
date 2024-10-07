### API Documentation - Anonymized Version

Below is an anonymized version of the API documentation. Sensitive information like API keys, tokens, and personal data has been replaced with placeholders.

## Event Codes

This is by no means an extensive list of event codes that a parcel can encounter but i'll put what i find here as they can provide useful information especially when used with the corresponding location name.

- EVKSP: Delivered and Signed
- EVKSF: Delivered to Safeplace by
- EVGPD: Due to be delivered today
- EVNSR: Item Prepared for Redelivery
- EVNDA: Available for Redelivery or Collection
- EVKNA: Delivery Attempted - No Answer
- EVODO: Item Despatched to DO
- EVORI: Arrived at
- EVODO: Item Despatched to MC
- EVOAC: Item received at
- EVAIE/EVAIP: Sender preparing/despatching item
- EVPPA: Accepted at Parcelshop
- EVDAV/EVIMC/EVDAC: Item Received
- EVKOP: Delivered by
- EVNRT: Item Retention
- EVOCO: We've received your item and its now being processed for delivery.
- EVKNR: Delivery Attempted
- RSRXS: Delivery request received


# Royal Mail Tracking API

## Authentication

### Login
**Request:**

****POST****: `https://api.example.com/login/v1/tokens`

***Headers:***
- `x-ibm-client-id = e83f49c439b0ebc0b130692bcb8b1cde`

***Body:***
```json
{
   "device_id": "<UNIQUE_DEVICE_ID>",
   "grant_type": "password",
   "password": "<YOUR_PASSWORD>",
   "username": "<YOUR_EMAIL>"
}
```
***Response:***
```json
{
   "access_token": "<ACCESS_TOKEN>",
   "refresh_token": "<REFRESH_TOKEN>",
   "token_type": "Bearer",
   "expires_in": 7199,
   "guid": "<USER_GUID>",
   "first_name": "<FIRST_NAME>"
}
```

### Refresh Token

This should be called if a `401 Unauthorized` response is received.

**Request**

****POST****: `https://api.royalmail.net/login/v1/tokens`

***Headers***:
- `x-ibm-client-id`: `e83f49c439b0ebc0b130692bcb8b1cde`

***Body***:
```json
{
   "device_id": "<UNIQUE_DEVICE_ID>",
   "grant_type": "refresh_token",
   "refresh_token": "<REFRESH_TOKEN>"
}
```
***Response:***
```json
{
   "access_token": "<ACCESS_TOKEN>",
   "refresh_token": "<REFRESH_TOKEN>",
   "token_type": "Bearer",
   "expires_in": 7199,
   "guid": "<USER_GUID>",
   "first_name": "<FIRST_NAME>"
}
```

## Pending Items

**Request**

****GET****: `https://api.royalmail.net/track/v2/pending/items`

***Headers***:
- `Authorization`: `Bearer (session access_token)`
- `x-ibm-client-id`: `e83f49c439b0ebc0b130692bcb8b1cde`
- `origin`: `consumermobile.royalmail.com`

***Response***

```json
{
   "totalRecords": 0,
   "mailPieces": []
}
```

## Mailpieces

**Request**

****GET****: `https://api.royalmail.net/mailpieces/v3.1/user/<GUID>/history/<IBM-CLIENT-ID>?limit=6`

***Headers***:
- `Authorization`: `Bearer (session access_token)`
- `x-ibm-client-id`: `e83f49c439b0ebc0b130692bcb8b1cde`
- `origin`: `consumermobile.royalmail.com`

**Response**

```json
{
   "mpDetails": [
       {
           "lastAccessedTimestamp": 1723803963880,
           "mailPieceId": "AA123456789US"
       },
       {
           "lastAccessedTimestamp": 1686773055097,
           "mailPieceId": "AA123456789US"
       }
   ],
   "jwt": "************"
}
```

## Mailpiece

**Request**

****GET****: `https://api.royalmail.net/mailpieces/v3.1/<MAILPIECE-ID>/events`

***Headers***:
- `Authorization`: `Bearer (session access_token)`
- `x-ibm-client-id`: `e83f49c439b0ebc0b130692bcb8b1cde`
- `origin`: `consumermobile.royalmail.com`

**Response**

```json
{
   "mailPieces": {
       "mailPieceId": "AA123456789US",
       "carrierShortName": "RM",
       "carrierFullName": "Royal Mail Group Ltd",
       "summary": {
           "uniqueItemId": "************",
           "oneDBarcode": "AA123456789US",
           "productId": "TPL01",
           "productName": "Royal Mail Tracked 48",
           "productDescription": "Aims to deliver within 2-3 days with online tracking",
           "productCategory": "NON-INTERNATIONAL",
           "destinationCountryCode": "GB",
           "destinationCountryName": "United Kingdom",
           "originCountryCode": "GB",
           "originCountryName": "United Kingdom",
           "lastEventCode": "EVKOP",
           "lastEventName": "Delivered by",
           "lastEventDateTime": "2023-07-18T12:19:25+01:00",
           "lastEventLocationName": "London DO",
           "statusDescription": "Delivered",
           "statusCategory": "Delivered",
           "statusHelpText": " ",
           "summaryLine": "Your item was delivered on 18-07-2023."
       },
      "signature":{
         "recipientName":"MR BLOBBY",
         "signatureDateTime":"2023-07-18T12:19:25+01:00"
      },
      "proofOfDeliveryData":{
         "recipientName":"MR BLOBBY",
         "deliveryDateTime":"2023-07-18T12:19:25+01:00",
         "signatureURI":"AA123456789US202408138271649706352724111173802",
         "photoURI":"AA123456789US2024081510487362513724111173802"
      },
       "position": {
           "longitude": **.*******,
           "latitude": **.*******,
           "altitude": ***.******
       },
       "events": [
           {
               "eventCode": "EVKOP",
               "eventName": "Delivered by",
               "eventDateTime": "2023-07-18T12:19:25+01:00",
               "locationName": "London DO"
           },
           {
               "eventCode": "EVGPD",
               "eventName": "Due to be delivered today",
               "eventDateTime": "2023-07-18T12:19:25+01:00",
               "locationName": "London DO"
           },
           {
               "eventCode": "EVIMC",
               "eventName": "Item Received",
               "eventDateTime": "2023-07-18T12:19:25+01:00",
               "locationName": "Norfolk MC"
           },
           {
               "eventCode": "EVDAV",
               "eventName": "Item Received",
               "eventDateTime": "2023-07-18T12:19:25+01:00",
               "locationName": "Edinburgh Super Hub"
           },
           {
               "eventCode": "EVAIE",
               "eventName": "Sender despatching item",
               "eventDateTime": "2023-07-18T12:19:25+01:00"
           }
       ],
       "greenCredentials": {
           "totalCO2e": 205,
           "dataAccuracy": "Average"
       },
       "links": {
           "summary": {
               "href": "/mailpieces/v3/summary?mailPieceId=AA123456789US",
               "title": "Summary",
               "description": "Get summary"
           },
           "signature":{
            "href":"/mailpieces/v3/AA123456789US/signature",
            "title":"Signature",
            "description":"Get Signature"
           },
           "signatureimage":{
            "href":"/v1/images/AA123456789US202408987654321596352724111173802/image",
            "title":"Signature Image",
            "description":"Get Signature Image"
           },
           "imagePhoto": {
               "href": "/v1/images/AA123456789US************/image",
               "title": "Image",
               "description": "Get Image"
           },
           "photo": {
               "href": "/mailpieces/v3/AA123456789US/photo",
               "title": "Photo",
               "description": "Get photo"
           },
           "photoimage": {
               "href": "/mailpieces/v3/AA123456789US/photoImage",
               "title": "Photo Image",
               "description": "Get photo image"
           },
           "imageSignature":{
            "href":"/v1/images/AA123456789US20240815189876754343252724111173802/image",
            "title":"Image Signature",
            "description":"Get image signature"
           }
       }
   }
}
```

## Tracking a New Mail Piece

To track a new mail piece and connect it to the account, follow these steps in sequential order. Once completed successfully, the new mail piece should appear in the `mpDetails` array within the Mailpieces response.

**1. Create Subscription**

***Request***

****POST****: `https://api.royalmail.net/pushapi/app/v2/subscription/track/<MAILPIECE-ID>`

***Headers***:
- `Authorization`: `Bearer (using session access_token)`
- `x-ibm-client-id`: `e83f49c439b0ebc0b130692bcb8b1cde`
- `origin`: `consumermobile.royalmail.com`
- `Content-Type`: `application/json; charset=utf-8`

**2. Push Notification**

Only continue with this request if `Create Subscription` returns a `200` response.

***Request***

****PUT****: `https://rmappgateway.dockethub.com/rmpushnotification/api/v3/user/<USER-ID>/trackedmailpieces/<MAILPIECE-ID>`

***Headers***:
- `accessToken`: `(using session access_token)`

***Body***:
```json
{
   "ProductName": "Royal Mail Tracked 24"
}
```

**3. Tracking Alias**

Only continue with this request if `Push Notification` returns a `201` response.

***Request***

****GET****: `https://api.royalmail.net/trackingalias`

***Headers***:
- `Bearer Token`: `(using session access_token)`
- `x-ibm-client-id`: `e83f49c439b0ebc0b130692bcb8b1cde`
- `origin`: `consumermobile.royalmail.com`
- `userId`: `12345678`
- `mailPieceId`: `AA123456789US`

***Response***:
```json
{
   "results": [
       {
           "userId": "12345678",
           "lastUpdateDateTime": 1723899365325,
           "mailPieceId": "AA123456789US"
       }
   ]
}
```

### Removing a Mailpiece

In order to remove a mail piece and have it disconnected from the account, the following 2 endpoints need to be requested in sequential order. Once this process is successful, the old mail piece should no longer be in the `mpDetails` array within the Mailpieces response.

**1. Push Notification**

***Request***

****DELETE****: `https://rmappgateway.dockethub.com/rmpushnotification/api/v3/user/<USER-ID>/trackedmailpieces/<MAILPIECE-ID>`

***Headers***:
- `accessToken`: `(using session access_token)`

***Body***:
```json
{
   "ProductName": "Royal Mail Tracked 24"
}
```

**2. Delete Mailpiece**

Only continue with this request if `Push Notification` returns a `201` response.

***Request***

****DELETE****: `https://api.royalmail.net/mailpieces/v3.1/user/<USER-ID>/history/e83f49c439b0ebc0b130692bcb8b1cde?mailPieceId=<MAILPIECE-ID>`

***Headers***:
- `Bearer Token`: `(using session access_token)`
- `x-ibm-client-id`: `e83f49c439b0ebc0b130692bcb8b1cde`
- `origin`: `consumermobile.royalmail.com`

***Response***:
```json
{
   "mpDetails": [
       {
           "lastAccessedTimestamp": 1723809720543,
           "mailPieceId": "AA123456789US"
       },
       {
           "lastAccessedTimestamp": 1723809109772,
           "mailPieceId": "AA123456789US"
       },
       {
           "lastAccessedTimestamp": 1723805773009,
           "mailPieceId": "AA123456789US"
       },
       {
           "lastAccessedTimestamp": 1686773055097,
           "mailPieceId": "AA123456789US"
       }
   ],
   "jwt": "****************************"
}
```

## Get Image

**Request**

****GET****: `https://api.royalmail.net<IMAGE-URL>`

***Headers***:
- `Authorization`: `Bearer (session access_token)`
- `x-ibm-client-id`: `e83f49c439b0ebc0b130692bcb8b1cde`
- `origin`: `consumermobile.royalmail.com`