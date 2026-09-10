# BLE protocol — command strings, replies, relearn semantics (authoritative)

Purpose: the complete application-layer wire protocol of the EasyStart Flex
(and siblings 364/368/399), as implemented by the EasyStart Android app v4.3
(build 23).
Status: **verified from source** — two independent decompile reads
(`docs/claude/research/explore-apk-protocol-openai.md`,
`…-anthropic.md`) agree on all 24 command forms and every byte offset. Firmware
*behaviour* after a write is ⚠️ unverified until a live test.

Transport (UUIDs, connect sequence, chunking) is on [ble-transport](ble-transport.md).
Decoded telemetry fields are on [available-data](available-data.md).
Path shorthand: `J/` = `sources/decompiled/jadx/sources/net/microair/easystart/`.

## Request format

Plain ASCII, written to `…f2e2` as one `setValue(String)` + write. Grammar:

```
{"<Key>": <Token>[=<HEX>]}
```

- `Key` ∈ `Cmd` | `Int` | `Wrt` | `End` | `Ver` (only `Cmd` matters outside firmware update).
- The value token is **unquoted**, so the string is *not* valid JSON — firmware pattern-matches it.
- Hex arguments are uppercase `%02X` / `%04X` (`J/Relearn.java:423-444`, `J/Faults.java:362-370`).
- No terminator, length prefix, sequence number or checksum.

Exact bytes for the three strings an HA integration needs:

```
{"Cmd": ReadEEP}    16 B  7B 22 43 6D 64 22 3A 20 52 65 61 64 45 45 50 7D
{"Cmd": ReadLive}   17 B  7B 22 43 6D 64 22 3A 20 52 65 61 64 4C 69 76 65 7D
{"Cmd": SMask=01}   17 B  7B 22 43 6D 64 22 3A 20 53 4D 61 73 6B 3D 30 31 7D
```

## Reply format

Zero or more **raw binary notifications** (concatenate in order), then one
**text notification containing `Success` or `Fail`**. Parameter writes
(`SMask`/`SCPT`/`FMask`) return only the completion text. See
[ble-transport](ble-transport.md) for routing details and the ⚠️ unknown
2-byte prefix on binary replies.

## Command inventory (all 24 strings the app can ever write)

### Normal operation (5)

| # | String | Screen | Effect | Reply | Class |
|---|---|---|---|---|---|
| 1 | `{"Cmd": ReadEEP}` | Connect / Relearn / Faults / Diagnose | dump EEPROM image (≤1100 B buffer) | binary + text | **read — SAFE** (`J/Connect.java:320`) |
| 2 | `{"Cmd": ReadLive}` | Status, every 5 s | live telemetry (≤20 B buffer) | binary + text | **read — SAFE** (`J/Status.java:58`) |
| 3 | `{"Cmd": SMask=HH}` | Relearn | write **startup mask** byte (EEP buffer idx 906) | text | parameter write — the relearn (`J/Relearn.java:431`) |
| 4 | `{"Cmd": SCPT=HH}` | Relearn | write SCPT / start-delay byte (idx 908), UI range 1–250 min | text | parameter write (`J/Relearn.java:444`) |
| 5 | `{"Cmd": FMask=HH}` | Faults | write **fault-enable mask** (idx 907), bits 0–6 | text | parameter write, confirm-gated in app; can disable protections (`J/Faults.java:370`) |

### Firmware update path (19) — NEVER SEND

`{"Cmd": ProgMode}` (reset into bootloader), `{"Cmd": ChipErase}`,
`{"Cmd": WrtFsL=HH}` / `WrtFsH=HH` / `WrtFsE=HH` (AVR fuses),
`{"Int": FlashBuff}`, `{"Wrt": FlashBuff}` (followed by raw binary records
`[len][addrHi][addrLo][data…][2's-compl chksum]`), `{"End": FlashBuff}`,
`{"Wrt": EEP=HHHH}`, `{"Ver": EEP=HHHH}`, `{"Wrt": FlashPg=HH}`,
`{"Ver": FlashPg=HH}`, `{"Cmd": WrtLkB=HH}`, `{"Cmd": NormMode}`,
`{"Cmd": OtaPrep}`, `OtaBegin`, `OtaWrt` (then raw 512-byte packets), `OtaAbort`,
`OtaEnd` (`J/Update.java:528-1092`).

The Flex (model `398ULBT`) update branch is `ProgMode → 5 s → ChipErase → …`;
a stray `ProgMode` alone reboots the unit into the programmer. The app also
notes that a firmware update with SMask bit 2 set may brick the unit
(`J/Update.java:1627-1637`).

**Protocol-layer rule for the integration:** whitelist exactly `ReadEEP`,
`ReadLive` and the templated `SMask=HH`; reject every other string and any raw
binary write to `…f2e2` at the lowest layer, with a test proving it.

## Startup mask (`SMask`, EEP buffer index 906) — the relearn

Bit semantics (`J/Relearn.java:329-346,380-394`):

