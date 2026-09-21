"""Control entities share the service's guarded, verified write path."""

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.microair_bt.coordinator import MicroAirCoordinator

from .conftest import EEPROM, LIVE, BluetoothHarness, chunks, make_entry
from .test_entities import entity_id, get_state
from .test_service import idle_live

FAULT_SWITCHES = [
    "unexpected_current",
    "power_interruption",
    "compressor_stall",
    "start_hardware_failed",
    "open_overload",
    "overcurrent",
    "wiring_issue",
]


def eeprom_with(**fields: int) -> bytes:
    raw = bytearray(EEPROM)
    for name, value in fields.items():
        raw[
            {"startup_mask": 906, "fault_mask": 907, "scpt": 908, "firmware": 10}[name]
        ] = value
    return bytes(raw)


def writes(ble: BluetoothHarness) -> list[bytes]:
    return [payload for _, payload, _ in ble.clients[-1].writes]


async def enable(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    ble: BluetoothHarness,
    eid: str,
    eeprom: bytes = EEPROM,
) -> None:
    """Enable a disabled-by-default control the way an operator would."""
    registry = er.async_get(hass)
    registered = registry.async_get(eid)
    assert registered is not None
    assert registered.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    registry.async_update_entity(eid, disabled_by=None)
    ble.replies = [chunks(LIVE), chunks(eeprom)]
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()


async def test_control_entities_reflect_eeprom(
    hass: HomeAssistant, ble: BluetoothHarness, loaded: MockConfigEntry
) -> None:
    registry = er.async_get(hass)
    # Relearn is a learn/reset command: the select is opt-in until enabled.
    await enable(hass, loaded, ble, entity_id(hass, "select", "startup_mode"))
    select = get_state(hass, entity_id(hass, "select", "startup_mode"))
    assert select.state == "normal"
    # Firmware 37 unlocks the app's hidden SuperLearn variant.
    assert select.attributes["options"] == [
        "normal",
        "relearn",
        "default_ramp",
        "superlearn",
    ]
    number = get_state(hass, entity_id(hass, "number", "scpt_minutes"))
    assert number.state == "3"
    assert number.attributes["min"] == 1
    assert number.attributes["max"] == 250
    assert number.attributes["step"] == 1
    assert number.attributes["unit_of_measurement"] == "min"
    assert number.attributes["mode"] == "box"
    assert number.attributes["interpretation"] == "short_cycle_protection"
    assert (
        get_state(hass, entity_id(hass, "switch", "no_power_up_delay")).state == "off"
    )
    fault_mask = get_state(hass, entity_id(hass, "sensor", "fault_mask"))
    assert fault_mask.state == "0x7F"
    assert fault_mask.attributes["compressor_stall"] is True
    startup_mask = get_state(hass, entity_id(hass, "sensor", "startup_mask"))
    assert startup_mask.attributes["relearn"] is False
    assert startup_mask.attributes["no_power_up_delay"] is False
    for platform, key in [("number", "scpt_minutes"), ("switch", "no_power_up_delay")]:
        registered = registry.async_get(entity_id(hass, platform, key))
        assert registered is not None
        assert registered.entity_category == "config"
        assert registered.disabled_by is None
    # Hidden OEM feature and the confirm-gated fault protections start disabled.
    hidden = [entity_id(hass, "switch", "start_delay_mode")] + [
        entity_id(hass, "switch", f"protect_{name}") for name in FAULT_SWITCHES
    ]
    for eid in hidden:
        registered = registry.async_get(eid)
        assert registered is not None
        assert registered.disabled_by is er.RegistryEntryDisabler.INTEGRATION
        assert registered.entity_category == "config"


async def test_startup_mode_select_disabled_until_enabled(
    hass: HomeAssistant, loaded: MockConfigEntry
) -> None:
    eid = entity_id(hass, "select", "startup_mode")
    registered = er.async_get(hass).async_get(eid)
    assert registered is not None
    assert registered.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert hass.states.get(eid) is None


async def test_superlearn_hidden_below_firmware_29(
    hass: HomeAssistant, ble: BluetoothHarness
) -> None:
    entry = make_entry()
    entry.add_to_hass(hass)
    ble.replies = [chunks(LIVE), chunks(eeprom_with(firmware=28))]
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    eid = entity_id(hass, "select", "startup_mode")
    await enable(hass, entry, ble, eid, eeprom_with(firmware=28))
    assert get_state(hass, eid).attributes["options"] == [
        "normal",
        "relearn",
        "default_ramp",
    ]
    clients_before = len(ble.clients)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": eid, "option": "superlearn"},
            blocking=True,
        )
    assert len(ble.clients) == clients_before


