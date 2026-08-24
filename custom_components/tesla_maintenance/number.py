"""Number entity for manual mileage entry.

Available whatever the mileage source is, so mileage can always be corrected by
hand - including while the Tesla integration is down.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import TeslaMaintenanceCoordinator
from .entity import TeslaMaintenanceEntity

if TYPE_CHECKING:
    from . import TeslaMaintenanceConfigEntry, TeslaMaintenanceRuntime


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TeslaMaintenanceConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the manual mileage number entity."""
    runtime = entry.runtime_data
    async_add_entities([TeslaManualMileageNumber(runtime.coordinator, runtime)])


class TeslaManualMileageNumber(TeslaMaintenanceEntity, NumberEntity):
    """Lets the user set the current odometer reading by hand."""

    _attr_translation_key = "manual_mileage"
    _attr_icon = "mdi:counter"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0
    _attr_native_max_value = 2_000_000
    _attr_native_step = 1

    def __init__(
        self, coordinator: TeslaMaintenanceCoordinator, runtime: TeslaMaintenanceRuntime
    ) -> None:
        """Initialise the entity."""
        super().__init__(coordinator, "manual_mileage")
        self._runtime = runtime
        self._attr_native_unit_of_measurement = coordinator.distance_unit

    @property
    def native_value(self) -> float | None:
        """Return the current mileage."""
        return self.coordinator.data.current_mileage

    async def async_set_native_value(self, value: float) -> None:
        """Store a corrected mileage reading."""
        await self.hass.async_add_executor_job(
            self._runtime.repository.force_set_mileage, self.vehicle_id, float(value)
        )
        await self.coordinator.async_request_refresh()
