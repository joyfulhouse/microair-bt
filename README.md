# MicroAir BT

A Home Assistant custom integration for the **Micro-Air EasyStart** family of
A/C compressor soft starters (the units driven by the *EasyStart* Android/iOS
app, `net.microair.easystart`), providing **local Bluetooth** monitoring and
explicit startup-mode control with **no cloud dependency**.

[![GitHub Release][releases-shield]][releases]
[![License][license-shield]](LICENSE)
[![HACS][hacs-shield]][hacs]
[![CI][ci-shield]][ci]
[![Project Maintenance][maintenance-shield]][maintenance]
[![GitHub Sponsors][sponsors-shield]][sponsors]
[![Ko-fi][kofi-shield]][kofi]
[![Built with Omnigent][omnigent-shield]][omnigent]

## What It Does

This integration connects Home Assistant directly to an EasyStart over
**Bluetooth Low Energy** — through a local adapter or an ESPHome BLE proxy —
with no cloud, account, or internet dependency. The wire protocol was
reverse-engineered from the OEM Android app and is documented in
[`wiki/`](wiki/index.md); the protocol layer is framework-free and fully
unit-tested.

The EasyStart "learns" the compressor's start profile over its first starts.
When that learned profile goes stale, the soft starter can keep the compressor
from starting at all. The primary purpose of this project is to **request a
relearn from Home Assistant** and to read the unit's fault and telemetry data
locally, without the vendor app.

> Not affiliated with Micro-Air or the *EasyStart* app.

> **Status:** the protocol is decoded from the OEM app and the HA integration is
> complete and tested against a fake peripheral. Live reads and the **relearn
> write are verified on a real `398ULBT`** over an ESPHome proxy (2026-09-21:
> `SMask=01` stored, and at the next power-up the unit reset its learned
> profile and lifetime counters and logged learning start 1). The SCPT and
> fault-protection writes added in 0.5.0 are **not yet verified on hardware**;
> treat those controls as experimental until [`wiki/index.md`](wiki/index.md)
> says otherwise. Version 0.5.0 runs in the author's production Home Assistant
> against two units. Expect REJECTED outcomes on weak proxy links (a dropped frame
> in the pre-write EEPROM read); a rejected call sends nothing and is safe to
> repeat.

## Features

- Live telemetry **sensors**: status, current, line frequency, last start peak,
  short-cycle delay, learned starts, total starts, total faults
- Estimated compressor **power** sensor (current x nominal voltage x power
  factor), with the voltage and power factor configurable in options
- Diagnostic sensors: model, firmware, startup mask, fault mask (with decoded
  bits as attributes)
- **Fault** and **Powered** (advertising) binary sensors
- A persistent **Polling** switch to pause all BLE traffic during OEM-app
  maintenance (survives restarts)
- **Feature parity with the OEM app's write path**: a **Startup mode** select
  (normal / relearn / default ramp / SuperLearn), **No power-up delay** and
  **Start delay mode** switches, a **Short-cycle protection timer** number, and
  seven **fault protection** switches — every write goes through one guarded,
  readback-verified path
- `microair_bt.set_startup_mode` **service** to store `normal`, `relearn`,
  `default_ramp` or `superlearn` with EEPROM readback verification and an
  operator notification
- Bluetooth **auto-discovery** (`EasyStart_*` local name) and manual add by
  address
- Multi-device: one config entry per EasyStart
- **Advertisement-gated polling**: the unit only advertises while the A/C powers
  it, so the integration polls only while it is heard, never holds an idle GATT
  connection, backs off exponentially on failure, and never evicts a connected
  OEM app

## Prerequisites

