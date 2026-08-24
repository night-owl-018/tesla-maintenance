"""Shared entity base for the Tesla Maintenance Tracker."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TeslaMaintenanceCoordinator


class TeslaMaintenanceEntity(CoordinatorEntity[TeslaMaintenanceCoordinator]):
    """Base class that attaches every entity to the vehicle device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: TeslaMaintenanceCoordinator, key: str) -> None:
        """Register the entity against its vehicle device."""
        super().__init__(coordinator)
        self._key = key
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{key}"
        vehicle = coordinator.data.vehicle
        model = vehicle.model or "Tesla"
        # The VIN is deliberately not published to the device registry.
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)},
            name=vehicle.name,
            manufacturer="Tesla",
            model=f"{vehicle.year} {model}".strip() if vehicle.year else model,
            configuration_url=None,
        )

    @property
    def vehicle_id(self) -> int:
        """Return the database id of this entity's vehicle."""
        return self.coordinator.vehicle_id
