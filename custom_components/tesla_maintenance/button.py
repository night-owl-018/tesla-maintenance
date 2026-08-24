"""Buttons for exports, backups and manual refresh."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import TeslaMaintenanceCoordinator
from .entity import TeslaMaintenanceEntity
from .exporter import export_csv, export_json

if TYPE_CHECKING:
    from . import TeslaMaintenanceConfigEntry, TeslaMaintenanceRuntime

_LOGGER = logging.getLogger(__name__)

BUTTONS: tuple[ButtonEntityDescription, ...] = (
    ButtonEntityDescription(
        key="export_json", translation_key="export_json", icon="mdi:code-json"
    ),
    ButtonEntityDescription(
        key="export_csv", translation_key="export_csv", icon="mdi:file-delimited"
    ),
    ButtonEntityDescription(
        key="backup_database", translation_key="backup_database", icon="mdi:database-export"
    ),
    ButtonEntityDescription(
        key="refresh", translation_key="refresh", icon="mdi:refresh"
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TeslaMaintenanceConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the maintenance buttons."""
    runtime = entry.runtime_data
    async_add_entities(
        TeslaMaintenanceButton(runtime.coordinator, runtime, description)
        for description in BUTTONS
    )


class TeslaMaintenanceButton(TeslaMaintenanceEntity, ButtonEntity):
    """A button that runs a maintenance housekeeping action."""

    def __init__(
        self,
        coordinator: TeslaMaintenanceCoordinator,
        runtime: TeslaMaintenanceRuntime,
        description: ButtonEntityDescription,
    ) -> None:
        """Initialise the button."""
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._runtime = runtime
        self._attr_translation_key = description.translation_key or description.key

    async def async_press(self) -> None:
        """Handle the press."""
        runtime = self._runtime
        key = self.entity_description.key

        if key == "refresh":
            await self.coordinator.async_request_refresh()
            return

        if key == "export_json":
            path = await self.hass.async_add_executor_job(
                export_json, runtime.repository, runtime.exports_dir, runtime.vehicle_id
            )
        elif key == "export_csv":
            path = await self.hass.async_add_executor_job(
                export_csv, runtime.repository, runtime.exports_dir, runtime.vehicle_id
            )
        else:
            name = f"maintenance_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.db"
            path = await self.hass.async_add_executor_job(
                runtime.repository.backup, runtime.backups_dir / name
            )
        _LOGGER.info("Tesla Maintenance wrote %s", path)
