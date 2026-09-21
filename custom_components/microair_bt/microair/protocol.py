"""EasyStart wire format from wiki/ble-protocol.md and wiki/available-data.md.

Buffer offsets include the two prefix bytes. For ReadEEP these encode the
remaining payload length as a little-endian uint16; incoming lengths are bounded.
"""

from dataclasses import dataclass
from enum import Enum, IntEnum


class ProtocolError(ValueError):
    """A peripheral reply does not satisfy the documented wire contract."""


class Command(Enum):
    """The complete command whitelist; never accept raw caller-supplied bytes.

    These are the five strings the OEM app writes outside its firmware-update
    path. Nothing else can be built, and the client write site re-checks.
    """

    READ_EEP = "ReadEEP"
    READ_LIVE = "ReadLive"
    SET_STARTUP_MASK = "SMask"
    SET_SCPT = "SCPT"
    SET_FAULT_MASK = "FMask"


PARAMETER_WRITES = frozenset(
    {Command.SET_STARTUP_MASK, Command.SET_SCPT, Command.SET_FAULT_MASK}
)
# The app's SCPT entry accepts 1..250 minutes (J/Relearn.java:312-313).
SCPT_MIN = 1
SCPT_MAX = 250
# Fault-enable mask: bits 0-6 (J/Faults.java:318-338).
FAULT_MASK_MAX = 0x7F
# Startup-mask bits the app can set: 0-4 (J/Relearn.java:380-394).
STARTUP_MASK_MAX = 0x1F
_FLAG_BITS = 0x0C
# The app's hidden SuperLearn label bit; it persists on its own until a plain
# ReLearn is chosen deliberately (J/Relearn.java:391-394,533-545).
SUPERLEARN_BIT = 0x10
# The app offers SuperLearn only from this firmware on (J/Relearn.java:353).
SUPERLEARN_MIN_FIRMWARE = 29


class StartupMode(Enum):
    """The mutually exclusive startup-mask choices; the value is the bit pattern.

    SuperLearn is the app's hidden long-press variant of ReLearn (bit 4 with
    bit 0), offered by the app only for firmware >= 29 on non-Breeze models.
    """

    NORMAL = 0x00
    RELEARN = 0x01
    DEFAULT_RAMP = 0x02
    SUPERLEARN = 0x01 | SUPERLEARN_BIT


class StartupFlag(IntEnum):
    """Independent startup-mask bits, preserved across mode changes."""

    NO_POWER_UP_DELAY = 0x04
    # Hidden in the app (3 s long-press): the SCPT byte becomes a start delay.
    START_DELAY_MODE = 0x08


class FaultProtection(IntEnum):
    """Fault-enable mask bits, in the app's Fault Control screen order."""

    UNEXPECTED_CURRENT = 0x01
    POWER_INTERRUPTION = 0x02
    COMPRESSOR_STALL = 0x04
    START_HARDWARE_FAILED = 0x08
    OPEN_OVERLOAD = 0x10
    OVERCURRENT = 0x20
    WIRING_ISSUE = 0x40


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
    if cmd in PARAMETER_WRITES:
        if arg is None:
            raise ValueError(f"{cmd.value} requires a value")
        if cmd is Command.SET_SCPT:
            if type(arg) is not int or not SCPT_MIN <= arg <= SCPT_MAX:
                raise ValueError(f"SCPT must be an integer in {SCPT_MIN}..{SCPT_MAX}")
        elif cmd is Command.SET_FAULT_MASK:
            _validate_mask(arg, FAULT_MASK_MAX)
            if arg == 0:
                raise ValueError("Fault mask must enable at least one protection")
        else:
            _validate_mask(arg, STARTUP_MASK_MAX)
        token = f"{cmd.value}={arg:02X}"
    else:
        if arg is not None:
            raise ValueError("Read commands do not take an argument")
        token = cmd.value
    return ('{"Cmd": ' + token + "}").encode("ascii")


def mode_mask(current: int, mode: StartupMode) -> int:
    """OEM switch arithmetic: keep the flag bits 2-3, replace bits 0 and 1.

    Not a factory reset. The SuperLearn label bit 4 persists through Normal
    and Default Ramp exactly as in the app; only choosing plain ReLearn clears
    it deliberately, and choosing SuperLearn sets it.
    """
    _validate_mask(current, 0xFF)
    if not isinstance(mode, StartupMode):
        raise ValueError("Unknown startup mode")
    preserved = current & _FLAG_BITS
    if mode in (StartupMode.NORMAL, StartupMode.DEFAULT_RAMP):
        preserved |= current & SUPERLEARN_BIT
    return preserved | mode.value


def mode_from_mask(mask: int) -> StartupMode:
    """Read the mode back the way the app's Relearn screen renders it.

    Bit 4 alone (SuperLearn label, no relearn requested) reads as Normal.
    """
    _validate_mask(mask, 0xFF)
    if mask & StartupMode.RELEARN.value:
        if mask & SUPERLEARN_BIT:
            return StartupMode.SUPERLEARN
        return StartupMode.RELEARN
    if mask & StartupMode.DEFAULT_RAMP.value:
        return StartupMode.DEFAULT_RAMP
    return StartupMode.NORMAL


def superlearn_available(firmware: int) -> bool:
    """Whether the app would offer SuperLearn for this firmware (>= 29)."""
    if type(firmware) is not int:
        raise ValueError("Firmware must be an integer")
    return firmware >= SUPERLEARN_MIN_FIRMWARE


def flag_mask(current: int, flag: StartupFlag, enabled: bool) -> int:
    """Set or clear one independent startup-mask flag, keeping every other bit."""
    _validate_mask(current, 0xFF)
    if not isinstance(flag, StartupFlag) or type(enabled) is not bool:
        raise ValueError("Unknown startup flag")
    return (current | flag) if enabled else (current & ~flag & 0xFF)


def fault_protection_mask(
    current: int, protection: FaultProtection, enabled: bool
) -> int:
    """Toggle one fault-enable bit; never produce an all-disabled mask."""
    _validate_mask(current, 0xFF)
    if not isinstance(protection, FaultProtection) or type(enabled) is not bool:
        raise ValueError("Unknown fault protection")
    result = (current | protection) if enabled else (current & ~protection & 0xFF)
    if result & FAULT_MASK_MAX == 0:
        raise ValueError("Fault mask must enable at least one protection")
    return result


def has_unsupported_bits(mask: int) -> bool:
    """Reject bits 5–7 in the original EEPROM mask; bit 4 is preserved."""
    _validate_mask(mask, 0xFF)
    return bool(mask & 0xE0)


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


def validate_eeprom(buf: bytes) -> None:
    """Require a complete length-prefixed image before decoding any fields."""
    if not 909 <= len(buf) <= 1100:
        raise ProtocolError("EEPROM reply must contain 909..1100 bytes")
    expected = int.from_bytes(buf[:2], "little") + 2
    if expected != len(buf):
        raise ProtocolError(
            f"EEPROM length mismatch: expected {expected} bytes, got {len(buf)}"
        )


def parse_eeprom(buf: bytes) -> EepromData:
    """Decode a complete EEPROM image; all other bytes remain opaque."""
    validate_eeprom(buf)
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
    """Match an exact status envelope, allowing trailing CR, LF and NUL."""
    text = notification.rstrip(b"\r\n\0")
    if text == b'{"Sts": Success}':
        return Completion.OK
    if text == b'{"Sts": Fail}':
        return Completion.FAIL
    return None
