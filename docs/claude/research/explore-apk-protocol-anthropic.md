# EasyStart Flex BLE protocol — independent RE from EasyStart Android v4.3 (lens 2)

STATUS: COMPLETE
Task: explore-apk-protocol-anthropic · run microair-bt-20260910 · contract_sha256 fc5eb4482171c652…
Paths are relative to `microair-bt/`: `J/` = `sources/decompiled/jadx/sources/net/microair/easystart/`, `S/` = `sources/decompiled/apktool/smali/net/microair/easystart/`, `R/` = `sources/decompiled/apktool/res/`.

## Summary (what the human needs)

**Transport.** One primary service `d973f2e0-b19e-11e2-9e96-0800200c9a66` with a notify characteristic `…f2e1…` and a write characteristic `…f2e2…` (`J/MainActivityKt.java:330-338`). Device advertises as `EasyStart_XXXX` (`J/MainActivityKt.java:359`, `J/Connect.java:594,643`). The app requests MTU 517, discovers services, writes the CCCD, waits 500 ms, then sends the first command (`J/Connect.java:260,378,418`; `J/MainActivityKt.java:426-434`). **No pairing, auth, handshake, or checksum exists** in the app layer.

**Wire format.** Commands are plain ASCII pseudo‑JSON strings written to the write characteristic, e.g. `{"Cmd": ReadEEP}` (16 bytes, `7b 22 43 6d 64 22 3a 20 52 65 61 64 45 45 50 7d`). Replies arrive as notifications: zero or more **raw binary chunks** (appended into a buffer) followed by one **text notification containing `Success` or `Fail`**, which the app substring‑matches (`S/MainActivityKt$gattCallBack$1.smali:112-142,282-300`). Buffer selection depends only on app‑side state, not on any framing byte.

**Relearn is one byte.** The ReLearn screen edits the *startup mask* byte at EEPROM‑image index 906 and the *SCPT* byte at 908 (`J/MainActivityKt.java:39-42`; `J/Relearn.java:329-348`). Bit 0 = ReLearn, bit 1 = Use Default Ramp, bit 2 = No Pwr‑Up Delay, bit 3 = SCPT‑label‑is‑"Start Delay (min)" (hidden), bit 4 = SuperLearn (hidden, FW ≥ 29 only). "Normal Operation" = bits 0‑2 all clear (`J/Relearn.java:329-333,380-394`). The app performs relearn by writing `{"Cmd": SMask=<%02X>}` where the value is the whole recomputed byte (`J/Relearn.java:420-457`), waits for a `Success` text notification, then re‑reads the EEPROM image with `{"Cmd": ReadEEP}` and re‑renders the switches from byte 906 (`J/Relearn.java:147-172`). **There is no confirmation dialog on the ReLearn screen** (`S/Relearn.smali` contains no AlertDialog; contrast `J/Faults.java:292-306`, `J/Update.java:1562-1576`). The app does not verify post‑write device behaviour beyond re‑reading the byte.

Minimal relearn sequence for HA (bytes exact, semantics per app):
1. Connect, enable notifications on `…f2e1`, wait ≈500 ms.
2. Write `{"Cmd": ReadEEP}`; collect binary chunks until a `Success` text notification (app timeout 20 s, `J/Connect.java:338`).
3. Compute `new = (eep[906] & 0x1C) | 0x01` (keeps hidden bits 3/4 and No‑Pwr‑Up‑Delay as the app would; clears Use‑Default‑Ramp because the ReLearn switch unchecks it, `J/Relearn.java:264-273`).
4. Write `{"Cmd": SMask=<%02X>}`; expect `Success`.
5. Write `{"Cmd": ReadEEP}` again and confirm `eep[906] & 1 == 1`.

