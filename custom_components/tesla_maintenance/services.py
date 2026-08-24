"""Home Assistant services for the Tesla Maintenance Tracker.

Services are registered once for the integration. Each call resolves a target
vehicle from ``entry_id`` or ``vehicle_id``; when only one vehicle is set up,
both may be omitted.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .attachments import AttachmentError, store_attachment
from .const import (
    ATTR_CATEGORY,
    ATTR_DATE_COMPLETED,
    ATTR_DESCRIPTION,
    ATTR_ENABLED,
    ATTR_ENTRY_ID,
    ATTR_FILE_PATH,
    ATTR_FORMAT,
    ATTR_INTERVAL_DAYS,
    ATTR_INTERVAL_MILES,
    ATTR_ITEMS,
    ATTR_LABOR_COST,
    ATTR_LIMIT,
    ATTR_LOCATION,
    ATTR_MILEAGE,
    ATTR_MODE,
    ATTR_NAME,
    ATTR_NOTES,
    ATTR_PARTS_COST,
    ATTR_QUERY,
    ATTR_SCHEDULE_ID,
    ATTR_SERVICE_DATE,
    ATTR_SERVICE_PROVIDER,
    ATTR_SERVICE_RECORD_ID,
    ATTR_SORT,
    ATTR_SOURCE,
    ATTR_TITLE,
    ATTR_TOTAL_COST,
    ATTR_VEHICLE_ID,
    ATTR_YEAR,
    BRAKE_AXLES,
    BRAKE_CONDITIONS,
    DOMAIN,
    EVENT_DATA_CHANGED,
    EXPORT_FORMAT_CSV,
    EXPORT_FORMAT_JSON,
    EXPORT_FORMATS,
    IMPORT_MODE_MERGE,
    IMPORT_MODES,
    SCHEDULE_SOURCES,
    SERVICE_ADD_ATTACHMENT,
    SERVICE_ADD_BRAKE_RECORD,
    SERVICE_ADD_CATEGORY,
    SERVICE_ADD_MAINTENANCE_ITEM,
    SERVICE_ADD_SCHEDULE,
    SERVICE_ADD_SERVICE_RECORD,
    SERVICE_ADD_TIRE_RECORD,
    SERVICE_BACKUP_DATABASE,
    SERVICE_COMPLETE_MAINTENANCE,
    SERVICE_DELETE_SCHEDULE,
    SERVICE_DELETE_SERVICE_RECORD,
    SERVICE_EXPORT_DATA,
    SERVICE_IMPORT_DATA,
    SERVICE_RESET_MAINTENANCE_SCHEDULE,
    SERVICE_SEARCH_SERVICE_RECORDS,
    SERVICE_SET_MILEAGE,
    SERVICE_UPDATE_SCHEDULE,
    SERVICE_UPDATE_SERVICE_RECORD,
    SORT_NEWEST,
    SORT_OPTIONS,
    SOURCE_USER,
    TIRE_POSITIONS,
)
from .database.models import (
    Attachment,
    BrakeRecord,
    MaintenanceItem,
    MaintenanceSchedule,
    ServiceRecord,
    TireRecord,
)
from .database.repository import RepositoryError
from .exporter import export_csv, export_json, import_json

if TYPE_CHECKING:
    from . import TeslaMaintenanceRuntime

_LOGGER = logging.getLogger(__name__)

_TARGET_SCHEMA = {
    vol.Optional(ATTR_ENTRY_ID): cv.string,
    vol.Optional(ATTR_VEHICLE_ID): vol.Coerce(int),
}

_ITEM_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_NAME): cv.string,
        vol.Optional(ATTR_CATEGORY, default="Other"): cv.string,
        vol.Optional(ATTR_NOTES, default=""): cv.string,
        vol.Optional("cost", default=0): vol.Coerce(float),
        vol.Optional("is_custom", default=False): cv.boolean,
    }
)

ADD_SERVICE_RECORD_SCHEMA = vol.Schema(
    {
        **_TARGET_SCHEMA,
        vol.Optional(ATTR_SERVICE_DATE): cv.string,
        vol.Optional(ATTR_MILEAGE): vol.Coerce(float),
        vol.Optional(ATTR_TITLE, default=""): cv.string,
        vol.Optional(ATTR_DESCRIPTION, default=""): cv.string,
        vol.Optional(ATTR_SERVICE_PROVIDER, default=""): cv.string,
        vol.Optional(ATTR_LOCATION, default=""): cv.string,
        vol.Optional(ATTR_LABOR_COST, default=0): vol.Coerce(float),
        vol.Optional(ATTR_PARTS_COST, default=0): vol.Coerce(float),
        vol.Optional(ATTR_TOTAL_COST): vol.Coerce(float),
        vol.Optional(ATTR_NOTES, default=""): cv.string,
        vol.Optional(ATTR_ITEMS, default=list): vol.All(cv.ensure_list, [_ITEM_SCHEMA]),
    }
)

UPDATE_SERVICE_RECORD_SCHEMA = vol.Schema(
    {
        **_TARGET_SCHEMA,
        vol.Required(ATTR_SERVICE_RECORD_ID): vol.Coerce(int),
        vol.Optional(ATTR_SERVICE_DATE): cv.string,
        vol.Optional(ATTR_MILEAGE): vol.Coerce(float),
        vol.Optional(ATTR_TITLE): cv.string,
        vol.Optional(ATTR_DESCRIPTION): cv.string,
        vol.Optional(ATTR_SERVICE_PROVIDER): cv.string,
        vol.Optional(ATTR_LOCATION): cv.string,
        vol.Optional(ATTR_LABOR_COST): vol.Coerce(float),
        vol.Optional(ATTR_PARTS_COST): vol.Coerce(float),
        vol.Optional(ATTR_TOTAL_COST): vol.Coerce(float),
        vol.Optional(ATTR_NOTES): cv.string,
    }
)

DELETE_SERVICE_RECORD_SCHEMA = vol.Schema(
    {**_TARGET_SCHEMA, vol.Required(ATTR_SERVICE_RECORD_ID): vol.Coerce(int)}
)

ADD_MAINTENANCE_ITEM_SCHEMA = vol.Schema(
    {
        **_TARGET_SCHEMA,
        vol.Required(ATTR_NAME): cv.string,
        vol.Optional(ATTR_CATEGORY, default="Other"): cv.string,
        vol.Optional(ATTR_SERVICE_RECORD_ID): vol.Coerce(int),
        vol.Optional(ATTR_MILEAGE): vol.Coerce(float),
        vol.Optional(ATTR_DATE_COMPLETED): cv.string,
        vol.Optional("cost", default=0): vol.Coerce(float),
        vol.Optional(ATTR_SERVICE_PROVIDER, default=""): cv.string,
        vol.Optional(ATTR_NOTES, default=""): cv.string,
        vol.Optional("is_custom", default=True): cv.boolean,
        vol.Optional("create_schedule", default=False): cv.boolean,
        vol.Optional(ATTR_INTERVAL_MILES): vol.Any(None, vol.Coerce(int)),
        vol.Optional(ATTR_INTERVAL_DAYS): vol.Any(None, vol.Coerce(int)),
    }
)

COMPLETE_MAINTENANCE_SCHEMA = vol.Schema(
    {
        **_TARGET_SCHEMA,
        vol.Optional(ATTR_SCHEDULE_ID): vol.Coerce(int),
        vol.Optional(ATTR_NAME): cv.string,
        vol.Optional(ATTR_SERVICE_DATE): cv.string,
        vol.Optional(ATTR_MILEAGE): vol.Coerce(float),
        vol.Optional("cost", default=0): vol.Coerce(float),
        vol.Optional(ATTR_SERVICE_PROVIDER, default=""): cv.string,
        vol.Optional(ATTR_NOTES, default=""): cv.string,
        vol.Optional("create_service_record", default=True): cv.boolean,
    }
)

ADD_SCHEDULE_SCHEMA = vol.Schema(
    {
        **_TARGET_SCHEMA,
        vol.Required(ATTR_NAME): cv.string,
        vol.Optional(ATTR_CATEGORY, default="Other"): cv.string,
        vol.Optional(ATTR_INTERVAL_MILES): vol.Any(None, vol.Coerce(int)),
        vol.Optional(ATTR_INTERVAL_DAYS): vol.Any(None, vol.Coerce(int)),
        vol.Optional(ATTR_SOURCE, default=SOURCE_USER): vol.In(SCHEDULE_SOURCES),
        vol.Optional(ATTR_NOTES, default=""): cv.string,
        vol.Optional("last_service_date"): cv.string,
        vol.Optional("last_service_mileage"): vol.Coerce(float),
    }
)

UPDATE_SCHEDULE_SCHEMA = vol.Schema(
    {
        **_TARGET_SCHEMA,
        vol.Required(ATTR_SCHEDULE_ID): vol.Coerce(int),
        vol.Optional(ATTR_NAME): cv.string,
        vol.Optional(ATTR_CATEGORY): cv.string,
        vol.Optional(ATTR_INTERVAL_MILES): vol.Any(None, vol.Coerce(int)),
        vol.Optional(ATTR_INTERVAL_DAYS): vol.Any(None, vol.Coerce(int)),
        vol.Optional(ATTR_ENABLED): cv.boolean,
        vol.Optional(ATTR_NOTES): cv.string,
    }
)

SCHEDULE_ID_SCHEMA = vol.Schema(
    {**_TARGET_SCHEMA, vol.Required(ATTR_SCHEDULE_ID): vol.Coerce(int)}
)

RESET_SCHEDULE_SCHEMA = vol.Schema(
    {
        **_TARGET_SCHEMA,
        vol.Required(ATTR_SCHEDULE_ID): vol.Coerce(int),
        vol.Optional(ATTR_SERVICE_DATE): cv.string,
        vol.Optional(ATTR_MILEAGE): vol.Coerce(float),
    }
)

ADD_ATTACHMENT_SCHEMA = vol.Schema(
    {
        **_TARGET_SCHEMA,
        vol.Required(ATTR_FILE_PATH): cv.string,
        vol.Optional(ATTR_SERVICE_RECORD_ID): vol.Coerce(int),
    }
)

ADD_CATEGORY_SCHEMA = vol.Schema({**_TARGET_SCHEMA, vol.Required(ATTR_NAME): cv.string})

ADD_TIRE_SCHEMA = vol.Schema(
    {
        **_TARGET_SCHEMA,
        vol.Required("position"): vol.In(TIRE_POSITIONS),
        vol.Optional("brand", default=""): cv.string,
        vol.Optional("model", default=""): cv.string,
        vol.Optional("size", default=""): cv.string,
        vol.Optional("installation_date"): cv.string,
        vol.Optional("installation_mileage"): vol.Coerce(float),
        vol.Optional("current_tread_depth"): vol.Coerce(float),
        vol.Optional("original_tread_depth"): vol.Coerce(float),
        vol.Optional("dot_date"): cv.string,
        vol.Optional("purchase_cost", default=0): vol.Coerce(float),
        vol.Optional("replacement_cost", default=0): vol.Coerce(float),
        vol.Optional(ATTR_NOTES, default=""): cv.string,
    }
)

ADD_BRAKE_SCHEMA = vol.Schema(
    {
        **_TARGET_SCHEMA,
        vol.Required("axle"): vol.In(BRAKE_AXLES),
        vol.Optional("condition", default="Good"): vol.In(BRAKE_CONDITIONS),
        vol.Optional("pad_thickness"): vol.Coerce(float),
        vol.Optional("rotor_condition", default=""): cv.string,
        vol.Optional("inspection_date"): cv.string,
        vol.Optional("inspection_mileage"): vol.Coerce(float),
        vol.Optional(ATTR_NOTES, default=""): cv.string,
    }
)

SET_MILEAGE_SCHEMA = vol.Schema(
    {**_TARGET_SCHEMA, vol.Required(ATTR_MILEAGE): vol.Coerce(float)}
)

SEARCH_SCHEMA = vol.Schema(
    {
        **_TARGET_SCHEMA,
        vol.Optional(ATTR_QUERY): cv.string,
        vol.Optional(ATTR_YEAR): vol.Coerce(int),
        vol.Optional(ATTR_CATEGORY): cv.string,
        vol.Optional(ATTR_SERVICE_PROVIDER): cv.string,
        vol.Optional(ATTR_NAME): cv.string,
        vol.Optional("min_cost"): vol.Coerce(float),
        vol.Optional("max_cost"): vol.Coerce(float),
        vol.Optional(ATTR_SORT, default=SORT_NEWEST): vol.In(SORT_OPTIONS),
        vol.Optional(ATTR_LIMIT, default=50): vol.Coerce(int),
    }
)

EXPORT_SCHEMA = vol.Schema(
    {
        **_TARGET_SCHEMA,
        vol.Optional(ATTR_FORMAT, default=EXPORT_FORMAT_JSON): vol.In(EXPORT_FORMATS),
        vol.Optional("all_vehicles", default=False): cv.boolean,
    }
)

IMPORT_SCHEMA = vol.Schema(
    {
        **_TARGET_SCHEMA,
        vol.Required(ATTR_FILE_PATH): cv.string,
        vol.Optional(ATTR_MODE, default=IMPORT_MODE_MERGE): vol.In(IMPORT_MODES),
    }
)

BACKUP_SCHEMA = vol.Schema({**_TARGET_SCHEMA})


def _resolve_runtime(hass: HomeAssistant, call: ServiceCall) -> TeslaMaintenanceRuntime:
    """Find the runtime for the targeted vehicle."""
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    if not entries:
        raise ServiceValidationError(
            "No loaded Tesla Maintenance Tracker config entries were found"
        )

    entry_id = call.data.get(ATTR_ENTRY_ID)
    vehicle_id = call.data.get(ATTR_VEHICLE_ID)

    for entry in entries:
        runtime: TeslaMaintenanceRuntime = entry.runtime_data
        if entry_id and entry.entry_id == entry_id:
            return runtime
        if vehicle_id and runtime.vehicle_id == int(vehicle_id):
            return runtime

    if entry_id or vehicle_id:
        raise ServiceValidationError(
            "No Tesla Maintenance Tracker vehicle matches the supplied "
            "entry_id/vehicle_id"
        )
    if len(entries) > 1:
        raise ServiceValidationError(
            "Multiple vehicles are configured - specify entry_id or vehicle_id"
        )
    return entries[0].runtime_data


def _notify_change(hass: HomeAssistant, runtime: TeslaMaintenanceRuntime) -> None:
    """Fire the data-changed event so dashboards can refresh."""
    hass.bus.async_fire(EVENT_DATA_CHANGED, {ATTR_VEHICLE_ID: runtime.vehicle_id})


@callback
def async_register_services(hass: HomeAssistant) -> None:
    """Register every service exactly once."""
    if hass.services.has_service(DOMAIN, SERVICE_ADD_SERVICE_RECORD):
        return

    async def _run(runtime: TeslaMaintenanceRuntime, func: Any, *args: Any) -> Any:
        """Run a blocking repository call in the executor and refresh."""
        result = await hass.async_add_executor_job(func, *args)
        await runtime.coordinator.async_request_refresh()
        _notify_change(hass, runtime)
        return result

    async def add_service_record(call: ServiceCall) -> ServiceResponse:
        runtime = _resolve_runtime(hass, call)
        record = ServiceRecord(
            vehicle_id=runtime.vehicle_id,
            service_date=call.data.get(ATTR_SERVICE_DATE, ""),
            mileage=call.data.get(ATTR_MILEAGE),
            title=call.data.get(ATTR_TITLE, ""),
            description=call.data.get(ATTR_DESCRIPTION, ""),
            service_provider=call.data.get(ATTR_SERVICE_PROVIDER, ""),
            location=call.data.get(ATTR_LOCATION, ""),
            labor_cost=call.data.get(ATTR_LABOR_COST, 0),
            parts_cost=call.data.get(ATTR_PARTS_COST, 0),
            total_cost=call.data.get(ATTR_TOTAL_COST, 0),
            notes=call.data.get(ATTR_NOTES, ""),
        )
        if record.mileage is None:
            record.mileage = runtime.coordinator.data.current_mileage
        items = [
            MaintenanceItem(
                vehicle_id=runtime.vehicle_id,
                name=item[ATTR_NAME],
                category=item.get(ATTR_CATEGORY, "Other"),
                notes=item.get(ATTR_NOTES, ""),
                cost=item.get("cost", 0),
                is_custom=item.get("is_custom", False),
            )
            for item in call.data.get(ATTR_ITEMS, [])
        ]
        try:
            record_id = await _run(
                runtime, runtime.repository.add_service_record, record, items
            )
        except RepositoryError as err:
            raise HomeAssistantError(str(err)) from err
        return {"service_record_id": record_id}

    async def update_service_record(call: ServiceCall) -> None:
        runtime = _resolve_runtime(hass, call)
        updates = {
            key: value
            for key, value in call.data.items()
            if key not in (ATTR_ENTRY_ID, ATTR_VEHICLE_ID, ATTR_SERVICE_RECORD_ID)
        }
        if not updates:
            raise ServiceValidationError("No fields supplied to update")
        try:
            await _run(
                runtime,
                runtime.repository.update_service_record,
                int(call.data[ATTR_SERVICE_RECORD_ID]),
                updates,
            )
        except RepositoryError as err:
            raise HomeAssistantError(str(err)) from err

    async def delete_service_record(call: ServiceCall) -> None:
        runtime = _resolve_runtime(hass, call)
        await _run(
            runtime,
            runtime.repository.delete_service_record,
            int(call.data[ATTR_SERVICE_RECORD_ID]),
        )

    async def add_maintenance_item(call: ServiceCall) -> ServiceResponse:
        """Add a maintenance item, optionally custom and optionally recurring."""
        runtime = _resolve_runtime(hass, call)
        repository = runtime.repository
        category = call.data.get(ATTR_CATEGORY, "Other")
        mileage = call.data.get(ATTR_MILEAGE) or runtime.coordinator.data.current_mileage

        # A custom category is created on demand so the user is never forced
        # to fall back to "Other".
        await hass.async_add_executor_job(
            repository.add_category, runtime.vehicle_id, category
        )

        record_id = call.data.get(ATTR_SERVICE_RECORD_ID)
        cost = call.data.get("cost", 0)
        if record_id is None:
            record = ServiceRecord(
                vehicle_id=runtime.vehicle_id,
                service_date=call.data.get(ATTR_DATE_COMPLETED, ""),
                mileage=mileage,
                title=call.data[ATTR_NAME],
                service_provider=call.data.get(ATTR_SERVICE_PROVIDER, ""),
                total_cost=cost,
                notes=call.data.get(ATTR_NOTES, ""),
            )
            item = MaintenanceItem(
                vehicle_id=runtime.vehicle_id,
                name=call.data[ATTR_NAME],
                category=category,
                cost=cost,
                notes=call.data.get(ATTR_NOTES, ""),
                is_custom=call.data.get("is_custom", True),
            )
            record_id = await hass.async_add_executor_job(
                repository.add_service_record, record, [item]
            )
        else:
            item = MaintenanceItem(
                service_record_id=int(record_id),
                vehicle_id=runtime.vehicle_id,
                name=call.data[ATTR_NAME],
                category=category,
                mileage=mileage,
                date_completed=call.data.get(ATTR_DATE_COMPLETED),
                cost=cost,
                notes=call.data.get(ATTR_NOTES, ""),
                is_custom=call.data.get("is_custom", True),
            )
            await hass.async_add_executor_job(repository.add_maintenance_item, item)

        schedule_id: int | None = None
        if call.data.get("create_schedule"):
            interval_miles = call.data.get(ATTR_INTERVAL_MILES)
            interval_days = call.data.get(ATTR_INTERVAL_DAYS)
            if not interval_miles and not interval_days:
                raise ServiceValidationError(
                    "Recurring maintenance needs interval_miles, interval_days, or both"
                )
            schedule_id = await hass.async_add_executor_job(
                repository.add_schedule,
                MaintenanceSchedule(
                    vehicle_id=runtime.vehicle_id,
                    item_name=call.data[ATTR_NAME],
                    category=category,
                    interval_miles=interval_miles,
                    interval_days=interval_days,
                    last_service_mileage=mileage,
                    last_service_date=call.data.get(ATTR_DATE_COMPLETED),
                    source=SOURCE_USER,
                    notes=call.data.get(ATTR_NOTES, ""),
                ),
            )

        await runtime.coordinator.async_request_refresh()
        _notify_change(hass, runtime)
        return {"service_record_id": record_id, "schedule_id": schedule_id}

    async def complete_maintenance(call: ServiceCall) -> ServiceResponse:
        """Mark a schedule as serviced and optionally log a service record."""
        runtime = _resolve_runtime(hass, call)
        repository = runtime.repository
        schedule_id = call.data.get(ATTR_SCHEDULE_ID)
        name = call.data.get(ATTR_NAME)
        if schedule_id is None and not name:
            raise ServiceValidationError("Supply either schedule_id or name")

        mileage = call.data.get(ATTR_MILEAGE) or runtime.coordinator.data.current_mileage
        service_date = call.data.get(ATTR_SERVICE_DATE)
        record_id: int | None = None

        schedule = None
        if schedule_id is not None:
            schedule = await hass.async_add_executor_job(
                repository.get_schedule, int(schedule_id)
            )
            if schedule is None:
                raise ServiceValidationError(f"Unknown schedule id {schedule_id}")
            name = schedule.item_name

        if call.data.get("create_service_record", True):
            record = ServiceRecord(
                vehicle_id=runtime.vehicle_id,
                service_date=service_date or "",
                mileage=mileage,
                title=str(name),
                service_provider=call.data.get(ATTR_SERVICE_PROVIDER, ""),
                total_cost=call.data.get("cost", 0),
                notes=call.data.get(ATTR_NOTES, ""),
            )
            item = MaintenanceItem(
                vehicle_id=runtime.vehicle_id,
                name=str(name),
                category=schedule.category if schedule else "Other",
                cost=call.data.get("cost", 0),
                notes=call.data.get(ATTR_NOTES, ""),
            )
            record_id = await hass.async_add_executor_job(
                repository.add_service_record, record, [item]
            )
        elif schedule_id is not None:
            await hass.async_add_executor_job(
                repository.reset_schedule, int(schedule_id)
            )
        else:
            await hass.async_add_executor_job(
                repository.mark_schedule_serviced, runtime.vehicle_id, str(name)
            )

        await runtime.coordinator.async_request_refresh()
        _notify_change(hass, runtime)
        return {"service_record_id": record_id}

    async def add_schedule(call: ServiceCall) -> ServiceResponse:
        runtime = _resolve_runtime(hass, call)
        schedule = MaintenanceSchedule(
            vehicle_id=runtime.vehicle_id,
            item_name=call.data[ATTR_NAME],
            category=call.data.get(ATTR_CATEGORY, "Other"),
            interval_miles=call.data.get(ATTR_INTERVAL_MILES),
            interval_days=call.data.get(ATTR_INTERVAL_DAYS),
            last_service_date=call.data.get("last_service_date"),
            last_service_mileage=call.data.get("last_service_mileage"),
            source=call.data.get(ATTR_SOURCE, SOURCE_USER),
            notes=call.data.get(ATTR_NOTES, ""),
        )
        try:
            schedule_id = await _run(runtime, runtime.repository.add_schedule, schedule)
        except RepositoryError as err:
            raise ServiceValidationError(str(err)) from err
        return {"schedule_id": schedule_id}

    async def update_schedule(call: ServiceCall) -> None:
        runtime = _resolve_runtime(hass, call)
        updates: dict[str, Any] = {}
        if ATTR_NAME in call.data:
            updates["item_name"] = call.data[ATTR_NAME]
        for key in (ATTR_CATEGORY, ATTR_INTERVAL_MILES, ATTR_INTERVAL_DAYS, ATTR_NOTES):
            if key in call.data:
                updates[key] = call.data[key]
        if ATTR_ENABLED in call.data:
            updates["enabled"] = 1 if call.data[ATTR_ENABLED] else 0
        if not updates:
            raise ServiceValidationError("No fields supplied to update")
        try:
            await _run(
                runtime,
                runtime.repository.update_schedule,
                int(call.data[ATTR_SCHEDULE_ID]),
                updates,
            )
        except RepositoryError as err:
            raise HomeAssistantError(str(err)) from err

    async def delete_schedule(call: ServiceCall) -> None:
        runtime = _resolve_runtime(hass, call)
        await _run(
            runtime, runtime.repository.delete_schedule, int(call.data[ATTR_SCHEDULE_ID])
        )

    async def reset_maintenance_schedule(call: ServiceCall) -> None:
        runtime = _resolve_runtime(hass, call)

        def _reset() -> bool:
            return runtime.repository.reset_schedule(
                int(call.data[ATTR_SCHEDULE_ID]),
                service_date=call.data.get(ATTR_SERVICE_DATE),
                mileage=call.data.get(ATTR_MILEAGE),
            )

        if not await _run(runtime, _reset):
            raise ServiceValidationError(
                f"Unknown schedule id {call.data[ATTR_SCHEDULE_ID]}"
            )

    async def add_attachment(call: ServiceCall) -> ServiceResponse:
        runtime = _resolve_runtime(hass, call)
        record_id = call.data.get(ATTR_SERVICE_RECORD_ID)

        def _store() -> dict[str, Any]:
            stored, mime_type, size = store_attachment(
                runtime.attachments_dir,
                call.data[ATTR_FILE_PATH],
                int(record_id) if record_id is not None else None,
            )
            attachment_id = runtime.repository.add_attachment(
                Attachment(
                    service_record_id=int(record_id) if record_id is not None else None,
                    vehicle_id=runtime.vehicle_id,
                    filename=stored.name,
                    mime_type=mime_type,
                    path=str(stored),
                    size_bytes=size,
                )
            )
            return {"attachment_id": attachment_id, "path": str(stored)}

        try:
            return await _run(runtime, _store)
        except AttachmentError as err:
            raise ServiceValidationError(str(err)) from err

    async def add_category(call: ServiceCall) -> None:
        runtime = _resolve_runtime(hass, call)
        try:
            await _run(
                runtime,
                runtime.repository.add_category,
                runtime.vehicle_id,
                call.data[ATTR_NAME],
            )
        except RepositoryError as err:
            raise ServiceValidationError(str(err)) from err

    async def add_tire_record(call: ServiceCall) -> ServiceResponse:
        runtime = _resolve_runtime(hass, call)
        tire = TireRecord(
            vehicle_id=runtime.vehicle_id,
            position=call.data["position"],
            brand=call.data.get("brand", ""),
            model=call.data.get("model", ""),
            size=call.data.get("size", ""),
            installation_date=call.data.get("installation_date"),
            installation_mileage=call.data.get("installation_mileage"),
            current_tread_depth=call.data.get("current_tread_depth"),
            original_tread_depth=call.data.get("original_tread_depth"),
            dot_date=call.data.get("dot_date"),
            purchase_cost=call.data.get("purchase_cost", 0),
            replacement_cost=call.data.get("replacement_cost", 0),
            notes=call.data.get(ATTR_NOTES, ""),
        )
        tire_id = await _run(runtime, runtime.repository.add_tire_record, tire)
        return {"tire_id": tire_id}

    async def add_brake_record(call: ServiceCall) -> ServiceResponse:
        runtime = _resolve_runtime(hass, call)
        brake = BrakeRecord(
            vehicle_id=runtime.vehicle_id,
            axle=call.data["axle"],
            condition=call.data.get("condition", "Good"),
            pad_thickness=call.data.get("pad_thickness"),
            rotor_condition=call.data.get("rotor_condition", ""),
            inspection_date=call.data.get("inspection_date"),
            inspection_mileage=call.data.get("inspection_mileage")
            or runtime.coordinator.data.current_mileage,
            notes=call.data.get(ATTR_NOTES, ""),
        )
        brake_id = await _run(runtime, runtime.repository.add_brake_record, brake)
        return {"brake_id": brake_id}

    async def set_mileage(call: ServiceCall) -> None:
        runtime = _resolve_runtime(hass, call)
        await _run(
            runtime,
            runtime.repository.force_set_mileage,
            runtime.vehicle_id,
            float(call.data[ATTR_MILEAGE]),
        )

    async def search_service_records(call: ServiceCall) -> ServiceResponse:
        """Search service history, including note contents."""
        runtime = _resolve_runtime(hass, call)

        def _search() -> list[dict[str, Any]]:
            records = runtime.repository.list_service_records(
                runtime.vehicle_id,
                query=call.data.get(ATTR_QUERY),
                year=call.data.get(ATTR_YEAR),
                category=call.data.get(ATTR_CATEGORY),
                provider=call.data.get(ATTR_SERVICE_PROVIDER),
                item_name=call.data.get(ATTR_NAME),
                min_cost=call.data.get("min_cost"),
                max_cost=call.data.get("max_cost"),
                sort=call.data.get(ATTR_SORT, SORT_NEWEST),
                limit=call.data.get(ATTR_LIMIT, 50),
            )
            return [record.to_dict() for record in records]

        results = await hass.async_add_executor_job(_search)
        return {"count": len(results), "records": results}

    async def export_data(call: ServiceCall) -> ServiceResponse:
        runtime = _resolve_runtime(hass, call)
        vehicle_id = None if call.data.get("all_vehicles") else runtime.vehicle_id
        writer = (
            export_csv if call.data.get(ATTR_FORMAT) == EXPORT_FORMAT_CSV else export_json
        )
        path = await hass.async_add_executor_job(
            writer, runtime.repository, runtime.exports_dir, vehicle_id
        )
        return {"path": path}

    async def import_data(call: ServiceCall) -> ServiceResponse:
        runtime = _resolve_runtime(hass, call)

        def _import() -> dict[str, int]:
            return import_json(
                runtime.repository,
                call.data[ATTR_FILE_PATH],
                runtime.vehicle_id,
                skip_duplicates=True,
            )

        try:
            counts = await _run(runtime, _import)
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err
        return {"imported": counts}

    async def backup_database(call: ServiceCall) -> ServiceResponse:
        runtime = _resolve_runtime(hass, call)

        def _backup() -> str:
            from datetime import UTC, datetime

            name = f"maintenance_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.db"
            return runtime.repository.backup(Path(runtime.backups_dir) / name)

        path = await hass.async_add_executor_job(_backup)
        return {"path": path}

    registrations: list[tuple[str, Any, Any, SupportsResponse]] = [
        (
            SERVICE_ADD_SERVICE_RECORD,
            add_service_record,
            ADD_SERVICE_RECORD_SCHEMA,
            SupportsResponse.OPTIONAL,
        ),
        (
            SERVICE_UPDATE_SERVICE_RECORD,
            update_service_record,
            UPDATE_SERVICE_RECORD_SCHEMA,
            SupportsResponse.NONE,
        ),
        (
            SERVICE_DELETE_SERVICE_RECORD,
            delete_service_record,
            DELETE_SERVICE_RECORD_SCHEMA,
            SupportsResponse.NONE,
        ),
        (
            SERVICE_ADD_MAINTENANCE_ITEM,
            add_maintenance_item,
            ADD_MAINTENANCE_ITEM_SCHEMA,
            SupportsResponse.OPTIONAL,
        ),
        (
            SERVICE_COMPLETE_MAINTENANCE,
            complete_maintenance,
            COMPLETE_MAINTENANCE_SCHEMA,
            SupportsResponse.OPTIONAL,
        ),
        (SERVICE_ADD_SCHEDULE, add_schedule, ADD_SCHEDULE_SCHEMA, SupportsResponse.OPTIONAL),
        (
            SERVICE_UPDATE_SCHEDULE,
            update_schedule,
            UPDATE_SCHEDULE_SCHEMA,
            SupportsResponse.NONE,
        ),
        (
            SERVICE_DELETE_SCHEDULE,
            delete_schedule,
            SCHEDULE_ID_SCHEMA,
            SupportsResponse.NONE,
        ),
        (
            SERVICE_RESET_MAINTENANCE_SCHEDULE,
            reset_maintenance_schedule,
            RESET_SCHEDULE_SCHEMA,
            SupportsResponse.NONE,
        ),
        (
            SERVICE_ADD_ATTACHMENT,
            add_attachment,
            ADD_ATTACHMENT_SCHEMA,
            SupportsResponse.OPTIONAL,
        ),
        (SERVICE_ADD_CATEGORY, add_category, ADD_CATEGORY_SCHEMA, SupportsResponse.NONE),
        (
            SERVICE_ADD_TIRE_RECORD,
            add_tire_record,
            ADD_TIRE_SCHEMA,
            SupportsResponse.OPTIONAL,
        ),
        (
            SERVICE_ADD_BRAKE_RECORD,
            add_brake_record,
            ADD_BRAKE_SCHEMA,
            SupportsResponse.OPTIONAL,
        ),
        (SERVICE_SET_MILEAGE, set_mileage, SET_MILEAGE_SCHEMA, SupportsResponse.NONE),
        (
            SERVICE_SEARCH_SERVICE_RECORDS,
            search_service_records,
            SEARCH_SCHEMA,
            SupportsResponse.ONLY,
        ),
        (SERVICE_EXPORT_DATA, export_data, EXPORT_SCHEMA, SupportsResponse.OPTIONAL),
        (SERVICE_IMPORT_DATA, import_data, IMPORT_SCHEMA, SupportsResponse.OPTIONAL),
        (
            SERVICE_BACKUP_DATABASE,
            backup_database,
            BACKUP_SCHEMA,
            SupportsResponse.OPTIONAL,
        ),
    ]

    for name, handler, schema, supports_response in registrations:
        hass.services.async_register(
            DOMAIN, name, handler, schema=schema, supports_response=supports_response
        )
    _LOGGER.debug("Registered %s services", len(registrations))


@callback
def async_unregister_services(hass: HomeAssistant) -> None:
    """Remove every service when the last entry is unloaded."""
    for service in list(hass.services.async_services_for_domain(DOMAIN)):
        hass.services.async_remove(DOMAIN, service)
