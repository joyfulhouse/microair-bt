# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Verified

- Relearn write path exercised live on `EasyStart_88CD` over the HA proxy
  mesh (2026-09-21): STORED `0x01`; next power-up reset learned starts and the
  lifetime start/fault counters to 0 and logged learning start 1. See
  `wiki/ble-protocol.md` and `docs/claude/research/live-relearn-validation-2026-09-21.md`.
- Upstairs relearn progress: 2 of 5 learning starts as of 2026-09-23; the
  relearn flag was still set after the second.

### Documentation

- README: what a relearn does to the counters, and how firmware updates work
  (OEM app only). INSTALL: entity list brought up to 0.5.0.
- Wiki: status as of 2026-09-23, open questions (Powered flag staying on while
  idle, Power Interruption at call end), and transport facts settled by live
  captures (no pairing needed over proxies, exact success envelope, ReadEEP
  length prefix). OEM firmware B38 archived under `sources/firmware/` as
  evidence (not applied).

## [0.5.0] - 2026-09-21

### Added

- **Feature parity with the OEM app's write path.** The EasyStart app can write
  exactly three parameters outside its firmware-update family: the startup
  mask (`SMask`), the short-cycle protection timer (`SCPT`) and the
  fault-enable mask (`FMask`). All three are now controllable from Home
  Assistant, through one shared guarded write path (live-status running
  guard, fresh EEPROM preflight, single write, EEPROM readback verification,
  persistent notification).
- **Startup mode** select entity (configuration): `normal`, `relearn`,
  `default_ramp`, plus `superlearn` (the app's hidden long-press variant of
  relearn) when the unit's firmware is 29 or newer. Selecting `relearn` sends
  the same relearn instruction as the `set_startup_mode` service and posts the
  OEM power-cycle / five-start procedure. **Disabled by default** until the
  write path is verified live: enabling the entity is the operator's explicit
  confirmation (the service keeps its `confirm: true` flag).
- **No power-up delay** switch (startup-mask bit 2) and, disabled by default,
  the hidden **Start delay mode** switch (bit 3, which makes the SCPT byte a
  start delay in the app).
- **Short-cycle protection timer** number entity (1-250 min, whole minutes),
  with an `interpretation` attribute that reports `start_delay` when the hidden
  mode is set.
- Seven **fault protection** switches (unexpected current, power interruption,
  compressor stall, start hardware failed, open overload, overcurrent, wiring
  issue). They are **disabled by default** in the entity registry, standing in
  for the app's confirm dialog: enable them deliberately before use. The
  integration refuses to disable the last enabled protection.
- **Fault mask** diagnostic sensor; the **Startup mask** and **Fault mask**
  sensors now expose their decoded bits as attributes.
- `set_startup_mode` service accepts `superlearn`.

### Changed

- The protocol whitelist grows from three to five command strings
  (`SCPT=HH` and `FMask=HH`); `SCPT=00` and `FMask=00` remain banned at both
  the builder and the single GATT write site. The 19 firmware-update commands
  stay structurally impossible to send.
- Startup-mode arithmetic follows the app's SuperLearn label bit 4: it
  persists through `normal` and `default_ramp`, is set by `superlearn`, and is
  cleared only by choosing plain `relearn` deliberately. Bits 2-3 (the flag
  switches) are preserved across every mode change. `superlearn` is refused
  for firmware below 29 at the client, so no surface can bypass the gate.
- Write notifications carry guidance specific to what was stored (the relearn
  procedure only for `relearn` / `superlearn`; a reminder for `default_ramp`
  and for a disabled protection).
- Client write API: `write_startup_mode`, `write_startup_flag`, `write_scpt`,
  `write_fault_protection`; `WriteRejected` / `WriteState` replace the
  startup-mask-specific names.

## [0.4.0] - 2026-09-16

### Added

- **Live mode** (opt-in, per device): holds one GATT connection open through a
  single Bluetooth proxy and reads `ReadLive` on a fast timer (default 5 s,
  minimum 2 s) for near-real-time compressor current, like the OEM app —
  instead of the default connect-per-poll. Two new options: **Live mode**
  (default off) and **Live-mode read interval**. Toggling either takes effect
  without a restart.
- Live mode reconnects on its own if the link drops (gated on the unit still
  advertising) and refreshes the near-static EEPROM image at most hourly, so a
  dropped frame in the big transfer never blocks live current.

### Changed

- While live mode is active the single BLE central is held open, so the OEM app
  cannot connect and `set_startup_mode` is **rejected up front** with a message
  to turn Live mode (or the Polling switch) off first. The default
  connect-per-poll mode is unchanged and remains recommended for reliability on
  weak proxy links.

## [0.3.0] - 2026-09-16

### Added

- **Estimated compressor power sensor** (`sensor.<name>_power`, W). The EasyStart
  reports compressor current but no line voltage, so power is estimated as
  `current x nominal voltage x power factor`. It covers the **compressor only**
  (not the air handler) and refreshes at the polling cadence; the assumptions
  are exposed as entity attributes (`estimate`, `scope`, `nominal_voltage`,
  `power_factor`). Use a dedicated meter for revenue-grade energy.
