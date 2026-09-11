# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/joyfulhouse/microair-bt/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/joyfulhouse/microair-bt/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/joyfulhouse/microair-bt/releases/tag/v0.1.0
