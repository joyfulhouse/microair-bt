# Debate seat — Anthropic (`debate-spec-anthropic`, round 1, independent)

COMPLETE

Subject: `wiki/integration-plan.md` (v1 spec) at `b895a575bf717dade21feba4a49b70b117fea456`.
Contract sha256: `59f75f5bb32786a70842b0887ec801070cefd6796607cce198eb27e1926fcd58`.
Machine report: `/Users/bryanli/Projects/joyfulhouse/homeassistant-dev/microair-bt/.pollux/reports/debate-spec-anthropic.json`.

MODEL requested=claude-fable-5-1[1m] observed=unknown source=unknown

## Position: REVISE

Every protocol fact re-verifies against the decompiled app, not only the wiki: `(m & 0x1C) | 0x01` is how the
app rebuilds the byte and unchecks Default Ramp (`Relearn.java:264-268, 380-394`); completion is a bare
`Success`/`Fail` substring match (`gattCallBack$1.smali:112-142`); offsets, UUIDs, CCCD loop and the absence of
`setWriteType` hold. Service-only, confirm-gated, verify-after-write, no button is the right shape for a mains
compressor controller. Four failure modes are unreasoned.

**Strongest objection.** "Both HIGHs hinge on firmware behaviour the spec defers to first live contact; approve
now, revise after the probe." Rebuttal: the probe is read-only and cannot show what follows an `SMask` write
(D-1), and the slot hazard (D-2) is a design decision, not a measurement.

**Evidence that would change it.** Live read-back showing bit 0 stays set until learning completes (D-1 → LOW);
proof the unit is not connectable in ProgMode (D-2 → LOW); a public static address on the proxy (D-5 dropped);
OEM confirmation that `SMask` is read only at power-up (D-3 default could flip).

## Findings (path `wiki/integration-plan.md`)

- **D-1 HIGH** `:153` — read-back bit 0 == 0 is treated as failure; if firmware self-clears (§11.6) a
  successful relearn is reported failed and the user writes again. Fix: VERIFIED / APPLIED_UNVERIFIED /
  FAILED outcomes, no auto-retry, 10-minute rate limit, `learned_starts` before and after.
- **D-2 HIGH** `:108` — OEM firmware update reboots the unit (`ProgMode` → 5 s) then reconnects; a 60 s poll
  can take the single slot in that gap and hold it 20 s, aborting a flash (`ble-protocol.md:67-70`). Fix:
  polling pause switch, README rule, ReadLive before ReadEEP on polls, disconnect on timeout.
- **D-3 MEDIUM** `:149` — running guard trips on every normal install (unit powered only while calling; OEM
  writes while powered). Say so, add an SCPT-window race check, revisit after live.
- **D-4 MEDIUM** `:81` — all-printable completion check fails on `Success\r\n`; strip terminators.
- **D-5 MEDIUM** `:114` — address-keyed identity; use local name as unique_id, refresh address on discovery.
- **D-6 MEDIUM** `:107` — fail fast without a `BLEDevice`, no backoff, ReadEEP every poll while learning.
- **D-7 MEDIUM** `:124` — add `binary_sensor.<dev>_powered` from advertisement presence.
- **D-8 MEDIUM** `:30` — include Default Ramp via one gated `set_startup_mode` (normal|relearn|default_ramp).
- **D-9 MEDIUM** `:36` — split: PR-1 protocol + probe + tests, then PR-2 component; explicit must-nots.
- **D-10…16 LOW** — no MTU request in bleak; write-site assertion; cancel restores `mask_before`; enum
  unknown handling; drop link after timeout; fuller OEM text; redact probe output.

## Perspectives

- **zombie-integrations:** single-client is a safety property (writes cannot interleave). App scans fail during
  a poll; HA goes `unavailable` three minutes after the app connects; the ProgMode gap is the real hazard (D-2).
- **supply-chain-partner:** a spoofed device only ever receives our three strings; parsers are bounds-checked;
  the model check gates writes. An on-air relay could rewrite bytes and nothing on our side can stop it (no
  link security, verified), but that adds no surface beyond the OEM app. Ours: no automatic writes,
  verify-after-write, rate limit, buffer caps.

