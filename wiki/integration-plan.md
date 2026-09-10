# Home Assistant integration plan — `microair_bt` (SPECIFICATION v1)

Purpose: the design and acceptance contract for the local-BLE Home Assistant
integration for the MicroAir EasyStart Flex. This page *is* the spec handed to
the implementer and to /debate.
Status: **planned** — spec drafted 2026-09-10 from the verified protocol pages;
open items marked ⚠️ are to be resolved on first live contact.

Facts this design rests on: [ble-transport](ble-transport.md),
[ble-protocol](ble-protocol.md), [available-data](available-data.md),
[device-easystart-flex](device-easystart-flex.md),
[ha-proxy-coverage](ha-proxy-coverage.md). Structural template:
`../fogmachine-bt` (same layout, tooling and wiki pattern).

## 1. Goal and non-goals

**Goal.** A HACS-installable custom integration `microair_bt` that, over HA's
Bluetooth stack (incl. ESPHome proxies), (a) reads the EasyStart's live
telemetry and settings as HA entities, and (b) lets the user **request a
relearn** (reset of the learned start profile) safely, and **track its
progress** until the five learning starts complete. No cloud.

**Primary user story.** "The soft starter seems to be keeping the compressor
from starting; from HA I want to reset it so it learns again, and see that it
did."

**Non-goals (v1).** Firmware update (all 19 update-path commands are banned at
the protocol layer); writing `FMask` (fault enables) or `SCPT`; "clearing
faults" (no such command exists — see [ble-protocol](ble-protocol.md));
Default-Ramp / SuperLearn toggles; multi-client arbitration with the OEM app
(the unit allows one client; the user closes the app).

## 2. Architecture

```
custom_components/microair_bt/
├── manifest.json            # bluetooth matcher, deps: bleak-retry-connector
├── __init__.py              # setup/unload entry; register services
├── config_flow.py           # bluetooth discovery + manual (address); options: poll interval
├── const.py
├── coordinator.py           # connect-on-demand poll, parse, availability
├── entity.py                # base entity / device info
├── sensor.py / binary_sensor.py
├── services.yaml            # relearn / cancel_relearn
├── diagnostics.py
├── strings.json / translations/en.json
└── microair/                # pure-python protocol lib — NO homeassistant imports
    ├── __init__.py
    ├── protocol.py          # Command whitelist, builders, parsers, relearn mask math
    └── client.py            # BleakClient wrapper: connect, notify, run_command
scripts/probe.py             # PEP-723 read-only live probe (uv run), bleak only
tests/                       # pytest; protocol/client tests need no HA
```

`microair/` must be importable and unit-testable without Home Assistant
installed. `scripts/probe.py` is the tool for the first live contact and must
never write anything but `ReadEEP`/`ReadLive`.

## 3. Protocol layer (`microair/protocol.py`)

- `class Command(Enum)`: exactly three members — `READ_EEP`, `READ_LIVE`,
  `SET_STARTUP_MASK`. `build(cmd, arg: int | None) -> bytes` returns the exact
  bytes on [ble-protocol](ble-protocol.md) (`{"Cmd": ReadEEP}`,
  `{"Cmd": ReadLive}`, `{"Cmd": SMask=%02X}`); `SET_STARTUP_MASK` requires
  `0 ≤ arg ≤ 0x1F` (bits 5–7 are never set by us).
- **Whitelist is structural:** the client's write path accepts only a
  `Command` + arg, never `str`/`bytes`. A test proves that every other string
  from the 24-command inventory (`ProgMode`, `ChipErase`, `FMask=…`, `SCPT=…`,
  `OtaPrep`, `{"Wrt": …}` …) cannot be produced or sent.
- `parse_live(buf: bytes) -> LiveData` per [available-data](available-data.md):
  state (enum, unknown codes map to `UNKNOWN(n)`), learned_starts, current_a,
  line_hz (None when period is 0), last_start_peak_a, scpt_delay_s,
  total_faults, total_starts. Requires `len(buf) ≥ 18`; keeps the raw bytes.
- `parse_eeprom(buf: bytes) -> EepromData`: model (ASCII idx 2–8), firmware
  (idx 10), startup_mask (906), fault_mask (907), scpt_minutes (908); raw kept.
  Requires `len(buf) ≥ 909`.
