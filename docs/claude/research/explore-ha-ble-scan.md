# Home Assistant BLE scan: MicroAir EasyStart Flex

Status: **PARTIAL — unit not identified**  
Date: 2026-09-10 (America/Los_Angeles)

## Result

The MicroAir EasyStart Flex did not appear in either the initial 90-second passive Home Assistant advertisement subscription or the required 180-second extension. The extension received 246 advertisement events representing 219 distinct device addresses, but no advertisement matched any of these deliberately permissive indicators:

- local name containing `EasyStart` or `MicroAir`;
- local name beginning `ES`;
- advertised service UUID or service-data key `d973f2e0-b19e-11e2-9e96-0800200c9a66`.

Consequently, the unit's address, advertised name, connectable flag, service UUIDs, manufacturer/service data, TX power, hearing proxies/RSSI, and best proxy for a GATT connection are **unknown**. No GATT connection was attempted.

## What the OEM app looks for

The Android app starts an unfiltered BLE scan (`startScan(callback)`) and its callback accepts a non-null device name containing the selected saved name, falling back to any name containing `EasyStart_` ([Connect.java:471](/Users/bryanli/Projects/joyfulhouse/homeassistant-dev/microair-bt/sources/decompiled/jadx/sources/net/microair/easystart/Connect.java:471), [MainActivityKt.java:342](/Users/bryanli/Projects/joyfulhouse/homeassistant-dev/microair-bt/sources/decompiled/jadx/sources/net/microair/easystart/MainActivityKt.java:342)). The UI recognizes either a 14-character exact ID (`EasyStart_` plus five characters) or the 10-character `EasyStart_` prefix/blank value as "scan for any" ([Connect.java:586](/Users/bryanli/Projects/joyfulhouse/homeassistant-dev/microair-bt/sources/decompiled/jadx/sources/net/microair/easystart/Connect.java:586), [Connect.java:631](/Users/bryanli/Projects/joyfulhouse/homeassistant-dev/microair-bt/sources/decompiled/jadx/sources/net/microair/easystart/Connect.java:631)).

The GATT UUIDs are primary service `d973f2e0-b19e-11e2-9e96-0800200c9a66`, notify characteristic `d973f2e1-b19e-11e2-9e96-0800200c9a66`, and write characteristic `d973f2e2-b19e-11e2-9e96-0800200c9a66` ([MainActivityKt.java:329](/Users/bryanli/Projects/joyfulhouse/homeassistant-dev/microair-bt/sources/decompiled/jadx/sources/net/microair/easystart/MainActivityKt.java:329), [MainActivityKt.java:407](/Users/bryanli/Projects/joyfulhouse/homeassistant-dev/microair-bt/sources/decompiled/jadx/sources/net/microair/easystart/MainActivityKt.java:407)). These are discovered only after connection; the app has no manufacturer-ID check and does not require this service to be present in the advertisement.

## Kaelyn's-bedroom proxy and neighbors

HA's `bluetooth/subscribe_scanner_details` response maps source `70:04:1D:1F:3B:8A` to adapter `aiosense-kaelyns-bedroom`, a connectable remote scanner. This agrees with the ESPHome configuration name, static IP `10.100.0.134`, and active proxy setting ([aiosense-kaelyns-bedroom.yaml:1](/Users/bryanli/Projects/joyfulhouse/homeassistant-dev/aiosense/devices/aiosense-kaelyns-bedroom.yaml:1), [aiosense-kaelyns-bedroom.yaml:54](/Users/bryanli/Projects/joyfulhouse/homeassistant-dev/aiosense/devices/aiosense-kaelyns-bedroom.yaml:54), [aiosense-kaelyns-bedroom.yaml:67](/Users/bryanli/Projects/joyfulhouse/homeassistant-dev/aiosense/devices/aiosense-kaelyns-bedroom.yaml:67)).

Every device heard by that source during the 180-second extension is below. Non-candidate addresses are reduced to the first three bytes.

| Address prefix | Name | Advertised service UUID(s) | Best RSSI |
|---|---|---|---:|
| `04:0E:9D:xx:xx:xx` | `PRP1-RD_2FF9` | `0000af30-0000-1000-8000-00805f9b34fb` | -70 dBm |
| `0B:DD:C4:xx:xx:xx` | unnamed/address-only | none | -95 dBm |
| `44:3E:8A:xx:xx:xx` | unnamed/address-only | none | -97 dBm |
| `50:E0:58:xx:xx:xx` | unnamed/address-only | `0000fea0-0000-1000-8000-00805f9b34fb` | -94 dBm |
| `55:5C:90:xx:xx:xx` | unnamed/address-only | `00003456-0000-1000-8000-00805f9b34fb` | -82 dBm |
| `60:85:B7:xx:xx:xx` | unnamed/address-only | `0000fe9f-0000-1000-8000-00805f9b34fb` | -84 dBm |
| `6E:A4:74:xx:xx:xx` | unnamed/address-only | none | -70 dBm |
| `73:8E:C0:xx:xx:xx` | unnamed/address-only | none | -85 dBm |
| `7B:4F:D5:xx:xx:xx` | unnamed/address-only | `0000fe9f-0000-1000-8000-00805f9b34fb` | -72 dBm |
| `C1:9A:5E:xx:xx:xx` | `Govee_H6093_9E58` | none | -47 dBm |
| `E8:06:90:xx:xx:xx` | unnamed/address-only | none | -35 dBm |
| `FC:F5:C4:xx:xx:xx` | `SPU-00009694-V002` | `0000ffff-0000-1000-8000-00805f9b34fb` | -70 dBm |
| `FE:0C:FE:xx:xx:xx` | unnamed/address-only | none | -91 dBm |

## Method and limits

The sibling PEP-723 scanner was copied to `/tmp/ble_scan.py` and adapted there only. It authenticated to `ws://hass.joyful.house:8123/api/websocket`, queried HA's device/config-entry registries, subscribed to scanner details, and passively subscribed to advertisements. Commands were `uv run /tmp/ble_scan.py` with `SCAN_SECONDS=90`, followed by the contract-required `SCAN_SECONDS=180`. The token was sourced from `../eg4_web_monitor/.env` into the process environment and was never placed in a command-line argument, scanner output, report, or repository file.

Absence is bounded to these observation windows. The mains-powered unit may have been unpowered, already connected, outside reception, advertising without a name/service UUID, or advertising under a shorter unexpected name. Because no candidate existed, cross-proxy RSSI comparison and best-proxy selection were impossible.

Raw/sanitized scan evidence: [ble-scan-dump.json](/Users/bryanli/Projects/joyfulhouse/homeassistant-dev/microair-bt/docs/claude/research/ble-scan-dump.json).

## Follow-up

Power the EasyStart while ensuring the OEM app is disconnected, then repeat the passive scan. If still absent, capture advertisements before and during opening the OEM app's scan screen to learn the exact current local name/address without initiating a GATT connection.
