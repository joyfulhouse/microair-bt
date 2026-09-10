"""Scheduling and connection ownership over actual MicroAir transactions."""

import asyncio

import pytest
from bleak.backends.device import BLEDevice
from homeassistant.core import HomeAssistant

from custom_components.microair_bt.coordinator import MicroAirCoordinator

from .conftest import (
    DOWNSTAIRS,
    EEPROM,
    LIVE,
    UPSTAIRS,
    BluetoothHarness,
    chunks,
    make_entry,
)


@pytest.fixture
async def coordinator(
    hass: HomeAssistant, ble: BluetoothHarness, monkeypatch: pytest.MonkeyPatch
) -> MicroAirCoordinator:
    monkeypatch.setattr(
        "custom_components.microair_bt.coordinator.monotonic", lambda: ble.now
    )
    entry = make_entry()
    entry.add_to_hass(hass)
    return MicroAirCoordinator(hass, entry)


@pytest.mark.parametrize("source", ["proxy", "local"])
async def test_fresh_route_after_lock(
    coordinator: MicroAirCoordinator, ble: BluetoothHarness, source: str
) -> None:
    ble.replies = [chunks(EEPROM), chunks(LIVE)]
    await coordinator.lock.acquire()
    task = asyncio.create_task(coordinator.async_refresh())
    await asyncio.sleep(0)
    assert not ble.resolutions
    replacement = BLEDevice(UPSTAIRS, "EasyStart_88CD", {"source": source})
    ble.routes[UPSTAIRS] = replacement
    coordinator.lock.release()
    await task
    assert ble.connected == [replacement]
    assert ble.resolutions == [(UPSTAIRS, True)]
    assert ble.attempts == [1]
    assert coordinator.data is not None
    assert coordinator.data.live.current_a == 9.2
    assert not ble.clients[0].is_connected


async def test_advertisement_elapsed_gate_and_no_overlap(
    coordinator: MicroAirCoordinator, ble: BluetoothHarness, hass: HomeAssistant
) -> None:
    ble.replies = [chunks(EEPROM), chunks(LIVE), chunks(EEPROM), chunks(LIVE)]
    await coordinator.async_start()
    for _ in range(5):
        ble.advertise()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(ble.clients) == 1
    ble.now += 30
    ble.block = "connect"
    ble.advertise()
    await ble.entered.wait()
    for _ in range(5):
        ble.advertise()
    await asyncio.sleep(0)
    assert len(ble.clients) == 2
    ble.release.set()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(ble.clients) == 2
    assert all(not client.is_connected for client in ble.clients)
    await coordinator.async_shutdown()


