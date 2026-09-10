# Home Assistant integration plan — `microair_bt` (SPECIFICATION v1.1)

Purpose: the design and acceptance contract for the local-BLE Home Assistant
integration for the MicroAir EasyStart Flex. This page *is* the spec handed to
the implementer.
Status: **planned** — v1.0 drafted 2026-09-10; **v1.1 after a three-vendor
/debate (REVISE × 3)**, synthesis in `docs/claude/research/debate-spec-synthesis.md`.
Items marked ⚠️ are resolved by evidence gates named in §12.

Facts this design rests on: [ble-transport](ble-transport.md),
[ble-protocol](ble-protocol.md), [available-data](available-data.md),
[device-easystart-flex](device-easystart-flex.md),
[ha-proxy-coverage](ha-proxy-coverage.md). Structural template:
`../fogmachine-bt` (layout, tooling, wiki pattern — copy the *structure*, not
its test stubs/suppressions).

## 1. Goal and non-goals

**Goal.** A HACS-installable custom integration `microair_bt` that, over HA's
Bluetooth stack (incl. ESPHome proxies), (a) reads the EasyStart's live
telemetry and settings as HA entities, and (b) lets the user **request a
startup-mode change** — chiefly **relearn** (the OEM's "restore to factory
settings, ready to learn again") — safely, and **observe** the learning
counter afterwards. No cloud.

**Primary user story.** "The soft starter seems to be keeping the compressor
from starting; from HA I want to reset it so it learns again, and see that it
did."

**Non-goals (v1).** Firmware update (all 19 update-path commands are
structurally impossible to send); writing `FMask` or `SCPT`; "clearing faults"
(no such command exists); SuperLearn / hidden modes (masks with bits 4–7 set
are refused); automatic retries, automatic relearns or automatic power
cycling; any claim that relearn diagnoses *why* a compressor does not start;
authentication of the peripheral (the link has none — see §10).

## 2. Delivery: two PRs, one implementer

**PR-1 — protocol foundation (no Home Assistant imports).**
`custom_components/microair_bt/microair/{__init__,protocol,client}.py`,
`scripts/probe.py`, `tests/` for both, `pyproject.toml`, tooling. Merges on its
own gates. Its probe is then run by the human near the powered unit and the
output is folded into the wiki (evidence gate G1, §12).

**PR-2 — HA component.** Everything else in §3, built on PR-1 and on G1
evidence. Control (`set_startup_mode`) ships in PR-2 but the first *live*
write is a supervised human action (gate G2).

Implementer must NOT: perform any BLE action from tests/CI; send anything but
`ReadEEP`/`ReadLive` from the probe; add `SCPT`/`FMask`/update builders "for
completeness"; accept a raw mask or raw bytes in any service; add a button
entity; add pairing/bonding code; vendor decompiled sources into the package;
edit wiki fact pages other than pasting probe output; contact any Micro-Air
endpoint; reconfigure proxies or anything electrical.

## 3. Architecture

```
custom_components/microair_bt/
├── manifest.json            # bluetooth matcher, deps: bleak-retry-connector
├── __init__.py              # setup/unload entry; register service
├── config_flow.py           # bluetooth discovery + manual (address); options: poll interval
├── const.py
├── coordinator.py           # connect-on-demand poll, parse, availability, persistence
├── entity.py
├── sensor.py / binary_sensor.py / switch.py
├── services.yaml            # set_startup_mode
├── diagnostics.py
├── strings.json / translations/en.json
└── microair/                # PR-1: pure-python protocol lib — NO homeassistant imports
    ├── __init__.py
    ├── protocol.py          # Command whitelist, builders, parsers, mask math, completion
    └── client.py            # BleakClient wrapper: connect, notify, transaction, disconnect
scripts/probe.py             # PR-1: PEP-723 read-only live probe (uv run), bleak only
tests/                       # pytest; PR-1 tests need no HA
```

## 4. Protocol layer (`microair/protocol.py`)

- `class Command(Enum)`: exactly `READ_EEP`, `READ_LIVE`, `SET_STARTUP_MASK`.
  `build(cmd, arg=None) -> bytes` returns the exact bytes on
  [ble-protocol](ble-protocol.md); `SET_STARTUP_MASK` requires
  `0 ≤ arg ≤ 0x1F`; the read commands reject any arg.
- **Whitelist is structural and defended in depth:** the client's write path
  accepts only `Command` + int, never `str`/`bytes`; the single
  `write_gatt_char` call site additionally asserts the payload matches
  `^\{"Cmd": (ReadEEP|ReadLive|SMask=[0-9A-F]{2})\}$` and is 16/17 bytes. Tests
  prove none of the other 21 inventory strings (`ProgMode`, `ChipErase`,
  `FMask=…`, `SCPT=…`, `OtaPrep`, `{"Wrt": …}` …) can be produced or sent.
- `parse_live(buf) -> LiveData`: requires `18 ≤ len(buf) ≤ 64`; fields per
  [available-data](available-data.md); `line_hz=None` when period is 0;
  unknown status codes → `StatusCode.UNKNOWN` with `raw_status:int` kept; raw
  bytes kept.
- `parse_eeprom(buf) -> EepromData`: requires `909 ≤ len(buf) ≤ 1100`; model
  (ASCII idx 2–8, must decode as printable ASCII), firmware (10), startup_mask
  (906), fault_mask (907), scpt_minutes (908); raw kept.
- `mode_mask(current: int, mode: StartupMode) -> int` =
  `(current & 0x1C) | {NORMAL: 0x00, RELEARN: 0x01, DEFAULT_RAMP: 0x02}` —
  the app's switch reconstruction (keeps No-Pwr-Up-Delay and hidden bits 3–4).
  Documented as switch-ON arithmetic, **not** a factory reset. A separate
  `has_unsupported_bits(mask) -> bool` is true when `mask & 0xF0`.
- `is_completion(notification: bytes) -> Completion | None` (**provisional
  until G1**): strip trailing `\r`, `\n`, `\0`, whitespace; then require
  `≤ 64` bytes, every byte in `0x20–0x7E`, and the substring `Success` → `OK`
  or `Fail` → `FAIL`; both substrings present → `CONFLICT` (treated as
  failure). Binary chunks that merely contain the bytes are not completions;
  this is a heuristic, not a framing guarantee. Tests: `Success\r\n`,
  `Success\0`, a 20-byte binary chunk containing `Success`, a 100-byte
  printable chunk containing `Success`, mixed tokens.

## 5. BLE client (`microair/client.py`)

- `bleak` + `bleak_retry_connector.establish_connection` with an explicit
  `max_attempts` (2 for polls, 4 for the service); takes a `BLEDevice`. No
  MTU request (not in bleak's public API); log `client.mtu_size`; reassembly
  is MTU-agnostic (test feeds the 1100-byte image in 20-byte chunks).
- **One transaction = one connection = one lock.** `async with
  client.transaction(): …` covers connect → `start_notify(…f2e1)` → 0.5 s
  settle → one or more commands → disconnect (always, in `finally`). A
  per-device `asyncio.Lock` serialises transactions (poll vs service). Each
  connection has a generation id; notification callbacks and futures are
  scoped to it, so a late notification from a timed-out command can never
  resolve the next one.
- `run(cmd, arg=None, *, timeout)` inside a transaction: clear buffer; write
  (with-response if the characteristic offers it, ⚠️ G1); append binary
  notifications up to the cap (ReadLive 64 B, ReadEEP 1100 B — overflow ⇒
  `ProtocolError`, connection poisoned); during `SET_STARTUP_MASK` any binary
  notification is dropped with a warning (app behaviour); resolve on `OK`,
  raise `CommandFailed` on `FAIL`/`CONFLICT`, `CommandTimeout` on deadline.
  The whole command including the GATT write is bounded by `timeout`. Any
  timeout, `Fail`, malformed framing or cancellation **poisons the
  connection**: it is disconnected and never reused.
- Timeouts (provisional until G1): ReadLive 10 s in polls / 20 s in the
  service, ReadEEP 20 s, SMask 10 s.
- Compatibility bind (before the service may write): connected service and
  both characteristics are the ST triplet; fresh EEPROM model ∈
  `CONTROL_MODELS = {"398ULBT"}` (a single constant; widening is a follow-up).

## 6. Read-only live probe (`scripts/probe.py`, PR-1)

PEP-723 (`uv run scripts/probe.py [--name EasyStart_XXXX | --address …]
[--json]`), bleak only. Scan (print candidates in full; **redact non-candidate
addresses to the first 3 bytes**), connect, dump services/characteristic
properties (write vs write-without-response, descriptors), `mtu_size`,
enable notify, `ReadEEP`, `ReadLive`, print every notification verbatim (hex +
repr, chunk sizes, timing) and the decoded fields. Contains no write path
other than the two reads (tests prove it). Its output is evidence gate **G1**.
Address *type* is to be taken from the HA proxy scan, not a laptop.

## 7. Coordinator, polling, availability (PR-2)

- `DataUpdateCoordinator`, fixed **60 s** (options 30–600 s), **no backoff**
  — the unit is absent most of the day and short powered windows must be
  caught. Fetch a fresh `BLEDevice` via
  `bluetooth.async_ble_device_from_address(hass, addr, connectable=True)` per
  operation; **fail fast** (no connect attempt) when it is `None`.
- Each poll (one transaction): `ReadLive` first; then `ReadEEP` on the first
  successful poll, after any write, on every poll while a request is pending
  (§9), otherwise at most every 10 min. Next poll is scheduled after the
  transaction finishes; polls never overlap.
- Availability: `unavailable` until the first valid sample; on failures 1–2
  keep the last sample (with `sample_time`); `unavailable` at 3 consecutive
  failures; counter resets only on a valid read. Every entity carries the
  timestamp of the sample it reflects.
- `switch.<dev>_polling` (default on): pause polling before OEM-app sessions
  and **always before a firmware update** (a poll in the `ProgMode` reboot gap
  could seize the single slot). README documents this; the integration never
  evicts the OEM app and never queues a write for later.
- Advertisement presence (`bluetooth.async_register_callback` +
  `async_track_unavailable`) drives `binary_sensor.powered` independently of
  GATT — it works even while the OEM app holds the link.
- unique_id = **local name** (`EasyStart_XXXX`, the OEM unit ID); address is
  mutable entry data refreshed on discovery via
  `_abort_if_unique_id_configured(updates={CONF_ADDRESS: …})` (⚠️ address
  stability unknown; dissent recorded in the synthesis).

## 8. Entities

Device info: name `EasyStart <suffix>`, manufacturer Micro-Air, model from
EEPROM (`398ULBT` → "EasyStart Flex"), `sw_version` = firmware byte.

| Entity | Source | Class / unit | Notes |
|---|---|---|---|
| `sensor.status` | live byte 2 | enum: 10 named states + `unknown` | `raw_state` attribute |
| `sensor.learned_starts` | live byte 3 | — | raw u8, no clamp; `sample_time` attr |
| `sensor.current` | live 4–5 | current, A | |
| `sensor.line_frequency` | live 6–7 | frequency, Hz | None when period 0 |
| `sensor.last_start_peak_current` | live 8–9 | current, A | |
| `sensor.short_cycle_delay` | live 10–11 | duration, s | |
| `sensor.total_faults` / `sensor.total_starts` | live 12–13 / 14–17 | total_increasing | |
| `binary_sensor.fault` | status ∈ {1,3,4,5,6,7,8,9} | problem | None for unknown codes |
| `binary_sensor.powered` | advertisement presence | connectivity | `last_seen` attr |
| `binary_sensor.relearn_request_flag` (diag) | SMask bit 0 | — | the *saved setting*, not progress; attrs: `sample_time`, last request (§9) |
| `binary_sensor.default_ramp` (diag) | SMask bit 1 | problem | so it is not left on |
| `sensor.startup_mask` (diag) | EEP 906 | hex | attrs: decoded bits 0–4 |
| `sensor.fault_mask` (diag) | EEP 907 | hex | read-only |
| `sensor.scpt` (diag) | EEP 908 | duration, min | read-only |
| `sensor.rssi` (diag) | HA bluetooth | dBm | |
| `switch.polling` | coordinator | — | §7 |

No button entity.

## 9. Service `microair_bt.set_startup_mode` (the point of the project)

Fields: `device_id` (target); `mode`: `normal` | `relearn` | `default_ramp`;
`confirm: bool` (**must be `true`**, else `ServiceValidationError`);
`allow_running: bool = false`; `allow_repeat: bool = false`.
(`default_ramp` is admitted pending the plan-gate ruling; if deferred, the
enum is `normal | relearn` and nothing else changes.)

Flow — one transaction, one connection:
1. Fresh `BLEDevice` or fail. Connect; compatibility bind (§5) or fail.
2. `ReadEEP` → `mask_before`; `has_unsupported_bits(mask_before)` ⇒ refuse
   ("SuperLearn/unknown bits set — needs OEM guidance"); `allow_running`
   cannot bypass this.
3. `ReadLive` fresh. Refuse if the sample is missing/invalid/stale (even with
   `allow_running`). Refuse if `current_a ≥ 1.0` unless `allow_running`
   (error text: "on a typical install the EasyStart is only powered while
   the A/C calls, so this guard trips; `allow_running: true` reproduces the
   OEM app's behaviour"). If status is Short Cycle Delay require
   `scpt_delay_s ≥ 10` so the compressor cannot start between read and write.
   This is a sampled safeguard with an unavoidable race, not an interlock.
4. `requested = mode_mask(mask_before, mode)` (for `normal`, if our last
   request set the mask, restore its `mask_before` instead). If `requested ==
   mask_before` → return outcome `ALREADY_SET`, no write, no timestamp reset.
5. Rate limit: refuse if our last write was < 10 min ago unless `allow_repeat`.
6. `SMask=<requested>` → then `ReadEEP` again. Outcome:
   - **VERIFIED**: `Success` and `startup_mask == requested` (also compare
     `fault_mask`/`scpt` with `mask_before` snapshot; warn if changed).
   - **APPLIED_UNVERIFIED**: `Success` but read-back ≠ requested (e.g. bit 0
     self-cleared ⚠️): do **not** raise; event carries `verified: false`;
     notification says the device acknowledged the write and the flag reads
     differently — watch `learned_starts`.
   - **FAILED**: `Fail`/timeout/conflict — the write *may* have reached the
     device; say so. **Never auto-retry, never toggle off/on.**
7. Persist on the entry: `{mode, requested_at, mask_before, mask_requested,
   mask_readback, outcome, learned_starts_before}`. Fire
   `microair_bt_startup_mode_set` with the same fields. Create a persistent
   notification (also shown in the service description) with the OEM
   procedure: **close the app / disconnect; power the A/C system down; use
   utility power that can start the compressor without EasyStart; one HVAC
   mode throughout; restore power; let the compressor (not just the fan) run
   ≥ 30 s; a fault in the first 15 s discards that attempt; five successful
   starts complete learning; the Flex insert recommends ≥ 8 cycles before
   limited-power use.** For `default_ramp`: "OEM says use under Micro-Air
   direction, temporarily; turn it off with `mode: normal`."
8. While a request is pending (`requested_at` set and no later `normal`),
   every poll re-reads EEPROM (§7). v1 **reports** `learned_starts` and the
   flag; it makes **no completion claim** (a pre-existing 5 is not evidence of
   a new learning cycle).

## 10. Safety model and its limits (README wording)

The BLE link is unauthenticated (no pairing, no checksum) and the UUIDs are
ST sample values. What the integration guarantees: it can only ever emit three
strings; writes happen only from an explicit, confirmed service call, once,
verified by read-back, rate-limited; incoming data is bounded and validated;
the OEM app is never evicted. What it cannot guarantee: an on-air
man-in-the-middle could rewrite bytes — this is inherent to the device and
equally true of the OEM app. Relearn does not diagnose *why* a compressor
fails to start; OEM lists bad learn data under *Stall*, and a unit that makes
no start attempt is more often power/wiring/thermostat (`binary_sensor.powered`
is the first thing to check).

## 11. Discovery / config flow

`manifest.json` bluetooth matcher: `{"connectable": true, "local_name":
"EasyStart_*"}` (legal: no wildcard in the first three characters). The UUID
is not a matcher on its own. Manual flow: address (+ name). `iot_class:
local_polling`, `integration_type: device`, dependency `bluetooth_adapters`,
requirement `bleak-retry-connector`.

## 12. Evidence gates and open items

**G1 — read-only probe (resolves before PR-2 is finalised):** completion
envelope text and length; 2-byte prefix of binary replies; characteristic
write type and descriptors; pairing/bonding requirement (a bonding requirement
**blocks** v1 rather than being "unhandled"); negotiated MTU / chunk sizes;
advertised name/suffix; which proxy hears the unit. Address type from the HA
proxy scan.

**G2 — supervised lifecycle observation (human-authorised, after PR-2):**
after the first live `relearn`: does bit 0 self-clear, when; how
`learned_starts` moves; whether a power cycle is required (OEM says yes).
Result decides whether v1.2 may claim completion.

**Hypothesis, not a gate:** whether bad learn data is what stops *this*
compressor.

## 13. Quality gates and conventions

Python 3.13, `uv` only; `ruff check` + `ruff format --check`; `mypy --strict`
on `custom_components`, `scripts`, `tests`; `pytest` (asyncio auto). No linter
or type suppressions. PR-1 tests: exact command bytes; whitelist/ban proof
(enum + write-site regex); parsers on synthetic buffers incl. short/over-cap/
garbage; `mode_mask` table (`0x00→01/02/00`, `0x02→01`, `0x14→15`,
`0x1F→1D`) and `has_unsupported_bits` (`0x10`, `0x20`, `0x80` refused by the
service path); completion cases from §4; client with a fake BleakClient
(20-byte chunking, `Fail`, conflict, timeout poisons connection, late
notification from an old generation ignored, poll-vs-service lock,
cancellation at each await). PR-2 tests: service flow with a fake client
(refuses running/stale/unsupported-bits/rate-limit, ALREADY_SET no-write,
VERIFIED/APPLIED_UNVERIFIED/FAILED, persistence survives reload), entity
mappings (unknown status, fault set), availability state machine, HA API
surface check against a pinned current HA release. Every new test shown red
with the fix reverted (/mutation-check). Direct `import microair` verified in
a fresh process without HA installed. HACS: `hacs.json`, README (install,
safety §10, OEM procedure, why entities go unavailable when the A/C is idle,
pause polling before the OEM app), CHANGELOG, MIT.
