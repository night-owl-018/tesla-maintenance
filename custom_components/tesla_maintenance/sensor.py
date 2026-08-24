"""Sensor platform for the Tesla Maintenance Tracker.

Sensors expose mileage, costs and maintenance status. Values that cannot be
derived from real data return ``None`` (shown as *Unknown*) rather than a
fabricated number.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONDITION_GOOD, DOMAIN
from .coordinator import TeslaMaintenanceCoordinator, TeslaMaintenanceData
from .entity import TeslaMaintenanceEntity

if TYPE_CHECKING:
    from . import TeslaMaintenanceConfigEntry


@dataclass(frozen=True, kw_only=True)
class TeslaMaintenanceSensorDescription(SensorEntityDescription):
    """Describes a maintenance sensor."""

    value_fn: Callable[[TeslaMaintenanceData], Any]
    attributes_fn: Callable[[TeslaMaintenanceData], dict[str, Any]] | None = None
    unit_fn: Callable[[TeslaMaintenanceCoordinator], str | None] | None = None


def _next_due_attributes(data: TeslaMaintenanceData) -> dict[str, Any]:
    """Return details about the schedule that is due next."""
    if data.next_due is None:
        return {"item_name": None, "source": None, "status": None}
    return data.next_due.to_dict()


def _due_attributes(data: TeslaMaintenanceData) -> dict[str, Any]:
    """Return the list of items that are due or due soon."""
    return {"items": [item.to_dict() for item in data.due_items]}


def _overdue_attributes(data: TeslaMaintenanceData) -> dict[str, Any]:
    """Return the list of overdue items."""
    return {"items": [item.to_dict() for item in data.overdue_items]}


def _tire_condition(data: TeslaMaintenanceData) -> str | None:
    """Summarise tire condition from recorded tread depth."""
    depths = [
        tire["current_tread_depth"]
        for tire in data.tires
        if tire.get("current_tread_depth") is not None
    ]
    if not depths:
        return None
    # Tread depths are recorded in 32nds of an inch.
    lowest = min(depths)
    if lowest <= 2:
        return "Replace"
    if lowest <= 4:
        return "Needs Service"
    if lowest <= 6:
        return "Fair"
    return CONDITION_GOOD


def _brake_condition(data: TeslaMaintenanceData) -> str | None:
    """Return the worst recorded brake condition across both axles."""
    order = ["Good", "Fair", "Needs Service", "Replace"]
    conditions = [record.get("condition") for record in data.brakes.values()]
    known = [item for item in conditions if item in order]
    if not known:
        return None
    return max(known, key=order.index)


def _battery_condition(data: TeslaMaintenanceData) -> str | None:
    """Return the most recent recorded battery-related maintenance status.

    This reflects logged inspections only. Battery health is never inferred
    from telemetry.
    """
    battery_items = [
        item for item in data.schedule_statuses if item.category == "Battery"
    ]
    if not battery_items:
        return None
    return battery_items[0].status


SENSORS: tuple[TeslaMaintenanceSensorDescription, ...] = (
    TeslaMaintenanceSensorDescription(
        key="current_mileage",
        translation_key="current_mileage",
        icon="mdi:counter",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: data.current_mileage,
        unit_fn=lambda coordinator: coordinator.distance_unit,
        attributes_fn=lambda data: {
            "mileage_source": data.mileage_source,
            "telemetry_available": data.telemetry_available,
        },
    ),
    TeslaMaintenanceSensorDescription(
        key="total_maintenance_cost",
        translation_key="total_maintenance_cost",
        icon="mdi:cash-multiple",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda data: data.analytics.get("total_cost"),
        unit_fn=lambda coordinator: coordinator.currency,
        attributes_fn=lambda data: {
            "cost_by_year": data.analytics.get("cost_by_year", {}),
            "cost_by_category": data.analytics.get("cost_by_category", {}),
            "cost_by_provider": data.analytics.get("cost_by_provider", {}),
        },
    ),
    TeslaMaintenanceSensorDescription(
        key="maintenance_cost_this_year",
        translation_key="maintenance_cost_this_year",
        icon="mdi:cash-clock",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda data: data.analytics.get("cost_this_year"),
        unit_fn=lambda coordinator: coordinator.currency,
        attributes_fn=lambda data: {
            "cost_last_year": data.analytics.get("cost_last_year"),
            "cost_by_month": data.analytics.get("cost_by_month", {}),
        },
    ),
    TeslaMaintenanceSensorDescription(
        key="last_service_date",
        translation_key="last_service_date",
        icon="mdi:calendar-check",
        device_class=SensorDeviceClass.DATE,
        value_fn=lambda data: _parse_date(data),
        attributes_fn=lambda data: {
            "title": (data.last_service or {}).get("title"),
            "provider": (data.last_service or {}).get("service_provider"),
            "notes": (data.last_service or {}).get("notes"),
            "total_cost": (data.last_service or {}).get("total_cost"),
        },
    ),
    TeslaMaintenanceSensorDescription(
        key="last_service_mileage",
        translation_key="last_service_mileage",
        icon="mdi:map-marker-distance",
        value_fn=lambda data: (data.last_service or {}).get("mileage"),
        unit_fn=lambda coordinator: coordinator.distance_unit,
    ),
    TeslaMaintenanceSensorDescription(
        key="next_service_mileage",
        translation_key="next_service_mileage",
        icon="mdi:wrench-clock",
        value_fn=lambda data: data.next_due.next_due_mileage if data.next_due else None,
        unit_fn=lambda coordinator: coordinator.distance_unit,
        attributes_fn=_next_due_attributes,
    ),
    TeslaMaintenanceSensorDescription(
        key="miles_until_service",
        translation_key="miles_until_service",
        icon="mdi:road-variant",
        value_fn=lambda data: data.next_due.miles_remaining if data.next_due else None,
        unit_fn=lambda coordinator: coordinator.distance_unit,
        attributes_fn=_next_due_attributes,
    ),
    TeslaMaintenanceSensorDescription(
        key="days_until_service",
        translation_key="days_until_service",
        icon="mdi:calendar-clock",
        native_unit_of_measurement="d",
        value_fn=lambda data: data.next_due.days_remaining if data.next_due else None,
        attributes_fn=_next_due_attributes,
    ),
    TeslaMaintenanceSensorDescription(
        key="maintenance_items_due",
        translation_key="maintenance_items_due",
        icon="mdi:alert-circle-outline",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: len(data.due_items),
        attributes_fn=_due_attributes,
    ),
    TeslaMaintenanceSensorDescription(
        key="maintenance_items_overdue",
        translation_key="maintenance_items_overdue",
        icon="mdi:alert-octagon",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: len(data.overdue_items),
        attributes_fn=_overdue_attributes,
    ),
    TeslaMaintenanceSensorDescription(
        key="total_service_records",
        translation_key="total_service_records",
        icon="mdi:file-document-multiple",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.analytics.get("service_count", 0),
        attributes_fn=lambda data: {
            "first_service_date": data.analytics.get("first_service_date"),
            "average_service_cost": data.analytics.get("average_service_cost"),
        },
    ),
    TeslaMaintenanceSensorDescription(
        key="average_annual_maintenance_cost",
        translation_key="average_annual_maintenance_cost",
        icon="mdi:chart-line",
        device_class=SensorDeviceClass.MONETARY,
        value_fn=lambda data: data.analytics.get("average_annual_cost"),
        unit_fn=lambda coordinator: coordinator.currency,
    ),
    TeslaMaintenanceSensorDescription(
        key="cost_per_mile",
        translation_key="cost_per_mile",
        icon="mdi:currency-usd",
        value_fn=lambda data: data.analytics.get("cost_per_mile"),
        unit_fn=lambda coordinator: f"{coordinator.currency}/{coordinator.distance_unit}",
    ),
    TeslaMaintenanceSensorDescription(
        key="maintenance_health",
        translation_key="maintenance_health",
        icon="mdi:heart-pulse",
        value_fn=lambda data: data.health,
        attributes_fn=lambda data: {
            "due_count": len(data.due_items),
            "overdue_count": len(data.overdue_items),
            "schedules": [item.to_dict() for item in data.schedule_statuses],
        },
    ),
    TeslaMaintenanceSensorDescription(
        key="tire_condition",
        translation_key="tire_condition",
        icon="mdi:tire",
        value_fn=_tire_condition,
        attributes_fn=lambda data: {"tires": data.tires},
    ),
    TeslaMaintenanceSensorDescription(
        key="brake_condition",
        translation_key="brake_condition",
        icon="mdi:car-brake-alert",
        value_fn=_brake_condition,
        attributes_fn=lambda data: {"axles": data.brakes},
    ),
    TeslaMaintenanceSensorDescription(
        key="battery_condition",
        translation_key="battery_condition",
        icon="mdi:car-battery",
        value_fn=_battery_condition,
        attributes_fn=lambda data: {
            "battery_schedules": [
                item.to_dict()
                for item in data.schedule_statuses
                if item.category == "Battery"
            ]
        },
    ),
    TeslaMaintenanceSensorDescription(
        key="telemetry_status",
        translation_key="telemetry_status",
        icon="mdi:transit-connection-variant",
        value_fn=lambda data: "Available" if data.telemetry_available else "Unavailable",
        attributes_fn=lambda data: {
            "optional_entities": data.optional_entities,
            "maintenance_database": "Available",
        },
    ),
)


def _parse_date(data: TeslaMaintenanceData) -> Any:
    """Return the last service date as a date object, or None."""
    from datetime import date

    raw = (data.last_service or {}).get("service_date")
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TeslaMaintenanceConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the maintenance sensors."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        TeslaMaintenanceSensor(coordinator, description) for description in SENSORS
    )


class TeslaMaintenanceSensor(TeslaMaintenanceEntity, SensorEntity):
    """A sensor derived from the maintenance database."""

    entity_description: TeslaMaintenanceSensorDescription

    def __init__(
        self,
        coordinator: TeslaMaintenanceCoordinator,
        description: TeslaMaintenanceSensorDescription,
    ) -> None:
        """Initialise the sensor from its description."""
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._attr_translation_key = description.translation_key or description.key
        if description.unit_fn is not None:
            self._attr_native_unit_of_measurement = description.unit_fn(coordinator)

    @property
    def native_value(self) -> Any:
        """Return the sensor value, or None when data is unavailable."""
        try:
            return self.entity_description.value_fn(self.coordinator.data)
        except (KeyError, TypeError, ValueError):
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return supporting detail for dashboards and automations."""
        if self.entity_description.attributes_fn is None:
            return None
        return self.entity_description.attributes_fn(self.coordinator.data)


__all__ = ["DOMAIN", "async_setup_entry"]
