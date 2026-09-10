"""Explicit maintenance outcomes at the real HA service and GATT boundaries."""

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.microair_bt.coordinator import MicroAirCoordinator

from .conftest import DOWNSTAIRS, EEPROM, LIVE, BluetoothHarness, chunks, make_entry


def idle_live() -> bytes:
    raw = bytearray(LIVE)
    raw[4:6] = b"\0\0"
    return bytes(raw)


async def call(
    hass: HomeAssistant, target: MockConfigEntry, **fields: object
) -> object:
    return await hass.services.async_call(
        "microair_bt",
        "set_startup_mode",
        {"entry": target.entry_id, "mode": "relearn", "confirm": True, **fields},
        blocking=True,
        return_response=True,
    )


@pytest.mark.parametrize(
    ("mode", "mask"), [("normal", 0x14), ("relearn", 0x15), ("default_ramp", 0x16)]
)
async def test_modes_readback_and_notification(
    hass: HomeAssistant,
    ble: BluetoothHarness,
    loaded: MockConfigEntry,
    mode: str,
    mask: int,
) -> None:
    before = bytearray(EEPROM)
    before[906] = 0x14
    after = bytearray(before)
    after[906] = mask
    ble.replies = [
        chunks(idle_live()),
        chunks(bytes(before)),
        [b'{"Sts": Success}'],
        chunks(bytes(after)),
    ]
    result = await call(hass, loaded, mode=mode)
    assert result == {"outcome": "STORED", "startup_mask": f"0x{mask:02X}"}
    writes = [payload for _, payload, _ in ble.clients[-1].writes]
    assert writes == [
        b'{"Cmd": ReadLive}',
        b'{"Cmd": ReadEEP}',
        f'{{"Cmd": SMask={mask:02X}}}'.encode(),
        b'{"Cmd": ReadEEP}',
    ]
    assert not ble.clients[-1].is_connected
    coordinator: MicroAirCoordinator = loaded.runtime_data
    assert coordinator.data is not None and coordinator.data.eeprom.startup_mask == mask
    notifications = hass.data["persistent_notification"]
    text = str(notifications)
    assert "power" in text.lower() and "5" in text and "30" in text
    assert "compressor" in text.lower()


@pytest.mark.parametrize(
    ("fields", "match"),
    [
        ({"confirm": False}, "REJECTED"),
        ({"mode": "erase"}, "REJECTED"),
        ({"entry": "missing"}, "REJECTED"),
        ({"device": "missing"}, "REJECTED"),
    ],
)
async def test_service_rejects_invalid_request(
    hass: HomeAssistant,
    ble: BluetoothHarness,
    loaded: MockConfigEntry,
    fields: dict[str, object],
    match: str,
) -> None:
    with pytest.raises(ServiceValidationError, match=match):
        await call(hass, loaded, **fields)
    assert len(ble.clients) == 1


@pytest.mark.parametrize(
    "reason",
    ["paused", "offline", "no_route", "running", "unknown", "model", "bits", "partial"],
)
async def test_prewrite_rejection(
    hass: HomeAssistant, ble: BluetoothHarness, loaded: MockConfigEntry, reason: str
) -> None:
    coordinator: MicroAirCoordinator = loaded.runtime_data
    raw = bytearray(EEPROM)
    live = bytearray(idle_live())
    if reason == "paused":
        await coordinator.async_set_polling(False)
    elif reason == "offline":
        ble.disappear()
    elif reason == "no_route":
        ble.routes.clear()
    elif reason == "running":
        live = bytearray(LIVE)
    elif reason == "unknown":
        live[2] = 255
    elif reason == "model":
        raw[2:9] = b"999ULBT"
    elif reason == "bits":
        raw[906] = 0x20
    elif reason == "partial":
        raw = raw[:-3]
    ble.replies = [chunks(bytes(live)), chunks(bytes(raw))]
    with pytest.raises(ServiceValidationError, match="REJECTED"):
        await call(hass, loaded)
    assert not any(
        b"SMask" in payload for client in ble.clients for _, payload, _ in client.writes
    )
    assert all(not client.is_connected for client in ble.clients)


