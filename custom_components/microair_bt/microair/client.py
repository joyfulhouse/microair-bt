"""Transaction-scoped BLE transport from wiki/ble-transport.md.

Command routing and bounds follow wiki/integration-plan.md §5. Connection
retries are delegated to bleak-retry-connector; commands are never retried.
"""

import asyncio
import logging
import math
import re
from asyncio import sleep
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from enum import Enum

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice
from bleak.backends.service import BleakGATTServiceCollection
from bleak.exc import BleakError
from bleak_retry_connector import establish_connection

from .protocol import (
    FAULT_MASK_MAX,
    PARAMETER_WRITES,
    SCPT_MAX,
    SCPT_MIN,
    Command,
    Completion,
    EepromData,
    FaultProtection,
    LiveData,
    ProtocolError,
    StartupFlag,
    StartupMode,
    build,
    fault_protection_mask,
    flag_mask,
    has_unsupported_bits,
    is_completion,
    mode_mask,
    parse_eeprom,
    parse_live,
    superlearn_available,
)

SERVICE_UUID = "d973f2e0-b19e-11e2-9e96-0800200c9a66"
NOTIFY_UUID = "d973f2e1-b19e-11e2-9e96-0800200c9a66"
WRITE_UUID = "d973f2e2-b19e-11e2-9e96-0800200c9a66"
CONTROL_MODELS = frozenset({"398ULBT"})
# Provisional until the G1 live probe establishes firmware timing.
READ_LIVE_TIMEOUT = 10.0
SERVICE_READ_LIVE_TIMEOUT = 20.0
READ_EEP_TIMEOUT = 20.0
PARAMETER_WRITE_TIMEOUT = 10.0
SETTLE_SECONDS = 0.5
# The five strings the OEM app writes outside its firmware-update path, with
# the app's value ranges enforced here as well as in the builder: SMask 00-1F,
# SCPT 01-FA (1-250 min; zero is outside the app's range), FMask 01-7F (zero
# would disable every protection).
_WRITE_PATTERN = re.compile(
    rb'^\{"Cmd": (ReadEEP|ReadLive|SMask=[01][0-9A-F]'
    rb"|SCPT=(0[1-9A-F]|[1-9A-E][0-9A-F]|F[0-9A])"
    rb"|FMask=(0[1-9A-F]|[1-7][0-9A-F]))\}$"
)
_LOGGER = logging.getLogger(__name__)


class CommandFailed(ProtocolError):
    """The device reported failure in an exact completion envelope."""


class CommandTimeout(TimeoutError):
    """The entire command, including the GATT write, exceeded its deadline."""


class WriteRejected(ProtocolError):
    """Validation or preflight failed; no parameter write was attempted."""


class WriteState(Enum):
    """Observed parameter-write phase, retained through failure and cleanup."""

    NOT_ATTEMPTED = "not_attempted"
    ATTEMPTED = "attempted"
    ACKNOWLEDGED = "acknowledged"


async def _finish_cleanup(task: asyncio.Task[None]) -> None:
    """Retain ownership until resource acquisition/disposal finishes.

    The connector does not expose its client until connect returns. Shielding
    that acquisition lets transaction.finally reclaim it even on cancellation.
    Repeated cancellation must not abandon a still-running disconnect either.
    """
    cancelled = False
    try:
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                cancelled = True
        task.result()
    finally:
        if cancelled:
            raise asyncio.CancelledError


