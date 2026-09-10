"""Exercise transaction safety using an in-memory peripheral, never real BLE."""

import asyncio
import inspect
from typing import cast

import pytest
from bleak import BleakClient

from custom_components.microair_bt.microair import client as client_module
from custom_components.microair_bt.microair.client import (
    WRITE_UUID,
    CommandFailed,
    CommandTimeout,
    MicroAirClient,
)
from custom_components.microair_bt.microair.protocol import Command, ProtocolError
from tests.conftest import DEVICE, FakeRadio
from tests.test_protocol import BANNED, eeprom_buffer, live_buffer


async def test_chunked_eeprom_then_live(
    radio: FakeRadio, caplog: pytest.LogCaptureFixture
) -> None:
    raw = eeprom_buffer()
    radio.replies = [
        [raw[i : i + 20] for i in range(0, 1100, 20)] + [b"Success\r\n"],
        [live_buffer(), b"Success"],
    ]
    notifications: list[bytes] = []
    client = MicroAirClient(
        DEVICE, max_attempts=2, on_notification=notifications.append
    )
    with caplog.at_level("DEBUG"):
        async with client.transaction():
            assert (await client.read_eeprom()).raw == raw
            assert (await client.read_live()).raw == live_buffer()
            assert client.mtu_size == 23
            assert client.services.get_characteristic(WRITE_UUID) is not None
    assert radio.trace == [
        "connect",
        "notify",
        "settle",
        "write",
        "write",
        "disconnect",
    ]
    assert radio.attempts == [2]
    assert radio.clients[0].writes == [
        (WRITE_UUID, b'{"Cmd": ReadEEP}', True),
        (WRITE_UUID, b'{"Cmd": ReadLive}', True),
    ]
    assert len(notifications) == 58
    assert "23" in caplog.text
    assert not radio.clients[0].is_connected


@pytest.mark.parametrize("with_response", [True, False])
async def test_characteristic_write_type(radio: FakeRadio, with_response: bool) -> None:
    radio.properties = ["write"] if with_response else ["write-without-response"]
    radio.replies = [[live_buffer(), b"Success"]]
    client = MicroAirClient(DEVICE, max_attempts=4)
    async with client.transaction():
        await client.read_live()
    assert radio.clients[0].writes[0][2] is with_response
    assert radio.attempts == [4]


@pytest.mark.parametrize("reply", [b"Fail", b"Fail\r\n", b"Success Fail"])
async def test_failure_poisons_until_next_transaction(
    radio: FakeRadio, reply: bytes
) -> None:
    radio.replies = [[reply], [live_buffer(), b"Success"]]
    client = MicroAirClient(DEVICE, max_attempts=2)
    async with client.transaction():
        with pytest.raises(CommandFailed):
            await client.read_live()
        assert not radio.clients[0].is_connected
        with pytest.raises(ProtocolError):
            await client.read_live()
    async with client.transaction():
        assert (await client.read_live()).raw == live_buffer()
    assert len(radio.clients) == 2


@pytest.mark.parametrize("stage", ["write", "reply"])
async def test_deadline_bounds_write_and_reply(radio: FakeRadio, stage: str) -> None:
    radio.replies = [[]]
    radio.block = "write" if stage == "write" else None
    client = MicroAirClient(DEVICE, max_attempts=2)
    async with client.transaction():
        with pytest.raises(CommandTimeout):
            await client.run(Command.READ_LIVE, timeout=0.01)
        assert not radio.clients[0].is_connected
        with pytest.raises(ProtocolError):
            await client.run(Command.READ_LIVE, timeout=1)
    radio.block = None
    radio.replies = [[live_buffer(), b"Success"]]
    async with client.transaction():
        assert (await client.read_live()).raw == live_buffer()


async def test_old_generation_cannot_finish_new_command(radio: FakeRadio) -> None:
    client = MicroAirClient(DEVICE, max_attempts=2)
    radio.replies = [[]]
    async with client.transaction():
        with pytest.raises(CommandTimeout):
            await client.run(Command.READ_LIVE, timeout=0.01)
    old = radio.clients[0]
    radio.block = "write"
    radio.replies = [[]]

    async def reader() -> bytes:
        async with client.transaction():
            return await client.run(Command.READ_LIVE, timeout=1)

    task = asyncio.create_task(reader())
    await asyncio.wait_for(radio.entered.wait(), 1)
    old.emit(b"Fail")
    old.emit(b"Success")
    old.emit(bytes(100))
    assert old.disconnected_callback is not None
    old.disconnected_callback(cast(BleakClient, old))
    radio.release.set()
    await asyncio.sleep(0)
    assert not task.done()
    radio.clients[1].emit(live_buffer())
    radio.clients[1].emit(b"Success")
    assert await task == live_buffer()