**Faults screen is a *mask*, not a log, and there is no clear‑faults command.** It edits EEPROM index 907 (`FMask`): bit 0 Unexpected Current, 1 Power Interruption, 2 Compressor Stall, 3 Start H/W Failed, 4 Open Overload, 5 Overcurrent, 6 Wiring Issue (`J/Faults.java:318-338,391-397`; `R/values/strings.xml:64-70`). Writing it (`{"Cmd": FMask=%02X}`) **disables/enables fault detection** and is gated by "Are you sure that you want to modify the EasyStart's fault behavior?" (`J/Faults.java:293`). Do not send it.

**Status screen.** Every 5 s the app writes `{"Cmd": ReadLive}` and decodes the binary reply: byte 2 = status code (0 Normal … 9 Wrong Voltage Flt), byte 3 = **Learned Starts (u8, shown raw)**, 4‑5 live current ×0.1 A, 6‑7 line period (freq = 500000/x Hz), 8‑9 last start peak ×0.1 A, 10‑11 SCPT delay seconds, 12‑13 total faults, 14‑17 total starts (all little‑endian) (`J/Status.java:33,58,74,96-119`). The app never interprets Learned Starts beyond display; any semantic is an inference.

**Destructive commands to never send:** `ProgMode`, `ChipErase`, `WrtFsL/H/E=`, `WrtLkB=`, `NormMode`, `OtaPrep`, `OtaBegin`, `OtaWrt`, `OtaAbort`, `OtaEnd`, and any `{"Int"|"Wrt"|"End"|"Ver": …}` string (`J/Update.java:541-1089`). `ProgMode` resets the unit into a bootloader (`J/Update.java:537`). Parameter writes `SMask`, `SCPT`, `FMask` change compressor behaviour; only `SMask` is needed. Safe read‑only set: `{"Cmd": ReadEEP}` and `{"Cmd": ReadLive}`.

Evidence tables and the unverified‑inference list follow the rule.

---

## 1. GATT profile

| Role | UUID | Evidence |
|---|---|---|
| Primary service | `d973f2e0-b19e-11e2-9e96-0800200c9a66` | `J/MainActivityKt.java:330-332` |
| Notify characteristic (device→app) | `d973f2e1-b19e-11e2-9e96-0800200c9a66` | `J/MainActivityKt.java:333-335`, matched at `:423` |
| Write characteristic (app→device) | `d973f2e2-b19e-11e2-9e96-0800200c9a66` | `J/MainActivityKt.java:336-338`, matched at `:445` |
| CCCD | every descriptor on the notify char is written with `ENABLE_NOTIFICATION_VALUE` | `J/MainActivityKt.java:430-435` |

The app never overrides the characteristic write type; Android's default is derived from the characteristic's property bits (inference: WRITE_TYPE_DEFAULT with response if the char advertises WRITE). No `onCharacteristicWrite` callback is implemented — the app fires and forgets, relying on notifications (`S/MainActivityKt$gattCallBack$1.smali` defines only `onCharacteristicChanged`, `onConnectionStateChange`, `onMtuChanged`, `onServicesDiscovered`).

## 2. Discovery, connection, and timing

| Step | Detail | Evidence |
|---|---|---|
| Scan filter | device name contains user‑entered ID, or contains `EasyStart_` | `J/MainActivityKt.java:348-369` |
| Valid IDs | `EasyStart_` + 4 chars (len 14) selects a unit; len 10 or empty = any unit | `J/Connect.java:594,643-650` |
| Scan budget | 5 × 1 s polls, then "Cannot find EasyStart" | `J/Connect.java:380-404` |
| Connect | `connectGatt(ctx, autoConnect=false, cb)` | `J/Connect.java:371` |
| MTU | `requestMtu(517)` immediately on connect | `J/Connect.java:257-264` |
| Service discovery | after `onMtuChanged` | `J/MainActivityKt.java:467-472`, `J/Connect.java:373-379` |
| Post‑discovery delay | 500 ms before first command | `J/Connect.java:417-418` |
| First command | `{"Cmd": ReadEEP}` (EEPROM image read), 20 s timeout | `J/Connect.java:313-338` |
| Success | text notification containing `Success` → state ConnGood, all screens enabled | `J/Connect.java:266-292`, `J/MainActivityKt.java:632-645` |
| Failure | `Fail`/empty → "connected for limited use", only Update enabled (emergency recovery) | `J/Connect.java:269-283,293-309`, `:750-760` |
| Disconnect | app just calls `gatt.close()`; no logout command | `J/Connect.java:444-453` |

