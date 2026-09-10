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