async def test_transactions_serialize(radio: FakeRadio) -> None:
    client = MicroAirClient(DEVICE, max_attempts=2)
    radio.replies = [[live_buffer(), b"Success"], [live_buffer(), b"Success"]]
    entered = asyncio.Event()
    release = asyncio.Event()

    async def first() -> None:
        async with client.transaction():
            entered.set()
            await release.wait()
            await client.read_live()

    async def second() -> None:
        async with client.transaction():
            await client.read_live()

    one = asyncio.create_task(first())
    await entered.wait()
    two = asyncio.create_task(second())
    await asyncio.sleep(0)
    assert len(radio.clients) == 1
    release.set()
    await asyncio.gather(one, two)
    assert radio.trace == ["connect", "notify", "settle", "write", "disconnect"] * 2
    assert all(not client.is_connected for client in radio.clients)


@pytest.mark.parametrize(
    "stage", ["connect", "notify", "settle", "write", "reply", "disconnect"]
)
async def test_cancellation_at_each_await_disconnects(
    radio: FakeRadio, stage: str
) -> None:
    client = MicroAirClient(DEVICE, max_attempts=2)
    radio.block = stage if stage != "reply" else "write"
    radio.replies = [[]] if stage == "reply" else [[live_buffer(), b"Success"]]

    async def transaction() -> None:
        async with client.transaction():
            await client.read_live()

    task = asyncio.create_task(transaction())
    await asyncio.wait_for(radio.entered.wait(), 1)
    if stage == "reply":
        radio.release.set()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
    task.cancel()
    await asyncio.sleep(0)
    radio.release.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 1)
    assert not radio.clients[0].is_connected
    radio.block = None
    radio.replies = [[live_buffer(), b"Success"]]
    async with client.transaction():
        assert (await client.read_live()).raw == live_buffer()


async def test_cancellation_while_waiting_for_lock_does_not_disconnect_owner(
    radio: FakeRadio,
) -> None:
    client = MicroAirClient(DEVICE, max_attempts=2)
    radio.replies = [[live_buffer(), b"Success"]]

    async def waiter() -> None:
        async with client.transaction():
            pytest.fail("Waiter must not acquire the active transaction")

    async with client.transaction():
        task = asyncio.create_task(waiter())
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert radio.clients[0].is_connected
        assert (await client.read_live()).raw == live_buffer()


async def test_repeated_cancellation_waits_for_disconnect(radio: FakeRadio) -> None:
    client = MicroAirClient(DEVICE, max_attempts=2)
    radio.replies = [[live_buffer(), b"Success"]]
    radio.block = "disconnect"

    async def transaction() -> None:
        async with client.transaction():
            await client.read_live()

    task = asyncio.create_task(transaction())
    await asyncio.wait_for(radio.entered.wait(), 1)
    task.cancel()
    await asyncio.sleep(0)
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    radio.release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not radio.clients[0].is_connected


@pytest.mark.parametrize(
    ("cmd", "chunks"),
    [
        (Command.READ_LIVE, [bytes(64), b"x"]),
        (Command.READ_EEP, [eeprom_buffer(), b"x"]),
        (Command.READ_LIVE, [bytes(65)]),
        (Command.READ_EEP, [bytes(1101)]),
        (Command.READ_LIVE, [b"Success"]),
        (Command.READ_EEP, [bytes(909), b"Success"]),
        (Command.READ_LIVE, [bytes(17), b"Success"]),
    ],
)
async def test_malformed_or_overflow_poisons(
    radio: FakeRadio, cmd: Command, chunks: list[bytes]
) -> None:
    radio.replies = [chunks]
    client = MicroAirClient(DEVICE, max_attempts=2)
    async with client.transaction():
        with pytest.raises(ProtocolError):
            await client.run(cmd, timeout=1)
        assert not radio.clients[0].is_connected
        with pytest.raises(ProtocolError):
            await client.read_live()


