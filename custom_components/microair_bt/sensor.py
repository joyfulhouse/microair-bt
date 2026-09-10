"""EasyStart telemetry; counters may reset when the operator relearns."""

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfFrequency,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import MicroAirConfigEntry, MicroAirCoordinator, MicroAirData
from .entity import MicroAirEntity
from .microair.protocol import StatusCode


@dataclass(frozen=True, kw_only=True)
class MicroAirSensorDescription(SensorEntityDescription):
    value: Callable[[MicroAirData], str | int | float | None]


SENSORS = (
    MicroAirSensorDescription(
        key="status",
        name="Status",
        device_class=SensorDeviceClass.ENUM,
        options=[
            status.name.lower() for status in StatusCode if status != StatusCode.UNKNOWN
        ],
        value=lambda data: (
            data.live.status.name.lower()
            if data.live.status != StatusCode.UNKNOWN
            else None
        ),
    ),
    MicroAirSensorDescription(
        key="learned_starts",
        name="Learned starts",
        value=lambda data: data.live.learned_starts,
    ),
    MicroAirSensorDescription(
        key="current_a",
        name="Current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda data: data.live.current_a,
    ),
    MicroAirSensorDescription(
        key="line_hz",
        name="Line frequency",
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value=lambda data: data.live.line_hz,
    ),
    MicroAirSensorDescription(
        key="last_start_peak_a",
        name="Last start peak",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda data: data.live.last_start_peak_a,
    ),
    MicroAirSensorDescription(
        key="scpt_delay_s",
        name="Short cycle delay",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda data: data.live.scpt_delay_s,
    ),
    MicroAirSensorDescription(
        key="total_faults",
        name="Total faults",
        state_class=SensorStateClass.TOTAL,
        value=lambda data: data.live.total_faults,
    ),
    MicroAirSensorDescription(
        key="total_starts",
        name="Total starts",
        state_class=SensorStateClass.TOTAL,
        value=lambda data: data.live.total_starts,
    ),
    MicroAirSensorDescription(
        key="model",
        name="Model",
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda data: data.eeprom.model,
    ),
    MicroAirSensorDescription(
        key="firmware",
        name="Firmware",
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda data: data.eeprom.firmware,
    ),
    MicroAirSensorDescription(
        key="startup_mask",
        name="Startup mask",
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda data: f"0x{data.eeprom.startup_mask:02X}",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MicroAirConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities(
        MicroAirSensor(entry.runtime_data, description) for description in SENSORS
    )


class MicroAirSensor(MicroAirEntity, SensorEntity):
    entity_description: MicroAirSensorDescription

    def __init__(
        self, coordinator: MicroAirCoordinator, description: MicroAirSensorDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> str | int | float | None:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, int] | None:
        if (
            self.entity_description.key == "status"
            and self.coordinator.data is not None
        ):
            return {"raw_status": self.coordinator.data.live.raw_status}
        return None
