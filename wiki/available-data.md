# Available data — what the device exposes over BLE

Purpose: every field the EasyStart app decodes, with offsets, units and scaling,
so the integration can map them to HA entities.
Status: **verified from source** (`J/Status.java:96-119`, `J/Relearn.java`,
`J/Faults.java`); real values ⚠️ unverified until a live read.

Where the bytes come from: [ble-protocol](ble-protocol.md). Offsets are into
the concatenated notification buffer (they include the 2 opaque prefix bytes).
All multi-byte integers are **little-endian, unsigned**.

## `ReadLive` reply (20-byte buffer) — poll every 5 s

| Bytes | Field | Decode | HA entity idea |
|---|---|---|---|
| 0–1 | opaque prefix | not decoded | — |
| 2 | **System state** | enum below | `sensor` (enum) |
| 3 | **Learned Starts** | u8, raw | `sensor` — the only relearn-progress signal |
| 4–5 | Live current | u16 / 10 → A (1 decimal) | `sensor` (current, A) |
| 6–7 | Line period | `500000 / u16` → Hz (1 decimal; guard ÷0) | `sensor` (frequency, Hz) |
| 8–9 | Last start peak | u16 / 10 → A | `sensor` (current, A) |
| 10–11 | SCPT delay remaining | u16 seconds | `sensor` (duration, s) |
| 12–13 | Total faults | u16 | `sensor` (total_increasing) |
| 14–17 | Total starts | u32 | `sensor` (total_increasing) |
| 18–19 | not decoded | — | — |

### System state enum (`J/Status.java:33`)

| Code | App text | Meaning |
|---|---|---|
| 0 | Normal | — |
| 1 | Unexpctd Curr Flt | unexpected current fault |
| 2 | Short Cycle Delay | SCPT lockout, *not* a fault |
| 3 | Pwr Intrrptn Fault | power interruption |
| 4 | Stall Fault | compressor stall |
| 5 | Stuck SR Fault | stuck start relay / start H/W failed |
| 6 | Open Ovrld Fault | open overload |
| 7 | Overcurrent Fault | |
| 8 | Bad Wiring Fault | |
| 9 | Wrong Voltage Flt | (no matching FMask bit) |
| >9 | Not Defined | |

Note this enum is **not** the same numbering as the FMask bits.

## `ReadEEP` reply (≤1100-byte buffer) — read on connect and after writes

| Idx | Field | Decode | HA entity idea |
|---|---|---|---|
| 2–8 | Model string | ASCII, e.g. `398ULBT` = Flex | device info `model` |
| 10 | Firmware version | u8 | device info `sw_version` |
| 906 | Startup mask (SMask) | bitfield, see [ble-protocol](ble-protocol.md) | `binary_sensor` relearn-pending (bit 0); diagnostic `sensor` raw mask |
| 907 | Fault-enable mask (FMask) | bitfield bits 0–6 | diagnostic `sensor` (read-only) |
| 908 | SCPT | u8 minutes (1–250) | diagnostic `sensor` (read-only in v1) |

## Not available over BLE (per the app)

- Fault **history/log** — only the live state code and the total-faults counter.
- Any clear-faults, reset-counters or factory-reset operation.
- Learning progress beyond the single `Learned Starts` byte.
- Temperatures, voltage, compressor profile or start waveforms (opaque EEPROM).