- `relearn_mask(current: int) -> int` = `(current & 0x1C) | 0x01`;
  `normal_mask(current: int) -> int` = `current & 0x1C` (clears ReLearn and
  Default-Ramp, keeps No-Pwr-Up-Delay and hidden bits) — the exact arithmetic
  the OEM app performs.
- `is_completion(notification: bytes) -> Completion | None`: a notification
  is a completion text iff it is ≤ 64 bytes, decodes as ASCII with all
  printable characters, and contains `Success` (→ `OK`) or `Fail` (→ `FAIL`).
  Binary chunks that merely contain those bytes are *not* completions.
  ⚠️ exact text unknown — the client logs the verbatim first completion text
  at INFO once per connection.

## 4. BLE client (`microair/client.py`)

- Uses `bleak` + `bleak_retry_connector.establish_connection`; accepts a
  `BLEDevice`; service/characteristic UUIDs from [ble-transport](ble-transport.md).
- `connect()`: establish → (best effort) request MTU 517 → `start_notify(…f2e1)`
  → sleep 0.5 s. No pairing. ⚠️ If the device turns out to require bonding, the
  first live probe will show it; not handled in v1.
- `run(cmd, arg=None, timeout) -> bytes`: single in-flight `asyncio.Lock`;
  clears the buffer; writes (`response=` whatever bleak reports the
  characteristic supports, preferring with-response); appends binary
  notifications; resolves on a completion (`OK` → return buffer; `FAIL` →
  `CommandFailed`); `asyncio.TimeoutError` → `CommandTimeout`. Timeouts:
  ReadLive 5 s, ReadEEP 20 s, SMask 10 s.
- `read_live()`, `read_eeprom()`, `write_startup_mask(mask)` convenience
  methods; `disconnect()`.
- Never sends anything not produced by `protocol.build`.

## 5. Coordinator and polling

- `DataUpdateCoordinator`, default interval **60 s** (options: 30–600 s).
- **Connect-on-demand, disconnect after each poll** (the unit allows a single
  client and is only powered while the A/C calls; holding a link blocks the
  OEM app). Each poll: connect → `ReadLive` → (`ReadEEP` on first poll, after
  a relearn/cancel, and at most every 10 min) → disconnect.
- Availability = last poll succeeded; entities become `unavailable` after 3
  consecutive failures (expected whenever the A/C is idle — document this).
- `BLEDevice` from `bluetooth.async_ble_device_from_address(hass, addr,
  connectable=True)`; unique_id = BLE address. ⚠️ address stability is
  unverified; the config flow also stores the local name so a re-discovery
  with a new address can be matched manually.

## 6. Entities

Device info: name `EasyStart <suffix>`, manufacturer Micro-Air, model from
EEPROM (`398ULBT` → "EasyStart Flex"), `sw_version` = firmware byte.

| Entity | Source | Class / unit | Notes |
|---|---|---|---|
| `sensor.<dev>_status` | live byte 2 | enum (options = 10 states + unknown) | |
| `sensor.<dev>_learned_starts` | live byte 3 | — | relearn progress (0→5) |
| `sensor.<dev>_current` | live 4–5 | current, A | |
| `sensor.<dev>_line_frequency` | live 6–7 | frequency, Hz | |
| `sensor.<dev>_last_start_peak_current` | live 8–9 | current, A | |
| `sensor.<dev>_short_cycle_delay` | live 10–11 | duration, s | |
| `sensor.<dev>_total_faults` | live 12–13 | total_increasing | |
| `sensor.<dev>_total_starts` | live 14–17 | total_increasing | |
| `binary_sensor.<dev>_relearn_pending` | SMask bit 0 | — | on after a relearn request until firmware clears it ⚠️ |
| `binary_sensor.<dev>_fault` | status ∉ {Normal, Short Cycle Delay} | problem | |
| `sensor.<dev>_startup_mask` (diag) | EEP 906 | hex text | |
| `sensor.<dev>_fault_mask` (diag) | EEP 907 | hex text | read-only |
| `sensor.<dev>_scpt` (diag) | EEP 908 | duration, min | read-only |
| `sensor.<dev>_rssi` (diag) | HA bluetooth | dBm | |