Connect‑state constants (resource IDs compared directly): Scan=0, Found=1, Connected=2, MTU=3, ServChar=4, EEPread=5, EEPproc=6, CommErr=7, CommTO=8, ConnGood=9, ConnFail=10, ConnGoodEEPFail=11 (`R/values/integers.xml:3-14`).

## 3. Wire format

### 3.1 Requests
ASCII string, set via `BluetoothGattCharacteristic.setValue(String)` (UTF‑8 bytes, no terminator, no length prefix, no checksum). Grammar observed: `{"<Key>": <Value>}` where Key ∈ {`Cmd`, `Int`, `Wrt`, `End`, `Ver`} and Value is a bare token optionally followed by `=<HEX>`. The value is **not** quoted, so the string is not valid JSON; the firmware evidently pattern‑matches it. Hex payloads are `String.format("%02X")` / `"%04X"` — uppercase (`J/Relearn.java:423-431,436-444`; `J/Faults.java:362-370`; `J/Update.java:698,918`).

Exact bytes for the commands relevant to the goal:

```
{"Cmd": ReadEEP}    16 B  7b 22 43 6d 64 22 3a 20 52 65 61 64 45 45 50 7d
{"Cmd": ReadLive}   17 B  7b 22 43 6d 64 22 3a 20 52 65 61 64 4c 69 76 65 7d
{"Cmd": SMask=01}   17 B  7b 22 43 6d 64 22 3a 20 53 4d 61 73 6b 3d 30 31 7d
{"Cmd": SMask=00}   17 B  7b 22 43 6d 64 22 3a 20 53 4d 61 73 6b 3d 30 30 7d
```

### 3.2 Replies (notifications) — routing in `onCharacteristicChanged`
Evidence: `S/MainActivityKt$gattCallBack$1.smali:64-553`.

1. The notification value is read as a string (`getStringValue(0)`, line 78‑82). If it contains `Success` or `Fail` (lines 112‑142) it is a **completion text** and the active fragment's state machine is posted (packed‑switch at 544‑552: 1 Connect, 2 Status, 3 Relearn, 4 Diagnose, 5 Faults, 6 Update; fragment IDs set in `J/MainActivity.java:171,263,277,291,305,319,333`). For the Connect fragment, if `esCmdState==1` the connect state is forced to EEPproc (lines 252‑261).
2. Otherwise the payload is a **raw binary chunk** and is appended according to `esCmdState` (lines 314‑332):
   - `0` → `esNotifyLiveData` (20‑byte buffer) (lines 482‑500)
   - `1` or `3` → `esNotifyEEPData` (1100‑byte buffer) (lines 421‑439)
   - `4` → `esNotifyBytes` (4‑byte buffer) then Update SM (lines 382‑416) — used only for the OTA tick/tock byte
   - anything else (e.g. `2` = parameter write in flight) → logged "Error: Raw data read during cmd write" and dropped (lines 335‑343)

Consequences: the exact full text of the completion notification is **unknown** (the app only substring‑matches); the binary payload has no framing, so chunk boundaries are MTU‑driven; the app zero‑fills the buffer and resets the length before each read command (`J/Connect.java:321-326`, `J/Status.java:59-64`).