async def test_offline_start_and_recovery(
    coordinator: MicroAirCoordinator,
    ble: BluetoothHarness,
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    ble.present.clear()
    await coordinator.async_start()
    assert not ble.clients
    assert not coordinator.last_update_success
    assert not coordinator.powered
    assert "not advertising" in caplog.text
    ble.replies = [chunks(EEPROM), chunks(LIVE)]
    ble.advertise()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert coordinator.powered
    assert coordinator.last_update_success
    assert coordinator.data is not None
    ble.disappear()
    assert not coordinator.powered
    assert not coordinator.last_update_success
    await coordinator.async_shutdown()
    assert not ble.callbacks
    assert not ble.unavailable_callbacks


async def test_no_route_never_connects(
    coordinator: MicroAirCoordinator,
    ble: BluetoothHarness,
    caplog: pytest.LogCaptureFixture,
) -> None:
    ble.routes.clear()
    await coordinator.async_refresh()
    assert not coordinator.last_update_success
    assert not ble.clients
    assert "No connectable" in caplog.text


async def test_busy_backoff_and_recovery(
    coordinator: MicroAirCoordinator,
    ble: BluetoothHarness,
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    ble.error_at = "notify"
    await coordinator.async_start()
    assert not coordinator.last_update_success
    assert not ble.clients[0].is_connected
    assert "busy or unavailable" in caplog.text
    ble.now += 30
    ble.advertise()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(ble.clients) == 1
    ble.now += 30
    ble.replies = [chunks(EEPROM), chunks(LIVE)]
    ble.error_at = None
    ble.advertise()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(ble.clients) == 2
    assert coordinator.last_update_success
    await coordinator.async_shutdown()


async def test_polling_pause_persisted_and_independent(
    hass: HomeAssistant, ble: BluetoothHarness
) -> None:
    entry = make_entry(polling_enabled=False)
    entry.add_to_hass(hass)
    coordinator = MicroAirCoordinator(hass, entry)
    await coordinator.async_start()
    ble.advertise()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert not ble.clients
    other = MicroAirCoordinator(hass, make_entry(DOWNSTAIRS))
    ble.replies = [chunks(EEPROM), chunks(LIVE)]
    await other.async_refresh()
    assert ble.connected[0].address == DOWNSTAIRS
    assert other.lock is not coordinator.lock
    ble.replies = [chunks(EEPROM), chunks(LIVE)]
    await coordinator.async_set_polling(True)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert coordinator.polling_enabled
    await coordinator.async_set_polling(False)
    assert entry.options["polling_enabled"] is False
    await coordinator.async_shutdown()
    restarted = MicroAirCoordinator(hass, entry)
    await restarted.async_start()
    assert not restarted.polling_enabled
    assert len(ble.clients) == 2
    await restarted.async_shutdown()
    await other.async_shutdown()


async def test_shutdown_cancels_transaction_and_callbacks(
    coordinator: MicroAirCoordinator, ble: BluetoothHarness, hass: HomeAssistant
) -> None:
    ble.present.clear()
    await coordinator.async_start()
    ble.block = "write"
    ble.replies = [chunks(EEPROM), chunks(LIVE)]
    ble.advertise()
    await ble.entered.wait()
    await coordinator.async_shutdown()
    assert not ble.clients[0].is_connected
    assert not ble.callbacks
    ble.advertise()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(ble.clients) == 1


async def test_short_read_unavailable_then_retry(
    coordinator: MicroAirCoordinator, ble: BluetoothHarness, hass: HomeAssistant
) -> None:
    ble.replies = [chunks(EEPROM[:-3]), chunks(LIVE)]
    await coordinator.async_start()
    assert not coordinator.last_update_success
    assert coordinator.data is None
    assert not ble.clients[-1].is_connected
    ble.now += 60
    ble.replies = [chunks(EEPROM), chunks(LIVE)]
    ble.advertise()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert coordinator.last_update_success
    assert coordinator.data is not None
    await coordinator.async_shutdown()


@pytest.mark.parametrize("first_read_fails", [False, True])
async def test_unchanged_advertisements_keep_polling(
    coordinator: MicroAirCoordinator,
    ble: BluetoothHarness,
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    first_read_fails: bool,
) -> None:
    from datetime import timedelta
    from unittest.mock import MagicMock

    from habluetooth.manager import BluetoothManager
    from habluetooth.models import BluetoothServiceInfoBleak
    from homeassistant.components import bluetooth
    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    class Manager(BluetoothManager):
        def __init__(self) -> None:
            self.deliveries = 0
            super().__init__(bluetooth_adapters=MagicMock(), slot_manager=MagicMock())

        def _discover_service_info(self, info: BluetoothServiceInfoBleak) -> None:
            self.deliveries += 1
            for _, callback in ble.callbacks:
                callback(info, bluetooth.BluetoothChange.ADVERTISEMENT)

    manager = Manager()
    manager.scanner_adv_received(ble.info())
    monkeypatch.setattr(
        bluetooth,
        "async_address_present",
        lambda hass, address, connectable=True: manager.async_address_present(
            address, connectable
        ),
    )
    ble.replies = [chunks(EEPROM), chunks(LIVE)]
    if first_read_fails:
        ble.error_at = "notify"
    await coordinator.async_start()
    remove_listener = coordinator.async_add_listener(lambda: None)
    delay = 61 if first_read_fails else 31
    ble.now += delay
    manager.scanner_adv_received(ble.info())
    assert manager.deliveries == 1  # HA suppresses this unchanged advertisement.
    ble.error_at = None
    ble.replies = [chunks(EEPROM), chunks(LIVE)]
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=delay))
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(ble.clients) == 2
    assert coordinator.last_update_success
    assert all(not client.is_connected for client in ble.clients)
    # Pausing while still advertising must prevent any timed connection.
    await coordinator.async_set_polling(False)
    ble.now += 90
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=150))
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(ble.clients) == 2
    remove_listener()
    await coordinator.async_shutdown()
