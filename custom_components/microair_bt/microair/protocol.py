"""EasyStart wire format from wiki/ble-protocol.md and wiki/available-data.md.

Buffer offsets include the two opaque prefix bytes. No peripheral identity or
checksum can be inferred from those bytes; all incoming lengths are bounded.
"""

from dataclasses import dataclass
from enum import Enum, IntEnum


class ProtocolError(ValueError):
    """A peripheral reply does not satisfy the documented wire contract."""


class Command(Enum):
    """The complete command whitelist; never accept raw caller-supplied bytes."""

    READ_EEP = "ReadEEP"
    READ_LIVE = "ReadLive"
    SET_STARTUP_MASK = "SMask"


class StartupMode(Enum):
    NORMAL = 0
    RELEARN = 1
    DEFAULT_RAMP = 2


class StatusCode(IntEnum):
    NORMAL = 0
    UNEXPECTED_CURRENT_FAULT = 1
    SHORT_CYCLE_DELAY = 2
    POWER_INTERRUPTION_FAULT = 3
    STALL_FAULT = 4
    STUCK_START_RELAY_FAULT = 5
    OPEN_OVERLOAD_FAULT = 6
    OVERCURRENT_FAULT = 7
    BAD_WIRING_FAULT = 8
    WRONG_VOLTAGE_FAULT = 9
    UNKNOWN = -1


class Completion(Enum):
    OK = "ok"
    FAIL = "fail"
    CONFLICT = "conflict"


@dataclass(frozen=True)
class LiveData:
    status: StatusCode
    raw_status: int
    learned_starts: int
    current_a: float
    line_hz: float | None
    last_start_peak_a: float
    scpt_delay_s: int
    total_faults: int
    total_starts: int
    raw: bytes


@dataclass(frozen=True)
class EepromData:
    model: str
    firmware: int
    startup_mask: int
    fault_mask: int
    scpt_minutes: int
    raw: bytes


def _validate_mask(mask: int, maximum: int) -> None:
    if type(mask) is not int or not 0 <= mask <= maximum:
        raise ValueError(f"Mask must be an integer in 0..{maximum}")


def build(cmd: Command, arg: int | None = None) -> bytes:
    """Produce the exact unquoted-token ASCII request, without a terminator."""
    if not isinstance(cmd, Command):
        raise ValueError("Only Command enum members are accepted")
    if cmd is Command.SET_STARTUP_MASK:
        if arg is None:
            raise ValueError("Startup mask is required")
        _validate_mask(arg, 0x1F)
        token = f"SMask={arg:02X}"
    else:
        if arg is not None:
            raise ValueError("Read commands do not take an argument")
        token = cmd.value
    return ('{"Cmd": ' + token + "}").encode("ascii")


def mode_mask(current: int, mode: StartupMode) -> int:
    """OEM switch-ON arithmetic, preserving bits 2–4; not a factory reset."""
    _validate_mask(current, 0xFF)
    if not isinstance(mode, StartupMode):
        raise ValueError("Unknown startup mode")
    return (current & 0x1C) | mode.value


def has_unsupported_bits(mask: int) -> bool:
    """Flag hidden SuperLearn/unknown bits for the future control guard."""
    _validate_mask(mask, 0xFF)
    return bool(mask & 0xF0)


def parse_live(buf: bytes) -> LiveData:
    """Decode little-endian fields from wiki/available-data.md, ReadLive."""
    if not 18 <= len(buf) <= 64:
        raise ProtocolError("Live reply must contain 18..64 bytes")
    raw = bytes(buf)
    period = int.from_bytes(raw[6:8], "little")
    status = StatusCode(raw[2]) if raw[2] < 10 else StatusCode.UNKNOWN
    return LiveData(
        status=status,
        raw_status=raw[2],
        learned_starts=raw[3],
        current_a=int.from_bytes(raw[4:6], "little") / 10,
        line_hz=500000 / period if period else None,
        last_start_peak_a=int.from_bytes(raw[8:10], "little") / 10,
        scpt_delay_s=int.from_bytes(raw[10:12], "little"),
        total_faults=int.from_bytes(raw[12:14], "little"),
        total_starts=int.from_bytes(raw[14:18], "little"),
        raw=raw,
    )


def parse_eeprom(buf: bytes) -> EepromData:
    """Decode the bounded EEPROM image; all other bytes remain opaque."""
    if not 909 <= len(buf) <= 1100:
        raise ProtocolError("EEPROM reply must contain 909..1100 bytes")
    raw = bytes(buf)
    if not all(0x20 <= byte <= 0x7E for byte in raw[2:9]):
        raise ProtocolError("EEPROM model must be printable ASCII")
    return EepromData(
        model=raw[2:9].decode("ascii"),
        firmware=raw[10],
        startup_mask=raw[906],
        fault_mask=raw[907],
        scpt_minutes=raw[908],
        raw=raw,
    )


def is_completion(notification: bytes) -> Completion | None:
    """Provisional completion heuristic from wiki/integration-plan.md §4.

    ponytail: short printable envelopes only until G1 supplies real framing;
    a printable binary chunk containing a token remains inherently ambiguous.
    """
    text = notification.rstrip(b"\r\n\0 \t\v\f")
    if len(text) > 64 or not all(0x20 <= byte <= 0x7E for byte in text):
        return None
    ok, fail = b"Success" in text, b"Fail" in text
    if ok and fail:
        return Completion.CONFLICT
    if ok:
        return Completion.OK
    return Completion.FAIL if fail else None
