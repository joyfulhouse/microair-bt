"""Local Bluetooth monitoring and explicit startup-mode control for EasyStart."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .const import DOMAIN, SERVICE_SET_STARTUP_MODE

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .coordinator import MicroAirConfigEntry


async def async_setup_entry(hass: HomeAssistant, entry: MicroAirConfigEntry) -> bool:
    # Keep standalone protocol/probe imports independent of Home Assistant.
    from homeassistant.const import Platform

    from .coordinator import MicroAirCoordinator
    from .services import async_register_services

    coordinator = MicroAirCoordinator(hass, entry)
    entry.runtime_data = coordinator
    try:
        await coordinator.async_start()
        await hass.config_entries.async_forward_entry_setups(
            entry, [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.SWITCH]
        )
    except BaseException:
        await coordinator.async_shutdown()
        raise
    async_register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: MicroAirConfigEntry) -> bool:
    from homeassistant.config_entries import ConfigEntryState
    from homeassistant.const import Platform

    if not await hass.config_entries.async_unload_platforms(
        entry, [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.SWITCH]
    ):
        return False
    await entry.runtime_data.async_shutdown()
    if not any(
        other.entry_id != entry.entry_id and other.state == ConfigEntryState.LOADED
        for other in hass.config_entries.async_entries(DOMAIN)
    ):
        hass.services.async_remove(DOMAIN, SERVICE_SET_STARTUP_MODE)
    return True