## 7. Relearn service (the point of the project)

`microair_bt.relearn` — fields: `device_id` (target), `confirm: bool`
(**must be `true`**, else `ServiceValidationError`), `allow_running: bool =
false`.

Flow (all in one connection):
1. `ReadEEP`; require a known model string; snapshot `startup_mask`.
2. `ReadLive`; if `current_a ≥ 1.0` (compressor running) and not
   `allow_running` → abort with a clear error (**never write while the
   compressor runs unless forced**).
3. `SMask=<relearn_mask(startup_mask)>` → expect `OK`.
4. `ReadEEP` again → assert `startup_mask & 0x01 == 1`, else raise.
5. Persist `relearn_requested_at` + `learned_starts_at_request` on the entry;
   fire event `microair_bt_relearn_requested` `{device_id, mask_before,
   mask_after}`; create a persistent notification with the OEM procedure:
   **power the A/C system down, restore power, let the compressor run ≥ 30 s;
   repeat for 5 successful starts; watch `learned_starts`.**

`microair_bt.cancel_relearn` — same shape; writes `normal_mask(startup_mask)`
and verifies bit 0 is clear. Exists because it is ⚠️ unknown whether firmware
clears bit 0 itself after learning.

No button entity in v1 (one-click writes to a mains compressor controller are
too easy to trigger by accident); a user script can wrap the service.

## 8. Discovery / config flow

`manifest.json` bluetooth matchers: `{"connectable": true, "local_name":
"EasyStart_*"}`. The ST sample UUID `d973f2e0…` is not unique to Micro-Air, so
it is *not* a matcher on its own. Manual flow: address (+ optional name).
`iot_class: local_polling`, `integration_type: device`, dependency
`bluetooth_adapters`, requirement `bleak-retry-connector`.

## 9. Read-only live probe (`scripts/probe.py`)

PEP-723 script (`uv run scripts/probe.py [--name EasyStart_XXXX | --address …]
[--json]`), bleak only, runnable from a laptop near the condenser: scan (print
every ADV with name/UUIDs/RSSI/address type), connect, list services/
characteristic properties (write vs write-without-response, descriptors), enable
notify, `ReadEEP`, `ReadLive`, print every notification verbatim (hex + repr),
print decoded fields. **It contains no write path other than the two reads.**
Its output resolves the ⚠️ items in §11 and is pasted into the wiki.

## 10. Quality gates and conventions

- Python 3.13, `uv` only; `ruff check` + `ruff format --check`;
  `mypy --strict` on `custom_components`, `scripts`, `tests`; `pytest`.
  No linter/type suppressions.
- Tests (pytest, asyncio auto): exact command bytes; whitelist/ban proof;
  parsers on synthetic buffers incl. short/garbage input; relearn/normal mask
  table (e.g. `0x00→0x01`, `0x02→0x01`, `0x14→0x15`, `0x1F→0x1D`); completion
  detection incl. a binary chunk containing `Success`; client with a fake
  BleakClient (chunked notifications, `Fail`, timeout, in-flight lock);
  service flow with a fake client (aborts when running, verifies bit 0,
  raises on mismatch); `confirm` validation. Every new test shown red with
  the fix reverted (/mutation-check).
- HA API surface check like fogmachine's `tests/_import_check.py` against a
  pinned current HA release.
- HACS: `hacs.json`, README (install, safety, relearn procedure, why entities
  go unavailable when the A/C is idle), CHANGELOG, MIT.

## 11. Open items — resolve on first live contact (read-only)

1. Exact completion notification text; the 2-byte prefix of binary replies.
2. Characteristic write type (with / without response) and descriptor set.
3. Whether the unit needs pairing/bonding; real negotiated MTU and chunk sizes.
4. Advertised name/suffix, address type, and whether the address changes.
5. Which proxy hears it (none did on 2026-09-10) — see
   [ha-proxy-coverage](ha-proxy-coverage.md).
6. After a relearn: does SMask bit 0 self-clear? How does `learned_starts`
   move? Is a power cycle required (OEM says yes)?
7. Whether bad learn data is in fact what stops this compressor (OEM lists it
   under *Stall*, not "no start attempt").
