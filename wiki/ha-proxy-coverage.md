# HA Bluetooth-proxy coverage of the EasyStart

Purpose: which HA Bluetooth proxies hear the unit, at what RSSI, and which
should be used for GATT connections.
Status: **unverified — unit not yet heard.**

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

## Likely explanations (resolve with the human)

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
