# MicroAir BT

A Home Assistant custom integration for the **MicroAir EasyStart Flex** home
A/C soft starter (the unit driven by the *EasyStart* Android/iOS app,
`net.microair.easystart`), providing **local Bluetooth** monitoring and control
with **no cloud dependency**.

> Status: **reverse-engineering in progress.** Nothing here is verified against a
> live unit yet. See [`wiki/index.md`](wiki/index.md) for the current state.

## Why

The EasyStart Flex "learns" the compressor's start profile over its first
starts. When that learned profile goes stale or wrong the soft starter can keep
the compressor from starting at all. The primary goal of this project is to be
able to **reset the learned profile from Home Assistant** (so the unit re-learns
on the next starts) and to read its fault/status data locally, without the
vendor app.

## What It Does (planned)

- Read live status: fault codes, start counts, learning state, firmware/model.
- **Reset learning / clear faults** via HA services and button entities.
- Bluetooth **auto-discovery** through Home Assistant's Bluetooth proxies
  (ESPHome), not just a local radio.

## Project layout

- `wiki/` — distilled, cross-referenced knowledge (the durable record; read
  [`wiki/SCHEMA.md`](wiki/SCHEMA.md) before editing).
- `sources/` — raw, immutable evidence (APK, decompiled code, scans, analyses).
  The APK and decompiled tree are git-ignored and regenerable; the analyses and
  scan tooling are committed.
- `custom_components/microair_bt/` — the HA integration (to be built).
- `docs/` — longer-form docs; `docs/claude/` holds session/research reports.

## Related

- [`fogmachine-bt`](https://github.com/joyfulhouse/fogmachine-bt) — the sibling
  local-BLE integration whose structure this project follows.

## License

MIT — see [LICENSE](LICENSE). Not affiliated with MicroAir.

## Development

Python 3.13 and `uv`:

```sh
uv sync
uv run ruff check .
uv run ruff format --check .
uv run mypy --strict custom_components scripts tests
uv run pytest -q
uv run pytest --collect-only -q | tail -1
```

The standalone `custom_components.microair_bt.microair` library needs no
Home Assistant. Tests use a fake peripheral and never access Bluetooth.
Protocol facts and provisional framing/timeouts are in `wiki/integration-plan.md`.

## Read-only probe

```sh
uv run scripts/probe.py --scan-seconds 2
uv run scripts/probe.py --name EasyStart_XXXX
uv run scripts/probe.py --address AA:BB:CC:DD:EE:FF --json
```

Without a selector, the probe only scans. A selected device must be heard as
an EasyStart candidate before connection. Candidate addresses are shown in
full; other addresses retain only their first three bytes. A selected probe
prints the GATT profile, MTU, every notification (hex, repr, length, timing),
and decoded EEPROM/live data. `--json` emits one document. Only the two read
requests are sent; the probe never changes settings. Close the OEM app first.
Real-device framing, write properties, and decoded values await G1 evidence.
