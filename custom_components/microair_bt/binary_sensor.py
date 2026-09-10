"""Advertising availability and the exact known fault codes."""

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import MicroAirConfigEntry, MicroAirCoordinator
from .entity import MicroAirEntity
from .microair.protocol import StatusCode


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MicroAirConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities(
        [MicroAirPowered(entry.runtime_data), MicroAirFault(entry.runtime_data)]
    )


class MicroAirPowered(MicroAirEntity, BinarySensorEntity):
    _attr_name = "Powered"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: MicroAirCoordinator) -> None:
        super().__init__(coordinator, "powered")

    @property
    def available(self) -> bool:
        # The advertising indicator reports off while telemetry is unavailable.
        return True

    @property
    def is_on(self) -> bool:
        return self.coordinator.powered


class MicroAirFault(MicroAirEntity, BinarySensorEntity):
    _attr_name = "Fault"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: MicroAirCoordinator) -> None:
        super().__init__(coordinator, "fault")

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data
        if data is None or data.live.status == StatusCode.UNKNOWN:
            return None
        return data.live.status not in {StatusCode.NORMAL, StatusCode.SHORT_CYCLE_DELAY}

    @property
    def extra_state_attributes(self) -> dict[str, int] | None:
        if self.coordinator.data is None:
            return None
        return {"raw_status": self.coordinator.data.live.raw_status}
