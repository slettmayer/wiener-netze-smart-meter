"""Sensor entities for Wiener Netze Smart Meter."""

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ZAEHLPUNKTNUMMER, DOMAIN
from .coordinator import SmartMeterCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities from a config entry."""
    coordinator: SmartMeterCoordinator = hass.data[DOMAIN][entry.entry_id]
    zpn = entry.data[CONF_ZAEHLPUNKTNUMMER]

    async_add_entities(
        [
            SmartMeterDiagnosticSensor(coordinator, zpn),
            SmartMeterReadingSensor(coordinator, zpn),
        ]
    )


class SmartMeterDiagnosticSensor(CoordinatorEntity[SmartMeterCoordinator], SensorEntity):
    """Sensor showing the last successful import timestamp."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:database-clock"

    def __init__(self, coordinator: SmartMeterCoordinator, zpn: str) -> None:
        super().__init__(coordinator)
        self._zpn = zpn
        self._attr_unique_id = f"{DOMAIN}_diagnostic_{zpn}"
        self._attr_name = f"Smart Meter Import Status {zpn[-8:]}"

    @property
    def native_value(self) -> str | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("last_import")

    @property
    def extra_state_attributes(self) -> dict:
        if self.coordinator.data is None:
            return {}
        stats_count = self.coordinator.data.get("stats_count", {})
        return {f"imported_hours_{k}": v for k, v in stats_count.items()}


class SmartMeterReadingSensor(CoordinatorEntity[SmartMeterCoordinator], SensorEntity):
    """Sensor showing the latest meter counter value."""

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_icon = "mdi:meter-electric"

    def __init__(self, coordinator: SmartMeterCoordinator, zpn: str) -> None:
        super().__init__(coordinator)
        self._zpn = zpn
        self._attr_unique_id = f"{DOMAIN}_reading_{zpn}"
        self._attr_name = f"Smart Meter Reading {zpn[-8:]}"

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("meter_reading")
