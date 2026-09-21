"""One guarded, verified write path shared by the service and control entities.

Every parameter write follows the same transaction: reject while live mode holds
the link, take the unit's lock, require an advertising device, read live status
and apply the compressor-running guard, let the client preflight a fresh EEPROM
image and write once, then read the EEPROM back and compare the stored value.
Outcomes are reported the same way whichever surface requested the write.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from bleak.exc import BleakError
from homeassistant.components import bluetooth, persistent_notification
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.update_coordinator import UpdateFailed

from .const import DOMAIN
from .coordinator import MicroAirCoordinator, MicroAirData
from .microair.client import (
    CommandFailed,
    MicroAirClient,
    WriteRejected,
    WriteState,
)
from .microair.protocol import (
    EepromData,
    FaultProtection,
    ProtocolError,
    StartupFlag,
    StartupMode,
    StatusCode,
)

RELEARN_GUIDANCE = (
    "Storage readback does not prove that relearning has completed. Follow the "
    "Micro-Air procedure: end the cooling call at the thermostat to power the "
    "EasyStart off, then allow 5 successful compressor starts, each running for "
    "at least 30 seconds. Respect the air conditioner's normal off-time and "
    "short-cycle protection between starts. This integration does not cycle the "
    "compressor. If the result is uncertain, inspect the startup mask before "
    "deciding whether to send another command."
)
DEFAULT_RAMP_GUIDANCE = (
    "Default ramp bypasses the learned profile; Micro-Air says to use it under "
    "their direction. Return to normal operation when the diagnosis is done."
)
FAULT_GUIDANCE = (
    "A disabled protection is no longer detected by the EasyStart. Re-enable it "
    "as soon as the diagnosis is done."
)


@dataclass(frozen=True)
class WriteRequest:
    """What to write, how to verify it, and what to tell the operator."""

    kind: str
    label: str
    perform: Callable[[MicroAirClient], Awaitable[int]]
    readback: Callable[[EepromData], int]
    guidance: str = ""


def startup_mode_request(mode: StartupMode) -> WriteRequest:
    guidance = {
        StartupMode.RELEARN: RELEARN_GUIDANCE,
        StartupMode.SUPERLEARN: RELEARN_GUIDANCE,
        StartupMode.DEFAULT_RAMP: DEFAULT_RAMP_GUIDANCE,
    }.get(mode, "")
    return WriteRequest(
        kind="startup_mode",
        label="startup mode",
        perform=lambda client: client.write_startup_mode(mode),
        readback=lambda eeprom: eeprom.startup_mask,
        guidance=guidance,
    )


def startup_flag_request(flag: StartupFlag, enabled: bool) -> WriteRequest:
    return WriteRequest(
        kind="startup_mode",
        label="startup mask",
        perform=lambda client: client.write_startup_flag(flag, enabled),
        readback=lambda eeprom: eeprom.startup_mask,
    )


def scpt_request(minutes: int) -> WriteRequest:
    return WriteRequest(
        kind="scpt",
        label="short-cycle protection timer",
        perform=lambda client: client.write_scpt(minutes),
        readback=lambda eeprom: eeprom.scpt_minutes,
    )


def fault_protection_request(
    protection: FaultProtection, enabled: bool
) -> WriteRequest:
    return WriteRequest(
        kind="fault_mask",
        label="fault protection",
        perform=lambda client: client.write_fault_protection(protection, enabled),
        readback=lambda eeprom: eeprom.fault_mask,
        guidance="" if enabled else FAULT_GUIDANCE,
    )


@callback
def _notify(
    coordinator: MicroAirCoordinator, request: WriteRequest, outcome: str
) -> None:
    message = f"{coordinator.entry.title}: {outcome}."
    if request.guidance:
        message = f"{message} {request.guidance}"
    persistent_notification.async_create(
        coordinator.hass,
        message,
        title=f"MicroAir EasyStart {request.label}",
        notification_id=f"{DOMAIN}_{coordinator.entry.entry_id}_{request.kind}",
    )


def _phase(client: MicroAirClient | None) -> WriteState:
    return client.write_state if client else WriteState.NOT_ATTEMPTED


async def async_write(coordinator: MicroAirCoordinator, request: WriteRequest) -> int:
    """Perform one verified write; return the value confirmed by EEPROM readback.

    Raises ServiceValidationError when nothing was sent (REJECTED) and
    HomeAssistantError once a write may have reached the device.
    """
    # Live mode holds the single BLE central open, so a write cannot share the
    # link. Reject early (before contending for the lock) rather than hang.
    if coordinator.live_mode:
        raise ServiceValidationError(
            "REJECTED: turn off Live mode (or the Polling switch) before writing"
        )
    async with coordinator.lock:
        if coordinator.stopping or not coordinator.polling_enabled:
            raise ServiceValidationError(
                "REJECTED: EasyStart polling is paused or unloading"
            )
        if not bluetooth.async_address_present(
            coordinator.hass, coordinator.address, connectable=False
        ):
            raise ServiceValidationError("REJECTED: EasyStart is not advertising")
        client: MicroAirClient | None = None
        try:
            client = coordinator.client_for_current_route()
            async with client.transaction():
                live = await client.read_live()
                if live.status == StatusCode.UNKNOWN:
                    raise ServiceValidationError("REJECTED: unknown EasyStart status")
                if live.current_a > 0 and not coordinator.allow_running:
                    raise ServiceValidationError(
                        "REJECTED: compressor is running; allow_running is disabled"
                    )
                expected = await request.perform(client)
                eeprom = await client.read_eeprom()
                if request.readback(eeprom) != expected:
                    raise ProtocolError(
                        f"{request.label} storage readback did not match"
                    )
        except WriteRejected as error:
            raise ServiceValidationError(f"REJECTED: {error}") from error
        except (BleakError, OSError, ProtocolError, UpdateFailed) as error:
            phase = _phase(client)
            if phase is WriteState.NOT_ATTEMPTED:
                raise ServiceValidationError(f"REJECTED: {error}") from error
            outcome = (
                "ACKNOWLEDGED-BUT-UNVERIFIED"
                if phase is WriteState.ACKNOWLEDGED
                else "FAILED"
                if isinstance(error, CommandFailed)
                else "INDETERMINATE"
            )
            _notify(coordinator, request, outcome)
            coordinator.async_set_update_error(error)
            raise HomeAssistantError(f"{outcome}: {error}") from error
        except asyncio.CancelledError:
            phase = _phase(client)
            if phase is not WriteState.NOT_ATTEMPTED:
                outcome = (
                    "ACKNOWLEDGED-BUT-UNVERIFIED"
                    if phase is WriteState.ACKNOWLEDGED
                    else "INDETERMINATE"
                )
                _notify(coordinator, request, outcome)
                # The stored value is unknown: the cached image must not keep
                # presenting the pre-write value as verified.
                coordinator.async_set_update_error(
                    UpdateFailed(f"{outcome}: {request.label} write was cancelled")
                )
            raise
        coordinator.cache_eeprom(eeprom)
        coordinator.async_set_updated_data(MicroAirData(eeprom, live))
        _notify(
            coordinator,
            request,
            f"STORED ({request.label} matched EEPROM readback)",
        )
        return expected
