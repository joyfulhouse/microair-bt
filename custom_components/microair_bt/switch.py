"""Maintenance gate plus the app's startup-mask flags and fault protections."""

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import MicroAirConfigEntry, MicroAirCoordinator
from .entity import MicroAirControlEntity, MicroAirEntity
from .microair.protocol import FaultProtection, StartupFlag
from .writes import async_write, fault_protection_request, startup_flag_request

FLAG_NAMES = {
    StartupFlag.NO_POWER_UP_DELAY: "No power-up delay",
    StartupFlag.START_DELAY_MODE: "Start delay mode",
}
# The app's Fault Control labels (res/values/strings.xml:64-70).
PROTECTION_NAMES = {
    FaultProtection.UNEXPECTED_CURRENT: "Unexpected current protection",
    FaultProtection.POWER_INTERRUPTION: "Power interruption protection",
    FaultProtection.COMPRESSOR_STALL: "Compressor stall protection",
    FaultProtection.START_HARDWARE_FAILED: "Start hardware failed protection",
    FaultProtection.OPEN_OVERLOAD: "Open overload protection",
    FaultProtection.OVERCURRENT: "Overcurrent protection",
    FaultProtection.WIRING_ISSUE: "Wiring issue protection",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MicroAirConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[SwitchEntity] = [MicroAirPollingSwitch(coordinator)]
    entities.extend(
        MicroAirStartupFlagSwitch(coordinator, flag) for flag in StartupFlag
    )
    entities.extend(
        MicroAirFaultProtectionSwitch(coordinator, protection)
        for protection in FaultProtection
    )
    async_add_entities(entities)


class MicroAirPollingSwitch(MicroAirEntity, SwitchEntity):
    """Persistent maintenance gate, operable even while EasyStart is unpowered."""

    _attr_name = "Polling"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:bluetooth-connect"

    def __init__(self, coordinator: MicroAirCoordinator) -> None:
        super().__init__(coordinator, "polling")

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        return self.coordinator.polling_enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_polling(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_polling(False)


class MicroAirStartupFlagSwitch(MicroAirControlEntity, SwitchEntity):
    """One independent startup-mask bit (the app's non-exclusive switches)."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:toggle-switch-variant"

    def __init__(self, coordinator: MicroAirCoordinator, flag: StartupFlag) -> None:
        super().__init__(coordinator, flag.name.lower())
        self._flag = flag
        self._attr_name = FLAG_NAMES[flag]
        # Start Delay mode is reachable in the app only by a 3 s long-press.
        self._attr_entity_registry_enabled_default = (
            flag is not StartupFlag.START_DELAY_MODE
        )

    @property
    def is_on(self) -> bool | None:
        eeprom = self.eeprom
        return None if eeprom is None else bool(eeprom.startup_mask & self._flag)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await async_write(self.coordinator, startup_flag_request(self._flag, True))

    async def async_turn_off(self, **kwargs: Any) -> None:
        await async_write(self.coordinator, startup_flag_request(self._flag, False))


class MicroAirFaultProtectionSwitch(MicroAirControlEntity, SwitchEntity):
    """One fault-enable bit. Disabled by default: the app confirm-gates these
    because turning one off stops the EasyStart from detecting that fault."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False
    _attr_icon = "mdi:shield-check-outline"

    def __init__(
        self, coordinator: MicroAirCoordinator, protection: FaultProtection
    ) -> None:
        super().__init__(coordinator, f"protect_{protection.name.lower()}")
        self._protection = protection
        self._attr_name = PROTECTION_NAMES[protection]

    @property
    def is_on(self) -> bool | None:
        eeprom = self.eeprom
        return None if eeprom is None else bool(eeprom.fault_mask & self._protection)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await async_write(
            self.coordinator, fault_protection_request(self._protection, True)
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        await async_write(
            self.coordinator, fault_protection_request(self._protection, False)
        )
