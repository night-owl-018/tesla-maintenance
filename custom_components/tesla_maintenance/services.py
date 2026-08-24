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
    SERVICE_DELETE_BRAKE_RECORD,
    SERVICE_DELETE_CATEGORY,
    SERVICE_DELETE_MAINTENANCE_ITEM,
    SERVICE_DELETE_SCHEDULE,
    SERVICE_DELETE_SERVICE_RECORD,
    SERVICE_DELETE_TIRE_RECORD,
    SERVICE_EXPORT_DATA,
    SERVICE_GET_DATA,
    SERVICE_GET_SERVICE_RECORD,
    SERVICE_IMPORT_DATA,
    SERVICE_RESET_MAINTENANCE_SCHEDULE,
    SERVICE_SEARCH_SERVICE_RECORDS,
    SERVICE_SET_MILEAGE,
    SERVICE_UPDATE_BRAKE_RECORD,
    SERVICE_UPDATE_MAINTENANCE_ITEM,
    SERVICE_UPDATE_SCHEDULE,
    SERVICE_UPDATE_SERVICE_RECORD,
    SERVICE_UPDATE_TIRE_RECORD,
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
