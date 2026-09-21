"""Explicit startup-mode writes with conservative, operator-visible outcomes."""

from typing import Any, cast

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN, SERVICE_SET_STARTUP_MODE
from .coordinator import MicroAirConfigEntry, MicroAirCoordinator
from .microair.protocol import StartupMode
from .writes import async_write, startup_mode_request

MODES = frozenset(mode.name.lower() for mode in StartupMode)


def _validate_request(data: dict[str, Any]) -> dict[str, Any]:
    if data.get("confirm") is not True:
        raise ServiceValidationError("REJECTED: confirm must be true")
    if not isinstance(data.get("mode"), str) or data.get("mode") not in MODES:
        raise ServiceValidationError(
            f"REJECTED: mode must be one of {', '.join(sorted(MODES))}"
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
def async_register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_SET_STARTUP_MODE):
        return

    async def async_set_startup_mode(call: ServiceCall) -> ServiceResponse:
        coordinator = _coordinator(hass, call)
        mode = StartupMode[call.data["mode"].upper()]
        mask = await async_write(coordinator, startup_mode_request(mode))
        return {"outcome": "STORED", "startup_mask": f"0x{mask:02X}"}

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_STARTUP_MODE,
        async_set_startup_mode,
        schema=vol.Schema(_validate_request),
        supports_response=SupportsResponse.OPTIONAL,
    )
