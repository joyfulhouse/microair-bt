# Live relearn validation — EasyStart_88CD over the HA proxy path (2026-09-21)

Process artifact; durable facts are folded into `wiki/index.md`,
`wiki/ble-protocol.md`, `wiki/device-easystart-flex.md`, `wiki/ha-proxy-coverage.md`.

## Setup

- HA 2026.9.3 (`hass.joyful.house`), integration **v0.4.0 loaded** (v0.5.0 was
  downloaded via HACS during the session; core restart deferred — house armed
  away, per the homelab restart rule).
- Unit `EasyStart_88CD` (upstairs), model `398ULBT`, firmware 37, SCPT 3 min,
  startup mask `0x00`, fault mask `0x7F`.
- Cooling call driven from HA: `climate.upstairs` (ecobee via HomeKit) set to
  64–70 °F with `automation.ac_upstairs` temporarily off (it reverts setpoints
  within 20 ms); restored to the `away_indefinitely` 64–80 hold afterwards and
  the automation re-enabled. Windows provably closed; safety interlocks left on.
- Entry options temporarily: live mode **off** (writes are rejected while live
  mode holds the link), allow-running **on** (the unit is powered only while
  the A/C calls, and the compressor started within ~40 s of power-up — no idle
  window). Both restored afterwards.

## Timeline (local time)

| Time | Event |
|---|---|
| 12:02:40 | cooling call set; unit advertising at 12:02:47 |
| 12:03:18 | first poll: Normal, Learned 6, 9.8 A rising to 20.3 A by 12:06, then 8 A; Total Starts 229, Total Faults 66, peak 20.7 A |
| 12:07:58, 12:09:31 | `set_startup_mode relearn` → REJECTED: preflight `ReadEEP` 1003/1023 bytes (dropped frame). Nothing sent. |
| 12:09:47 | → ACKNOWLEDGED-BUT-UNVERIFIED: `SMask=01` acknowledged `Success`, readback `ReadEEP` truncated |
| 12:10:07 | → **STORED**, `startup_mask 0x01` (a second, idempotent `SMask=01`; the operator retry loop should have inspected the mask first) |
| 12:11:20 | cooling call ended (hold restored); A/C idle 12:12; HA marks unit unpowered 12:16:49 |
| 12:17:20 | second cooling call |
| 12:17:29 | **power-up telemetry: Learned 0, Total Starts 0, Total Faults 0, peak 0.0 A, SCPT delay 2 s, mask still `0x01`** |
| 12:17:50 | Learned 1, Total Starts 1, peak 18.5 A, 9.4 A → 8 A; ran > 4 min |
| 12:22 | hold restored, automation on, options restored |

## Conclusions

See `wiki/ble-protocol.md` → "What the app does NOT tell us — resolved live".
Open: whether bit 0 clears after the fifth learning start; SCPT/FMask writes.

## Follow-up (2026-09-23)

- Learning start 2 logged at 2026-09-21 22:55 UTC (Learned 2, Total Starts 2);
  status Power Interruption at 23:00 when that 5-minute call ended. No upstairs
  cooling call since, so learning is paused at 2 / 5.
- Mask still reported `0x01` after start 2 (possibly the cached image; live
  mode refreshes the EEPROM hourly).
- v0.5.0 became active at the 2026-09-22 11:23 UTC core restart.
- `binary_sensor.easystart_88cd_powered` stayed on from 19:17 until that
  restart despite no cooling after 23:00; recorded as an open question in
  `wiki/ha-proxy-coverage.md`.