@pytest.mark.parametrize(
    ("option", "mask"),
    [("relearn", 0x01), ("default_ramp", 0x02), ("superlearn", 0x11), ("normal", 0x00)],
)
async def test_select_startup_mode_writes_and_verifies(
    hass: HomeAssistant,
    ble: BluetoothHarness,
    loaded: MockConfigEntry,
    option: str,
    mask: int,
) -> None:
    eid = entity_id(hass, "select", "startup_mode")
    await enable(hass, loaded, ble, eid)
    ble.replies = [
        chunks(idle_live()),
        chunks(EEPROM),
        [b'{"Sts": Success}'],
        chunks(eeprom_with(startup_mask=mask)),
    ]
    await hass.services.async_call(
        "select", "select_option", {"entity_id": eid, "option": option}, blocking=True
    )
    assert writes(ble) == [
        b'{"Cmd": ReadLive}',
        b'{"Cmd": ReadEEP}',
        f'{{"Cmd": SMask={mask:02X}}}'.encode(),
        b'{"Cmd": ReadEEP}',
    ]
    assert not ble.clients[-1].is_connected
    assert get_state(hass, eid).state == option
    assert get_state(hass, entity_id(hass, "sensor", "startup_mask")).state == (
        f"0x{mask:02X}"
    )
    text = str(hass.data["persistent_notification"])
    assert "STORED" in text
    if option in {"relearn", "superlearn"}:
        assert "30" in text and "5" in text and "power" in text.lower()


@pytest.mark.parametrize(("service", "mask"), [("turn_on", 0x04), ("turn_off", 0x00)])
async def test_no_power_up_delay_switch(
    hass: HomeAssistant,
    ble: BluetoothHarness,
    loaded: MockConfigEntry,
    service: str,
    mask: int,
) -> None:
    coordinator: MicroAirCoordinator = loaded.runtime_data
    before = 0x00 if service == "turn_on" else 0x04
    eid = entity_id(hass, "switch", "no_power_up_delay")
    ble.replies = [
        chunks(idle_live()),
        chunks(eeprom_with(startup_mask=before)),
        [b'{"Sts": Success}'],
        chunks(eeprom_with(startup_mask=mask)),
    ]
    await hass.services.async_call("switch", service, {"entity_id": eid}, blocking=True)
    assert writes(ble)[2] == f'{{"Cmd": SMask={mask:02X}}}'.encode()
    assert get_state(hass, eid).state == ("on" if mask else "off")
    assert coordinator.data is not None and coordinator.data.eeprom is not None
    assert coordinator.data.eeprom.startup_mask == mask


async def test_start_delay_mode_switch_after_enabling(
    hass: HomeAssistant, ble: BluetoothHarness, loaded: MockConfigEntry
) -> None:
    eid = entity_id(hass, "switch", "start_delay_mode")
    await enable(hass, loaded, ble, eid)
    assert get_state(hass, eid).state == "off"
    ble.replies = [
        chunks(idle_live()),
        chunks(EEPROM),
        [b'{"Sts": Success}'],
        chunks(eeprom_with(startup_mask=0x08)),
    ]
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": eid}, blocking=True
    )
    assert writes(ble)[2] == b'{"Cmd": SMask=08}'
    assert get_state(hass, eid).state == "on"
    number = get_state(hass, entity_id(hass, "number", "scpt_minutes"))
    assert number.attributes["interpretation"] == "start_delay"


@pytest.mark.parametrize("minutes", [1, 10, 250])
async def test_scpt_number_writes_and_verifies(
    hass: HomeAssistant, ble: BluetoothHarness, loaded: MockConfigEntry, minutes: int
) -> None:
    eid = entity_id(hass, "number", "scpt_minutes")
    ble.replies = [
        chunks(idle_live()),
        chunks(EEPROM),
        [b'{"Sts": Success}'],
        chunks(eeprom_with(scpt=minutes)),
    ]
    await hass.services.async_call(
        "number", "set_value", {"entity_id": eid, "value": minutes}, blocking=True
    )
    assert writes(ble) == [
        b'{"Cmd": ReadLive}',
        b'{"Cmd": ReadEEP}',
        f'{{"Cmd": SCPT={minutes:02X}}}'.encode(),
        b'{"Cmd": ReadEEP}',
    ]
    assert get_state(hass, eid).state == str(minutes)
    assert "STORED" in str(hass.data["persistent_notification"])


@pytest.mark.parametrize("value", [0, 251, 2.5])
async def test_scpt_number_rejects_out_of_range_without_io(
    hass: HomeAssistant, ble: BluetoothHarness, loaded: MockConfigEntry, value: float
) -> None:
    eid = entity_id(hass, "number", "scpt_minutes")
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "number", "set_value", {"entity_id": eid, "value": value}, blocking=True
        )
    assert len(ble.clients) == 1