COVERAGE: spec; five evidence pages; four research reports; the five cited Java files and the gattCallBack
smali; fogmachine-bt coordinator, client, config flow, manifest; HA 2026.1.3 bluetooth API; bleak-retry-connector 4.6.3.
LIMITS: no live device; no code run; OEM PDFs via the prior-art report's quotes; other seats' reports not read.
FOLLOWUPS: resolve §11.4 via the HA proxy scan, not the laptop; run the PR-1 probe before component work.

---

## Evidence and detail (longer form)

### Verification of the spec's protocol claims against primary source (facts)

| Spec claim | Primary evidence | Result |
|---|---|---|
| `relearn_mask = (m & 0x1C) \| 0x01` is "the exact arithmetic the OEM app performs" (`integration-plan.md:77-80`) | `Relearn.java:380-394` rebuilds the byte from five UI states (bits 0–4); `:264-268` ReLearn-on unchecks Normal and Default Ramp; `:329-346` renders bits from `eep[906]`; bits 5–7 are never reconstructed | **Verified.** Bit 4 (SuperLearn) is preserved, so a unit with 0x10 set will be written 0x11. |
| completion = notification containing `Success`/`Fail` (`:81-86`) | `MainActivityKt$gattCallBack$1.smali:78-82` (`getStringValue(0)`), `:112-142` (`contains` both), packed-switch `:544-552` | **Verified**; the app tolerates arbitrary surrounding bytes and does not require printability. |
| live offsets 2..17 and scaling (`:70-73`, `available-data.md:12-25`) | `Status.java:96-119` | **Verified.** No ÷0 guard in the app (`:109`); the spec's `None when period is 0` is a correct hardening. |
| EEPROM idx 906/907/908, fw idx 10, model idx 2–8 | `MainActivityKt.java:39-42`, `Relearn.java:349-353`, `Update.java:362-380` | **Verified.** |
| UUIDs, CCCD loop, MTU 517, 500 ms settle, 20 s ReadEEP timeout, no `setWriteType` | `MainActivityKt.java:330-338, 423-445, 467-472`; `Connect.java:257-264, 313-338, 417-418`; `Relearn.java:431, 450`; `Status.java:58, 68` | **Verified.** The app writes every descriptor on the notify characteristic, not only 0x2902. |
| "firmware update with SMask bit 2 set may brick" (`ble-protocol.md:68-70`) | `Update.java:1627-1637` (`& 4`) | **Verified**; note the app's own wording is "system may shut down during updating". |
| Flex update branch `ProgMode → 5 s → ChipErase` | `explore-apk-protocol-openai.md:175`, `-anthropic.md:105-106` (both cite `Update.java:528-553`) | Accepted from two agreeing reads; not re-read line by line. |
| No compressor-idle check, no confirm dialog in the app's relearn path | `Relearn.java:250-262` (Send), `:420-457` (dispatch) | **Verified** — the app writes whenever the UI mask differs. |

HA API facts checked against the installed 2026.1.3 (`/Users/bryanli/Projects/joyfulhouse/homeassistant-dev/.venv/lib/python3.14/site-packages/homeassistant`):

- `bluetooth/match.py:35, 384-396`: `local_name` matchers may not contain a wildcard in the first 3 characters; `EasyStart_*` is legal.
- `bluetooth/api.py:106-135, 177-191`: `async_ble_device_from_address`, `async_register_callback`, `async_track_unavailable`, `async_last_service_info` exist; `update_coordinator.py:22-45` derives availability from advertisement presence. Used by D-6/D-7.
- `bluetooth/active_update_coordinator.py:23-60`: advertisement-driven polling with `needs_poll_method` exists as an alternative to a fixed-interval `DataUpdateCoordinator`.
- bleak-retry-connector 4.6.3 `__init__.py:101-102, 407-418`: `MAX_CONNECT_ATTEMPTS = 4`, `BLEAK_TIMEOUT = 20.0`, `establish_connection(..., max_attempts=...)`. A poll against a stale `BLEDevice` can therefore block ~80 s before failing (D-6).
- bleak 3.0.2: `BleakClient` has no public `request_mtu`; `mtu_size` is a property (D-10). *(Inference from API knowledge; not grepped.)*

### Answers to the contract's numbered items

**1. Safety of the relearn design.** The gates are right in kind. Three problems in degree:

