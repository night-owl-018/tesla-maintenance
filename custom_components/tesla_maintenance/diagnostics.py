"""Diagnostics for the Tesla Maintenance Tracker.

Diagnostics describe configuration and health only. The VIN, location entity
states and note contents are never included.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import (
    ALL_ENTITY_KEYS,
    CONF_LATITUDE_ENTITY,
    CONF_LOCATION_ENTITY,
    CONF_LONGITUDE_ENTITY,
    CONF_VIN,
)

if TYPE_CHECKING:
    from . import TeslaMaintenanceConfigEntry

TO_REDACT = {CONF_VIN, CONF_LOCATION_ENTITY, CONF_LATITUDE_ENTITY, CONF_LONGITUDE_ENTITY}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: TeslaMaintenanceConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    runtime = entry.runtime_data
    coordinator = runtime.coordinator
    data = coordinator.data

    counts = await hass.async_add_executor_job(_counts, runtime)

    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": async_redact_data(dict(entry.options), TO_REDACT),
        },
        "entity_mapping": {
            key: bool({**entry.data, **entry.options}.get(key))
            for key in ALL_ENTITY_KEYS
        },
        "telemetry": {
            "available": data.telemetry_available,
            "mileage_source": data.mileage_source,
            "has_mileage": data.current_mileage is not None,
            "optional_entities": {
                key: value["status"] for key, value in data.optional_entities.items()
            },
        },
        "maintenance": {
            "health": data.health,
            "due_count": len(data.due_items),
            "overdue_count": len(data.overdue_items),
            "schedule_count": len(data.schedule_statuses),
        },
        "database": {
            "path": str(runtime.repository.db_path),
            **counts,
        },
    }


def _counts(runtime: Any) -> dict[str, int]:
    """Return row counts. Runs in the executor."""
    repository = runtime.repository
    vehicle_id = runtime.vehicle_id
    return {
        "vehicles": len(repository.list_vehicles()),
        "service_records": repository.service_count(vehicle_id),
        "maintenance_items": len(repository.list_maintenance_items(vehicle_id)),
        "schedules": len(repository.list_schedules(vehicle_id)),
        "tires": len(repository.list_tire_records(vehicle_id)),
        "brakes": len(repository.list_brake_records(vehicle_id)),
        "attachments": len(repository.list_attachments(vehicle_id=vehicle_id)),
    }