| Bit | Value | App control | Notes |
|---|---|---|---|
| 0 | `0x01` | **ReLearn** switch | *the relearn request* |
| 1 | `0x02` | Use Default Ramp | UI makes it mutually exclusive with ReLearn (`:264-284`) |
| 2 | `0x04` | No Pwr-Up Delay | preserved by ReLearn toggle |
| 3 | `0x08` | hidden: SCPT label → "Start Delay (min)" | 3 s long-press on label; preserved |
| 4 | `0x10` | hidden: ReLearn label → "SuperLearn" | FW ≥ 29 and model ≠ 399BT; preserved by toggle, cleared if ordinary ReLearn is chosen deliberately |
| 5–7 | — | not represented; app reconstruction drops them | meaning unknown |
| — | bits 0–2 all clear | "Normal Operation" | `(mask & 7) == 0` |

### How the app performs a relearn (`J/Relearn.java:147-190,250-262,420-457`)

Preconditions in the app: connection state ConnGood and a valid EEPROM image
(`eepDataState == 2`). **No compressor-idle check, no confirmation dialog, no
reboot command, no automatic power cycle.**

1. (Optional) Refresh: `{"Cmd": ReadEEP}` → `Success`.
2. Compute `new = (eep[906] & 0x1C) | 0x01` — set bit 0, clear bit 1, keep
   bits 2–4. For a unit in Normal Operation with hidden bits clear this is `01`.
3. Write `{"Cmd": SMask=<%02X>}` → wait for `Success` (`Fail` ⇒ "Unable to
   Write Settings to EasyStart. Please try refreshing.").
4. If SCPT also changed: `{"Cmd": SCPT=%02X}` → `Success` (not needed for relearn).
5. Write `{"Cmd": ReadEEP}` → `Success`; re-render from the fresh image and show
   "SUCCESS — Settings written to EasyStart".
6. The app never compares the read-back byte with the requested value; a
   robust client should assert `eep[906] & 0x01 == 1` after step 5.

There are no deliberate delays between steps; each waits on the notification.

### What the app does NOT tell us (⚠️ unverified, resolve live)

- Whether firmware acts on bit 0 immediately or at the next compressor start.
- Whether bit 0 self-clears after a completed relearn, and how many starts
  the relearn takes (the Status screen's **Learned Starts** byte is the only
  progress signal; see [available-data](available-data.md)).
- Whether a power cycle is needed, and whether the device accepts `SMask`
  while the compressor is running.
- Whether a stale learned profile is actually what keeps this compressor from
  starting (the diagnosis itself is unverified).

`SMask=00` merely selects "Normal Operation"; it is **not** a factory reset.
`SMask=11` = ReLearn + SuperLearn (hidden mode).

## Fault-enable mask (`FMask`, EEP buffer index 907)

The "Fault Control" screen is a set of **enables**, not a fault log. Bits
(`J/Faults.java:318-338,391-397`; `res/values/strings.xml:64-70`):

| Bit | Label |
|---|---|
| 0 | Unexpected Current |
| 1 | Power Interruption |
| 2 | Compressor Stall |
| 3 | Start H/W Failed (stuck start relay) |
| 4 | Open Overload |
| 5 | Overcurrent |
| 6 | Wiring Issue (no start-winding zero crossing) |

Set bit = switch checked; polarity "checked = protection enabled" is plausible
but ⚠️ unverified. **There is no clear-faults / reset-counters / factory-reset
command anywhere in the app.** `FMask=00` would *disable* all detections, not
clear history — do not send it. The integration exposes `FMask` read-only.

## EEPROM image (`ReadEEP` reply) — known buffer offsets

| Buffer idx | Meaning | Evidence |
|---|---|---|
| 0–1 | opaque prefix (skipped when the app re-serialises the dump) | `J/Diagnose.java:185,206` |
| 2–8 | 7-char model string: `364ULBT`, `368ULBT`, `398ULBT` (**Flex**), `399BT` (Breeze) | `J/Update.java:362-380` |
| 10 | firmware version, unsigned int (≥ 29 unlocks hidden modes) | `J/MainActivityKt.java:40`, `J/Relearn.java:353` |
| 906 | SMask (startup mask) | `J/MainActivityKt.java:42` |
| 907 | FMask (fault-enable mask) | `J/MainActivityKt.java:39` |
| 908 | SCPT minutes (u8) | `J/MainActivityKt.java:41` |

Buffer idx − 2 = the address the app exports in its Intel-HEX diagnostic dump
(so SMask = exported address 904) — derived, ⚠️ unverified as a physical EEPROM
address. All other bytes are opaque to the app.

## Non-BLE side channels (for awareness only)

Diagnose → "Send Data to Micro-Air" POSTs the EEPROM dump (as Intel HEX) plus
name/e-mail/phone/BLE-ID to `http://easystart.microair.net/upload.php` over
plain HTTP; Update checks `…/downloads/registration.txt` and `updates.txt`.
Neither is used by the integration.
