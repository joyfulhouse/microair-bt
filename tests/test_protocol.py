"""Wire fixtures from wiki/ble-protocol.md and wiki/available-data.md."""

from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import cast

import pytest

from custom_components.microair_bt.microair.protocol import (
    FAULT_MASK_MAX,
    SCPT_MAX,
    SCPT_MIN,
    Command,
    Completion,
    FaultProtection,
    ProtocolError,
    StartupFlag,
    StartupMode,
    StatusCode,
    build,
    fault_protection_mask,
    flag_mask,
    has_unsupported_bits,
    is_completion,
    mode_from_mask,
    mode_mask,
    parse_eeprom,
    parse_live,
    superlearn_available,
)

BANNED = (
    '{"Cmd": ProgMode}',
    '{"Cmd": ChipErase}',
    '{"Cmd": WrtFsL=00}',
    '{"Cmd": WrtFsH=00}',
    '{"Cmd": WrtFsE=00}',
    '{"Cmd": WrtLkB=00}',
    '{"Cmd": NormMode}',
    '{"Cmd": OtaPrep}',
    '{"Cmd": OtaBegin}',
    '{"Cmd": OtaWrt}',
    '{"Cmd": OtaAbort}',
    '{"Cmd": OtaEnd}',
    '{"Int": FlashBuff}',
    '{"Wrt": FlashBuff}',
    '{"End": FlashBuff}',
    '{"Wrt": EEP=0000}',
    '{"Ver": EEP=0000}',
    '{"Wrt": FlashPg=00}',
    '{"Ver": FlashPg=00}',
    '{"Cmd": SCPT=00}',
    '{"Cmd": FMask=00}',
)


@pytest.mark.parametrize(
    ("cmd", "arg", "hex_value"),
    [
        (Command.READ_EEP, None, "7B22436D64223A20526561644545507D"),
        (Command.READ_LIVE, None, "7B22436D64223A20526561644C6976657D"),
        (Command.SET_STARTUP_MASK, 1, "7B22436D64223A20534D61736B3D30317D"),
        (Command.SET_SCPT, 1, "7B22436D64223A20534350543D30317D"),
        (Command.SET_SCPT, 250, "7B22436D64223A20534350543D46417D"),
        (Command.SET_FAULT_MASK, 0x7F, "7B22436D64223A20464D61736B3D37467D"),
    ],
)
def test_exact_bytes(cmd: Command, arg: int | None, hex_value: str) -> None:
    assert build(cmd, arg) == bytes.fromhex(hex_value)


def test_whitelist_is_exhaustive() -> None:
    assert {cmd.name for cmd in Command} == {
        "READ_EEP",
        "READ_LIVE",
        "SET_STARTUP_MASK",
        "SET_SCPT",
        "SET_FAULT_MASK",
    }
    outputs = {build(Command.READ_EEP), build(Command.READ_LIVE)}
    outputs.update(build(Command.SET_STARTUP_MASK, mask) for mask in range(32))
    outputs.update(
        build(Command.SET_SCPT, minutes) for minutes in range(SCPT_MIN, SCPT_MAX + 1)
    )
    outputs.update(
        build(Command.SET_FAULT_MASK, mask) for mask in range(1, FAULT_MASK_MAX + 1)
    )
    assert len(outputs) == 2 + 32 + 250 + 127
    assert not outputs.intersection(token.encode() for token in BANNED)
    for mask in range(32):
        assert (
            build(Command.SET_STARTUP_MASK, mask)
            == ('{"Cmd": SMask=' + f"{mask:02X}" + "}").encode()
        )
    assert all(16 <= len(payload) <= 17 for payload in outputs)