### 3.3 esCmdState values (app‑side, define reply routing)
| Value | Meaning | Set at |
|---|---|---|
| 0 | ReadLive in flight | `J/Status.java:65` |
| 1 | ReadEEP in flight (initial/refresh) | `J/Connect.java:327`, `J/Relearn.java:229`, `J/Faults.java:269`, `J/Diagnose.java:257` |
| 2 | parameter write (SMask/SCPT/FMask) in flight | `J/Relearn.java:447`, `J/Faults.java:360` |
| 3 | post‑write verification ReadEEP in flight | `J/Relearn.java:152`, `J/Faults.java:157` |
| 4 | firmware/OTA command in flight | `J/Update.java:1689,1716,1737` |

## 4. Complete command inventory (every string the app can write)

| # | String written | Screen | Purpose | Reply | Destructive? |
|---|---|---|---|---|---|
| 1 | `{"Cmd": ReadEEP}` | Connect/Relearn/Faults/Diagnose | dump EEPROM image (≤1100 B incl. 2‑byte header) | binary chunks + `Success`/`Fail` | No (read) — `J/Connect.java:320` |
| 2 | `{"Cmd": ReadLive}` | Status (every 5 s) | live telemetry (≤20 B) | binary chunk(s) + `Success`/`Fail` | No (read) — `J/Status.java:58` |
| 3 | `{"Cmd": SMask=%02X}` | Relearn | write startup‑mask byte (EEP idx 906) | `Success`/`Fail` | Parameter write; changes start behaviour — `J/Relearn.java:431` |
| 4 | `{"Cmd": SCPT=%02X}` | Relearn | write SCPT byte (EEP idx 908), UI‑validated 1..250 | `Success`/`Fail` | Parameter write — `J/Relearn.java:444`, range `:313` |
| 5 | `{"Cmd": FMask=%02X}` | Faults | write fault‑enable mask (EEP idx 907), bits 0‑6 | `Success`/`Fail` | Parameter write; can disable protections — `J/Faults.java:370` |
| 6 | `{"Cmd": ProgMode}` | Update | reset into programmer/bootloader ("Resetting EasyStart and entering program mode"; app then waits 5 s) | `Success`/`Fail` | **DESTRUCTIVE** — `J/Update.java:537-551` |
| 7 | `{"Cmd": ChipErase}` | Update | erase MCU flash | text | **DESTRUCTIVE** — `:561` |
| 8 | `{"Cmd": WrtFsL=<hh>}` | Update | write AVR low fuse | text | **DESTRUCTIVE** — `:573` |
| 9 | `{"Cmd": WrtFsH=<hh>}` | Update | write high fuse | text | **DESTRUCTIVE** — `:589` |
| 10 | `{"Cmd": WrtFsE=<hh>}` | Update | write extended fuse | text | **DESTRUCTIVE** — `:605` |
| 11 | `{"Int": FlashBuff}` | Update | init page buffer | text | **DESTRUCTIVE** context — `:632,905` |
| 12 | `{"Wrt": FlashBuff}` | Update | open buffer; followed by **raw binary records** `[len][addrHi][addrLo][data…][2's‑compl chksum]` | text | **DESTRUCTIVE** — `:639,789`, records built `:652-672,825-863` |
| 13 | `{"End": FlashBuff}` | Update | close buffer | text | **DESTRUCTIVE** — `:690,912` |
| 14 | `{"Wrt": EEP=<hhhh>}` | Update | commit buffer to EEPROM (len hex16) | text | **DESTRUCTIVE (overwrites settings)** — `:700` |
| 15 | `{"Ver": EEP=<hhhh>}` | Update | verify EEPROM | text | part of destructive flow — `:710` |
| 16 | `{"Wrt": FlashPg=<hh>}` | Update | commit page to flash | text | **DESTRUCTIVE** — `:920` |
| 17 | `{"Ver": FlashPg=<hh>}` | Update | verify flash page | text | part of destructive flow — `:928` |
| 18 | `{"Cmd": WrtLkB=<hh>}` | Update | write lock bits | text | **DESTRUCTIVE** — `:938` |
| 19 | `{"Cmd": NormMode}` | Update | leave programmer mode, restart ("Compressor restart may be delayed up to 3 minutes") | text | mode change — `:950-956` |
| 20 | `{"Cmd": OtaPrep}` | Update (399 Breeze only) | prepare OTA, unit shuts down 5 s | text | **DESTRUCTIVE** — `:963-978` |
| 21 | `{"Cmd": OtaBegin}` | Update | begin OTA | text | **DESTRUCTIVE** — `:988` |
| 22 | `{"Cmd": OtaWrt}` | Update | then raw 512‑byte packets; device echoes a tick/tock byte per packet | binary byte | **DESTRUCTIVE** — `:1018-1068` |
| 23 | `{"Cmd": OtaAbort}` | Update | abort OTA | text | — `:1078` |
| 24 | `{"Cmd": OtaEnd}` | Update | finish OTA, reboot | text | **DESTRUCTIVE** — `:1089` |

