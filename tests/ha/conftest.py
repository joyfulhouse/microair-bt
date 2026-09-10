"""Fake only Bluetooth I/O; retain HA flows, coordinators and entity platforms."""

from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest
from bleak import BleakClient
from bleak.backends.device import BLEDevice
from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    MockModule,
    mock_integration,
)

from custom_components.microair_bt.microair import client as client_module
from tests.conftest import FakeBleakClient, FakeRadio

UPSTAIRS = "C9:6A:70:95:4E:CE"
DOWNSTAIRS = "FA:2F:D9:57:08:D4"
EEPROM = (Path(__file__).parents[1] / "fixtures/capture-08-ReadEEP.bin").read_bytes()
# The live frame fields are independent hand-encoded expectations, not parser output.
LIVE = bytes.fromhex("100000055c008d20fa00000002000a000000")


def chunks(raw: bytes) -> list[bytes]:
    return [raw[i : i + 20] for i in range(0, len(raw), 20)] + [b'{"Sts": Success}']


def make_entry(address: str = UPSTAIRS, **options: object) -> MockConfigEntry:
    return MockConfigEntry(
        domain="microair_bt",
        unique_id=address,
        title="EasyStart_88CD" if address == UPSTAIRS else "EasyStart_DC5A",
        data={"address": address, "model": "398ULBT", "firmware": 37},
        options=options,
    )


class BluetoothHarness(FakeRadio):
    def __init__(self, hass: HomeAssistant) -> None:
        super().__init__()
        self.hass = hass
        self.routes: dict[str, BLEDevice] = {
            UPSTAIRS: BLEDevice(UPSTAIRS, "EasyStart_88CD", {"source": "proxy"}),
            DOWNSTAIRS: BLEDevice(DOWNSTAIRS, "EasyStart_DC5A", {"source": "local"}),
        }
        self.present = set(self.routes)
        self.resolutions: list[tuple[str, bool]] = []
        self.connected: list[BLEDevice] = []
        self.callbacks: list[tuple[str, bluetooth.BluetoothCallback]] = []
        self.unavailable_callbacks: list[
            tuple[str, Callable[[bluetooth.BluetoothServiceInfoBleak], None]]
        ] = []
        self.now = 1000.0

    def info(
        self, address: str = UPSTAIRS, *, connectable: bool = True
    ) -> bluetooth.BluetoothServiceInfoBleak:
        device = self.routes.get(address) or BLEDevice(address, "EasyStart_88CD", {})
        return bluetooth.BluetoothServiceInfoBleak(
            name=device.name or address,
            address=address,
            rssi=-50,
            manufacturer_data={},
            service_data={},
            service_uuids=[],
            source="proxy",
            device=device,
            advertisement=None,
            connectable=connectable,
            time=self.now,
            tx_power=None,
        )

    def resolve(
        self, hass: HomeAssistant, address: str, connectable: bool = True
    ) -> BLEDevice | None:
        self.resolutions.append((address, connectable))
        return self.routes.get(address) if address in self.present else None

    def address_present(
        self, hass: HomeAssistant, address: str, connectable: bool = True
    ) -> bool:
        return address in self.present

    def last_info(
        self, hass: HomeAssistant, address: str, connectable: bool = True
    ) -> bluetooth.BluetoothServiceInfoBleak | None:
        return (
            self.info(address, connectable=connectable)
            if address in self.present
            else None
        )

    def register(
        self,
        hass: HomeAssistant,
        callback: bluetooth.BluetoothCallback,
        match: bluetooth.BluetoothCallbackMatcher,
        mode: bluetooth.BluetoothScanningMode,
    ) -> Callable[[], None]:
        item = (match["address"], callback)
        self.callbacks.append(item)
        return lambda: self.callbacks.remove(item)

    def track_unavailable(
        self,
        hass: HomeAssistant,
        callback: Callable[[bluetooth.BluetoothServiceInfoBleak], None],
        address: str,
        connectable: bool = True,
    ) -> Callable[[], None]:
        item = (address, callback)
        self.unavailable_callbacks.append(item)
        return lambda: self.unavailable_callbacks.remove(item)

    def advertise(self, address: str = UPSTAIRS) -> None:
        self.present.add(address)
        for target, callback in list(self.callbacks):
            if target == address:
                callback(self.info(address), bluetooth.BluetoothChange.ADVERTISEMENT)

    def disappear(self, address: str = UPSTAIRS) -> None:
        self.present.discard(address)
        for target, callback in list(self.unavailable_callbacks):
            if target == address:
                callback(self.info(address))

    async def establish(
        self,
        client_class: type[BleakClient],
        device: BLEDevice,
        name: str,
        *,
        max_attempts: int,
        disconnected_callback: Callable[[BleakClient], None],
    ) -> BleakClient:
        self.connected.append(device)
        self.attempts.append(max_attempts)
        client = FakeBleakClient(self)
        client.disconnected_callback = disconnected_callback
        self.clients.append(client)
        await self.pause("connect")
        return cast(BleakClient, client)


@pytest.fixture
async def ble(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    enable_custom_integrations: None,
) -> BluetoothHarness:
    # Bluetooth manager/hardware are the external boundary. Everything in this
    # custom integration and HA's config/entity/service machinery stays real.
    mock_integration(hass, MockModule("bluetooth"))
    fake = BluetoothHarness(hass)
    monkeypatch.setattr(bluetooth, "async_ble_device_from_address", fake.resolve)
    monkeypatch.setattr(bluetooth, "async_address_present", fake.address_present)
    monkeypatch.setattr(bluetooth, "async_last_service_info", fake.last_info)
    monkeypatch.setattr(bluetooth, "async_register_callback", fake.register)
    monkeypatch.setattr(bluetooth, "async_track_unavailable", fake.track_unavailable)
    monkeypatch.setattr(client_module, "establish_connection", fake.establish)
    monkeypatch.setattr(client_module, "sleep", fake.settle)
    return fake


@pytest.fixture
async def loaded(hass: HomeAssistant, ble: BluetoothHarness) -> MockConfigEntry:
    entry = make_entry()
    entry.add_to_hass(hass)
    ble.replies = [chunks(EEPROM), chunks(LIVE)]
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry
