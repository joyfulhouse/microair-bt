# microair-bt — wiki index

Reverse-engineering the **MicroAir EasyStart Flex** A/C soft starter's BLE
protocol (Android app `net.microair.easystart`, "EasyStart") to build a
**local Home Assistant Bluetooth integration** — no cloud, controllable via
HA's ESPHome BLE proxies. Primary goal: **reset the learned start profile**
from HA.

> Read [SCHEMA](SCHEMA.md) first if you're going to edit the wiki.

## Effort status (2026-09-23)

| Workstream | State |
|---|---|
| APK acquired + decompiled (jadx + apktool) | ✅ done — see [sources](sources.md) |
| BLE protocol reverse-engineered from source | ✅ done — two independent reads agree ([ble-protocol](ble-protocol.md)) |
| Public documentation / prior art collected | ✅ done — OEM relearn procedure + community ESPHome read path ([device-easystart-flex](device-easystart-flex.md)) |
| Device located on an HA Bluetooth proxy | ✅ **both units heard and connectable over ESPHome active proxies** (2026-09-11/12) while their A/C is calling. Links are marginal: −75 to −94 dBm depending on which proxy wins ([ha-proxy-coverage](ha-proxy-coverage.md)). Production path is HA's proxy mesh, never an ad-hoc host adapter. |
| Specification for the integration | ✅ **implemented** — [integration-plan](integration-plan.md) is the original v1.1 spec (three-vendor /debate, `docs/claude/research/debate-spec-synthesis.md`), kept for rationale; README and code are the current behaviour |
| HA custom integration | ✅ **v0.5.0 released 2026-09-21 and running in production** (activated by the 2026-09-22 11:23 UTC core restart; two config entries). History: PR #1–#3 protocol lib, hardening, HA integration; #7 brand; #8 live-only polling; #10 power estimate (0.3.0); #11 live mode (0.4.0); #12 **OEM-app write-path parity (0.5.0)** — startup-mode select incl. SuperLearn, no-power-up-delay / start-delay switches, SCPT number, seven fault-protection switches, one guarded readback-verified write path (`writes.py`) |
| Live validation on real device | ✅ **Reads** verified over the proxy path since 2026-09-12. ✅ **Relearn write** verified 2026-09-21 on `EasyStart_88CD`: `SMask=01` stored; next power-up reset learned starts **and** lifetime counters to 0 ([ble-protocol](ble-protocol.md)). **Progress 2 / 5 learning starts** as of 2026-09-23 (starts at 09-21 19:17 and 22:55 UTC); the upstairs A/C has not called for cooling since, so the relearn is waiting on weather. ⚠️ **SCPT / FMask writes unverified** on hardware. [#5](https://github.com/joyfulhouse/microair-bt/issues/5) closed. |
| OEM firmware | Both units run **37**; Micro-Air serves **B38** (files dated 2026-09-18), archived under `sources/firmware/398ULBT-B38/`. **Not applied**: no changelog published, and an update rewrites the whole EEPROM (forces a new learn). OEM app only — see [device-easystart-flex](device-easystart-flex.md) → Firmware. |

## The one-paragraph answer

Relearn is a single byte: write ASCII `{"Cmd": SMask=01}` (bit 0 of the
startup mask at EEPROM buffer index 906) to characteristic `d973f2e2…`, wait
for a notification containing `Success`, re-read with `{"Cmd": ReadEEP}`. Then
the **human must power-cycle the A/C** (end the cooling call; the unit is
powered only while the A/C calls); at the next power-up the firmware zeroes
the learned profile **and the lifetime start/fault counters**, and the next
five successful ≥ 30 s compressor starts rebuild the profile, visible as
`Learned Starts` in the `ReadLive` telemetry. **Verified live 2026-09-21.**
Bit 0 stayed set through the first learning start (⚠️ still `0x01` after the
second, possibly from the cached image; whether it clears after the fifth is open). The device accepts
the write while the compressor is running (the OEM app does the same; the
unit is never powered otherwise). There is no clear-faults command; never send
anything from the firmware-update family.

## Pages

- [sources](sources.md) — registry of raw evidence.
- [ble-transport](ble-transport.md) — GATT UUIDs, connect sequence, notification routing, timing.
- [ble-protocol](ble-protocol.md) — the 24 command strings, replies, SMask/FMask semantics, banned commands.
- [available-data](available-data.md) — decoded `ReadLive` / `ReadEEP` fields, units, scaling.
- [device-easystart-flex](device-easystart-flex.md) — identity, OEM learning/relearn procedure, fault/LED table.
- [ha-proxy-coverage](ha-proxy-coverage.md) — which proxies hear each unit, link quality, and the live write attempts.
- [integration-plan](integration-plan.md) — the original specification for `custom_components/microair_bt` (implemented; kept for rationale).

## Open questions (2026-09-23)

- Does SMask bit 0 clear after the fifth learning start? Watch `sensor.easystart_88cd_startup_mask` as upstairs learning completes.
- SCPT and FMask writes have never been sent to hardware.
- ⚠️ **Powered stays on for hours after a cooling call ends** on both units, in live and connect-per-poll mode (2026-09-21..23); the telemetry entities go unavailable meanwhile. Either some installs keep the unit powered/advertising while idle, or HA's presence tracking is stale. See [ha-proxy-coverage](ha-proxy-coverage.md).
- ⚠️ Both units report **Power Interruption** at the end of some cooling calls, then self-clear; the Fault binary sensor turns on for it. Cause unconfirmed ([device-easystart-flex](device-easystart-flex.md)).
- Meaning of the 2-byte prefix on `ReadLive` replies; write type (with/without response) and MTU on the live link.
- What B38 changes (ask Micro-Air).