The Update path is additionally gated client‑side: firmware availability requires the device's BLE name (or wildcard `EasyStart_XXXX`) to appear in `http://easystart.microair.net/downloads/registration.txt` with a newer version than EEP byte 10, then `updates.txt` supplies fuses, lock bits and file names (`J/Update.java:1221-1310,1607-1613`). Confirmation text: "Are you sure that you want to update the EasyStart firmware?" (`:1563`). Warning shown when SMask bit 2 (No Pwr‑Up Delay) is set: update may brick the unit (`:1627-1637`).

**Avoidance rule for the HA integration:** whitelist exactly two strings (`ReadEEP`, `ReadLive`) for polling and one templated string (`SMask=`) behind an explicit confirm; reject anything else at the protocol layer. Never write raw binary to `…f2e2`.

## 5. EEPROM image (`ReadEEP` reply) — known offsets

Indices are into the app's receive buffer, i.e. **raw notification stream**; the app skips the first 2 bytes when re‑serialising the dump (`J/Diagnose.java:185,206-207`), so EEPROM address ≈ index − 2 (inference).

| Index | Meaning | Evidence |
|---|---|---|
| 0‑1 | header, never decoded (unknown; possibly length or echo) | skipped in `J/Diagnose.java:185,206` |
| 2‑8 | 7‑char model string: `364ULBT`, `368ULBT`, `398ULBT` (Flex), `399BT` (Breeze) | `J/Update.java:362-380`, `J/Relearn.java:349-358` |
| 10 | firmware version (u8). ≥29 unlocks SuperLearn/StartDelay; 368 @ 26 flagged "may be incorrect" | `J/MainActivityKt.java:40`, `J/Relearn.java:353`, `J/Update.java:381` |
| 906 | **SMask** startup mask (see §7) | `J/MainActivityKt.java:42`, `J/Relearn.java:329-346` |
| 907 | **FMask** fault‑enable mask (see §8) | `J/MainActivityKt.java:39`, `J/Faults.java:391-397` |
| 908 | **SCPT** minutes (u8, UI range 1‑250) | `J/MainActivityKt.java:41`, `J/Relearn.java:313-316,348` |

Buffer is 1100 bytes; anything past that would overflow `copyInto` (app assumption that the dump is ≤1100 B).

## 6. Live data (`ReadLive` reply) and status codes

Buffer 20 bytes; all multi‑byte fields little‑endian (`J/Status.java:96-119`).

| Bytes | Field | Decode |
|---|---|---|
| 0‑1 | unknown header (never read) | — |
| 2 | system state code | table below; >9 → "Not Defined" (`:96-100`, `R/values/strings.xml:100`) |
| 3 | **Learned Starts** | u8, displayed raw (`:101`) |
| 4‑5 | live current | u16 / 10 A (`:104`) |
| 6‑7 | line period | freq Hz = 500000 / u16 (`:109`) |
| 8‑9 | last start peak | u16 / 10 A (`:114`) |
| 10‑11 | SCPT delay | u16 seconds (`:117`) |
| 12‑13 | total faults | u16 (`:118`) |
| 14‑17 | total starts | u32 (`:119`) |

