# ![Logo](https://github.com/jampez77/RoyalMail/blob/main/logo.png "Royal Mail Logo") Royal Mail parcel tracking for Home Assistant

This integration synchronises your Royal Mail tracking data and adds sensors to [Home Assistant](https://www.home-assistant.io/) which can be used in your own automations.

---

[![GitHub Release][releases-shield]][releases]
[![License][license-shield]](LICENSE.md)
[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg?style=for-the-badge)](https://github.com/custom-components/hacs)
![Project Maintenance][maintenance-shield]


Enjoying this? Help me out with a :beers: or :coffee:!

[![coffee](https://www.buymeacoffee.com/assets/img/custom_images/black_img.png)](https://www.buymeacoffee.com/whenitworks)


## Installation through [HACS](https://hacs.xyz/)

There is an active [PR](https://github.com/hacs/default/pull/2711) to get this into [HACS](https://hacs.xyz/), once that is merged then you can install the **Royal Mail** integration by searching for it there in HA instance.

Until then you will have to add this repository manually:

Go to HACS -> 3 dot menu -> Custom Repositories:- 

Paste `https://github.com/jampez77/RoyalMail` into Repository field and select `Integration`

Now you should be able to find it in HACS as normal.

You can install the **Royal Mail** integration by searching for it there in HA instance.

## Manual Installation
Use this route only if you do not want to use [HACS](https://hacs.xyz/) and love the pain of manually installing regular updates.
* Add the `royalmail` folder in your `custom_components` folder

---
## Data 
The integration creates a new entity for each parcel on you Royal Mail account with it's current delivery status, all other associated data are saved as attributes. Additionally there are entities for total mail pieces and total number of mail pieces that are due to be delivered today.

The integration will automatically remove a mail piece from your Royal Mail account and Home Assistant 24 hours after the delivery event.

## Contributing

Contirbutions are welcome from everyone! By contributing to this project, you help improve it and make it more useful for the community. Here's how you can get involved:

### How to Contribute

1. **Report Bugs**: If you encounter a bug, please open an issue with details about the problem and how to reproduce it.
2. **Suggest Features**: Have an idea for a new feature? I'd love to hear about it! Please open an issue to discuss it.
3. **Submit Pull Requests**: If you'd like to contribute code:
   - Fork the repository and create your branch from `main`.
   - Make your changes in the new branch.
   - Open a pull request with a clear description of what you’ve done.

### Royal Mail Tracking API
To acheive all that this integration does I reverse engineered the Royal Mail tracking API, here is everything i've found so far, i will keep it as up to date as i can.

[Royal Mail Tracking API Document](https://github.com/jampez77/RoyalMail/blob/main/api.md)

---

[commits-shield]: https://img.shields.io/github/commit-activity/y/jampez77/RoyalMail.svg?style=for-the-badge
[commits]: https://github.com/jampez77/RoyalMail/commits/main
[license-shield]: https://img.shields.io/github/license/jampez77/RoyalMail.svg?style=for-the-badge
[maintenance-shield]: https://img.shields.io/badge/Maintainer-Jamie%20Nandhra--Pezone-blue
[releases-shield]: https://img.shields.io/github/v/release/jampez77/RoyalMail.svg?style=for-the-badge
[releases]: https://github.com/jampez77/RoyalMail/releases 
