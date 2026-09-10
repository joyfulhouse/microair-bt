"""Device isolation, monitoring semantics and HA lifecycle behavior."""

from dataclasses import replace

import pytest
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.microair_bt.coordinator import MicroAirCoordinator
from custom_components.microair_bt.microair.protocol import parse_live

from .conftest import (
    DOWNSTAIRS,
    EEPROM,
    LIVE,
    UPSTAIRS,
    BluetoothHarness,
    chunks,
    make_entry,
)


def entity_id(
    hass: HomeAssistant, platform: str, key: str, address: str = UPSTAIRS
) -> str:
    result = er.async_get(hass).async_get_entity_id(
        platform, "microair_bt", f"{address}_{key}"
    )
    assert result is not None
    return result


def get_state(hass: HomeAssistant, eid: str) -> State:
    state = hass.states.get(eid)
    assert state is not None
    return state


@pytest.mark.parametrize(
    ("key", "value", "unit", "device_class", "state_class"),
    [
        ("status", "normal", None, "enum", None),
        ("learned_starts", "5", None, None, None),
        ("current_a", "9.2", "A", "current", "measurement"),
        ("line_hz", "60.0024", "Hz", "frequency", "measurement"),
        ("last_start_peak_a", "25.0", "A", "current", "measurement"),
        ("scpt_delay_s", "0", "s", "duration", "measurement"),
        ("total_faults", "2", None, None, "total"),
        ("total_starts", "10", None, None, "total"),
        ("model", "398ULBT", None, None, None),
        ("firmware", "37", None, None, None),
        ("startup_mask", "0x00", None, None, None),
    ],
)
async def test_sensor_values_and_metadata(
    hass: HomeAssistant,
    loaded: MockConfigEntry,
    key: str,
    value: str,
    unit: str | None,
    device_class: str | None,
    state_class: str | None,
) -> None:
    eid = entity_id(hass, "sensor", key)
    state = hass.states.get(eid)
    assert state is not None
    if key == "line_hz":
        assert float(state.state) == pytest.approx(60.0024, abs=0.001)
    else:
        assert state.state == value
    assert state.attributes.get("unit_of_measurement") == unit
    assert state.attributes.get("device_class") == device_class
    assert state.attributes.get("state_class") == state_class
    registered = er.async_get(hass).async_get(eid)
    assert registered is not None
    if key in {"model", "firmware", "startup_mask"}:
        assert registered.entity_category == "diagnostic"
    assert registered.device_id is not None


@pytest.mark.parametrize(
    ("raw", "status", "fault"),
    [
        (0, "normal", "off"),
        (1, "unexpected_current_fault", "on"),
        (2, "short_cycle_delay", "off"),
        (3, "power_interruption_fault", "on"),
        (4, "stall_fault", "on"),
        (5, "stuck_start_relay_fault", "on"),
        (6, "open_overload_fault", "on"),
        (7, "overcurrent_fault", "on"),
        (8, "bad_wiring_fault", "on"),
        (9, "wrong_voltage_fault", "on"),
        (10, "unknown", "unknown"),
        (255, "unknown", "unknown"),
    ],
)
async def test_status_and_fault(
    hass: HomeAssistant, loaded: MockConfigEntry, raw: int, status: str, fault: str
) -> None:
    coordinator: MicroAirCoordinator = loaded.runtime_data
    assert coordinator.data is not None
    frame = bytearray(LIVE)
    frame[2] = raw
    frame[6:8] = b"\0\0"
    coordinator.async_set_updated_data(
        replace(coordinator.data, live=parse_live(bytes(frame)))
    )
    await hass.async_block_till_done()
    for platform, key, expected in [
        ("sensor", "status", status),
        ("binary_sensor", "fault", fault),
        ("sensor", "line_hz", "unknown"),
    ]:
        state = hass.states.get(entity_id(hass, platform, key))
        assert state is not None
        assert state.state == expected
        if key in {"status", "fault"}:
            assert state.attributes["raw_status"] == raw


async def test_unpowered_availability_and_pause(
    hass: HomeAssistant, ble: BluetoothHarness, loaded: MockConfigEntry
) -> None:
    ble.disappear()
    await hass.async_block_till_done()
    for key in ["status", "current_a", "model", "startup_mask"]:
        state = hass.states.get(entity_id(hass, "sensor", key))
        assert state is not None and state.state == "unavailable"
    powered = hass.states.get(entity_id(hass, "binary_sensor", "powered"))
    assert powered is not None and powered.state == "off"
    switch = entity_id(hass, "switch", "polling")
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": switch}, blocking=True
    )
    assert loaded.options["polling_enabled"] is False
    assert get_state(hass, switch).state == "off"
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": switch}, blocking=True
    )
    assert loaded.options["polling_enabled"] is True
    assert get_state(hass, switch).state == "on"
    assert len(ble.clients) == 1


async def test_multi_device_reload_unload(
    hass: HomeAssistant, ble: BluetoothHarness, loaded: MockConfigEntry
) -> None:
    second = make_entry(DOWNSTAIRS)
    second.add_to_hass(hass)
    ble.replies = [chunks(EEPROM), chunks(LIVE)]
    assert await hass.config_entries.async_setup(second.entry_id)
    await hass.async_block_till_done()
    first_id = entity_id(hass, "sensor", "status")
    second_id = entity_id(hass, "sensor", "status", DOWNSTAIRS)
    assert first_id != second_id
    registry = er.async_get(hass)
    first_registered = registry.async_get(first_id)
    second_registered = registry.async_get(second_id)
    assert first_registered is not None and second_registered is not None
    assert first_registered.device_id != second_registered.device_id
    switch = entity_id(hass, "switch", "polling")
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": switch}, blocking=True
    )
    assert await hass.config_entries.async_reload(loaded.entry_id)
    await hass.async_block_till_done()
    assert entity_id(hass, "sensor", "status") == first_id
    assert get_state(hass, switch).state == "off"
    assert len(ble.clients) == 2
    assert await hass.config_entries.async_unload(loaded.entry_id)
    assert len(ble.callbacks) == 1
    assert get_state(hass, second_id).state == "normal"
    assert hass.services.has_service("microair_bt", "set_startup_mode")
    assert await hass.config_entries.async_unload(second.entry_id)
    assert not ble.callbacks
    assert not ble.unavailable_callbacks
    assert not hass.services.has_service("microair_bt", "set_startup_mode")


async def test_pause_saved_for_restart(
    hass: HomeAssistant,
    ble: BluetoothHarness,
    loaded: MockConfigEntry,
    hass_storage: dict[str, object],
) -> None:
    from datetime import timedelta
    from typing import Any, cast

    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    switch = entity_id(hass, "switch", "polling")
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": switch}, blocking=True
    )
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=2))
    await hass.async_block_till_done(wait_background_tasks=True)
    storage = cast(dict[str, Any], hass_storage["core.config_entries"])
    saved = next(
        item
        for item in storage["data"]["entries"]
        if item["entry_id"] == loaded.entry_id
    )
    assert saved["options"]["polling_enabled"] is False
    assert await hass.config_entries.async_unload(loaded.entry_id)
    # Reconstruct from persisted options as HA does on the next process start.
    restored = make_entry(**saved["options"])
    restored.add_to_hass(hass)
    assert await hass.config_entries.async_setup(restored.entry_id)
    assert restored.runtime_data.polling_enabled is False
    assert len(ble.clients) == 1
