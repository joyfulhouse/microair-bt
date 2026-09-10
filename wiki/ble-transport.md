# BLE transport — GATT, connect sequence, notifications

Purpose: how bytes get to/from an EasyStart Flex over BLE (below the command layer).
Status: **verified from source** (two independent decompile reads agree); live GATT
properties (write type, exact descriptor set, real MTU) are ⚠️ unverified.

Command strings and reply decoding live on [ble-protocol](ble-protocol.md).
Path shorthand: `J/` = `sources/decompiled/jadx/sources/net/microair/easystart/`,
`S/` = `sources/decompiled/apktool/smali/net/microair/easystart/`.

## GATT profile

| Role | UUID | Evidence |
|---|---|---|
| Primary service | `d973f2e0-b19e-11e2-9e96-0800200c9a66` | `J/MainActivityKt.java:330-332` |
| Notify characteristic (device → app) | `d973f2e1-b19e-11e2-9e96-0800200c9a66` | `J/MainActivityKt.java:333-335`, matched `:423` |
| Write characteristic (app → device) | `d973f2e2-b19e-11e2-9e96-0800200c9a66` | `J/MainActivityKt.java:336-338`, matched `:445` |
| CCCD | every descriptor on the notify char is written with `ENABLE_NOTIFICATION_VALUE` (`01 00`); no explicit `0x2902` selection, no indications | `J/MainActivityKt.java:430-435` |

**No pairing, bonding, application password, challenge, or checksum exists in
the app** (`J/Connect.java:349,406`, `J/MainActivityKt.java:378`, manifest). This
does not prove the peripheral never requires link encryption — ⚠️ unverified live.

**Write type**: the app calls the legacy one-arg `writeCharacteristic()` after
`setValue(String)` and never calls `setWriteType`, so Android's default for the
characteristic's property bits applies (`J/Relearn.java:431,450`,
`J/Status.java:58`). With-response vs without-response is ⚠️ unverified; an HA
client should use whatever `bleak` reports for the characteristic and prefer
write-with-response if both are offered.

## Advertising / discovery

- App scans **unfiltered** (`startScan(callback)`), then accepts a device whose
  name contains the user-entered ID or the case-sensitive substring `EasyStart_`
  (`J/Connect.java:468`, `S/MainActivityKt$scanCallBack$1.smali:86-160`). No
  service-UUID, manufacturer-data, RSSI or MAC filter.
- App-side ID validation: `EasyStart_` + 4 chars (length 14) selects one unit;
  length 10 or empty = any unit (`J/Connect.java:594,643-650`). Real advertised
  name/suffix alphabet is ⚠️ unverified — see [ha-proxy-coverage](ha-proxy-coverage.md).
- Scan budget in app: 5 × 1 s polls, then "Cannot find EasyStart" (`J/Connect.java:380-404`).

## Connect sequence (as the app does it)

```
stop scan
→ connectGatt(ctx, autoConnect=false, cb)            J/Connect.java:371
→ onConnectionStateChange(connected)
→ requestMtu(517)                                   J/Connect.java:257-264
→ onMtuChanged (result ignored; advances regardless) J/MainActivityKt.java:466-472
→ discoverServices()                                J/Connect.java:373-379
→ find …f2e1 / …f2e2, enable notifications (CCCD)   J/MainActivityKt.java:423-445
→ sleep 500 ms                                      J/Connect.java:417-418
→ write {"Cmd": ReadEEP}, 20 s timeout              J/Connect.java:313-338
→ text notification containing "Success" ⇒ ConnGood (all screens enabled)
   "Fail"/timeout ⇒ "connected for limited use" (only Update enabled)
```

Disconnect is a bare `gatt.close()`; there is no logout/goodbye command
(`J/Connect.java:444-453`).

App connect-state constants (for reading the decompile): Scan=0, Found=1,
Connected=2, MTU=3, ServChar=4, EEPread=5, EEPproc=6, CommErr=7, CommTO=8,
ConnGood=9, ConnFail=10, ConnGoodEEPFail=11 (`res/values/integers.xml:3-14`).

## Notification handling (the receive side)

Authoritative implementation is smali (jadx dropped the method):
`S/MainActivityKt$gattCallBack$1.smali:64-553`.

1. Each notification value is first decoded as a string. If it **contains**
   the case-sensitive substring `Success` or `Fail`, it is a **completion text**:
   the active fragment's state machine is signalled and the bytes are *not*
   appended to any buffer (`:78-142`, dispatch packed-switch `:544-552`).
2. Otherwise the payload is a **raw binary chunk**, appended to a buffer chosen
   purely by the app-side `esCmdState` (`:314-332`):
   - `0` → live-data buffer (20 B) — `ReadLive` reply
   - `1` or `3` → EEPROM buffer (1100 B) — `ReadEEP` reply
   - `4` → 4-byte OTA tick/tock buffer (Update only)
   - anything else (e.g. `2` = parameter write in flight) → logged
     "Error: Raw data read during cmd write" and dropped.

Consequences for an HA client:

- There is **no framing**: no length prefix, opcode echo, sequence number or
  CRC. Chunk boundaries are MTU-driven; concatenate chunks in order until the
  completion text arrives. The app zero-fills and resets the buffer before each
  read command (`J/Connect.java:321-326`, `J/Status.java:59-64`).
- The **exact completion text is unknown** (only the substrings are matched)
  — ⚠️ unverified; log it verbatim on first live contact.
- The first two bytes of both binary replies are never decoded by the app —
  ⚠️ unverified meaning (possibly a length/echo header). Field offsets on
  [available-data](available-data.md) are *buffer* offsets including them.
- A binary chunk that happened to contain ASCII `Success`/`Fail` would be
  misrouted by the app; a robust client should only treat a notification as
  completion when it is short and mostly printable.
- Only one command may be in flight; the app's Status poller uses an
  in-progress flag so a missed reply stalls polling rather than overlapping.

## Timing constants

| What | Value | Evidence |
|---|---|---|
| Post-discovery settle | 500 ms | `J/Connect.java:417-418` |
| Initial `ReadEEP` timeout | 20 s | `J/Connect.java:338` |
| Status poll period | 100 ms initial, then 5000 ms | `J/Status.java:48-74` |
| MTU request | 517 | `J/Connect.java:257-264` |
