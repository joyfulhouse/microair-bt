"""Local Bluetooth monitoring and control for MicroAir EasyStart soft starters."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .const import DOMAIN, SERVICE_SET_STARTUP_MODE

if TYPE_CHECKING:
    from homeassistant.const import Platform
    from homeassistant.core import HomeAssistant

    from .coordinator import MicroAirConfigEntry


async def async_setup_entry(hass: HomeAssistant, entry: MicroAirConfigEntry) -> bool:
    # Keep standalone protocol/probe imports independent of Home Assistant.
    from .coordinator import MicroAirCoordinator
    from .services import async_register_services

    coordinator = MicroAirCoordinator(hass, entry)
    entry.runtime_data = coordinator
    try:
        await coordinator.async_start()
        await hass.config_entries.async_forward_entry_setups(entry, _platforms())
    except BaseException:
        await coordinator.async_shutdown()
        raise
    # React to option edits (live mode, interval, voltage/PF) without a reload.
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    async_register_services(hass)
    return True


def _platforms() -> list[Platform]:
    from homeassistant.const import Platform

    return [
        Platform.SENSOR,
        Platform.BINARY_SENSOR,
        Platform.SWITCH,
        Platform.SELECT,
        Platform.NUMBER,
    ]


async def _async_options_updated(
    hass: HomeAssistant, entry: MicroAirConfigEntry
) -> None:
    entry.runtime_data.async_options_updated()


async def async_unload_entry(hass: HomeAssistant, entry: MicroAirConfigEntry) -> bool:
    from homeassistant.config_entries import ConfigEntryState

    if not await hass.config_entries.async_unload_platforms(entry, _platforms()):
        return False
    if not any(
        other.entry_id != entry.entry_id and other.state == ConfigEntryState.LOADED
        for other in hass.config_entries.async_entries(DOMAIN)
    ):
        hass.services.async_remove(DOMAIN, SERVICE_SET_STARTUP_MODE)
    return True
