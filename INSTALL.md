# Installing MicroAir BT

## Prerequisites

- Home Assistant 2026.1.0 or newer.
- A **connectable** Bluetooth path to the EasyStart: a local adapter or an
  **ESPHome BLE proxy** (`bluetooth_proxy: active: true`) within a few metres
  of the unit. See [`wiki/ha-proxy-coverage.md`](wiki/ha-proxy-coverage.md).
- The EasyStart advertises only while the A/C supplies it control power, so
  have the thermostat calling for cooling when you add the device, and close
  the OEM app (the unit accepts one BLE client at a time).

## Option A — HACS (recommended)

1. In HACS, open the three-dot menu → **Custom repositories**.
2. Add `https://github.com/joyfulhouse/microair-bt` with category
   **Integration**.
3. Search for **MicroAir BT**, download it.
4. **Restart Home Assistant.**

## Option B — Manual

1. Copy `custom_components/microair_bt/` into your Home Assistant
   `config/custom_components/` directory.
2. **Restart Home Assistant.**

## Add the device

After restart, the EasyStart is auto-discovered (**Settings → Devices &
Services**) once a Bluetooth proxy hears its `EasyStart_…` advertisement.
Otherwise click **Add Integration**, search **MicroAir BT**, and enter the
Bluetooth address. Setup reads the EEPROM and rejects models other than the
verified `398ULBT`.

## Entities

- `sensor` — status, current, line frequency, last start peak, short-cycle
  delay, learned starts, total starts, total faults; diagnostic model,
  firmware, startup mask.
- `binary_sensor` — powered (advertising), fault.
- `switch` — polling (pause/resume all BLE traffic; persists).
- Service `microair_bt.set_startup_mode` — see the README before using it.

## Troubleshooting

- **Not discovered / unavailable:** the unit is probably unpowered (A/C idle)
  or the OEM app is connected. Confirm a proxy hears it with the read-only
  probe: `uv run scripts/probe.py --scan-seconds 5`.
- **Debug logs:**

  ```yaml
  logger:
    logs:
      custom_components.microair_bt: debug
  ```
