# Device — MicroAir EasyStart Flex (398ULBT)

Purpose: what the physical unit is, how it identifies itself over BLE, and how
Micro-Air says learning / relearning works.
Status: **partial** — identity facts from the app + OEM manuals; the specific
unit's address/name is ⚠️ unverified (not yet heard on a proxy, see
[ha-proxy-coverage](ha-proxy-coverage.md)).

Sources: `docs/claude/research/search-easystart-prior-art.md` (OEM manuals O1–O16,
community C1–C13) and the APK reads cited on [ble-protocol](ble-protocol.md).

## Identity

| Item | Value | Evidence |
|---|---|---|
| Product | EasyStart Flex home A/C soft starter | O1 |
| Model string in EEPROM | `398ULBT` (siblings: `364ULBT`, `368ULBT`, `399BT` Breeze) | `J/Update.java:362-380` |
| BLE local name | `EasyStart_` + 4 chars, case-sensitive (manual example `EasyStart_CFFA`; observed `EasyStart_25AC`) | O2, C2, C7 |
| GATT | ST "BLE Chat/UART" sample profile — service `d973f2e0…`, notify `…f2e1`, write `…f2e2` | [ble-transport](ble-transport.md), C13 |
| Address type / stability | ⚠️ unverified — one report of a PUBLIC address, another of the MAC changing after hours | C2, C3 |
| Pairing | none in app; ⚠️ unverified on device | [ble-transport](ble-transport.md) |
| Concurrency | **only one BLE client at a time** (the OEM app must be closed for HA to connect) | O2 |
| Power / advertising | powered from the A/C control circuit; community reports it **advertises only while the HVAC is calling** (i.e. while the unit has power) | O2, C2, C3 |
| Range | short — community recommends a proxy within ~3–6 ft | C3 |
| Firmware version | EEPROM idx 10 (u8); ≥ 29 unlocks hidden SuperLearn/Start-Delay modes in the app | `J/Relearn.java:353` |

## Learning and relearning (OEM semantics)

- The first **five successful starts** populate the learned profile (each must run
  the *compressor* ≥ 30 s; a fault in the first 15 s discards the attempt and does
  not increment **Learned Starts**). The Flex quick-insert additionally says to
  allow **≥ 8 cycles** before running on limited power. O2, O9, O10.
- "Relearning is simply restoring EasyStart back to its factory settings, ready
  to learn again." O3. Learned data is retained through ordinary power cycles;
  a power cycle clears a fault *lockout* but does not erase learning. O2, O4–O6.
- Official Bluetooth relearn procedure (O2 p.9), with the electrical steps
  made explicit:
  1. Unit powered, connect in the app.
  2. Re-learn screen → ReLearn on → **Send Settings to EasyStart** → success; close the app.
  3. **Power the system down.** The saved setting makes the *next* power-up learning start 1.
  4. Prefer utility power that can start the compressor without EasyStart.
  5. Restore power; let the compressor run ≥ 30 s; power down.
  6. Repeat for five successful learning starts (natural thermostat cycling may complete them after the first).
- Official reasons to relearn: run capacitor replaced; unit moved to a different
  compressor; power applied while miswired and faults persist after correction;
  initial learning done on a poor power source. O2, O3.
- **Use Default Ramp** (SMask bit 1) bypasses learned data and is the OEM's
  diagnostic for "is bad learn data the problem?" — to be used under Micro-Air
  direction. O2.
- Does bad learn data stop the compressor? OEM lists *bad learn data* as a cause
  of **Stall** (start attempted but failed). A compressor that makes *no* start
  attempt is more often power/wiring/thermostat. Relearn is "confirmed as
  possible, not proven as the cause" — treat the project hypothesis accordingly.

## Fault / LED table (current OEM, Bluetooth models)

| State | LED flashes | Reset | Notes |
|---|---:|---|---|
| Normal | steady green | — | |
| Unexpected Current | 1 red | **Lockout** (remove power) | large current at start; verify wiring, then relearn if appropriate |
| Over-Current | 2 red | self-reset ~3 min | |
| Short-Cycle Prevention Timer | 3 green (FRM B27+) | after timer | normal |
| Power Interruption | 3 red | self-reset | |
| Open Overload / Klixon | 4 red | self-reset | airflow / compressor / overload switch |
| Stall | 5 red | self-reset | failed start; **bad learn data** is a listed cause |
| Wrong Line Voltage | 6 red | Lockout | 120 V models only |
| Miswiring / Start Winding Not Detected | 7 red | Lockout | |

Non-Bluetooth 364/368 boards have a JP1 jumper relearn (pins 4–6); **the Flex
has no documented non-BLE reset** and Micro-Air warns not to open Bluetooth
models.

## What this means for the integration

See [integration-plan](integration-plan.md). In short: the integration can
*request* a relearn (`SMask` bit 0) and *observe* progress (`Learned Starts`,
SMask bit 0), but the human must perform the power cycle and the compressor
must complete the learning starts on its own.
