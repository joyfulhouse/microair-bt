"""Shared stable device identity and telemetry availability."""

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MicroAirCoordinator


class MicroAirEntity(CoordinatorEntity[MicroAirCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: MicroAirCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.address)},
            name=coordinator.entry.title,
            manufacturer="Micro-Air",
            model=coordinator.entry.data.get("model"),
            sw_version=str(coordinator.entry.data.get("firmware", "")),
        )

    @property
    def available(self) -> bool:
        return (
            super().available
            and self.coordinator.powered
            and self.coordinator.polling_enabled
            and self.coordinator.data is not None
        )
