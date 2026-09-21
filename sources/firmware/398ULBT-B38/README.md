# 398ULBT-B38 — OEM firmware images for the EasyStart Flex (raw evidence)

Fetched read-only 2026-09-21 from the URLs the EasyStart app v4.3 uses
(`J/Update.java:1221,1264,1494`); server `Last-Modified: Fri, 18 Sep 2026 12:51:02 GMT`.

| File | Source URL | Bytes | Notes |
|---|---|---|---|
| `398ULBT-B38.hex` | `http://easystart.microair.net/downloads/398ULBT-B38.hex` | 69 956 | Intel HEX; decodes to a 24 864-byte AVR flash image, no printable strings |
| `398ULBT-B38.eep` | `http://easystart.microair.net/downloads/398ULBT-B38.eep` | 2 891 | Intel HEX; decodes to the 1023-byte factory EEPROM image |
| `updates.txt` | `http://easystart.microair.net/downloads/updates.txt` | — | the app's per-model update table at fetch time (fields: model, ?, low/high/ext fuses, lock bits, eep file, hex file) |

`registration.txt` (the per-device gate list) was read but is **not stored**: it
lists other customers' BLE device names. At fetch time it contained entries up
to version 39; the app treats any listed version above the unit's own as "update
available", then offers the model's row from `updates.txt`.

Older builds (`398ULBT-B35..B37`) return 404 on the server, so no diff against
the units' firmware 37 is possible. Checksums in `SHA256SUMS`.

**Never send these to a unit from this project.** The integration cannot emit
any of the 19 firmware-update commands by design; updating is done with the OEM
app only. Factory EEPROM defaults decoded from the `.eep` are recorded in
`wiki/device-easystart-flex.md`.