- Home Assistant 2026.1.0 or newer
- [HACS](https://hacs.xyz) installed (recommended for installation)
- A **connectable** Bluetooth path to the EasyStart: a local adapter or an
  active ESPHome BLE proxy within a few metres of the unit (see
  [`wiki/ha-proxy-coverage.md`](wiki/ha-proxy-coverage.md))
- The EasyStart advertises only while the A/C is supplying it control power, so
  the thermostat must be calling for cooling during setup

## Installation

See **[INSTALL.md](INSTALL.md)** for the complete guide.

**Quick version (HACS):** add this repository as a custom repository in HACS,
install **MicroAir BT**, restart Home Assistant, then add the integration from
**Settings → Devices & Services**.

[![Open in HACS][hacs-repo-shield]][hacs-repo]

## Configuration

The EasyStart is discovered automatically once a Bluetooth proxy hears it. No
credentials are required — control is entirely local. Setup reads the unit's
EEPROM to confirm a supported model before the entry is created.

### Configuration Steps

1. Make sure the A/C is calling for cooling and the OEM app is closed
2. Go to **Settings → Devices & Services**
3. If the unit was auto-discovered, click **Configure** on the notification;
   otherwise click **Add Integration**, search for **MicroAir BT**, and enter
   the Bluetooth address
4. Click **Submit**

### Options

| Option | Default | Description |
|---|---|---|
| Minimum polling interval | 30 s | Lower bound between reads (minimum 15 s) |
| Allow writes while running | off | Permit any write (service or control entity) while the compressor draws current |
| Nominal line voltage | 240 V | Voltage used for the power estimate (90-300) |
| Compressor power factor | 0.9 | Power factor used for the power estimate (0-1) |
| Live mode | off | Hold one connection open for near-real-time current (see below) |
| Live-mode read interval | 5 s | Seconds between reads in live mode (minimum 2 s) |

### Live mode

By default the integration **connects per poll** — it connects, reads, and
disconnects each cycle, so Home Assistant re-picks the best proxy every time and
never holds an idle connection. This is the most reliable behaviour on weak
proxy links and is recommended.

**Live mode** instead holds **one** connection open through a single proxy and
reads every few seconds, giving near-real-time current like the OEM app. It
reconnects on its own if the link drops. The trade-offs:

- It **monopolises the unit's Bluetooth**: the OEM app cannot connect, and
  `set_startup_mode` is rejected until you turn live mode (or the Polling
  switch) off.
- On a marginal link a held connection is less resilient than reconnect-per-read;
  if entities flap, use the default mode or a closer proxy.

Live mode and its interval can be changed at any time in the integration options
and take effect without a restart.

## Supported Equipment

Startup-mode control is enabled for the **`398ULBT`** (EasyStart Flex) model.
Other EasyStart models that speak the same protocol are rejected at setup until
they have been verified. Entities are created per device.

### Sensors

| Entity | Description |
|---|---|
| Status | Enum: `normal`, `short_cycle_delay`, or one of the fault codes |
| Current | Compressor current (A) |
| Line frequency | Mains frequency (Hz) |
| Last start peak | Peak current of the last start (A) |
| Power | Estimated compressor real power (W): current x voltage x power factor — compressor only, an estimate |
| Short cycle delay | Remaining short-cycle protection delay (s) |
| Learned starts | Starts recorded toward the learned profile |
| Total starts | Lifetime start counter |
| Total faults | Lifetime fault counter |
| Model / Firmware / Startup mask / Fault mask | Diagnostic; the two masks expose their decoded bits as attributes |

### Binary Sensors

| Entity | Description |
|---|---|
| Powered | The unit is advertising (A/C is supplying it power) |
| Fault | Status is a fault code (not `normal` or `short_cycle_delay`) |

### Controls

Every control below is a **configuration** entity that writes to the EasyStart's
EEPROM through the same guarded path as the service: it reads live status first
(refusing while the compressor runs unless the option above is enabled), reads
a fresh EEPROM image, writes once, re-reads the EEPROM and reports `STORED` only
when the readback matches. Controls are unavailable until an EEPROM image has
been read and while **Live mode** holds the connection.

| Entity | Type | Description |
|---|---|---|
| Polling | switch | Pause/resume all BLE reads and writes; available even while unpowered |
| Startup mode | select | *Disabled by default*: enabling it is your explicit confirmation, like the service's `confirm` flag. `normal`, `relearn`, `default_ramp`; `superlearn` (the app's hidden long-press variant of relearn) appears for firmware 29+. Selecting `relearn` sends the relearn instruction and posts the OEM power-cycle procedure |
| No power-up delay | switch | Startup-mask bit 2, the app's "No Pwr-Up Delay" |
| Start delay mode | switch | *Disabled by default.* Hidden app mode (bit 3) that turns the SCPT byte into a start delay |
| Short-cycle protection timer | number | SCPT, 1-250 whole minutes; attribute `interpretation` reports `start_delay` when the hidden mode is set |
| Unexpected current / Power interruption / Compressor stall / Start hardware failed / Open overload / Overcurrent / Wiring issue protection | switch | *Disabled by default.* The app's Fault Control enables. Turning one **off stops the EasyStart from detecting that fault**; enable these entities deliberately (they stand in for the app's confirm dialog). The last enabled protection cannot be turned off |

