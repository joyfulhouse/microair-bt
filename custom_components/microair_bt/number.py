"""The app's SCPT entry: short-cycle protection timer in minutes (1-250)."""

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import MicroAirConfigEntry, MicroAirCoordinator
from .entity import MicroAirControlEntity
from .microair.protocol import SCPT_MAX, SCPT_MIN, StartupFlag
from .writes import async_write, scpt_request


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MicroAirConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([MicroAirScptNumber(entry.runtime_data)])


class MicroAirScptNumber(MicroAirControlEntity, NumberEntity):
    _attr_name = "Short-cycle protection timer"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:timer-cog-outline"
    _attr_device_class = NumberDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_native_min_value = SCPT_MIN
    _attr_native_max_value = SCPT_MAX
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: MicroAirCoordinator) -> None:
        super().__init__(coordinator, "scpt_minutes")

    @property
    def native_value(self) -> int | None:
        eeprom = self.eeprom
        return None if eeprom is None else eeprom.scpt_minutes

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        eeprom = self.eeprom
        if eeprom is None:
            return None
        # With the hidden Start Delay mode set, the app relabels this byte.
        start_delay = bool(eeprom.startup_mask & StartupFlag.START_DELAY_MODE)
        return {
            "interpretation": "start_delay" if start_delay else "short_cycle_protection"
        }

    async def async_set_native_value(self, value: float) -> None:
        # Home Assistant has already enforced min/max; a display unit such as
        # hours converts back with float error, so only whole minutes matter.
        minutes = round(value)
        if abs(value - minutes) > 1e-6:
            raise ServiceValidationError(
                "REJECTED: SCPT must be a whole number of minutes"
            )
        await async_write(self.coordinator, scpt_request(minutes))