- *Verify-after-write ambiguity (D-1).* `integration-plan.md:153` says "assert `startup_mask & 0x01 == 1`, else raise". `ble-protocol.md:109-114` and both APK reads say it is unknown whether firmware acts on bit 0 immediately and self-clears. If it does, the very first successful relearn will be reported as an error. The predictable human response is to run the service again — repeated EEPROM writes on a mains controller, driven by a tool that is lying about the outcome. Fix in the spec: (a) treat `Success` + read-back bit 0 = 1 as **VERIFIED**; (b) `Success` + bit 0 = 0 as **APPLIED_UNVERIFIED** — do not raise; fire the event with `verified: false`; notification says "device acknowledged the write and cleared the flag itself; watch `learned_starts`"; (c) `Fail`/timeout as **FAILED**; (d) never retry automatically; (e) refuse a second relearn within 10 minutes of the last unless `allow_repeat: true`; (f) snapshot `learned_starts` before and after (a drop to 0 is corroborating evidence).
- *Running guard (D-3).* `integration-plan.md:149-151`. `device-easystart-flex.md:23` and `ha-proxy-coverage.md:26-29`: the unit is powered from the A/C control circuit and advertises only while the HVAC calls. Therefore, whenever HA can reach it, the compressor is normally running, in SCPT delay, or faulted. The OEM procedure (`device-easystart-flex.md:38-40`) sends the setting while the unit is powered and *then* powers down; the OEM app has no idle check (`Relearn.java:250-262`). The guard as written blocks the OEM-sanctioned path and permits only two untested windows (SCPT delay with `current_a < 1.0`, or a fault). It is still worth keeping as defence in depth, but the spec must (a) state that on a typical install the guard will trip and that `allow_running: true` reproduces the OEM app's behaviour; (b) in the SCPT window require `scpt_delay_s ≥ 10` so the compressor cannot start between `ReadLive` and `SMask` (the two commands are ~1 s apart); (c) mark the default as "revisit after first live relearn".
- *`cancel_relearn` (D-12).* Justified as an escape hatch because firmware self-clear is unknown, and it is app-equivalent (toggling ReLearn off). But `normal_mask = current & 0x1C` also clears bit 1, and the service is not stated to carry the same `confirm`/running gates. Fix: same gates; restore the persisted `mask_before` when present, else `current & 0x1C`; document that cancel does not restore the previous learned profile and that mid-learning cancel behaviour is unverified. If D-8 is adopted, `cancel_relearn` becomes `set_startup_mode: normal` and this finding is subsumed.
- Persistent notification and no button: correct. Add the OEM details listed in D-15.

**2. Protocol layer.** Structural whitelist: sound; add defence in depth at the one `write_gatt_char` call site (D-11): assert the payload matches `^\{"Cmd": (ReadEEP|ReadLive|SMask=[0-9A-F]{2})\}$` and is 16/17 bytes, so a refactor cannot bypass the enum. Mask math: verified. Completion detection (D-4): the spec's "all printable" rule is stricter than the app and will reject a completion that carries `\r\n` or a NUL terminator — plausible for a firmware that pattern-matches unquoted pseudo-JSON. Fix: strip trailing `\r`, `\n`, `\0` and whitespace, then require ≤ 64 bytes, all remaining bytes in 0x20–0x7E, and the substring; tests for `Success\r\n`, `Success\0`, `"Success"` inside a 20-byte binary chunk (not a completion), and a 100-byte printable chunk containing `Success` (not a completion). Also specify that during `SMask` any binary notification is dropped with a warning (the app does this: smali `:334-339`), and cap buffers (ReadLive 64 B, ReadEEP 1100 + one MTU).

**3. Connection strategy.** Connect-on-demand per 60 s poll is correct for a single-client peripheral that must remain reachable by the OEM app, and matches the proven sibling (`fogmachine-bt/custom_components/fogmachine_bt/const.py:17-32`, `client.py:181-186`). Two differences from fogmachine must be explicit (D-6): **no exponential backoff** — the device is absent most of the day and the whole point of (b) "track progress" is to catch the short powered windows, so the interval must stay at 60 s; and **fail fast** when `async_ble_device_from_address` returns `None` (fogmachine `coordinator.py:106-111`), otherwise `establish_connection` burns up to 4 × 20 s per poll on a stale device. Use `max_attempts=2` for polls, 4 for the service. `ReadEEP` "at most every 10 min" is too slow for `relearn_pending` during learning; read it every poll while `relearn_requested_at` is set and `learned_starts < 5`. Availability after 3 failures is fine; `async_track_unavailable` (advertisement-based) would make "unavailable = unpowered" more honest and is what D-7's `powered` sensor should use. MTU (D-10): `integration-plan.md:92` "request MTU 517" cannot be done through bleak's public API on the HA/ESPHome or CoreBluetooth backends; log `client.mtu_size` and make reassembly MTU-agnostic (a 1100-byte image at MTU 23 is 55 notifications; ReadEEP 20 s still suffices). After any timeout, disconnect rather than reuse the link (D-14): with no sequence numbers, a late completion would resolve the next command.

