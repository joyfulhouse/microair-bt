"""Exercise transaction safety using an in-memory peripheral, never real BLE."""

import asyncio
import inspect
from pathlib import Path
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
from custom_components.microair_bt.microair.protocol import (
    Command,
    ProtocolError,
)
from tests.conftest import DEVICE, FakeRadio
from tests.test_protocol import BANNED, eeprom_buffer, live_buffer


async def test_chunked_eeprom_then_live(
    radio: FakeRadio, caplog: pytest.LogCaptureFixture
) -> None:
    raw = eeprom_buffer()
    radio.replies = [
        [raw[i : i + 20] for i in range(0, 1100, 20)] + [b'{"Sts": Success}\r\n'],
        [live_buffer(), b'{"Sts": Success}'],
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
    radio.replies = [[live_buffer(), b'{"Sts": Success}']]
    client = MicroAirClient(DEVICE, max_attempts=4)
    async with client.transaction():
        await client.read_live()
    assert radio.clients[0].writes[0][2] is with_response
    assert radio.attempts == [4]


@pytest.mark.parametrize(
    "reply", [b'{"Sts": Fail}', b'{"Sts": Fail}\r\n', b'{"Sts": Fail}\0']
)
async def test_failure_poisons_until_next_transaction(
    radio: FakeRadio, reply: bytes
) -> None:
    radio.replies = [[reply], [live_buffer(), b'{"Sts": Success}']]
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
    radio.replies = [[live_buffer(), b'{"Sts": Success}']]
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
    old.emit(b'{"Sts": Fail}')
    old.emit(b'{"Sts": Success}')
    old.emit(bytes(100))
    assert old.disconnected_callback is not None
    old.disconnected_callback(cast(BleakClient, old))
    radio.release.set()
    await asyncio.sleep(0)
    assert not task.done()
    radio.clients[1].emit(live_buffer())
    radio.clients[1].emit(b'{"Sts": Success}')
    assert await task == live_buffer()


async def test_transactions_serialize(radio: FakeRadio) -> None:
    client = MicroAirClient(DEVICE, max_attempts=2)
    radio.replies = [
        [live_buffer(), b'{"Sts": Success}'],
        [live_buffer(), b'{"Sts": Success}'],
    ]
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
    radio.replies = [[]] if stage == "reply" else [[live_buffer(), b'{"Sts": Success}']]

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
    radio.replies = [[live_buffer(), b'{"Sts": Success}']]
    async with client.transaction():
        assert (await client.read_live()).raw == live_buffer()


async def test_cancellation_while_waiting_for_lock_does_not_disconnect_owner(
    radio: FakeRadio,
) -> None:
    client = MicroAirClient(DEVICE, max_attempts=2)
    radio.replies = [[live_buffer(), b'{"Sts": Success}']]

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
    radio.replies = [[live_buffer(), b'{"Sts": Success}']]
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
        (Command.READ_LIVE, [b'{"Sts": Success}']),
        (Command.READ_EEP, [bytes(909), b'{"Sts": Success}']),
        (Command.READ_LIVE, [bytes(17), b'{"Sts": Success}']),
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
    radio.replies = [
        [eeprom_buffer(), b'{"Sts": Success}'],
        [bytes(2000), b'{"Sts": Success}'],
    ]
    client = MicroAirClient(DEVICE, max_attempts=4)
    async with client.transaction():
        await client.write_startup_mask(0x01)
    assert "binary" in caplog.text.lower()
    assert radio.clients[0].writes == [
        (WRITE_UUID, b'{"Cmd": ReadEEP}', True),
        (WRITE_UUID, b'{"Cmd": SMask=15}', True),
    ]


@pytest.mark.parametrize("bad", [-1, 32, None, True, "01", b"01", 1.0])
async def test_mask_rejects_invalid_values_without_sending(
    radio: FakeRadio, bad: object
) -> None:
    client = MicroAirClient(DEVICE, max_attempts=4)
    radio.replies = [[live_buffer(), b'{"Sts": Success}']]
    async with client.transaction():
        with pytest.raises((ValueError, TypeError)):
            await client.write_startup_mask(cast(int, bad))
        assert not radio.clients[0].writes
        assert radio.clients[0].is_connected
        assert (await client.read_live()).raw == live_buffer()
    assert radio.clients[0].writes == [(WRITE_UUID, b'{"Cmd": ReadLive}', True)]


@pytest.mark.parametrize("mode", [0x03, 0x1D, 0x07])
async def test_mask_rejects_undefined_modes_before_io(
    radio: FakeRadio, mode: int
) -> None:
    radio.replies = [
        [eeprom_buffer(), b'{"Sts": Success}'],
        [b'{"Sts": Success}'],
    ]
    client = MicroAirClient(DEVICE, max_attempts=2)
    async with client.transaction():
        with pytest.raises(ValueError, match="Startup mode must be"):
            await client.write_startup_mask(mode)
        assert not radio.clients[0].writes
        assert radio.clients[0].is_connected


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


@pytest.mark.parametrize(
    ("reply", "error"),
    [
        (b'{"Sts": Fail}', CommandFailed),
        (b'{"Sts": Fail}\0', CommandFailed),
        (bytes(65), ProtocolError),
    ],
)
async def test_reply_failure_interrupts_blocked_write(
    radio: FakeRadio, reply: bytes, error: type[ProtocolError]
) -> None:
    radio.block = "write"
    client = MicroAirClient(DEVICE, max_attempts=2)

    async def owner() -> None:
        async with client.transaction():
            await client.run(Command.READ_LIVE, timeout=10)

    task = asyncio.create_task(owner())
    await asyncio.wait_for(radio.entered.wait(), 1)
    radio.clients[0].emit(reply)
    # Do not release the GATT write: the failure must cancel/drain it promptly.
    with pytest.raises(error):
        await asyncio.wait_for(task, 0.2)
    assert not radio.release.is_set()
    assert radio.clients[0].write_cancelled
    assert not radio.clients[0].is_connected


@pytest.mark.parametrize("stage", ["connect", "disconnect"])
async def test_cancellation_survives_cleanup_failure(
    radio: FakeRadio, stage: str
) -> None:
    radio.block = stage
    radio.error_at = stage
    client = MicroAirClient(DEVICE, max_attempts=2)

    async def owner() -> None:
        async with client.transaction():
            pass

    task = asyncio.create_task(owner())
    await asyncio.wait_for(radio.entered.wait(), 1)
    task.cancel()
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    radio.release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert task.cancelled()
    # A transport failure can leave physical state unknown, but no connection
    # handle may be reused, and the transaction lock must always be released.
    radio.block = None
    radio.error_at = None
    radio.replies = [[live_buffer(), b'{"Sts": Success}']]
    async with client.transaction():
        assert (await client.read_live()).raw == live_buffer()
    assert len(radio.clients) == 2


@pytest.mark.parametrize("model", [b"398ULBT", b"364ULBT", b"399BT  "])
async def test_mask_requires_fresh_model_match(radio: FakeRadio, model: bytes) -> None:
    fresh = bytearray(eeprom_buffer())
    fresh[2:9] = model
    radio.replies = [
        [eeprom_buffer(), b'{"Sts": Success}'],
        [bytes(fresh), b'{"Sts": Success}'],
        [b'{"Sts": Success}'],
    ]
    client = MicroAirClient(DEVICE, max_attempts=4)
    async with client.transaction():
        # An earlier matching model must not substitute for the fresh bind.
        assert (await client.read_eeprom()).model == "398ULBT"
        if model == b"398ULBT":
            await client.write_startup_mask(1)
        else:
            with pytest.raises(ProtocolError, match="model"):
                await client.write_startup_mask(1)
    expected = [
        (WRITE_UUID, b'{"Cmd": ReadEEP}', True),
        (WRITE_UUID, b'{"Cmd": ReadEEP}', True),
    ]
    if model == b"398ULBT":
        expected.append((WRITE_UUID, b'{"Cmd": SMask=15}', True))
    assert radio.clients[0].writes == expected
    assert len(radio.clients) == 1


@pytest.mark.parametrize("reply", [[b'{"Sts": Fail}'], [b'{"Sts": Success}']])
async def test_mask_refused_when_eeprom_read_fails(
    radio: FakeRadio, reply: list[bytes]
) -> None:
    radio.replies = [reply]
    client = MicroAirClient(DEVICE, max_attempts=4)
    async with client.transaction():
        with pytest.raises(ProtocolError):
            await client.write_startup_mask(1)
    assert radio.clients[0].writes == [(WRITE_UUID, b'{"Cmd": ReadEEP}', True)]
    assert not radio.clients[0].is_connected


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf")])
async def test_invalid_timeout_keeps_transaction_usable(
    radio: FakeRadio, timeout: float
) -> None:
    radio.replies = [[live_buffer(), b'{"Sts": Success}']]
    client = MicroAirClient(DEVICE, max_attempts=2)
    async with client.transaction():
        with pytest.raises(ValueError):
            await client.run(Command.READ_LIVE, timeout=timeout)
        assert not radio.clients[0].writes
        assert radio.clients[0].is_connected
        assert (await client.read_live()).raw == live_buffer()
    assert radio.clients[0].writes == [(WRITE_UUID, b'{"Cmd": ReadLive}', True)]


@pytest.mark.parametrize(
    ("fixture", "length"),
    [
        pytest.param("capture-06-ReadEEP.bin", 923, id="capture-06-923"),
        pytest.param("capture-08-ReadEEP.bin", 1020, id="capture-08-1020"),
    ],
)
@pytest.mark.parametrize("write_mask", [False, True], ids=["read", "write"])
async def test_truncated_capture_refused(
    radio: FakeRadio, write_mask: bool, fixture: str, length: int
) -> None:
    raw = (Path(__file__).parent / "fixtures" / fixture).read_bytes()[:length]
    assert len(raw) == length
    assert raw[:2] == b"\xfd\x03"
    radio.replies = [[raw, b'{"Sts": Success}'], [b'{"Sts": Success}']]

    client = MicroAirClient(DEVICE, max_attempts=2)
    async with client.transaction():
        with pytest.raises(ProtocolError, match="length"):
            if write_mask:
                await client.write_startup_mask(1)
            else:
                await client.read_eeprom()
        assert not radio.clients[0].is_connected
        with pytest.raises(ProtocolError):
            await client.read_live()
    assert radio.clients[0].writes == [(WRITE_UUID, b'{"Cmd": ReadEEP}', True)]


async def test_golden_eeprom_chunks_containing_status_words(radio: FakeRadio) -> None:
    raw = bytearray(
        (Path(__file__).parent / "fixtures" / "capture-08-ReadEEP.bin").read_bytes()
    )
    # Printable words inside the opaque EEPROM data must not finish a read.
    chunk = b"prefix Success Fail suffix"
    raw[100 : 100 + len(chunk)] = chunk
    radio.replies = [
        [bytes(raw[:100]), chunk, bytes(raw[100 + len(chunk) :]), b'{"Sts": Success}']
    ]
    client = MicroAirClient(DEVICE, max_attempts=2)
    async with client.transaction():
        data = await client.read_eeprom()
    assert data.raw == bytes(raw)
    assert data.model == "398ULBT"
    assert data.startup_mask == 0


@pytest.mark.parametrize("original", [0x20, 0x40, 0x80, 0xE0, 0xFF])
async def test_mask_refuses_forbidden_original_bits(
    radio: FakeRadio, original: int
) -> None:
    raw = bytearray(eeprom_buffer())
    raw[906] = original
    radio.replies = [[bytes(raw), b'{"Sts": Success}'], [b'{"Sts": Success}']]
    client = MicroAirClient(DEVICE, max_attempts=2)
    async with client.transaction():
        with pytest.raises(ProtocolError, match="[Uu]nsupported.*mask"):
            await client.write_startup_mask(1)
    assert radio.clients[0].writes == [(WRITE_UUID, b'{"Cmd": ReadEEP}', True)]


@pytest.mark.parametrize(
    ("original", "requested", "expected"),
    [
        (0x10, 0, b"10"),
        (0x10, 1, b"11"),
        (0x10, 2, b"12"),
        (0x14, 1, b"15"),
        (0x1F, 1, b"1D"),
    ],
)
async def test_mask_preserves_supported_original_bits(
    radio: FakeRadio, original: int, requested: int, expected: bytes
) -> None:
    raw = bytearray(eeprom_buffer())
    raw[906] = original
    radio.replies = [[bytes(raw), b'{"Sts": Success}'], [b'{"Sts": Success}']]
    client = MicroAirClient(DEVICE, max_attempts=2)
    async with client.transaction():
        await client.write_startup_mask(requested)
    assert radio.clients[0].writes == [
        (WRITE_UUID, b'{"Cmd": ReadEEP}', True),
        (WRITE_UUID, b'{"Cmd": SMask=' + expected + b"}", True),
    ]