Status codes (`J/Status.java:33`): 0 Normal · 1 Unexpctd Curr Flt · 2 Short Cycle Delay · 3 Pwr Intrrptn Fault · 4 Stall Fault · 5 Stuck SR Fault · 6 Open Ovrld Fault · 7 Overcurrent Fault · 8 Bad Wiring Fault · 9 Wrong Voltage Flt.

Polling: `Timer.scheduleAtFixedRate(…, 100 ms, 5000 ms)`, guarded by an in‑progress flag so a missed reply stalls polling until the next `Success` (`J/Status.java:48-74,124`). Screen text "Refreshes automatically every 5 sec" (`R/values/strings.xml:90`).

## 7. ReLearn screen — step by step as the app performs it

Screen title "ReLearn / Power‑Up" (`R/values/strings.xml:78`); controls: Refresh button, switches Normal Operation / ReLearn / Use Default Ramp / No Pwr‑Up Delay, SCPT text box, Send button (`R/layout/fragment_relearn.xml` ids `switchNormalOperation`, `switchRelearn`, `switchUseDefaultRamp`, `switchNoPwrUpDelay`, `etSCPT`, `buttonRelearnSend`).

Preconditions: connect state ConnGood (button bar enabled only then, `J/MainActivityKt.java:632-645`) and `eepDataState==2` (EEPROM image valid) — otherwise all switches are disabled (`J/Relearn.java:324,364-370`).

Startup‑mask byte (EEP idx 906) bit semantics (`J/Relearn.java:329-346,380-394`):

| Bit | Value | UI | Notes |
|---|---|---|---|
| 0 | 0x01 | **ReLearn** switch | the relearn request |
| 1 | 0x02 | Use Default Ramp | mutually exclusive with ReLearn in UI (`:264-284`) |
| 2 | 0x04 | No Pwr‑Up Delay | also triggers the "may shut down during update" warning (`J/Update.java:1627`) |
| 3 | 0x08 | SCPT label → "Start Delay (min)" | hidden; toggled by 3 s long‑press on the SCPT label (`:506-531,546-557`) |
| 4 | 0x10 | ReLearn label → "SuperLearn" | hidden; 3 s long‑press on the ReLearn label, only if FW ≥ 29 and model ≠ 399BT (`:353-358,533-544`) |
| — | 0x00 (bits 0‑2) | Normal Operation | `(mask & 7)==0` (`:329`) |

Flow:
1. Screen opens; `updateScreen()` renders switches from `eep[906]`, SCPT from `eep[908]` (`:66,323-348`). No BLE traffic on open.
2. (Optional) Refresh → `esCmdState=1`, write `{"Cmd": ReadEEP}` (`:221-248`).
3. User toggles ReLearn ON → NormalOperation and UseDefaultRamp forced OFF (`:264-273`); `checkForChanges()` recomputes `startupMask` from the switches and the two hidden label states and enables Send only if it differs from `eep[906]` (`:373-418`).
4. Send (**no confirmation dialog**) → progress bar on, button bar disabled, `dispatchChanges()` (`:250-262`).
5. `dispatchChanges()` writes `{"Cmd": SMask=%02X}` with `esCmdState=2` (`:420-457`). If SCPT also changed it is sent *after* SMask succeeds, as a second `{"Cmd": SCPT=%02X}` write (`:147-150,433-446`).
6. On `Success` with `esCmdState==2` and nothing pending: `esCmdState=3`, write `{"Cmd": ReadEEP}` (`:152-171`).
7. On `Success` with `esCmdState==3`: re‑render from the fresh image, alert "SUCCESS — Settings written to EasyStart" (`:173-190`).
8. On `Fail` (or a local write failure, which the app simulates by setting the string to "Failure"): alert "Unable to Write Settings to EasyStart. Please try refreshing." (`:194-218`).

