# microair-bt — wiki index

Reverse-engineering the **MicroAir EasyStart Flex** A/C soft starter's BLE
protocol (Android app `net.microair.easystart`, "EasyStart") to build a
**local Home Assistant Bluetooth integration** — no cloud, controllable via
HA's ESPHome BLE proxies. Primary goal: **reset the learned start profile**
from HA.

> Read [SCHEMA](SCHEMA.md) first if you're going to edit the wiki.

## Effort status (2026-09-21)

| Workstream | State |
|---|---|
| APK acquired + decompiled (jadx + apktool) | ✅ done — see [sources](sources.md) |
| BLE protocol reverse-engineered from source | ✅ done — two independent reads agree ([ble-protocol](ble-protocol.md)) |
| Public documentation / prior art collected | ✅ done — OEM relearn procedure + community ESPHome read path ([device-easystart-flex](device-easystart-flex.md)) |
| Device located on an HA Bluetooth proxy | ✅ **both units heard and connectable over ESPHome active proxies** (2026-09-11/12) while their A/C is calling. Links are marginal: −75 to −94 dBm depending on which proxy wins ([ha-proxy-coverage](ha-proxy-coverage.md)). Production path is HA's proxy mesh, never an ad-hoc host adapter. |
| Specification for the integration | ✅ v1.1 — [integration-plan](integration-plan.md); three-vendor /debate REVISE×3 folded in (`docs/claude/research/debate-spec-synthesis.md`); awaiting plan-gate ruling |
| HA custom integration | ✅ **merged + released** — PR #1 protocol lib/BLE client/probe, PR #2 hardening, PR #3 HA integration (sensors, binary sensors, polling switch, `set_startup_mode`), PR #7 brand assets, PR #8 live-only polling with cached EEPROM, PR #10 power estimate (v0.3.0), PR #11 live mode (v0.4.0); **v0.5.0 (2026-09-21) adds app write-path parity**: startup-mode select (incl. hidden SuperLearn), no-power-up-delay / start-delay switches, SCPT number, seven disabled-by-default fault-protection switches, all through one guarded readback-verified path (`writes.py`). Shipped via HACS custom repository, two config entries loaded in production |
| Live validation on real device | ✅ **read path verified over the HA proxy path** (2026-09-12, v0.2.2): `EasyStart_88CD` polls `ReadLive` every 30 s and read a complete EEPROM image (`398ULBT` fw 37, mask `0x00`), telemetry consistent (8.5 A, 59.78 Hz, 60 total starts, 6 learned). ⚠️ **Write path still unverified** (now also covers `SCPT` / `FMask`) — see [GitHub #5](https://github.com/joyfulhouse/microair-bt/issues/5). The 2026-09-10 host-adapter `total_starts` 3671-vs-7 inconsistency is explained: there are **two units** (`88CD` upstairs, `DC5A` downstairs) and the probes hit different ones. |

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