- Two options to tune the estimate: **nominal line voltage** (default 240 V,
  accepted 90-300) and **compressor power factor** (default 0.9, accepted
  0-1). Editing them rescales the sensor without a new BLE read. To integrate
  energy (kWh), add a Riemann-sum helper on this sensor and feed the Energy
  dashboard.

## [0.2.2] - 2026-09-12

### Changed

- **Polls read live telemetry only.** The ~1 KB EEPROM image (about 50
  notification frames at the proxy MTU of 23) is now read at the first
  successful poll, after a `set_startup_mode` readback, and at most hourly;
  every other poll sends just `ReadLive`. On a marginal ESPHome-proxy link a
  single dropped frame in the EEPROM transfer used to fail the whole poll and
  leave every entity unavailable (#6).
- The live read runs first, so a failed EEPROM refresh keeps the cached image
  and the poll still succeeds. A failed bootstrap read gets one immediate retry
  on a fresh connection; until an image is read the model, firmware and startup
  mask sensors report unknown while telemetry flows.

### Added

- Debug logging of the reassembled reply size and frame count per command, and
  of the underlying error when config-flow setup cannot read the unit.

## [0.2.1] - 2026-09-12

### Added

- Brand assets (`custom_components/microair_bt/brand/{icon,logo}.png` + hDPI
  `@2x` variants; sources under `brand/`): the OEM *EasyStart* app launcher
  icon and the Micro-Air wordmark from microair.net, so HACS and Home
  Assistant render an icon and brand validation passes without the
  `ignore: brands` workaround.

## [0.2.0] - 2026-09-11

### Added

- **Home Assistant integration** (`custom_components/microair_bt`), one config
  entry per EasyStart:
  - Bluetooth auto-discovery on the `EasyStart_*` local name plus manual add by
    address; setup reads the EEPROM and only accepts the verified control model
    (`398ULBT`).
  - Sensors: status (enum), current, line frequency, last start peak,
    short-cycle delay, learned starts, total starts, total faults; diagnostic
    model, firmware and startup-mask sensors.
  - Binary sensors: **Powered** (advertising) and **Fault**.
  - **Polling** configuration switch that pauses all BLE reads and writes and
    persists across restarts, for OEM-app maintenance.
  - `microair_bt.set_startup_mode` service (`normal` / `relearn` /
    `default_ramp`) with explicit `confirm`, a running-compressor guard
    (`allow_running` option), EEPROM readback verification, a response payload
    and a persistent notification describing the outcome and the OEM
    power-cycle procedure.
  - Options flow: minimum polling interval (≥ 15 s) and `allow_running`.
- Advertisement-gated coordinator: polls only while the unit is heard, never
  retains an idle GATT connection, single connection attempt per poll (never
  evicts the OEM app), exponential backoff to 5 minutes.
- HA-level tests (config flow, coordinator, entities, service outcomes) against
  a fake peripheral.
- HACS metadata (`hacs.json`), `INSTALL.md`, and GitHub Actions for HACS
  validation, hassfest, and lint/type/test gates.

### Changed

- Rewrote `README.md` to the standard JoyfulHouse integration layout (badges,
  features, install, entities, service, automations, troubleshooting) and this
  changelog to Keep a Changelog format.
- Scrubbed environment-specific network details (Home Assistant hostnames,
  proxy names and addresses, token paths) from `CLAUDE.md` and the wiki; the
  wiki now documents the device, protocol and integration design generically.
- `pyproject.toml` version aligned with the integration manifest.

## [0.1.0] - 2026-09-10

### Added

- Standalone EasyStart protocol library (`microair/protocol.py`) with bounded
  parsers for `ReadLive` / `ReadEEP` replies and a three-command whitelist
  (`ReadLive`, `ReadEEP`, `SMask=xx`); the firmware-update command family can
  not be built.
- Transaction-scoped BLE client (`microair/client.py`) with timeout and
  cancellation cleanup, protection against late notifications from previous
  connections, EEPROM preflight before any startup-mask write, and an explicit
  write-state machine (`NOT_ATTEMPTED` → `SENT` → `ACKNOWLEDGED`).
- Read-only probe (`scripts/probe.py`) and protocol/client tests that run
  without Home Assistant or BLE hardware.
- Reverse-engineering wiki: GATT transport, the 24 OEM command strings,
  decoded telemetry fields, device identity and OEM relearn procedure, and the
  integration specification.

[Unreleased]: https://github.com/joyfulhouse/microair-bt/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/joyfulhouse/microair-bt/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/joyfulhouse/microair-bt/compare/v0.2.2...v0.3.0
[0.2.2]: https://github.com/joyfulhouse/microair-bt/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/joyfulhouse/microair-bt/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/joyfulhouse/microair-bt/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/joyfulhouse/microair-bt/releases/tag/v0.1.0