### Services

`microair_bt.set_startup_mode` — store a startup mode on one EasyStart:

| Field | Description |
|---|---|
| `entry` or `device` | Exactly one target |
| `mode` | `normal`, `relearn`, `default_ramp` or `superlearn` |
| `confirm` | Must be `true` |

The service reads live status first, refuses to write while the compressor is
running unless the option above is enabled, writes the startup mask, re-reads
the EEPROM, and returns `STORED` only when the readback matches. Outcomes are
also posted as a persistent notification. **The integration never cycles the
compressor**: after a `relearn`, follow the Micro-Air procedure (end the cooling
call so the unit powers off, then allow five successful starts of at least 30 s).

### What a relearn does

Storing `relearn` only sets a flag. At the **next power-up** (the next cooling
call after the unit has powered off) the EasyStart erases its learned profile
**and its lifetime counters**: Learned starts, Total starts, Total faults and
Last start peak all drop to 0, then Learned starts counts up as the compressor
completes learning starts. Five successful starts of at least 30 s finish the
learn. Normal thermostat cycling completes them; the integration never cycles
the compressor.

### Firmware updates

Micro-Air publishes firmware for the EasyStart over its own app. The
integration **cannot and will not** send any firmware-update command. Update
with the OEM EasyStart app, with the A/C calling for the whole flash and the
integration's **Polling** switch off. An update rewrites the unit's EEPROM,
so the unit learns again afterwards.

## Automation Examples

**Notify on a soft-starter fault:**

```yaml
automation:
  - alias: "EasyStart fault"
    trigger:
      - platform: state
        entity_id: binary_sensor.easystart_88cd_fault
        to: "on"
    action:
      - service: notify.mobile_app
        data:
          message: "EasyStart fault: {{ states('sensor.easystart_88cd_status') }}"
```

**Request a relearn (script, run deliberately):**

```yaml
script:
  easystart_relearn:
    sequence:
      - service: microair_bt.set_startup_mode
        data:
          device: !input easystart_device
          mode: relearn
          confirm: true
```

The same write is one tap away as the **Startup mode** select entity:

```yaml
      - service: select.select_option
        target:
          entity_id: select.easystart_88cd_startup_mode
        data:
          option: relearn
```

**Lovelace card:**

```yaml
type: entities
title: EasyStart
entities:
  - entity: sensor.easystart_88cd_status
  - entity: sensor.easystart_88cd_current
  - entity: sensor.easystart_88cd_learned_starts
  - entity: binary_sensor.easystart_88cd_powered
  - entity: switch.easystart_88cd_polling
  - entity: select.easystart_88cd_startup_mode
  - entity: number.easystart_88cd_short_cycle_protection_timer
  - entity: switch.easystart_88cd_no_power_up_delay
```

## Troubleshooting

**Integration not appearing / device not discovered**
- The EasyStart only advertises while the A/C is powering it: make sure the
  thermostat is calling for cooling
- Close the OEM app — the unit accepts one BLE client and stops advertising
  while connected
- Confirm a proxy hears it with the read-only probe (below) or HA's Bluetooth
  advertisement monitor; usable range is only a few metres
- Restart Home Assistant completely after installing

**Entities show "unavailable"**
- Expected whenever the unit is unpowered (A/C idle) or the **Polling** switch
  is off. The **Powered** binary sensor stays available and reports the
  advertising state.
- On a failed read the integration backs off (up to 5 min) and holds the error
  until the next successful poll.

**A write (service or control entity) returns REJECTED / INDETERMINATE**
- `REJECTED` means nothing was written (not advertising, compressor running,
  unsupported model, polling paused, live mode on, or a value the device does
  not accept). `INDETERMINATE` or `ACKNOWLEDGED-BUT-UNVERIFIED` means a write
  may have landed but the readback failed — the affected entities go
  unavailable until the next successful poll; inspect the **Startup mask** /
  **Fault mask** sensors before sending another command.