@pytest.mark.parametrize("arg", [None, 0, 251, 255, 256, True, 1.0, "5", b"5"])
def test_invalid_scpt(arg: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        build(Command.SET_SCPT, cast(int, arg))


@pytest.mark.parametrize("arg", [None, 0, 0x80, 0xFF, 256, True, 1.0, "7F"])
def test_invalid_fault_mask(arg: object) -> None:
    # Zero would disable every protection; it is refused at the lowest layer.
    with pytest.raises((TypeError, ValueError)):
        build(Command.SET_FAULT_MASK, cast(int, arg))


@pytest.mark.parametrize("token", BANNED)
def test_banned_commands_cannot_be_built(token: str) -> None:
    with pytest.raises((TypeError, ValueError)):
        build(cast(Command, token))
    with pytest.raises((TypeError, ValueError)):
        build(cast(Command, token.encode()))


@pytest.mark.parametrize("arg", [None, -1, 32, 255, True, 1.5, "01", b"01"])
def test_invalid_mask(arg: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        build(Command.SET_STARTUP_MASK, cast(int, arg))


@pytest.mark.parametrize("cmd", [Command.READ_EEP, Command.READ_LIVE])
@pytest.mark.parametrize("arg", [0, 1, True, "injection"])
def test_reads_reject_arguments(cmd: Command, arg: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        build(cmd, cast(int, arg))


@pytest.mark.parametrize(
    ("current", "mode", "expected"),
    [
        (0, StartupMode.RELEARN, 1),
        (0, StartupMode.DEFAULT_RAMP, 2),
        (0, StartupMode.NORMAL, 0),
        (2, StartupMode.RELEARN, 1),
        (0x14, StartupMode.RELEARN, 0x05),
        (0x1F, StartupMode.RELEARN, 0x0D),
        (0x10, StartupMode.NORMAL, 0x10),
        (0x14, StartupMode.NORMAL, 0x14),
        (0x12, StartupMode.DEFAULT_RAMP, 0x12),
        (0x11, StartupMode.DEFAULT_RAMP, 0x12),
        (0x0C, StartupMode.SUPERLEARN, 0x1D),
        (0x03, StartupMode.SUPERLEARN, 0x11),
    ],
)
def test_mode_mask(current: int, mode: StartupMode, expected: int) -> None:
    # Bits 2-3 (flags) are preserved; bits 0-1 belong to the mode. The
    # SuperLearn label bit 4 persists except when plain relearn is chosen.
    assert mode_mask(current, mode) == expected


@pytest.mark.parametrize(("firmware", "offered"), [(28, False), (29, True), (37, True)])
def test_superlearn_available(firmware: int, offered: bool) -> None:
    assert superlearn_available(firmware) is offered


def test_superlearn_available_rejects_non_int() -> None:
    with pytest.raises((TypeError, ValueError)):
        superlearn_available(cast(int, "37"))


@pytest.mark.parametrize(
    ("mask", "mode"),
    [
        (0x00, StartupMode.NORMAL),
        (0x01, StartupMode.RELEARN),
        (0x02, StartupMode.DEFAULT_RAMP),
        (0x11, StartupMode.SUPERLEARN),
        (0x10, StartupMode.NORMAL),
        (0x15, StartupMode.SUPERLEARN),
        (0x05, StartupMode.RELEARN),
        (0x03, StartupMode.RELEARN),
        (0x0E, StartupMode.DEFAULT_RAMP),
        (0x12, StartupMode.DEFAULT_RAMP),
    ],
)
def test_mode_from_mask(mask: int, mode: StartupMode) -> None:
    assert mode_from_mask(mask) is mode


@pytest.mark.parametrize(
    ("current", "flag", "enabled", "expected"),
    [
        (0x00, StartupFlag.NO_POWER_UP_DELAY, True, 0x04),
        (0x15, StartupFlag.NO_POWER_UP_DELAY, False, 0x11),
        (0x01, StartupFlag.START_DELAY_MODE, True, 0x09),
        (0x0F, StartupFlag.START_DELAY_MODE, False, 0x07),
        (0x04, StartupFlag.NO_POWER_UP_DELAY, True, 0x04),
    ],
)
def test_flag_mask(
    current: int, flag: StartupFlag, enabled: bool, expected: int
) -> None:
    assert flag_mask(current, flag, enabled) == expected


def test_startup_flags_are_the_app_bits() -> None:
    assert int(StartupFlag.NO_POWER_UP_DELAY) == 0x04
    assert int(StartupFlag.START_DELAY_MODE) == 0x08
    assert [int(bit) for bit in FaultProtection] == [1, 2, 4, 8, 16, 32, 64]


@pytest.mark.parametrize(
    ("current", "bit", "enabled", "expected"),
    [
        (0x7F, FaultProtection.COMPRESSOR_STALL, False, 0x7B),
        (0x7B, FaultProtection.COMPRESSOR_STALL, True, 0x7F),
        (0x01, FaultProtection.UNEXPECTED_CURRENT, True, 0x01),
        (0x41, FaultProtection.WIRING_ISSUE, False, 0x01),
    ],
)
def test_fault_protection_mask(
    current: int, bit: FaultProtection, enabled: bool, expected: int
) -> None:
    assert fault_protection_mask(current, bit, enabled) == expected


def test_fault_protection_mask_refuses_disabling_everything() -> None:
    with pytest.raises(ValueError, match="at least one"):
        fault_protection_mask(0x01, FaultProtection.UNEXPECTED_CURRENT, False)


@pytest.mark.parametrize("bad", [-1, 256, True, "7F"])
def test_fault_protection_mask_rejects_bad_current(bad: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        fault_protection_mask(cast(int, bad), FaultProtection.OVERCURRENT, True)
    with pytest.raises((TypeError, ValueError)):
        flag_mask(cast(int, bad), StartupFlag.NO_POWER_UP_DELAY, True)
    with pytest.raises((TypeError, ValueError)):
        mode_from_mask(cast(int, bad))


@pytest.mark.parametrize("mask", range(256))
def test_unsupported_bits(mask: int) -> None:
    assert has_unsupported_bits(mask) is (mask >= 32)


@pytest.mark.parametrize("bad", [-1, 256, True, "00"])
def test_invalid_current_mask(bad: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        mode_mask(cast(int, bad), StartupMode.NORMAL)
    with pytest.raises((TypeError, ValueError)):
        has_unsupported_bits(cast(int, bad))


def test_invalid_mode() -> None:
    with pytest.raises((TypeError, ValueError)):
        mode_mask(0, cast(StartupMode, "relearn"))


@pytest.mark.parametrize("token", [b"Success", b"Fail"])
def test_completion(token: bytes) -> None:
    envelope = b'{"Sts": ' + token + b"}"
    expected = Completion.OK if token == b"Success" else Completion.FAIL
    for suffix in (b"", b"\r", b"\n", b"\0", b"\r\n\0"):
        assert is_completion(envelope + suffix) is expected
    for invalid in (
        token,
        b"prefix " + envelope,
        envelope + b" trailing",
        b'{"Other": ' + token + b"}",
        b'{"Sts": "' + token + b'"}',
        b'{"Sts": ' + token.lower() + b"}",
        b'{"Sts": ' + token + b"Extra}",
        b'{"Sts":Success}',
        b'{"Sts": Success Fail}',
        b"Success Fail",
        b"Fail then Success",
        b"\x01" + envelope,
        envelope + b"\x80",
        envelope + b"\0x",
        envelope + b" ",
        envelope + b"\t",
        envelope + b"\v",
        envelope + b"\f",
        b"x" * 57 + b"Success",
        b"",
    ):
        assert is_completion(invalid) is None, invalid


def live_buffer(length: int = 20) -> bytes:
    buf = bytearray(length)
    buf[:18] = bytes.fromhex("1234 02 ff 7b00 8d20 c801 2c01 f401 78563412")
    return bytes(buf)


def eeprom_buffer(length: int = 1100) -> bytes:
    buf = bytearray(length)
    buf[:2] = (length - 2).to_bytes(2, "little")
    buf[2:9] = b"398ULBT"
    buf[10] = 29
    buf[906:909] = bytes([0x15, 0x7F, 5])
    return bytes(buf)


@pytest.mark.parametrize("length", [18, 20, 64])
def test_live_fields(length: int) -> None:
    raw = live_buffer(length)
    data = parse_live(raw)
    assert data.raw == raw
    assert data.status is StatusCode.SHORT_CYCLE_DELAY
    assert data.raw_status == 2
    assert data.learned_starts == 255
    assert data.current_a == 12.3
    assert data.line_hz == pytest.approx(500000 / 8333)
    assert data.last_start_peak_a == 45.6
    assert data.scpt_delay_s == 300
    assert data.total_faults == 500
    assert data.total_starts == 0x12345678
    with pytest.raises(FrozenInstanceError):
        data.__setattr__("total_starts", 0)


@pytest.mark.parametrize("status", range(256))
def test_live_status_and_zero_period(status: int) -> None:
    buf = bytearray(18)
    buf[2] = status
    data = parse_live(bytes(buf))
    assert data.raw_status == status
    assert data.status is (StatusCode(status) if status < 10 else StatusCode.UNKNOWN)
    assert data.line_hz is None
    assert len(StatusCode) == 11


@pytest.mark.parametrize("length", [0, 17, 65, 1100])
def test_live_length_bounds(length: int) -> None:
    with pytest.raises(ProtocolError):
        parse_live(bytes(length))


@pytest.mark.parametrize("length", [909, 1100])
def test_eeprom_fields(length: int) -> None:
    raw = eeprom_buffer(length)
    data = parse_eeprom(raw)
    assert (data.model, data.firmware) == ("398ULBT", 29)
    assert (data.startup_mask, data.fault_mask, data.scpt_minutes) == (0x15, 0x7F, 5)
    assert data.raw == raw
    with pytest.raises(FrozenInstanceError):
        data.__setattr__("model", "changed")


@pytest.mark.parametrize("length", [0, 908, 1101])
def test_eeprom_length_bounds(length: int) -> None:
    with pytest.raises(ProtocolError):
        parse_eeprom(bytes(length))


@pytest.mark.parametrize(
    "bad", [b"\xff98ULBT", b"398ULB\0", b"398ULB\n", b"398ULB\x7f"]
)
def test_eeprom_rejects_nonprintable_model(bad: bytes) -> None:
    buf = bytearray(eeprom_buffer())
    buf[2:9] = bad
    with pytest.raises(ProtocolError):
        parse_eeprom(bytes(buf))


def test_eeprom_golden_captures() -> None:
    fixtures = Path(__file__).parent / "fixtures"
    truncated = (fixtures / "capture-06-ReadEEP.bin").read_bytes()
    complete = (fixtures / "capture-08-ReadEEP.bin").read_bytes()
    assert len(truncated) == 923
    assert len(complete) == 1023
    assert truncated[:2] == complete[:2] == b"\xfd\x03"
    with pytest.raises(ProtocolError, match="length"):
        parse_eeprom(truncated)
    data = parse_eeprom(complete)
    assert data.startup_mask == 0x00
    assert data.model == "398ULBT"
    assert data.raw == complete


def test_eeprom_rejects_1020_byte_partial_capture() -> None:
    complete = (
        Path(__file__).parent / "fixtures" / "capture-08-ReadEEP.bin"
    ).read_bytes()
    assert len(complete) == 1023
    partial = complete[:1020]
    assert len(partial) == 1020
    assert partial[:2] == complete[:2] == b"\xfd\x03"
    with pytest.raises(ProtocolError, match="length"):
        parse_eeprom(partial)


@pytest.mark.parametrize("length", [909, 923, 1023, 1100])
def test_eeprom_requires_exact_length_prefix(length: int) -> None:
    raw = eeprom_buffer(length)
    assert parse_eeprom(raw).raw == raw
    for declared_length in (0, length - 3, length - 1, length, 65535):
        malformed = declared_length.to_bytes(2, "little") + raw[2:]
        with pytest.raises(ProtocolError, match="length"):
            parse_eeprom(malformed)
