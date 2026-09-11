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
- Home Assistant access for live scans: set `HA_URL` and `HA_TOKEN` (a
  long-lived access token) in a git-ignored `.env`; never commit, print, or
  pass tokens on a command line. Environment specifics (hostnames, proxy names
  and addresses) live in the operator's private notes, not in this repo.
- **Bluetooth path policy:** the integration reaches the unit only through Home
  Assistant's Bluetooth stack — the nearest **ESPHome active BLE proxy** in
  production. Do not stand up an ad-hoc host adapter (a desktop's `hci0`) as
  the production path; `scripts/probe.py` on a laptop is for one-off read-only
  diagnostics only.

## Safety when live-testing

- This device switches a **mains-powered A/C compressor**. Prefer a
  **read-only probe first** (connect, enable notifications, read status) before
  sending any write.
- Never send an untested write while the A/C is calling for cooling. Gate
  reset/learn commands behind explicit confirmation until verified live.

## Next steps

Tracked in [`wiki/index.md`](wiki/index.md) (status table).