Timing: no deliberate delays between steps; each step waits on the notification. Post‑relearn device state: the app only shows whatever `eep[906]` now reads; it does **not** observe learning progress. Inference (unverified): firmware clears bit 0 itself once a relearn completes, and Learned Starts on the Status screen reflects progress.

Bytes for the common case (starting from Normal Operation with hidden bits clear): `{"Cmd": SMask=01}`.

## 8. Faults screen ("Fault Control")

Title `faults_fragment_title` = "Fault Control" (`R/values/strings.xml:71`). Seven switches map 1:1 to FMask bits (`J/Faults.java:318-338` for write, `:391-397` for read); labels `R/values/strings.xml:64-70`:

| Bit | Label | Switch id |
|---|---|---|
| 0 | Unexpected Current | switchUnexpectedCurrentFault |
| 1 | Power Interruption | switchPowerInterruptionFault |
| 2 | Compressor Stall | switchCompressorStallFault |
| 3 | Start H/W Failed | switchStuckStartRelayFault |
| 4 | Open Overload | switchOpenOverloadFault |
| 5 | Overcurrent | switchOvercurrentFault |
| 6 | Wiring Issue | switchNoStartWindingZCFault |

Write path mirrors Relearn (`FMask=` → `Success` → `ReadEEP` verify) with a CONFIRM dialog first (`:290-313,352-380`). **The app has no "clear faults"/"reset counters" command; fault history is only the live counters (total faults, status code).** Faults are therefore *enables* (which detections are armed), not a log.

## 9. Status screen — Learned Starts

Label "Learned Starts:" (`R/values/strings.xml:96`) bound to `tvLearnedStarts` = live byte 3 (`J/Status.java:101`). It is one unsigned byte, displayed without scaling or interpretation; no other code path reads it. Whether it counts down, up, or is compared to a target is not derivable from the app.

## 10. Diagnose screen (network, not BLE)
Refresh sends `ReadEEP` (`J/Diagnose.java:257-276`). "Send Data to Micro‑Air" re‑encodes the EEPROM dump (skipping 2 header bytes) as Intel‑HEX and POSTs it with name/e‑mail/phone/BLE ID to `http://easystart.microair.net/upload.php` over plain HTTP (`:183-221,414-446`). Not needed for HA; noted for privacy.

## 11. Unverified inferences (explicit)
- Write type (with/without response) — app uses Android default; depends on characteristic properties.
- Exact completion‑notification text; app only checks for substrings `Success` / `Fail`.
- Meaning of bytes 0‑1 in both replies; that EEPROM address = index − 2.
- Firmware clears SMask bit 0 after relearn; Learned Starts semantics.
- Whether the device accepts `SMask` while the compressor is running (app has no interlock; CLAUDE.md safety rule applies).
- Whether SCPT (EEP idx 908, "minutes") and live bytes 10‑11 ("seconds") are the same quantity in different units.

## 12. Coverage
Read fully: `J/MainActivityKt.java`, `J/MainActivity.java`, `J/Connect.java`, `J/Relearn.java`, `J/Status.java`, `J/Faults.java`, `J/Diagnose.java`, `J/Update.java` lines 300‑1776, `S/MainActivityKt$gattCallBack$1.smali`, `R/values/strings.xml`, `R/values/integers.xml`, layout id/text attributes for connect/status/relearn/faults, `BuildConfig.java`. Skimmed: `J/Update.java` lines 1‑300 (fields/enums), `S/Relearn.smali` (string constants only, to confirm absence of dialogs), `J/R.java` integer block. Not read: databinding classes, other smali files (jadx output for those classes was clean and complete), wiki/ and any prior analyses (deliberately, for independence).
