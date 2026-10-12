# ![Logo](https://github.com/jampez77/RoyalMail/blob/main/logo.png "Royal Mail Logo") Royal Mail parcel tracking for Home Assistant

This integration signs in to your [royalmail.com](https://www.royalmail.com) account and adds a sensor to [Home Assistant](https://www.home-assistant.io/) for every item in the account's tracked items. That includes items you track in the Royal Mail app, so parcels show up on their own, with no tracking numbers to type in.

---

[![GitHub Release][releases-shield]][releases]
[![License][license-shield]](LICENSE)
[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg?style=for-the-badge)](https://github.com/custom-components/hacs)
![Project Maintenance][maintenance-shield]


Enjoying this? Help me out with a :beers: or :coffee:!

[![coffee](https://www.buymeacoffee.com/assets/img/custom_images/black_img.png)](https://www.buymeacoffee.com/whenitworks)

## Requirements

- Home Assistant 2026.10.0 or newer.
- A Royal Mail account that signs in at royalmail.com with an email address and password. It's the same account the Royal Mail app uses.

## Installation

### Through [HACS](https://hacs.xyz/)

Search for **Royal Mail** in HACS and download it. If it isn't listed, add the repository yourself:

1. In HACS, open the ⋮ menu and choose **Custom repositories**.
2. Paste `https://github.com/jampez77/RoyalMail` into **Repository**, pick **Integration** as the type and select **Add**.
3. Search for **Royal Mail**, download it and restart Home Assistant.

### Manually

Copy `custom_components/royalmail` into the `custom_components` folder of your Home Assistant configuration and restart Home Assistant. You'll have to repeat this for every update.

## Configuration

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=royalmail)

1. Go to **Settings** > **Devices & services**, select **Add integration** and pick **Royal Mail**.
2. Enter your royalmail.com email address and password.

| Field | Description |
| --- | --- |
| Email | The email address you sign in to royalmail.com with. |
| Password | Your royalmail.com password. |

Home Assistant signs in once to check the details before it saves them. You can add one Royal Mail account.

If Royal Mail later stops accepting the password, for example because you changed it, Home Assistant asks you to re-authenticate. Enter the new password there; nothing else needs setting up again.

## How it works

The integration does what the track page on royalmail.com does when you're signed in:

- **Every 15 minutes** it reads the account's tracked items, the list royalmail.com shows as *Recently tracked items*, together with the latest tracking event for each one. That takes two small requests.
- **About every two hours** it asks the website for a fresh access token, using the session it already has.
- **Only when that session expires** does it sign in with your password again. Royal Mail refuses sign-ins for a while after a few in quick succession. When that happens the integration waits 30 minutes before trying again, doubling the wait each time up to four hours.

The website session is saved with the integration's settings, so restarting Home Assistant doesn't mean signing in again. The integration reads the web API's settings, such as its client ID and address, from royalmail.com itself, so a change on Royal Mail's side doesn't need an update here.

It never removes anything from your Royal Mail account on its own. An item keeps its sensor until it leaves the account's tracked items, either because Royal Mail drops it or because you remove it on royalmail.com, in the app or with the **Stop tracking an item** action.

## Entities

Everything belongs to a **Royal Mail** device of type *service*.

### Tracked parcels

`sensor.royal_mail_tracked_parcels` counts the items in the account's tracked items. If you upgraded from 2024.x it keeps its old ID, `sensor.royalmail_tracked_parcels`.

| Attribute | Description |
| --- | --- |
| `parcels` | The tracking numbers of every item. |
| `out_for_delivery` | Tracking numbers of the items due today. |
| `ready_for_collection` | Tracking numbers of the items waiting at a collection point. |

### One sensor per item

Each item gets a sensor named after the alias you gave it on royalmail.com or in the app, or after its tracking number if it has no alias. For example, an item called "Kettle" becomes `sensor.royal_mail_kettle`. Renaming the alias renames the sensor's friendly name; the entity ID stays the same.

The state is one of:

| State | Meaning |
| --- | --- |
| `in_transit` | Royal Mail has the item. This includes failed delivery attempts. |
| `out_for_delivery` | Due to be delivered today. |
| `ready_for_collection` | Waiting at a Post Office, Customer Service Point or other collection point. |
| `delivered` | Delivered. |
| `collected` | Collected from a collection point. |
| `unknown` | Royal Mail has no tracking events for it yet, for example when a label has been printed but the item hasn't been handed over. |

| Attribute | Description |
| --- | --- |
| `tracking_number` | The Royal Mail reference, for example `AB123456789GB`. |
| `alias` | The name you gave the item, if any. |
| `product` | The service, for example *Royal Mail Tracked 48*. |
| `last_event` | Royal Mail's description of the latest event, for example *Delivered by*. |
| `last_event_time` | When the latest event happened. |
| `last_event_location` | Where it happened, for example a delivery office. |
| `status_description` | Royal Mail's short status. |
| `summary_line` | Royal Mail's one-line summary. |
| `carrier` | The carrier, usually Royal Mail Group Ltd. |

## Actions

### Track your item (`royalmail.track_your_item`)

Looks an item up while signed in, which adds it to the account's tracked items, the same as tracking it on royalmail.com. Its sensor appears straight away.

| Field | Required | Description |
| --- | --- | --- |
| `reference_number` | Yes | The tracking reference. Spaces and lower case are fine. |

```yaml
action: royalmail.track_your_item
data:
  reference_number: AB123456789GB
```

### Stop tracking an item (`royalmail.stop_tracking_item`)

Removes an item from the account's tracked items, on royalmail.com and in the app as well, and removes its sensor.

| Field | Required | Description |
| --- | --- | --- |
| `reference_number` | Yes | The tracking reference of an item the account is tracking. |

```yaml
action: royalmail.stop_tracking_item
data:
  reference_number: AB123456789GB
```

Both actions raise an error if Royal Mail refuses the request. See [Known limitations](#known-limitations).

## Examples

### Notify when a parcel is out for delivery

```yaml
automation:
  - alias: "Royal Mail: out for delivery"
    triggers:
      - trigger: state
        entity_id: sensor.royal_mail_tracked_parcels
        attribute: out_for_delivery
    conditions:
      # Only when an item joined the list, not when one left it.
      - "{{ trigger.to_state.attributes.out_for_delivery
            | reject('in', trigger.from_state.attributes.out_for_delivery or [])
            | list | count > 0 }}"
    actions:
      - action: notify.notify
        data:
          message: >
            Out for delivery today:
            {{ integration_entities('royalmail')
               | select('is_state', 'out_for_delivery')
               | map('state_attr', 'friendly_name') | join(', ') }}
```

### Clear out delivered items every night

The integration no longer removes delivered items for you. This automation does it at 3am instead.

```yaml
automation:
  - alias: "Royal Mail: clear delivered items"
    triggers:
      - trigger: time
        at: "03:00:00"
    actions:
      - repeat:
          for_each: >
            {{ integration_entities('royalmail')
               | select('is_state', ['delivered', 'collected'])
               | map('state_attr', 'tracking_number') | list }}
          sequence:
            - action: royalmail.stop_tracking_item
              data:
                reference_number: "{{ repeat.item }}"
```

### List items on a dashboard

```yaml
type: markdown
title: Parcels
content: >
  {% for entity in integration_entities('royalmail')
     if state_attr(entity, 'tracking_number') %}
  - **{{ state_attr(entity, 'friendly_name') }}**:
    {{ states(entity) | replace('_', ' ') }}
  {% endfor %}
```

## Known limitations

- **This isn't an official API.** It talks to the same endpoints as royalmail.com and can break when Royal Mail changes the website.
- **Sign-ins are rate limited.** Royal Mail refuses sign-ins for a while after a few in quick succession. The integration keeps its session to avoid signing in, and backs off when refused, but setting the integration up, re-authenticating and restarting repeatedly can still trip it.
- **Actions may need a captcha.** royalmail.com sometimes asks for a captcha before it tracks or removes an item. Home Assistant can't solve one, so the action fails and says so. Track or remove the item on royalmail.com or in the app instead; the sensor follows within 15 minutes.
- **Only the account's tracked items appear.** Items addressed to you that nobody tracked with your account don't show up.
- **One account.** You can only add one Royal Mail account.
- **Fixed polling interval.** Updates happen every 15 minutes. To update sooner, call `homeassistant.update_entity` on any Royal Mail sensor.
- **It doesn't use Home Assistant's shared web session.** royalmail.com sits behind a bot filter that only lets browsers through, so the integration uses [curl_cffi](https://github.com/lexiforest/curl_cffi) to connect the way Chrome does.

## Troubleshooting

**"Royal Mail is temporarily refusing sign-ins"**

Royal Mail blocks sign-ins after several attempts. Wait at least 30 minutes before trying again, and don't keep retrying in the meantime, because each attempt can extend the block. A running integration retries by itself.

**"Invalid authentication"**

Check you can sign in at [royalmail.com](https://www.royalmail.com/login) with the same email address and password. If you can, wait half an hour and try again, in case Royal Mail was refusing sign-ins.

**An item is missing**

Sign in to royalmail.com and open [Track your item](https://www.royalmail.com/track-your-item). Only items listed under *Recently tracked items* appear in Home Assistant. Track it there, or use the **Track your item** action.

**A sensor is `unknown`**

Royal Mail has no tracking summary for the item yet. The sensor updates once the item is scanned.

**Sensors are `unavailable`**

The last update failed. The integration keeps trying every 15 minutes. Check the logs for the reason.

**Collecting information for an issue**

Turn on debug logging, reproduce the problem and attach the log and the integration's diagnostics to an [issue](https://github.com/jampez77/RoyalMail/issues). Diagnostics hide your email address, password, session and tracking numbers; check the log for personal details before posting it.

```yaml
logger:
  logs:
    custom_components.royalmail: debug
```

To download diagnostics, go to **Settings** > **Devices & services** > **Royal Mail**, open the ⋮ menu and select **Download diagnostics**.

## Removing the integration

1. Go to **Settings** > **Devices & services** and select **Royal Mail**.
2. Open the ⋮ menu next to the account and select **Delete**.
3. If you installed it with HACS, remove it in HACS too and restart Home Assistant.

Removing the integration doesn't change anything in your Royal Mail account.

## Upgrading from 2024.x

Version 2026.10.0 replaced the Royal Mail app API, which had stopped accepting sign-ins, with the royalmail.com web API. Your account details carry over and existing sensors keep their entity IDs, but some things changed:

- **Home Assistant 2026.10.0 or newer is required.**
- **Parcel states are fixed values** such as `in_transit` or `delivered`, not Royal Mail's event text. The text is in the `last_event` attribute. Update automations that compare the state with text like `Delivered by`.
- **Parcel attributes changed.** The long list of raw API fields, such as `summary_productName` and `events`, is replaced by the attributes listed under [Entities](#entities).
- **`available_for_collection` is now `ready_for_collection`** on the tracked parcels sensor.
- **New items get new-style entity IDs** based on the alias, such as `sensor.royal_mail_kettle`, instead of `sensor.royalmail_parcel_ab123456789gb`. Existing entities keep theirs.
- **The device is called Royal Mail**, unless you renamed it, and sensor names start with it, for example *Royal Mail Kettle*.
- **Delivered items aren't removed automatically any more.** Before, the integration deleted items from your account 24 hours after delivery. See [Clear out delivered items every night](#clear-out-delivered-items-every-night) to keep that behaviour.
- **Actions raise errors** when they fail, instead of returning an error message.

## Integration quality

The integration follows Home Assistant's [integration quality scale](https://developers.home-assistant.io/docs/core/integration-quality-scale/). The rules that don't apply, and why:

| Rule | Why it doesn't apply |
| --- | --- |
| Discovery, discovery update info | Royal Mail is a cloud service; there's nothing on the network to discover. |
| Reconfiguration flow | The email address identifies the account, and re-authentication covers a new password. |
| Entity category, entities disabled by default | Every entity is a primary entity. |
| Repair issues | Nothing can go wrong that the user can fix from a repair. Sign-in problems use re-authentication. |
| Inject web session | Home Assistant's shared HTTP session can't connect the way Chrome does, which royalmail.com requires. |
| Brands | Needs a separate pull request to [home-assistant/brands](https://github.com/home-assistant/brands). |

The Royal Mail client lives in this repository, in `custom_components/royalmail/api.py`, not in a library on PyPI. It has no Home Assistant imports, so it can be published separately later.

## Contributing

Contributions are welcome from everyone! By contributing to this project, you help improve it and make it more useful for the community. Here's how you can get involved:

### How to contribute

1. **Report bugs**: If you encounter a bug, please open an issue with details about the problem and how to reproduce it.
2. **Suggest features**: Have an idea for a new feature? I'd love to hear about it! Please open an issue to discuss it.
3. **Submit pull requests**: If you'd like to contribute code:
   - Fork the repository and create your branch from `main`.
   - Make your changes in the new branch.
   - Open a pull request with a clear description of what you've done.

### Development

The tests need Python 3.14.2 or newer, like Home Assistant itself.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.test.txt ruff mypy
pytest --cov --cov-report=term-missing
ruff check . && ruff format --check .
mypy
```

The tests never contact Royal Mail.

### Royal Mail web API

[Royal Mail web API notes](api.md) documents the requests the integration makes.

---

[commits-shield]: https://img.shields.io/github/commit-activity/y/jampez77/RoyalMail.svg?style=for-the-badge
[commits]: https://github.com/jampez77/RoyalMail/commits/main
[license-shield]: https://img.shields.io/github/license/jampez77/RoyalMail.svg?style=for-the-badge
[maintenance-shield]: https://img.shields.io/badge/Maintainer-Jamie%20Nandhra--Pezone-blue
[releases-shield]: https://img.shields.io/github/v/release/jampez77/RoyalMail.svg?style=for-the-badge
[releases]: https://github.com/jampez77/RoyalMail/releases
