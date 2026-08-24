"""Binary sensors for maintenance due/overdue conditions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import STATUS_DUE, STATUS_DUE_SOON, STATUS_OVERDUE
from .coordinator import TeslaMaintenanceCoordinator, TeslaMaintenanceData
from .entity import TeslaMaintenanceEntity

if TYPE_CHECKING:
    from . import TeslaMaintenanceConfigEntry

_DUE_STATUSES = (STATUS_DUE, STATUS_DUE_SOON, STATUS_OVERDUE)


@dataclass(frozen=True, kw_only=True)
class TeslaMaintenanceBinarySensorDescription(BinarySensorEntityDescription):
    """Describes a maintenance binary sensor."""

    value_fn: Callable[[TeslaMaintenanceData], bool]
    attributes_fn: Callable[[TeslaMaintenanceData], dict[str, Any]] | None = None


def _category_due(data: TeslaMaintenanceData, category: str) -> bool:
    """Return True when any schedule in a category needs attention."""
    return any(
        item.category == category and item.status in _DUE_STATUSES
        for item in data.schedule_statuses
    )


def _category_items(data: TeslaMaintenanceData, category: str) -> dict[str, Any]:
    """Return the schedules in a category that need attention."""
    return {
        "items": [
            item.to_dict()
            for item in data.schedule_statuses
            if item.category == category and item.status in _DUE_STATUSES
        ]
    }


BINARY_SENSORS: tuple[TeslaMaintenanceBinarySensorDescription, ...] = (
    TeslaMaintenanceBinarySensorDescription(
        key="maintenance_due",
        translation_key="maintenance_due",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:wrench-clock",
        value_fn=lambda data: bool(data.due_items or data.overdue_items),
        attributes_fn=lambda data: {
            "due": [item.to_dict() for item in data.due_items],
            "overdue": [item.to_dict() for item in data.overdue_items],
        },
    ),
    TeslaMaintenanceBinarySensorDescription(
        key="maintenance_overdue",
        translation_key="maintenance_overdue",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:alert-octagon",
        value_fn=lambda data: bool(data.overdue_items),
        attributes_fn=lambda data: {
            "overdue": [item.to_dict() for item in data.overdue_items]
        },
    ),
    TeslaMaintenanceBinarySensorDescription(
        key="tire_service_due",
        translation_key="tire_service_due",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:tire",
        value_fn=lambda data: _category_due(data, "Tires"),
        attributes_fn=lambda data: _category_items(data, "Tires"),
    ),
    TeslaMaintenanceBinarySensorDescription(
        key="brake_service_due",
        translation_key="brake_service_due",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:car-brake-alert",
        value_fn=lambda data: _category_due(data, "Brakes"),
        attributes_fn=lambda data: _category_items(data, "Brakes"),
    ),
    TeslaMaintenanceBinarySensorDescription(
        key="telemetry_unavailable",
        translation_key="telemetry_unavailable",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        icon="mdi:transit-connection-variant",
        # CONNECTIVITY: on means connected.
        value_fn=lambda data: data.telemetry_available,
        attributes_fn=lambda data: {"optional_entities": data.optional_entities},
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TeslaMaintenanceConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the maintenance binary sensors."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        TeslaMaintenanceBinarySensor(coordinator, description)
        for description in BINARY_SENSORS
    )


class TeslaMaintenanceBinarySensor(TeslaMaintenanceEntity, BinarySensorEntity):
    """A binary sensor derived from schedule status."""

    entity_description: TeslaMaintenanceBinarySensorDescription

    def __init__(
        self,
        coordinator: TeslaMaintenanceCoordinator,
        description: TeslaMaintenanceBinarySensorDescription,
    ) -> None:
        """Initialise from the description."""
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._attr_translation_key = description.translation_key or description.key

    @property
    def is_on(self) -> bool:
        """Return the current state."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return supporting detail."""
        if self.entity_description.attributes_fn is None:
            return None
        return self.entity_description.attributes_fn(self.coordinator.data)
