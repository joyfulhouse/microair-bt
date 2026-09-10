"""Persistent maintenance gate, operable even while EasyStart is unpowered."""

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import MicroAirConfigEntry, MicroAirCoordinator
from .entity import MicroAirEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MicroAirConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([MicroAirPollingSwitch(entry.runtime_data)])


class MicroAirPollingSwitch(MicroAirEntity, SwitchEntity):
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
