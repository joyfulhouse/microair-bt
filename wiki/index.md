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
| BLE protocol reverse-engineered from source | ✅ done — two independent reads agree ([ble-protocol](ble-protocol.md)) |
| Public documentation / prior art collected | ✅ done — OEM relearn procedure + community ESPHome read path ([device-easystart-flex](device-easystart-flex.md)) |
| Device located on an HA Bluetooth proxy | ❌ **not heard** in a 270 s passive scan — likely unpowered / A/C idle ([ha-proxy-coverage](ha-proxy-coverage.md)) |
| Specification for the integration | ✅ drafted — [integration-plan](integration-plan.md) (pending /debate) |
| HA custom integration | ⏳ pending spec approval |
| Live validation on real device | ⏳ blocked on hearing the unit |

## The one-paragraph answer

Relearn is a single byte: write ASCII `{"Cmd": SMask=01}` (bit 0 of the
startup mask at EEPROM buffer index 906) to characteristic `d973f2e2…`, wait
for a notification containing `Success`, re-read with `{"Cmd": ReadEEP}`. Then
the **human must power-cycle the A/C**; the next five successful ≥ 30 s
compressor starts rebuild the profile, visible as `Learned Starts` in the
`ReadLive` telemetry. There is no clear-faults command; never send anything
from the firmware-update family.

## Pages

- [sources](sources.md) — registry of raw evidence.
- [ble-transport](ble-transport.md) — GATT UUIDs, connect sequence, notification routing, timing.
- [ble-protocol](ble-protocol.md) — the 24 command strings, replies, SMask/FMask semantics, banned commands.
- [available-data](available-data.md) — decoded `ReadLive` / `ReadEEP` fields, units, scaling.
- [device-easystart-flex](device-easystart-flex.md) — identity, OEM learning/relearn procedure, fault/LED table.
- [ha-proxy-coverage](ha-proxy-coverage.md) — scan results per proxy (unit not yet heard).
- [integration-plan](integration-plan.md) — **the specification** for `custom_components/microair_bt`.
