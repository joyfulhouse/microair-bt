"""Explicit startup-mode writes with conservative, operator-visible outcomes."""

import asyncio
from typing import Any, cast

import voluptuous as vol
from bleak.exc import BleakError
from homeassistant.components import bluetooth, persistent_notification
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import UpdateFailed

from .const import DOMAIN, SERVICE_SET_STARTUP_MODE
from .coordinator import MicroAirConfigEntry, MicroAirCoordinator, MicroAirData
from .microair.client import (
    CommandFailed,
    MicroAirClient,
    StartupModeRejected,
    StartupWriteState,
)
from .microair.protocol import ProtocolError, StartupMode, StatusCode


def _validate_request(data: dict[str, Any]) -> dict[str, Any]:
    if data.get("confirm") is not True:
        raise ServiceValidationError("REJECTED: confirm must be true")
    if not isinstance(data.get("mode"), str) or data.get("mode") not in {
        "normal",
        "relearn",
        "default_ramp",
    }:
        raise ServiceValidationError(
            "REJECTED: mode must be normal, relearn or default_ramp"
        )
    if bool(data.get("entry")) == bool(data.get("device")):
        raise ServiceValidationError("REJECTED: select exactly one entry or device")
    if any(
        not isinstance(data[key], str) for key in ("entry", "device") if key in data
    ):
        raise ServiceValidationError("REJECTED: entry/device must be an identifier")
    if set(data) - {"entry", "device", "mode", "confirm"}:
        raise ServiceValidationError("REJECTED: unknown service fields")
    return data


def _coordinator(hass: HomeAssistant, call: ServiceCall) -> MicroAirCoordinator:
    entry_id = call.data.get("entry")
    if device_id := call.data.get("device"):
        device = dr.async_get(hass).async_get(device_id)
        entries = [
            entry
            for entry in hass.config_entries.async_entries(DOMAIN)
            if device is not None and entry.entry_id in device.config_entries
        ]
        if len(entries) != 1:
            raise ServiceValidationError(
                "REJECTED: device must identify one EasyStart entry"
            )
        entry_id = entries[0].entry_id
    if not isinstance(entry_id, str):
        raise ServiceValidationError("REJECTED: entry identifier required")
    entry = hass.config_entries.async_get_entry(entry_id)
    if (
        entry is None
        or entry.domain != DOMAIN
        or entry.state != ConfigEntryState.LOADED
    ):
        raise ServiceValidationError("REJECTED: EasyStart entry is not loaded")
    return cast(MicroAirConfigEntry, entry).runtime_data


@callback
def _notify(coordinator: MicroAirCoordinator, outcome: str) -> None:
    persistent_notification.async_create(
        coordinator.hass,
        f"{coordinator.entry.title}: {outcome}. Storage readback does not prove "
        "that relearning has completed. If relearn was requested, follow the "
        "Micro-Air procedure: end the cooling call at the thermostat to power "
        "the EasyStart off, then allow 5 successful compressor starts, each "
        "running for at least 30 seconds. Respect the air conditioner's normal "
        "off-time and short-cycle protection between starts. This integration "
        "does not cycle the compressor. If the result is uncertain, inspect "
        "the startup mask before deciding whether to send another command.",
        title="MicroAir EasyStart startup mode",
        notification_id=f"{DOMAIN}_{coordinator.entry.entry_id}_startup_mode",
    )


async def _async_write(
    coordinator: MicroAirCoordinator, mode: StartupMode
) -> ServiceResponse:
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
                expected = await client.write_startup_mask(mode.value)
                eeprom = await client.read_eeprom()
                if eeprom.startup_mask != expected:
                    raise ProtocolError("Startup mask storage readback did not match")
        except StartupModeRejected as error:
            raise ServiceValidationError(f"REJECTED: {error}") from error
        except (BleakError, OSError, ProtocolError, UpdateFailed) as error:
            phase = (
                client.startup_write_state
                if client
                else StartupWriteState.NOT_ATTEMPTED
            )
            if phase is StartupWriteState.NOT_ATTEMPTED:
                raise ServiceValidationError(f"REJECTED: {error}") from error
            outcome = (
                "ACKNOWLEDGED-BUT-UNVERIFIED"
                if phase is StartupWriteState.ACKNOWLEDGED
                else "FAILED"
                if isinstance(error, CommandFailed)
                else "INDETERMINATE"
            )
            _notify(coordinator, outcome)
            coordinator.async_set_update_error(error)
            raise HomeAssistantError(f"{outcome}: {error}") from error
        except asyncio.CancelledError:
            phase = (
                client.startup_write_state
                if client
                else StartupWriteState.NOT_ATTEMPTED
            )
            if phase is not StartupWriteState.NOT_ATTEMPTED:
                _notify(
                    coordinator,
                    "ACKNOWLEDGED-BUT-UNVERIFIED"
                    if phase is StartupWriteState.ACKNOWLEDGED
                    else "INDETERMINATE",
                )
            raise
        coordinator.async_set_updated_data(MicroAirData(eeprom, live))
        _notify(coordinator, "STORED (startup mask matched EEPROM readback)")
        return {"outcome": "STORED", "startup_mask": f"0x{expected:02X}"}


@callback
def async_register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_SET_STARTUP_MODE):
        return

    async def async_set_startup_mode(call: ServiceCall) -> ServiceResponse:
        coordinator = _coordinator(hass, call)
        mode = StartupMode[call.data["mode"].upper()]
        return await _async_write(coordinator, mode)

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_STARTUP_MODE,
        async_set_startup_mode,
        schema=vol.Schema(_validate_request),
        supports_response=SupportsResponse.OPTIONAL,
    )