async def test_mask_drops_binary_and_warns(
    radio: FakeRadio, caplog: pytest.LogCaptureFixture
) -> None:
    radio.replies = [[bytes(2000), b"Success"]]
    client = MicroAirClient(DEVICE, max_attempts=4)
    async with client.transaction():
        await client.write_startup_mask(0x1F)
    assert "binary" in caplog.text.lower()
    assert radio.clients[0].writes == [(WRITE_UUID, b'{"Cmd": SMask=1F}', True)]


@pytest.mark.parametrize("bad", [-1, 32, None, True, "01", b"01", 1.0])
async def test_mask_rejects_invalid_values_without_sending(
    radio: FakeRadio, bad: object
) -> None:
    client = MicroAirClient(DEVICE, max_attempts=4)
    async with client.transaction():
        with pytest.raises((ValueError, TypeError)):
            await client.write_startup_mask(cast(int, bad))
    assert not radio.clients[0].writes


async def test_public_run_cannot_bypass_mask_entry_point(radio: FakeRadio) -> None:
    client = MicroAirClient(DEVICE, max_attempts=2)
    async with client.transaction():
        with pytest.raises(ValueError):
            await client.run(Command.SET_STARTUP_MASK, 1, timeout=1)
    assert not radio.clients[0].writes


@pytest.mark.parametrize(
    "token", BANNED + ('{"Cmd": ReadLive}\n', '{"Cmd": SMask=GG}', '{"Cmd": SMask=001}')
)
async def test_single_write_site_rejects_banned_payloads(
    radio: FakeRadio, monkeypatch: pytest.MonkeyPatch, token: str
) -> None:
    def corrupt_build(cmd: Command, arg: int | None = None) -> bytes:
        return token.encode()

    monkeypatch.setattr(client_module, "build", corrupt_build)
    client = MicroAirClient(DEVICE, max_attempts=2)
    async with client.transaction():
        with pytest.raises(AssertionError):
            await client.read_live()
    assert not radio.clients[0].writes
    assert inspect.getsource(client_module).count(".write_gatt_char(") == 1


async def test_requires_owned_transaction(radio: FakeRadio) -> None:
    client = MicroAirClient(DEVICE, max_attempts=2)
    with pytest.raises(ProtocolError):
        await client.read_live()
    async with client.transaction():
        with pytest.raises(ProtocolError):
            async with client.transaction():
                pytest.fail("Nested transaction must not deadlock")
        with pytest.raises(ProtocolError):
            await asyncio.create_task(client.read_live())
    assert not radio.clients[0].writes


@pytest.mark.parametrize("stage", ["notify", "write"])
async def test_transport_exception_disconnects(radio: FakeRadio, stage: str) -> None:
    radio.error_at = stage
    client = MicroAirClient(DEVICE, max_attempts=2)
    with pytest.raises(OSError):
        async with client.transaction():
            await client.read_live()
    assert not radio.clients[0].is_connected


async def test_unexpected_disconnect_fails_pending_command(radio: FakeRadio) -> None:
    client = MicroAirClient(DEVICE, max_attempts=2)
    radio.block = "write"
    radio.replies = [[]]

    async def reader() -> None:
        async with client.transaction():
            await client.read_live()

    task = asyncio.create_task(reader())
    await asyncio.wait_for(radio.entered.wait(), 1)
    await radio.clients[0].disconnect()
    radio.release.set()
    with pytest.raises(ProtocolError):
        await task


@pytest.mark.parametrize("stage", ["write", "reply"])
async def test_caught_command_cancellation_still_poisons(
    radio: FakeRadio, stage: str
) -> None:
    client = MicroAirClient(DEVICE, max_attempts=2)
    radio.block = "write"
    radio.replies = [[]]

    async def owner() -> None:
        async with client.transaction():
            try:
                await client.read_live()
            except asyncio.CancelledError:
                assert not radio.clients[0].is_connected
                with pytest.raises(ProtocolError):
                    await client.read_live()
                raise

    task = asyncio.create_task(owner())
    await asyncio.wait_for(radio.entered.wait(), 1)
    if stage == "reply":
        radio.release.set()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not radio.clients[0].is_connected
