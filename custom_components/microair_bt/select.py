"""The app's Relearn screen as one mutually exclusive startup-mode choice."""

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import MicroAirConfigEntry, MicroAirCoordinator
from .entity import MicroAirControlEntity
from .microair.protocol import StartupMode, mode_from_mask, superlearn_available
from .writes import async_write, startup_mode_request

BASE_OPTIONS = ["normal", "relearn", "default_ramp"]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MicroAirConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([MicroAirStartupModeSelect(entry.runtime_data)])


class MicroAirStartupModeSelect(MicroAirControlEntity, SelectEntity):
    """Disabled by default: relearn is a learn/reset command, and the write
    path is not yet verified on hardware, so enabling this entity is the
    operator's explicit confirmation (the service keeps its confirm flag)."""

    _attr_name = "Startup mode"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False
    _attr_icon = "mdi:restart-alert"
    _attr_translation_key = "startup_mode"

    def __init__(self, coordinator: MicroAirCoordinator) -> None:
        super().__init__(coordinator, "startup_mode")

    @property
    def options(self) -> list[str]:
        eeprom = self.eeprom
        if eeprom is not None and superlearn_available(eeprom.firmware):
            return [*BASE_OPTIONS, StartupMode.SUPERLEARN.name.lower()]
        return list(BASE_OPTIONS)

    @property
    def current_option(self) -> str | None:
        eeprom = self.eeprom
        if eeprom is None:
            return None
        return mode_from_mask(eeprom.startup_mask).name.lower()

    async def async_select_option(self, option: str) -> None:
        # Home Assistant has already rejected options outside self.options.
        await async_write(
            self.coordinator, startup_mode_request(StartupMode[option.upper()])
        )
