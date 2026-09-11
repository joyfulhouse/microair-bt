# microair-bt — wiki index

Reverse-engineering the **MicroAir EasyStart Flex** A/C soft starter's BLE
protocol (Android app `net.microair.easystart`, "EasyStart") to build a
**local Home Assistant Bluetooth integration** — no cloud, controllable via
HA's ESPHome BLE proxies. Primary goal: **reset the learned start profile**
from HA.

> Read [SCHEMA](SCHEMA.md) first if you're going to edit the wiki.

## Effort status (2026-09-11)

| Workstream | State |
|---|---|
| APK acquired + decompiled (jadx + apktool) | ✅ done — see [sources](sources.md) |
| BLE protocol reverse-engineered from source | ✅ done — two independent reads agree ([ble-protocol](ble-protocol.md)) |
| Public documentation / prior art collected | ✅ done — OEM relearn procedure + community ESPHome read path ([device-easystart-flex](device-easystart-flex.md)) |
| Device located on an HA Bluetooth proxy | ⚠️ **not yet heard by a proxy** (270 s passive scan 2026-09-10, A/C likely idle). Heard and read once via a host adapter probe: `EasyStart_88CD`, model `398ULBT`, fw 37 ([ha-proxy-coverage](ha-proxy-coverage.md)). Production path is HA's nearest ESPHome active proxy, never an ad-hoc host adapter. |
| Specification for the integration | ✅ v1.1 — [integration-plan](integration-plan.md); three-vendor /debate REVISE×3 folded in (`docs/claude/research/debate-spec-synthesis.md`); awaiting plan-gate ruling |
| HA custom integration | ✅ **merged + released** — PR #1 protocol lib/BLE client/probe, PR #2 hardening, PR #3 HA integration (sensors, binary sensors, polling switch, `set_startup_mode`); shipped as **v0.2.0** via HACS custom repository |
| Live validation on real device | ⚠️ **read path exercised, write path unverified.** 2026-09-10 host-adapter probes read EEP/LIVE; one `SMask` write attempt returned BlueZ `NotAuthorized` and every readback still showed `startup_mask 0`. Telemetry was also internally inconsistent across the day (`total_starts` 3671 vs 7), so treat both results as unconfirmed until reproduced over the HA proxy path. |

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