async def test_scpt_readback_mismatch_is_unverified(
    hass: HomeAssistant, ble: BluetoothHarness, loaded: MockConfigEntry
) -> None:
    eid = entity_id(hass, "number", "scpt_minutes")
    ble.replies = [
        chunks(idle_live()),
        chunks(EEPROM),
        [b'{"Sts": Success}'],
        chunks(EEPROM),
    ]
    with pytest.raises(HomeAssistantError, match="ACKNOWLEDGED-BUT-UNVERIFIED"):
        await hass.services.async_call(
            "number", "set_value", {"entity_id": eid, "value": 7}, blocking=True
        )
    # The stored value is now uncertain, so the entity is unavailable until
    # the next successful poll re-reads the image.
    assert get_state(hass, eid).state == "unavailable"
    assert "ACKNOWLEDGED-BUT-UNVERIFIED" in str(hass.data["persistent_notification"])


@pytest.mark.parametrize(
    ("name", "service", "before", "after"),
    [
        ("compressor_stall", "turn_off", 0x7F, 0x7B),
        ("compressor_stall", "turn_on", 0x7B, 0x7F),
        ("wiring_issue", "turn_off", 0x7F, 0x3F),
        ("unexpected_current", "turn_on", 0x40, 0x41),
    ],
)
async def test_fault_protection_switch_after_enabling(
    hass: HomeAssistant,
    ble: BluetoothHarness,
    loaded: MockConfigEntry,
    name: str,
    service: str,
    before: int,
    after: int,
) -> None:
    eid = entity_id(hass, "switch", f"protect_{name}")
    await enable(hass, loaded, ble, eid)
    ble.replies = [
        chunks(idle_live()),
        chunks(eeprom_with(fault_mask=before)),
        [b'{"Sts": Success}'],
        chunks(eeprom_with(fault_mask=after)),
    ]
    await hass.services.async_call("switch", service, {"entity_id": eid}, blocking=True)
    assert writes(ble) == [
        b'{"Cmd": ReadLive}',
        b'{"Cmd": ReadEEP}',
        f'{{"Cmd": FMask={after:02X}}}'.encode(),
        b'{"Cmd": ReadEEP}',
    ]
    assert get_state(hass, eid).state == ("on" if service == "turn_on" else "off")
    assert get_state(hass, entity_id(hass, "sensor", "fault_mask")).state == (
        f"0x{after:02X}"
    )


async def test_fault_protection_cannot_disable_last_protection(
    hass: HomeAssistant, ble: BluetoothHarness, loaded: MockConfigEntry
) -> None:
    eid = entity_id(hass, "switch", "protect_compressor_stall")
    await enable(hass, loaded, ble, eid)
    ble.replies = [chunks(idle_live()), chunks(eeprom_with(fault_mask=0x04))]
    with pytest.raises(ServiceValidationError, match="REJECTED"):
        await hass.services.async_call(
            "switch", "turn_off", {"entity_id": eid}, blocking=True
        )
    assert not any(b"FMask" in payload for payload in writes(ble))
    assert not ble.clients[-1].is_connected


@pytest.mark.parametrize("reason", ["running", "paused", "live_mode"])
async def test_entity_writes_share_service_guards(
    hass: HomeAssistant, ble: BluetoothHarness, loaded: MockConfigEntry, reason: str
) -> None:
    coordinator: MicroAirCoordinator = loaded.runtime_data
    eid = entity_id(hass, "select", "startup_mode")
    await enable(hass, loaded, ble, eid)
    ble.replies = [chunks(LIVE), chunks(EEPROM)]
    if reason == "paused":
        await coordinator.async_set_polling(False)
    elif reason == "live_mode":
        hass.config_entries.async_update_entry(
            loaded, options={**loaded.options, "live_mode": True}
        )
        await hass.async_block_till_done()
    call = hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": eid, "option": "relearn"},
        blocking=True,
    )
    if reason == "paused":
        # Pausing makes the control unavailable, so HA never invokes it.
        assert get_state(hass, eid).state == "unavailable"
        await call
    else:
        with pytest.raises(ServiceValidationError):
            await call
    assert not any(
        b"SMask" in payload for client in ble.clients for _, payload, _ in client.writes
    )


async def test_controls_unavailable_without_eeprom_image(
    hass: HomeAssistant, ble: BluetoothHarness
) -> None:
    entry = make_entry()
    entry.add_to_hass(hass)
    ble.replies = [chunks(LIVE), [b'{"Sts": Fail}'], [b'{"Sts": Fail}']]
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert get_state(hass, entity_id(hass, "sensor", "current_a")).state == "9.2"
    for platform, key in [
        ("number", "scpt_minutes"),
        ("switch", "no_power_up_delay"),
        ("sensor", "fault_mask"),
        ("sensor", "model"),
    ]:
        assert get_state(hass, entity_id(hass, platform, key)).state == "unavailable"