**The Startup mode select or the fault protection switches are missing**
- They are created disabled. Enable them from the device page (entity
  settings) and reload the entry; this deliberate step replaces the OEM app's
  confirm dialog and the service's `confirm` flag.

**Debug logging:**

```yaml
logger:
  default: info
  logs:
    custom_components.microair_bt: debug
```

## Development

The wire protocol and reverse-engineering notes live in
[`wiki/`](wiki/index.md) (read [`wiki/SCHEMA.md`](wiki/SCHEMA.md) before
editing). The protocol layer
(`custom_components/microair_bt/microair/`) is framework-free and unit-tested;
tests use a fake peripheral and never touch Bluetooth.

```bash
uv sync
uv run ruff check .
uv run ruff format --check .
uv run mypy --strict custom_components scripts tests
uv run pytest -q
```

### Read-only probe

```sh
uv run scripts/probe.py --scan-seconds 2
uv run scripts/probe.py --name EasyStart_XXXX
uv run scripts/probe.py --address AA:BB:CC:DD:EE:FF --json
```

Without a selector, the probe only scans. A selected device must be heard as an
EasyStart candidate before connection. The probe prints the GATT profile, MTU,
every notification and the decoded EEPROM/live data; it sends only the two read
requests and never changes settings. Close the OEM app first.

## Support

- **Issues:** <https://github.com/joyfulhouse/microair-bt/issues>
- **Discussions / questions:** open an issue with the `question` label.

## Support Development

If this project is useful to you, please consider supporting its development:

- [GitHub Sponsors][sponsors]
- [Ko-fi][kofi]

## License

This project is licensed under the **MIT** License — see [LICENSE](LICENSE) for
details.

## Credits

Built and maintained by [JoyfulHouse](https://github.com/joyfulhouse). Sibling
project: [`fogmachine-bt`](https://github.com/joyfulhouse/fogmachine-bt), whose
structure this repository follows.

This is an unofficial integration and is not affiliated with or endorsed by
Micro-Air or the *EasyStart* app.

---

<p align="center">
  <a href="https://github.com/omnigent-ai/omnigent"><img src="https://raw.githubusercontent.com/joyfulhouse/.github/main/assets/badges/built-with-omnigent.svg" alt="Built with Omnigent"></a>
  <br>
  <sub>Built with <a href="https://github.com/omnigent-ai/omnigent">Omnigent</a> — the open-source AI agent framework and meta-harness.</sub>
</p>

<!-- Badge links -->
[releases-shield]: https://img.shields.io/github/release/joyfulhouse/microair-bt.svg?style=for-the-badge
[releases]: https://github.com/joyfulhouse/microair-bt/releases
[license-shield]: https://img.shields.io/github/license/joyfulhouse/microair-bt.svg?style=for-the-badge
[hacs-shield]: https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge
[hacs]: https://github.com/hacs/integration
[hacs-repo-shield]: https://my.home-assistant.io/badges/hacs_repository.svg
[hacs-repo]: https://my.home-assistant.io/redirect/hacs_repository/?owner=joyfulhouse&repository=microair-bt&category=integration
[ci-shield]: https://img.shields.io/github/actions/workflow/status/joyfulhouse/microair-bt/hacs-validate.yml?style=for-the-badge&label=CI
[ci]: https://github.com/joyfulhouse/microair-bt/actions
[maintenance-shield]: https://img.shields.io/badge/maintainer-%40btli-blue.svg?style=for-the-badge
[maintenance]: https://github.com/btli
[sponsors-shield]: https://img.shields.io/badge/sponsor-GitHub-EA4AAA.svg?style=for-the-badge&logo=githubsponsors&logoColor=white
[sponsors]: https://github.com/sponsors/btli
[kofi-shield]: https://img.shields.io/badge/Ko--fi-donate-FF5E5B.svg?style=for-the-badge&logo=ko-fi&logoColor=white
[kofi]: https://ko-fi.com/bryanli
[omnigent-shield]: https://raw.githubusercontent.com/joyfulhouse/.github/main/assets/badges/built-with-omnigent.svg
[omnigent]: https://github.com/omnigent-ai/omnigent
