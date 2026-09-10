# CLAUDE.md — microair-bt

Guidance for Claude Code (and humans) working in this repo.

## What this project is

Reverse-engineering the **MicroAir EasyStart Flex** home A/C soft starter's BLE
protocol (OEM Android app `net.microair.easystart`, "EasyStart") and building a
**local Home Assistant Bluetooth integration** — no cloud. The immediate goal
is to **reset the unit's learned start profile** (and read faults/status) from
HA, because a stale learned profile can keep the compressor from starting.

Sibling project and structural template: `../fogmachine-bt` (same layout, same
wiki pattern, same tooling).

## Knowledge lives in the wiki — read it first

This project uses an **LLM-maintained wiki** (the karpathy "LLM Wiki" pattern)
for durable, cross-session memory. **Start every session at
[`wiki/index.md`](wiki/index.md)**, and read [`wiki/SCHEMA.md`](wiki/SCHEMA.md)
before editing the wiki.

- `wiki/` — distilled, cross-referenced knowledge (edit these as you learn).
- `sources/` — **raw, immutable** evidence (APK, decompiled code, scans,
  independent analyses). Never edit; register new evidence in `wiki/sources.md`.
- `custom_components/microair_bt/` — the HA integration.
- `docs/claude/` — session and research reports (process artifacts, not the
  durable record — fold durable facts into the wiki).

## Tooling / conventions

- **Python: use `uv`** (`uv run …`, `uv sync`). Python 3.13+. Never pip.
- RE tools: `apkeep` (download), `jadx` (Java), `apktool` (manifest/smali).
  Decompiled tree: `sources/decompiled/jadx/sources/net/microair/easystart/`.
- The HA integration follows HA custom-component conventions; keep the protocol
  layer (`microair/`) free of HA imports so it is unit-testable.
- Home Assistant access for live scans: direct URL `http://hass.joyful.house:8123`
  (WebSocket `ws://hass.joyful.house:8123/api/websocket`); the long-lived token
  is `HA_PROD_LONG_LIVED_TOKEN` in `../eg4_web_monitor/.env`. Never commit or
  print tokens; keep local copies in a git-ignored `.env`.
- Nearest known Bluetooth proxy to the unit: ESPHome `aiosense-kaelyns-bedroom`
  (10.100.0.134, `bluetooth_proxy: active: true`; config in
  `../aiosense/devices/aiosense-kaelyns-bedroom.yaml`).

## Safety when live-testing

- This device switches a **mains-powered A/C compressor**. Prefer a
  **read-only probe first** (connect, enable notifications, read status) before
  sending any write.
- Never send an untested write while the A/C is calling for cooling. Gate
  reset/learn commands behind explicit confirmation until verified live.

## Next steps

Tracked in [`wiki/index.md`](wiki/index.md) (status table).