**4. Entity set.** Mostly right. Missing: `binary_sensor.<dev>_powered` (D-7) from advertisement presence with a `last_seen` attribute — per `device-easystart-flex.md:50-53` a compressor that makes no start attempt is usually power/wiring/thermostat, and "is the EasyStart even powered when the thermostat calls?" is the first question; it works without a GATT connection and without the OEM app being closed. Wrong in detail: HA enum sensors raise if the state is outside `options`, so `UNKNOWN(n)` must map to `unknown` with `raw_state` as an attribute (D-13); `fault` should be status ∈ {1,3,4,5,6,7,8,9} and `None` for unknown codes rather than "problem" for anything not Normal/SCPT. Add attributes: decoded bits on `startup_mask` (relearn, default_ramp, no_pwr_up_delay, start_delay_label, superlearn), `relearn_requested_at` and `learned_starts_at_request` on `relearn_pending`. `total_increasing` on total_starts/total_faults is acceptable even if a relearn resets counters (HA treats a drop as a meter reset).

**5. Scope.** Split (D-9). §11 has seven open items and four of them (completion text, write type, MTU/bonding, address) shape the client. PR-1: `microair/protocol.py`, `microair/client.py`, `scripts/probe.py`, tests — no HA imports, small, reviewable, and it is what unblocks live contact. Run the probe, paste results into the wiki, then PR-2: the component. Implementer must NOT: perform any BLE action from tests/CI; send anything but `ReadEEP`/`ReadLive` from the probe; add `SCPT`/`FMask` builders "for completeness"; accept a raw mask in any service; add a button entity; vendor the decompiled sources into the package; edit wiki fact pages other than pasting probe output; contact any Micro-Air endpoint (`ble-protocol.md:158-163`).

**6. Gaps.** Include Default Ramp (D-8). `device-easystart-flex.md:47-49` and the prior-art report (`search-easystart-prior-art.md:135`) identify it as the OEM's diagnostic for exactly this project's hypothesis; it is reversible (does not erase learning) and its risk profile is the same as relearn's first un-learned start. One gated service `set_startup_mode` with mode ∈ {normal, relearn, default_ramp} → mask `(m & 0x1C) | {0x00, 0x01, 0x02}` replaces both existing services with one gate and one verify path and mirrors the app's three switches. Add `binary_sensor.<dev>_default_ramp` (problem class) so it is not left on, and say in the notification that the OEM wants it used under Micro-Air direction and temporarily. If the plan gate keeps it out of v1, record the reason and leave `build()`'s 0..0x1F range so it is a service-only addition. Open items that could invalidate the design: §11.6 (self-clear) → D-1; §11.4 (address rotation) → D-5, hedge with name-keyed identity and `updates={CONF_ADDRESS}`; §11.3 (bonding) → state explicitly that a bonding requirement blocks v1 rather than being "not handled"; §11.7 (diagnosis) → D-7 and D-8 are the hedges; §11.1 → D-4.

**7. Contradictions.** None that invalidate. Minor: `integration-plan.md:108-109` states "only powered while the A/C calls" as fact where `device-easystart-flex.md:23` marks it as community-reported — keep the ⚠️. `:83` "all printable" vs `ble-transport.md:93-95` "short and mostly printable" — D-4 resolves it. `:156-158` notification omits the OEM's utility-power preference, the 15-second discard rule and the Flex insert's ≥ 8 cycles (`device-easystart-flex.md:29-43`) — D-15. `:180` "print every ADV" conflicts with the redaction practice of `explore-ha-ble-scan.md:26` — D-16. `:20` "reset of the learned start profile" vs OEM "restoring … to factory settings" — wording only; note that other settings may also reset.

### Zombie-integrations: how the design coexists with the OEM app, and what happens when it does not

