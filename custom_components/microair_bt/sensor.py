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
    UnitOfPower,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import MicroAirConfigEntry, MicroAirCoordinator, MicroAirData
from .entity import MicroAirEntity
from .microair.protocol import (
    SUPERLEARN_BIT,
    FaultProtection,
    StartupFlag,
    StartupMode,
    StatusCode,
)


@dataclass(frozen=True, kw_only=True)
class MicroAirSensorDescription(SensorEntityDescription):
    value: Callable[[MicroAirData], str | int | float | None]
    attributes: Callable[[MicroAirData], dict[str, int | bool] | None] | None = None
    # Decoded from the EEPROM image; unavailable until one has been read.
    eeprom_backed: bool = False


def _startup_bits(data: MicroAirData) -> dict[str, int | bool] | None:
    if data.eeprom is None:
        return None
    mask = data.eeprom.startup_mask
    return {
        "relearn": bool(mask & StartupMode.RELEARN.value),
        "default_ramp": bool(mask & StartupMode.DEFAULT_RAMP.value),
        "no_power_up_delay": bool(mask & StartupFlag.NO_POWER_UP_DELAY),
        "start_delay_mode": bool(mask & StartupFlag.START_DELAY_MODE),
        "superlearn": bool(mask & SUPERLEARN_BIT),
    }


def _fault_bits(data: MicroAirData) -> dict[str, int | bool] | None:
    if data.eeprom is None:
        return None
    mask = data.eeprom.fault_mask
    return {bit.name.lower(): bool(mask & bit) for bit in FaultProtection}


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
        eeprom_backed=True,
        name="Model",
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda data: data.eeprom.model if data.eeprom else None,
    ),
    MicroAirSensorDescription(
        key="firmware",
        eeprom_backed=True,
        name="Firmware",
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda data: data.eeprom.firmware if data.eeprom else None,
    ),
    MicroAirSensorDescription(
        key="startup_mask",
        eeprom_backed=True,
        name="Startup mask",
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda data: f"0x{data.eeprom.startup_mask:02X}" if data.eeprom else None,
        attributes=_startup_bits,
    ),
    MicroAirSensorDescription(
        key="fault_mask",
        eeprom_backed=True,
        name="Fault mask",
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda data: f"0x{data.eeprom.fault_mask:02X}" if data.eeprom else None,
        attributes=_fault_bits,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MicroAirConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [
        MicroAirSensor(coordinator, description) for description in SENSORS
    ]
    entities.append(MicroAirPowerSensor(coordinator))
    async_add_entities(entities)


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
    def available(self) -> bool:
        return super().available and (
            not self.entity_description.eeprom_backed or self.eeprom is not None
        )

    @property
    def extra_state_attributes(self) -> dict[str, int | bool] | None:
        data = self.coordinator.data
        if data is None:
            return None
        if self.entity_description.key == "status":
            return {"raw_status": data.live.raw_status}
        if self.entity_description.attributes is not None:
            return self.entity_description.attributes(data)
        return None


class MicroAirPowerSensor(MicroAirEntity, SensorEntity):
    """Estimated compressor real power from the measured current.

    The EasyStart reports compressor current but not line voltage, so this is
    an estimate: current x nominal voltage x power factor (both configurable).
    It covers the compressor only, not the air handler, and refreshes at the
    polling cadence. The assumptions are exposed as attributes so the estimate
    is transparent; for revenue-grade energy use a dedicated meter.
    """

    _attr_name = "Power"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator: MicroAirCoordinator) -> None:
        super().__init__(coordinator, "power")

    @property
    def native_value(self) -> float | None:
        data = self.coordinator.data
        if data is None:
            return None
        return (
            data.live.current_a
            * self.coordinator.nominal_voltage
            * self.coordinator.power_factor
        )

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        return {
            "estimate": True,
            "scope": "compressor_only",
            "nominal_voltage": self.coordinator.nominal_voltage,
            "power_factor": self.coordinator.power_factor,
        }
