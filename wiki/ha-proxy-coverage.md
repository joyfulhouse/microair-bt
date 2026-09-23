# HA Bluetooth-proxy coverage of the EasyStart

Purpose: which HA Bluetooth proxies hear the unit, at what RSSI, and which
should be used for GATT connections.
Status: **verified live (2026-09-12)** — both units heard, connected and read over ESPHome active proxies; links marginal.

Source: `docs/claude/research/explore-ha-ble-scan.md` + `ble-scan-dump.json`
(2026-09-10, passive `bluetooth/subscribe_advertisements` over the HA
websocket at `<ha-host>`, 90 s + 180 s windows). No GATT connection
was attempted.

## Result (2026-09-10)

- Nearest proxy: the ESPHome AIOsense node in the room adjacent to the condenser,
  ESPHome `bluetooth_proxy: active: true`, registered in HA as a
  **connectable** remote scanner.
- **No advertisement matched** any of: name containing `EasyStart` / `MicroAir`,
  name starting `ES`, or service UUID `d973f2e0-b19e-11e2-9e96-0800200c9a66` —
  across 246 events / 219 distinct addresses on all proxies.
- Devices that proxy did hear (for RF sanity): `Govee_H6093_9E58` −47 dBm,
  `PRP1-RD_2FF9` −70 dBm, `SPU-00009694-V002` −70 dBm, plus unnamed devices
  down to −97 dBm — so the proxy is alive and hearing weak signals.

## Result (2026-09-11/12, live over HA proxies)

- Two EasyStarts exist, one per A/C system. Each advertises **only while its
  A/C is calling for cooling**, which is why the 2026-09-10 idle-A/C scan heard
  nothing.
- Advertisements arrive at **−75 to −94 dBm**; HA's connection scorer picks a
  different proxy from poll to poll (whichever heard the last advert best).
  The proxy in the room nearest each condenser is not always the winner.
- GATT connects succeed at MTU 23 on the first or second attempt. The **~1 KB
  `ReadEEP` reply (≈50 notification frames) drops a frame often enough that a
  poll depending on it fails most of the time** (`EEPROM length mismatch:
  expected 1023 bytes, got 1003`); the 1–4-frame `ReadLive` reply is reliable.
  This drove the v0.2.2 design: poll `ReadLive` only, cache the EEPROM image.
- Discovery-flow setup (which needs one complete `ReadEEP`) typically needs
  two or three **Configure** attempts on these links.

## Likely explanations for a silent scan (historical, resolved)

1. The unit was **unpowered** — the EasyStart draws control power from the A/C
   and community reports say it advertises only while the HVAC is calling
   ([device-easystart-flex](device-easystart-flex.md)). If the thermostat was
   satisfied / the system was off, nothing would advertise.
2. The OEM app (or another client) was **connected**, so it stopped advertising.
3. **Range** — reported usable range is ~3–6 ft; the outdoor condenser may be
   too far from the nearest indoor proxy.
4. Advertises **without a name or service UUID** in the ADV packet (name only
   in the scan response, which passive subscription may still surface).

## Next steps

1. Confirm the A/C is calling for cooling (or force a call) and the phone app is
   closed, then re-run the passive scan (`explore-ha-ble-scan` procedure).
2. If still absent, place a proxy (or a laptop running the read-only
   `scripts/probe.py`) near the condenser.
3. Record here: address, address type, name, RSSI per proxy, connectable flag,
   raw ADV/scan-response bytes.

## Host-adapter probe (2026-09-10, outside HA)

Read-only `scripts/probe.py` runs from a Linux host adapter (BlueZ `hci0`)
near the condenser did connect and read the unit: `EasyStart_88CD`, model
`398ULBT`, firmware 37, `startup_mask 0x00`, status `NORMAL`. This confirms
the GATT read path and the decoders, but not the HA proxy path — the unit has
still not been captured advertising on an ESPHome proxy. A single `SMask`
write from that host returned BlueZ `Operation Not Authorized` and readbacks
never changed; see [index](index.md). Host adapters are a diagnostic tool only:
the production connection is HA's nearest ESPHome active proxy.

## Write path over the proxy mesh (2026-09-21, `EasyStart_88CD`)

First live write, `set_startup_mode relearn` (v0.4.0), compressor running at
8 A, live mode temporarily off, `allow_running` temporarily on:

| Attempt | Time | Outcome | Cause |
|---|---|---|---|
| 1–2 | 12:07:58, 12:09:31 | REJECTED (nothing sent) | preflight `ReadEEP` 1003 of 1023 bytes — one dropped 20-byte frame |
| 3 | 12:09:47 | ACKNOWLEDGED-BUT-UNVERIFIED | `SMask=01` → `Success`; readback `ReadEEP` truncated |
| 4 | 12:10:07 | **STORED** `0x01` | full readback matched |

Same link that dropped frames during live-mode polling minutes earlier
(`Peripheral disconnected`, GATT error 133, `READ_LIVE exceeded 10s`). The
service never retries on its own; each attempt above was a separate operator
call. A closer proxy would remove most of this friction.

## ⚠️ Powered flag stays on while idle (2026-09-21..23, unresolved)

`binary_sensor.<unit>_powered` is driven by HA's advertisement tracking. It
went off about 4.5 min after a cooling call ended during the 2026-09-21 test
(`88CD`, connect-per-poll mode). Since then it has stayed **on for hours of
idle time** on both units:

| Unit | Mode | On from → until (UTC) | Cooling during that window |
|---|---|---|---|
| `88CD` | live | 09-21 19:17 → 09-22 11:22 (core restart) | one 5-min call, 22:55–23:00 |
| `DC5A` | connect-per-poll | 09-21 22:29 → 09-22 11:22 (core restart) | frequent cycling, gaps of up to ~3 h |
| `DC5A` | connect-per-poll | 09-22 16:15 → still on 09-23 | cycling; telemetry unavailable since 09-23 09:19 |

Telemetry entities go unavailable during these windows because polls fail, so
the integration degrades safely, but "Powered" is not a reliable "A/C is
calling" signal. Either some installs keep the EasyStart powered (and
advertising) while idle, or HA's presence tracking for these adverts is stale.
Next step: capture raw advertisements during an idle window.