- Single client is a *safety property*: our `SMask` write and the app's cannot interleave, and the app cannot be mid-write when we read.
- While HA polls (roughly 3–8 s of every 60 s at proxy latency), the app's 5 × 1 s scan (`Connect.java:380-404`) fails with "Cannot find EasyStart"; the user retries and succeeds between polls. Document this.
- While the app is connected, the unit stops advertising; HA's poll fails and after 3 failures entities go `unavailable`; on app disconnect the next poll recovers. If the user relearned from the app, `relearn_pending` turns on with no HA event — document.
- The hazard (D-2): the OEM update path sends `ProgMode`, waits 5 s, and expects to reconnect (`explore-apk-protocol-anthropic.md:105`, `-openai.md:175`). If the bootloader advertises and is connectable, a poll landing in that gap takes the only slot, our `ReadEEP` then waits up to 20 s for a completion the bootloader may never send, and the app's reconnect fails mid-update. The app itself warns that an interrupted update leaves the unit non-functional (`Update.java:1637`). Mitigation belongs in the spec: `switch.<dev>_polling` (or a pause service with auto-resume), README "disable polling before any OEM app session, always before a firmware update", ReadLive-first with a 5 s timeout on polls, disconnect on timeout.

### Supply-chain-partner: a rogue or misbehaving peripheral with the same UUIDs

- The UUIDs are ST sample UUIDs (`device-easystart-flex.md:19`, prior-art C13); the matcher therefore also requires `EasyStart_*`. Both are spoofable; there is no pairing, bonding or checksum to authenticate the peripheral (`ble-transport.md:20-22`, verified in source).
- Containment that is ours: (1) the protocol layer can only ever emit three strings, so the worst outbound consequence of talking to an impostor is that the impostor receives `SMask=xx`; (2) parsers are bounds-checked and must additionally cap buffer growth (D-11) so a chattering peripheral cannot exhaust memory; (3) the relearn/set-mode path refuses to write unless the model string is one of the four known values — spoofable, but then the write goes to the spoofer, not to the compressor; (4) verify-after-write and the rate limit (D-1) bound how often a misbehaving reply can induce writes; (5) no automatic writes exist anywhere.
- What we cannot contain: a relay-style man-in-the-middle can rewrite our bytes on the wire (e.g. `SMask=01` → `ProgMode`). This is inherent to the device's unauthenticated link and is already true for the OEM app; the integration adds no new surface. The spec should say this plainly in the README's safety section rather than imply the whitelist protects against it.

### Coverage (files and ranges read)

- Spec: `wiki/integration-plan.md` 1–214 (all).
- Evidence pages: `wiki/ble-protocol.md` 1–163, `wiki/ble-transport.md` 1–106, `wiki/available-data.md` 1–60, `wiki/device-easystart-flex.md` 1–78, `wiki/ha-proxy-coverage.md` 1–43, `wiki/index.md`, `wiki/sources.md`, `wiki/SCHEMA.md`, `CLAUDE.md`, `README.md`.
- Research: `docs/claude/research/explore-apk-protocol-anthropic.md` 1–226, `explore-apk-protocol-openai.md` 1–190, `search-easystart-prior-art.md` 1–241, `explore-ha-ble-scan.md` 1–54.
- Primary source: `Relearn.java` 140–200, 245–300, 320–470, 470–564; `Status.java` 25–125; `Connect.java` 250–460; `MainActivityKt.java` 30–50, 320–345, 370–480; `Update.java` 355–385, 1620–1640; `MainActivityKt$gattCallBack$1.smali` 60–150, 300–340, 535–560.
- Template: `fogmachine-bt` `manifest.json`, `pyproject.toml`, `__init__.py`, `coordinator.py` 1–302, `config_flow.py` 1–100, `fogmachine/client.py` 1–330, `const.py`, `tests/_import_check.py`, `wiki/ha-proxy-coverage.md`, `CLAUDE.md`.
- Libraries: HA 2026.1.3 `components/bluetooth/{match.py, api.py, __init__.py, active_update_coordinator.py, update_coordinator.py}`, `loader.py:182-200`; bleak-retry-connector 4.6.3 `__init__.py:35-168, 407-418`.

### Limitations

- No live device, no BLE traffic, no code executed; all firmware behaviour claims remain ⚠️ as in the spec.
- OEM manuals were not opened; their content is taken from the quotations in `search-easystart-prior-art.md`.
- bleak's lack of a public `request_mtu` is stated from API knowledge, not grepped in the installed package.
- Other seats' debate reports were not read (independent mode).
