# microair-bt — wiki index

Reverse-engineering the **MicroAir EasyStart Flex** A/C soft starter's BLE
protocol (Android app `net.microair.easystart`, "EasyStart") to build a
**local Home Assistant Bluetooth integration** — no cloud, controllable via
HA's ESPHome BLE proxies. Primary goal: **reset the learned start profile**
from HA.

> Read [SCHEMA](SCHEMA.md) first if you're going to edit the wiki.

## Effort status (2026-09-10)

| Workstream | State |
|---|---|
| APK acquired + decompiled (jadx + apktool) | ✅ done — see [sources](sources.md) |
| BLE protocol reverse-engineered from source | 🔄 in progress (parallel independent analyses) |
| Device located on an HA Bluetooth proxy | 🔄 in progress (scan near `aiosense-kaelyns-bedroom`) |
| Public documentation / prior art collected | 🔄 in progress |
| Specification for the integration | ⏳ pending research |
| HA custom integration | ⏳ pending spec |
| Live validation on real device | ⏳ pending |

## Pages

- [sources](sources.md) — registry of raw evidence.
- `ble-transport.md` — GATT services/characteristics, connect/auth sequence (to be written).
- `ble-protocol.md` — frame format, commands, reset/learn semantics (to be written).
- `available-data.md` — what the device exposes over BLE (to be written).
- `ha-proxy-coverage.md` — which proxy hears the unit and at what RSSI (to be written).
- `integration-plan.md` — entity/service design and open items (to be written).