@pytest.mark.parametrize(
    "outcome",
    ["FAILED", "INDETERMINATE", "ACKNOWLEDGED-BUT-UNVERIFIED", "readback_failed"],
)
async def test_write_outcomes(
    hass: HomeAssistant,
    ble: BluetoothHarness,
    loaded: MockConfigEntry,
    outcome: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ble.replies = [chunks(idle_live()), chunks(EEPROM)]
    if outcome == "FAILED":
        ble.replies += [[b'{"Sts": Fail}']]
    elif outcome == "INDETERMINATE":
        # The write is sent but never acknowledged; do not retry it.
        monkeypatch.setattr(
            "custom_components.microair_bt.microair.client.STARTUP_MASK_TIMEOUT", 0.01
        )
        ble.replies += [[]]
    else:
        ble.replies += [
            [b'{"Sts": Success}'],
            [b'{"Sts": Fail}'] if outcome == "readback_failed" else chunks(EEPROM),
        ]
    expected = (
        "ACKNOWLEDGED-BUT-UNVERIFIED" if outcome == "readback_failed" else outcome
    )
    with pytest.raises(HomeAssistantError, match=expected):
        await call(hass, loaded)
    assert (
        sum(
            b"SMask" in payload
            for client in ble.clients
            for _, payload, _ in client.writes
        )
        == 1
    )
    assert all(not client.is_connected for client in ble.clients)
    assert expected in str(hass.data["persistent_notification"])


async def test_device_target_and_allow_running(
    hass: HomeAssistant, ble: BluetoothHarness, loaded: MockConfigEntry
) -> None:
    second = make_entry(DOWNSTAIRS, allow_running=True)
    second.add_to_hass(hass)
    ble.replies = [chunks(EEPROM), chunks(LIVE)]
    assert await hass.config_entries.async_setup(second.entry_id)
    device = dr.async_get(hass).async_get_device(
        identifiers={("microair_bt", DOWNSTAIRS)}
    )
    assert device is not None
    after = bytearray(EEPROM)
    after[906] = 2
    ble.replies = [
        chunks(LIVE),
        chunks(EEPROM),
        [b'{"Sts": Success}'],
        chunks(bytes(after)),
    ]
    result = await hass.services.async_call(
        "microair_bt",
        "set_startup_mode",
        {"device": device.id, "mode": "default_ramp", "confirm": True},
        blocking=True,
        return_response=True,
    )
    assert result == {"outcome": "STORED", "startup_mask": "0x02"}
    assert ble.connected[-1].address == DOWNSTAIRS


async def test_service_waits_for_lock_and_honors_pause(
    hass: HomeAssistant, ble: BluetoothHarness, loaded: MockConfigEntry
) -> None:
    import asyncio

    coordinator: MicroAirCoordinator = loaded.runtime_data
    await coordinator.lock.acquire()
    task = asyncio.create_task(call(hass, loaded))
    await asyncio.sleep(0)
    assert len(ble.clients) == 1
    hass.config_entries.async_update_entry(loaded, options={"polling_enabled": False})
    coordinator.lock.release()
    with pytest.raises(ServiceValidationError, match="REJECTED"):
        await task
    assert len(ble.clients) == 1


async def test_service_rejects_during_shutdown(
    hass: HomeAssistant, ble: BluetoothHarness, loaded: MockConfigEntry
) -> None:
    import asyncio

    coordinator: MicroAirCoordinator = loaded.runtime_data
    await coordinator.lock.acquire()
    # Queue the service before shutdown acquires the lock; shutdown must close
    # the gate immediately, before its awaited cleanup finishes.
    task = asyncio.create_task(call(hass, loaded))
    await asyncio.sleep(0)
    shutdown = asyncio.create_task(coordinator.async_shutdown())
    await asyncio.sleep(0)
    ble.replies = [
        chunks(idle_live()),
        chunks(EEPROM),
        [b'{"Sts": Success}'],
        chunks(EEPROM),
    ]
    coordinator.lock.release()
    with pytest.raises(ServiceValidationError, match="REJECTED"):
        await task
    await shutdown
    assert len(ble.clients) == 1


async def test_acknowledgement_survives_gatt_write_error(
    hass: HomeAssistant,
    ble: BluetoothHarness,
    loaded: MockConfigEntry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from tests.conftest import FakeBleakClient

    original_write = FakeBleakClient.write_gatt_char

    async def write(
        client: FakeBleakClient,
        characteristic: BleakGATTCharacteristic,
        payload: bytes,
        *,
        response: bool,
    ) -> None:
        if b"SMask=" in payload:
            client.writes.append((characteristic.uuid, payload, response))
            client.emit(b'{"Sts": Success}')
            raise OSError("GATT completion failed after device acknowledgement")
        await original_write(client, characteristic, payload, response=response)

    monkeypatch.setattr(FakeBleakClient, "write_gatt_char", write)
    ble.replies = [chunks(idle_live()), chunks(EEPROM)]
    with pytest.raises(HomeAssistantError, match="ACKNOWLEDGED-BUT-UNVERIFIED"):
        await call(hass, loaded)
    assert "ACKNOWLEDGED-BUT-UNVERIFIED" in str(hass.data["persistent_notification"])
    assert not ble.clients[-1].is_connected
    assert sum(b"SMask=" in payload for _, payload, _ in ble.clients[-1].writes) == 1


@pytest.mark.parametrize("phase", ["preflight", "write"])
async def test_cancellation_tracks_actual_write_phase(
    hass: HomeAssistant,
    ble: BluetoothHarness,
    loaded: MockConfigEntry,
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
) -> None:
    import asyncio

    from bleak.backends.characteristic import BleakGATTCharacteristic

    from tests.conftest import FakeBleakClient

    original_write = FakeBleakClient.write_gatt_char

    async def write(
        client: FakeBleakClient,
        characteristic: BleakGATTCharacteristic,
        payload: bytes,
        *,
        response: bool,
    ) -> None:
        blocked = b"ReadEEP" if phase == "preflight" else b"SMask="
        if blocked in payload:
            client.writes.append((characteristic.uuid, payload, response))
            ble.entered.set()
            await ble.release.wait()
        await original_write(client, characteristic, payload, response=response)

    monkeypatch.setattr(FakeBleakClient, "write_gatt_char", write)
    ble.replies = [chunks(idle_live()), chunks(EEPROM)]
    task = asyncio.create_task(call(hass, loaded))
    await ble.entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    notifications = str(hass.data.get("persistent_notification", {}))
    if phase == "preflight":
        assert "INDETERMINATE" not in notifications
        assert not any(b"SMask=" in payload for _, payload, _ in ble.clients[-1].writes)
    else:
        assert "INDETERMINATE" in notifications
        assert any(b"SMask=" in payload for _, payload, _ in ble.clients[-1].writes)
    assert not ble.clients[-1].is_connected
