"""Typed, in-memory GATT fixtures; no test may touch a real Bluetooth adapter."""

import asyncio
from collections.abc import Callable
from typing import cast

import pytest
from bleak import BleakClient, BleakScanner
from bleak.assigned_numbers import CharacteristicPropertyName
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.descriptor import BleakGATTDescriptor
from bleak.backends.device import BLEDevice
from bleak.backends.service import BleakGATTService, BleakGATTServiceCollection

from custom_components.microair_bt.microair import client as client_module
from custom_components.microair_bt.microair.client import (
    NOTIFY_UUID,
    SERVICE_UUID,
    WRITE_UUID,
)

DEVICE = BLEDevice("AA:BB:CC:DD:EE:FF", "EasyStart_TEST", None)


@pytest.fixture(autouse=True)
def forbid_real_bluetooth(monkeypatch: pytest.MonkeyPatch) -> None:
    async def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("Tests must never access real Bluetooth")

    monkeypatch.setattr(BleakClient, "connect", forbidden)
    monkeypatch.setattr(BleakClient, "write_gatt_char", forbidden)
    monkeypatch.setattr(BleakScanner, "start", forbidden)


class FakeBleakClient:
    def __init__(self, radio: "FakeRadio") -> None:
        self.radio = radio
        self.is_connected = True
        self.mtu_size = 23
        self.services = BleakGATTServiceCollection()
        service = BleakGATTService(None, 1, SERVICE_UUID)
        self.services.add_service(service)
        self.notify = BleakGATTCharacteristic(
            None, 2, NOTIFY_UUID, ["notify"], lambda: 20, service
        )
        self.write = BleakGATTCharacteristic(
            None, 3, WRITE_UUID, radio.properties, lambda: 20, service
        )
        self.services.add_characteristic(self.notify)
        self.services.add_characteristic(self.write)
        self.services.add_descriptor(
            BleakGATTDescriptor(
                None, 4, "00002902-0000-1000-8000-00805f9b34fb", self.notify
            )
        )
        self.callback: Callable[[BleakGATTCharacteristic, bytearray], None] | None = (
            None
        )
        self.disconnected_callback: Callable[[BleakClient], None] | None = None
        self.writes: list[tuple[str, bytes, bool]] = []
        self.write_cancelled = False

    async def start_notify(
        self,
        characteristic: str,
        callback: Callable[[BleakGATTCharacteristic, bytearray], None],
    ) -> None:
        assert characteristic == NOTIFY_UUID
        self.callback = callback
        await self.radio.pause("notify")

    async def write_gatt_char(
        self, characteristic: BleakGATTCharacteristic, payload: bytes, *, response: bool
    ) -> None:
        assert self.is_connected
        self.writes.append((characteristic.uuid, payload, response))
        try:
            await self.radio.pause("write")
            for chunk in self.radio.replies.pop(0):
                self.emit(chunk)
        except asyncio.CancelledError:
            self.write_cancelled = True
            raise

    def emit(self, payload: bytes) -> None:
        assert self.callback is not None
        self.callback(self.notify, bytearray(payload))

    async def disconnect(self) -> None:
        await self.radio.pause("disconnect")
        self.is_connected = False
        if self.disconnected_callback is not None:
            self.disconnected_callback(cast(BleakClient, self))


class FakeRadio:
    def __init__(self) -> None:
        self.clients: list[FakeBleakClient] = []
        self.properties: list[CharacteristicPropertyName] = [
            "write",
            "write-without-response",
        ]
        self.replies: list[list[bytes]] = []
        self.trace: list[str] = []
        self.block: str | None = None
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.attempts: list[int] = []
        self.error_at: str | None = None

    async def pause(self, stage: str) -> None:
        self.trace.append(stage)
        if self.block == stage:
            self.entered.set()
            await self.release.wait()
        if self.error_at == stage:
            raise OSError(f"Synthetic {stage} failure")
        await asyncio.sleep(0)

    async def establish(
        self,
        client_class: type[BleakClient],
        device: BLEDevice,
        name: str,
        *,
        max_attempts: int,
        disconnected_callback: Callable[[BleakClient], None],
    ) -> BleakClient:
        assert client_class is BleakClient
        assert device is DEVICE
        assert name == DEVICE.name
        self.attempts.append(max_attempts)
        client = FakeBleakClient(self)
        client.disconnected_callback = disconnected_callback
        self.clients.append(client)
        await self.pause("connect")
        return cast(BleakClient, client)

    async def settle(self, delay: float) -> None:
        assert delay == 0.5
        await self.pause("settle")


@pytest.fixture
def radio(monkeypatch: pytest.MonkeyPatch) -> FakeRadio:
    fake = FakeRadio()
    monkeypatch.setattr(client_module, "establish_connection", fake.establish)
    monkeypatch.setattr(client_module, "sleep", fake.settle)
    return fake
