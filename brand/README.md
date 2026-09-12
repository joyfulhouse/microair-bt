# Brand sources

- `icon-source.png` — the OEM *EasyStart* Android app launcher icon
  (`net.microair.easystart`, adaptive-icon foreground composited over its
  `#404040` background, cropped to the 72/108 safe zone).
- `logo-wordmark-white-source.png` — the Micro-Air wordmark as served by
  <https://www.microair.net/> (`cdn/shop/files/logo_micro-air_white.png`).

The shipped HACS/HA brand files in `custom_components/microair_bt/brand/`
(`icon.png` 256², `icon@2x.png` 512², `logo.png` 256 px tall, `logo@2x.png`
512 px tall) are derived from these. The wordmark is white, so the logo is
rendered on the same `#404040` tile as the icon to stay legible on both light
and dark Home Assistant themes.

Micro-Air and EasyStart are trademarks of Micro-Air, LLC; assets are used
solely to identify the device this unofficial integration talks to.