class MicroAirClient:
    """One owner task, one connection, and sequential commands per transaction."""

    def __init__(
        self,
        ble_device: BLEDevice,
        *,
        max_attempts: int,
        on_notification: Callable[[bytes], None] | None = None,
    ) -> None:
        if type(max_attempts) is not int or max_attempts < 1:
            raise ValueError("max_attempts must be a positive integer")
        self._device = ble_device
        self._max_attempts = max_attempts
        self._on_notification = on_notification
        self._lock = asyncio.Lock()
        self._owner: asyncio.Task[object] | None = None
        self._client: BleakClient | None = None
        self._generation = 0
        self._poisoned = True
        self._pending: asyncio.Future[bytes] | None = None
        self._command: Command | None = None
        self._buffer = bytearray()
        self._frames = 0
        self.write_state = WriteState.NOT_ATTEMPTED

    def _connected(self) -> BleakClient:
        if (
            self._owner is not asyncio.current_task()
            or self._client is None
            or self._poisoned
            or not self._client.is_connected
        ):
            raise ProtocolError(
                "An active, healthy transaction owned by this task is required"
            )
        return self._client

    @property
    def services(self) -> BleakGATTServiceCollection:
        """The connected GATT profile, for the read-only evidence probe."""
        return self._connected().services

    @property
    def mtu_size(self) -> int:
        return self._connected().mtu_size

    async def _connect(self, generation: int) -> None:
        def disconnected(client: BleakClient) -> None:
            if generation != self._generation:
                return
            self._poisoned = True
            self._fail(ProtocolError("Peripheral disconnected during transaction"))

        self._client = await establish_connection(
            BleakClient,
            self._device,
            self._device.name or self._device.address,
            max_attempts=self._max_attempts,
            disconnected_callback=disconnected,
        )

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        """Connect → notify → 500 ms settle → commands → unconditional disconnect."""
        if self._owner is asyncio.current_task():
            raise ProtocolError("Nested transactions are not supported")
        async with self._lock:
            self._owner = asyncio.current_task()
            self._generation += 1
            generation = self._generation
            self._poisoned = False
            try:
                await _finish_cleanup(asyncio.create_task(self._connect(generation)))
                client = self._connected()
                _LOGGER.debug("Connected; mtu_size=%s", client.mtu_size)
                service = client.services.get_service(SERVICE_UUID)
                if (
                    service is None
                    or service.get_characteristic(NOTIFY_UUID) is None
                    or service.get_characteristic(WRITE_UUID) is None
                ):
                    raise ProtocolError(
                        "EasyStart service/characteristic triplet is missing"
                    )

                def notification(
                    sender: BleakGATTCharacteristic, data: bytearray
                ) -> None:
                    self._notification(generation, bytes(data))

                await client.start_notify(NOTIFY_UUID, notification)
                await sleep(SETTLE_SECONDS)
                yield
            finally:
                try:
                    await self._disconnect()
                finally:
                    self._owner = None

    async def _disconnect(self) -> None:
        self._poisoned = True
        self._generation += 1
        pending, self._pending = self._pending, None
        if pending is not None:
            if not pending.done():
                pending.cancel()
            elif not pending.cancelled():
                # Consume a failure that raced a write/cancellation.
                pending.exception()
        self._buffer.clear()
        self._command = None
        client, self._client = self._client, None
        if client is not None:
            await _finish_cleanup(asyncio.create_task(client.disconnect()))

    def _fail(self, error: ProtocolError) -> None:
        self._poisoned = True
        if self._pending is not None and not self._pending.done():
            self._pending.set_exception(error)

    def _notification(self, generation: int, data: bytes) -> None:
        if generation != self._generation or self._poisoned:
            return
        if self._on_notification is not None:
            self._on_notification(data)
        pending = self._pending
        if pending is None or pending.done():
            return
        completion = is_completion(data)
        if completion is Completion.FAIL:
            self._fail(CommandFailed(f"Command completion: {completion.value}"))
        elif completion is Completion.OK:
            if self._command in PARAMETER_WRITES:
                self.write_state = WriteState.ACKNOWLEDGED
            raw = bytes(self._buffer)
            _LOGGER.debug(
                "%s complete: %s bytes in %s frames",
                self._command.name if self._command else "command",
                len(raw),
                self._frames,
            )
            try:
                if self._command is Command.READ_EEP:
                    parse_eeprom(raw)
                elif self._command is Command.READ_LIVE:
                    parse_live(raw)
            except ProtocolError as error:
                self._fail(error)
            else:
                pending.set_result(raw)
        elif self._command in PARAMETER_WRITES:
            _LOGGER.warning(
                "Dropped binary notification during %s write (%s bytes)",
                self._command.value,
                len(data),
            )
        else:
            cap = 64 if self._command is Command.READ_LIVE else 1100
            if len(self._buffer) + len(data) > cap:
                self._fail(ProtocolError(f"Reply exceeds {cap}-byte cap"))
            else:
                self._buffer.extend(data)
                self._frames += 1

    async def run(
        self, cmd: Command, arg: int | None = None, *, timeout: float
    ) -> bytes:
        """Run a read; parameter writes must use the typed write_* methods."""
        if cmd in PARAMETER_WRITES:
            raise ValueError("Parameter writes must use a typed write_* method")
        return await self._run(cmd, arg, timeout=timeout)

    async def _run(
        self, cmd: Command, arg: int | None = None, *, timeout: float
    ) -> bytes:
        client = self._connected()
        if self._pending is not None:
            raise ProtocolError("A command is already in flight")
        payload = build(cmd, arg)
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be finite and positive")
        try:
            self._buffer.clear()
            self._frames = 0
            self._command = cmd
            pending: asyncio.Future[bytes] = asyncio.get_running_loop().create_future()
            self._pending = pending
            characteristic = client.services.get_characteristic(WRITE_UUID)
            if characteristic is None:
                raise ProtocolError("Write characteristic is missing")
            if not {"write", "write-without-response"}.intersection(
                characteristic.properties
            ):
                raise ProtocolError("Characteristic does not support writes")
            async with asyncio.timeout(timeout):
                # A runtime assertion (also enforced under python -O), directly
                # at the SINGLE write site: no update/raw/configuration payloads.
                if len(payload) not in (16, 17) or not _WRITE_PATTERN.fullmatch(
                    payload
                ):
                    raise AssertionError("Payload violates command whitelist")

                async def write() -> None:
                    if cmd in PARAMETER_WRITES:
                        self.write_state = WriteState.ATTEMPTED
                    await client.write_gatt_char(
                        characteristic,
                        payload,
                        response="write" in characteristic.properties,
                    )

                write_task = asyncio.create_task(write())
                try:
                    await asyncio.wait(
                        (write_task, pending), return_when=asyncio.FIRST_COMPLETED
                    )
                    # A peer failure must interrupt a stalled write. Early OK
                    # still requires the write itself to finish by the deadline.
                    if pending.done():
                        pending.result()
                    await write_task
                    return await pending
                finally:
                    if not write_task.done():
                        write_task.cancel()
                    # Drain cancellation/transport errors without replacing the
                    # peer failure that initiated cleanup.
                    await asyncio.gather(write_task, return_exceptions=True)
        except TimeoutError as error:
            await self._disconnect()
            raise CommandTimeout(
                f"{cmd.name} exceeded {timeout:g}s deadline"
            ) from error
        except BaseException:
            await self._disconnect()
            raise
        finally:
            self._pending = None
            self._command = None
            self._buffer.clear()

    async def read_live(self, *, timeout: float = READ_LIVE_TIMEOUT) -> LiveData:
        return parse_live(await self.run(Command.READ_LIVE, timeout=timeout))

    async def read_eeprom(self, *, timeout: float = READ_EEP_TIMEOUT) -> EepromData:
        return parse_eeprom(await self.run(Command.READ_EEP, timeout=timeout))

    async def _preflight(self) -> EepromData:
        """Bind to a fresh EEPROM image from a control model within this transaction.

        The transaction already verified the ST triplet; its lock covers this
        read and the write that follows. Both mask bytes must contain only bits
        the OEM app understands, so a write can never carry unknown bits along.
        """
        try:
            eeprom = await self.read_eeprom()
        except (ProtocolError, BleakError, OSError) as error:
            raise WriteRejected(f"EEPROM preflight failed: {error}") from error
        if eeprom.model not in CONTROL_MODELS:
            raise WriteRejected(f"Unsupported control model: {eeprom.model}")
        if has_unsupported_bits(eeprom.startup_mask):
            raise WriteRejected(
                f"Unsupported original startup mask: 0x{eeprom.startup_mask:02X}"
            )
        if eeprom.fault_mask > FAULT_MASK_MAX:
            raise WriteRejected(
                f"Unsupported original fault mask: 0x{eeprom.fault_mask:02X}"
            )
        return eeprom

    async def _write_parameter(self, cmd: Command, value: int) -> int:
        """Send one parameter write; the caller has validated and preflighted.

        Return the acknowledged value for the caller's storage readback. An
        acknowledgement alone does not prove that the device acted on it.
        """
        try:
            payload = build(cmd, value)
        except ValueError as error:
            raise WriteRejected(str(error)) from error
        _LOGGER.debug("Writing %s", payload)
        await self._run(cmd, value, timeout=PARAMETER_WRITE_TIMEOUT)
        return value

    async def write_startup_mode(self, mode: StartupMode) -> int:
        """Store a startup mode, keeping the flag bits 2-3 of the fresh image.

        Reject anything but a StartupMode member before any device I/O.
        """
        self.write_state = WriteState.NOT_ATTEMPTED
        if not isinstance(mode, StartupMode):
            raise WriteRejected("Startup mode must be a StartupMode member")
        eeprom = await self._preflight()
        if mode is StartupMode.SUPERLEARN and not superlearn_available(eeprom.firmware):
            raise WriteRejected(
                f"SuperLearn is not offered for firmware {eeprom.firmware}"
            )
        mask = mode_mask(eeprom.startup_mask, mode)
        return await self._write_parameter(Command.SET_STARTUP_MASK, mask)

    async def write_startup_flag(self, flag: StartupFlag, enabled: bool) -> int:
        """Set or clear one independent startup-mask flag bit."""
        self.write_state = WriteState.NOT_ATTEMPTED
        if not isinstance(flag, StartupFlag) or type(enabled) is not bool:
            raise WriteRejected("Startup flag must be a StartupFlag member and bool")
        eeprom = await self._preflight()
        mask = flag_mask(eeprom.startup_mask, flag, enabled)
        return await self._write_parameter(Command.SET_STARTUP_MASK, mask)

    async def write_scpt(self, minutes: int) -> int:
        """Store the short-cycle protection timer (or start delay) in minutes."""
        self.write_state = WriteState.NOT_ATTEMPTED
        if type(minutes) is not int or not SCPT_MIN <= minutes <= SCPT_MAX:
            raise WriteRejected(f"SCPT must be an integer in {SCPT_MIN}..{SCPT_MAX}")
        await self._preflight()
        return await self._write_parameter(Command.SET_SCPT, minutes)

    async def write_fault_protection(
        self, protection: FaultProtection, enabled: bool
    ) -> int:
        """Enable or disable one fault detection; never disable all of them."""
        self.write_state = WriteState.NOT_ATTEMPTED
        if not isinstance(protection, FaultProtection) or type(enabled) is not bool:
            raise WriteRejected(
                "Fault protection must be a FaultProtection member and bool"
            )
        eeprom = await self._preflight()
        try:
            mask = fault_protection_mask(eeprom.fault_mask, protection, enabled)
        except ValueError as error:
            raise WriteRejected(str(error)) from error
        return await self._write_parameter(Command.SET_FAULT_MASK, mask)
