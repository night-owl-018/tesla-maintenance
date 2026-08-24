"""Constants for the Tesla Maintenance Tracker integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "tesla_maintenance"

# --------------------------------------------------------------------------
# Storage
# --------------------------------------------------------------------------
# All user data lives under <config>/tesla_maintenance/ so that it is picked up
# by Home Assistant backups and is NEVER written into .storage or into the
# integration source directory.
DATA_DIR_NAME: Final = "tesla_maintenance"
DB_FILENAME: Final = "maintenance.db"
ATTACHMENTS_DIRNAME: Final = "attachments"
EXPORTS_DIRNAME: Final = "exports"
BACKUPS_DIRNAME: Final = "backups"

# --------------------------------------------------------------------------
# Config entry keys - vehicle information
# --------------------------------------------------------------------------
CONF_VEHICLE_NAME: Final = "vehicle_name"
CONF_VEHICLE_MODEL: Final = "vehicle_model"
CONF_VEHICLE_YEAR: Final = "vehicle_year"
CONF_VIN: Final = "vin"
CONF_PURCHASE_DATE: Final = "purchase_date"
CONF_VEHICLE_ID: Final = "vehicle_id"

# --------------------------------------------------------------------------
# Config entry keys - Tesla entity mapping (telemetry only)
# --------------------------------------------------------------------------
CONF_MILEAGE_SOURCE: Final = "mileage_source"
MILEAGE_SOURCE_ENTITY: Final = "tesla_entity"
MILEAGE_SOURCE_MANUAL: Final = "manual"
MILEAGE_SOURCES: Final = [MILEAGE_SOURCE_ENTITY, MILEAGE_SOURCE_MANUAL]

CONF_ODOMETER_ENTITY: Final = "odometer_entity"
CONF_MANUAL_MILEAGE: Final = "manual_mileage"

CONF_BATTERY_LEVEL_ENTITY: Final = "battery_level_entity"
CONF_BATTERY_RANGE_ENTITY: Final = "battery_range_entity"
CONF_CHARGING_STATE_ENTITY: Final = "charging_state_entity"
CONF_VEHICLE_STATE_ENTITY: Final = "vehicle_state_entity"
CONF_LOCATION_ENTITY: Final = "location_entity"
CONF_LATITUDE_ENTITY: Final = "latitude_entity"
CONF_LONGITUDE_ENTITY: Final = "longitude_entity"
CONF_CLIMATE_STATE_ENTITY: Final = "climate_state_entity"
CONF_TPMS_FL_ENTITY: Final = "tpms_front_left_entity"
CONF_TPMS_FR_ENTITY: Final = "tpms_front_right_entity"
CONF_TPMS_RL_ENTITY: Final = "tpms_rear_left_entity"
CONF_TPMS_RR_ENTITY: Final = "tpms_rear_right_entity"

#: Optional telemetry entities, in display order. (config key, friendly label)
OPTIONAL_ENTITY_KEYS: Final[tuple[tuple[str, str], ...]] = (
    (CONF_BATTERY_LEVEL_ENTITY, "Battery Level"),
    (CONF_BATTERY_RANGE_ENTITY, "Battery Range"),
    (CONF_CHARGING_STATE_ENTITY, "Charging State"),
    (CONF_VEHICLE_STATE_ENTITY, "Vehicle State"),
    (CONF_LOCATION_ENTITY, "Location"),
    (CONF_LATITUDE_ENTITY, "Latitude"),
    (CONF_LONGITUDE_ENTITY, "Longitude"),
    (CONF_CLIMATE_STATE_ENTITY, "Climate State"),
    (CONF_TPMS_FL_ENTITY, "Tire Pressure - Front Left"),
    (CONF_TPMS_FR_ENTITY, "Tire Pressure - Front Right"),
    (CONF_TPMS_RL_ENTITY, "Tire Pressure - Rear Left"),
    (CONF_TPMS_RR_ENTITY, "Tire Pressure - Rear Right"),
)

#: Every entity mapping key. Used to split telemetry config from maintenance data.
ALL_ENTITY_KEYS: Final[tuple[str, ...]] = (
    CONF_ODOMETER_ENTITY,
    *(key for key, _ in OPTIONAL_ENTITY_KEYS),
)

# --------------------------------------------------------------------------
# Config entry keys - maintenance settings
# --------------------------------------------------------------------------
CONF_DISTANCE_UNIT: Final = "distance_unit"
CONF_CURRENCY: Final = "currency"
CONF_WARN_MILES: Final = "warn_miles"
CONF_WARN_DAYS: Final = "warn_days"
CONF_CREATE_DEFAULT_SCHEDULES: Final = "create_default_schedules"

CONF_NOTIFICATIONS_ENABLED: Final = "notifications_enabled"
CONF_NOTIFY_SERVICE: Final = "notify_service"
CONF_NOTIFY_ON_DUE: Final = "notify_on_due"
CONF_NOTIFY_ON_OVERDUE: Final = "notify_on_overdue"

DISTANCE_UNIT_MILES: Final = "mi"
DISTANCE_UNIT_KM: Final = "km"
DISTANCE_UNITS: Final = [DISTANCE_UNIT_MILES, DISTANCE_UNIT_KM]

DEFAULT_CURRENCY: Final = "USD"
DEFAULT_WARN_MILES: Final = 500
DEFAULT_WARN_DAYS: Final = 30
DEFAULT_SCAN_INTERVAL_MINUTES: Final = 15

# --------------------------------------------------------------------------
# Maintenance status
# --------------------------------------------------------------------------
STATUS_OK: Final = "OK"
STATUS_DUE_SOON: Final = "DUE_SOON"
STATUS_DUE: Final = "DUE"
STATUS_OVERDUE: Final = "OVERDUE"
STATUS_COMPLETED: Final = "COMPLETED"
STATUS_DISABLED: Final = "DISABLED"

MAINTENANCE_STATUSES: Final = [
    STATUS_OK,
    STATUS_DUE_SOON,
    STATUS_DUE,
    STATUS_OVERDUE,
    STATUS_COMPLETED,
    STATUS_DISABLED,
]

#: Health roll-up shown on the dashboard.
HEALTH_GOOD: Final = "GOOD"
HEALTH_ATTENTION: Final = "NEEDS ATTENTION"
HEALTH_OVERDUE: Final = "OVERDUE"
HEALTH_UNKNOWN: Final = "UNKNOWN"

# --------------------------------------------------------------------------
# Schedule sources
# --------------------------------------------------------------------------
SOURCE_DEFAULT: Final = "Default"
SOURCE_USER: Final = "User Defined"
SOURCE_TESLA: Final = "Tesla Recommendation"
SCHEDULE_SOURCES: Final = [SOURCE_DEFAULT, SOURCE_USER, SOURCE_TESLA]

# --------------------------------------------------------------------------
# Categories / items
# --------------------------------------------------------------------------
DEFAULT_CATEGORIES: Final[tuple[str, ...]] = (
    "Battery",
    "Brakes",
    "Tires",
    "Suspension",
    "Steering",
    "Fluids",
    "Filters",
    "Electrical",
    "HVAC",
    "Exterior",
    "Interior",
    "Drive Unit",
    "Software",
    "Safety",
    "Inspection",
    "Other",
)

#: Application default maintenance items. These are convenience defaults only -
#: they are NOT presented as official Tesla-required maintenance.
DEFAULT_MAINTENANCE_ITEMS: Final[tuple[tuple[str, str], ...]] = (
    ("Tire Rotation", "Tires"),
    ("Tire Inspection", "Tires"),
    ("Tire Replacement", "Tires"),
    ("Brake Inspection", "Brakes"),
    ("Brake Service", "Brakes"),
    ("Brake Fluid", "Fluids"),
    ("Brake Pad Inspection", "Brakes"),
    ("Brake Rotor Inspection", "Brakes"),
    ("Cabin Air Filter", "Filters"),
    ("HEPA Filter", "Filters"),
    ("Wiper Blades", "Exterior"),
    ("Low Voltage Battery", "Battery"),
    ("Battery Inspection", "Battery"),
    ("High Voltage Battery Inspection", "Battery"),
    ("Wheel Alignment", "Suspension"),
    ("Suspension Inspection", "Suspension"),
    ("Steering Inspection", "Steering"),
    ("Coolant Inspection", "Fluids"),
    ("Drive Unit Inspection", "Drive Unit"),
    ("HVAC Service", "HVAC"),
    ("Safety Inspection", "Safety"),
    ("Software/Service Inspection", "Software"),
    ("Other", "Other"),
)

#: Optional starter schedules. Intervals are this application's own defaults and
#: are labelled SOURCE_DEFAULT - never SOURCE_TESLA.
#: (item_name, category, interval_miles, interval_days)
STARTER_SCHEDULES: Final[tuple[tuple[str, str, int | None, int | None], ...]] = (
    ("Tire Rotation", "Tires", 6250, None),
    ("Cabin Air Filter", "Filters", None, 730),
    ("Brake Fluid", "Fluids", None, 730),
    ("Brake Inspection", "Brakes", None, 365),
    ("Wiper Blades", "Exterior", None, 365),
    ("Tire Inspection", "Tires", None, 180),
)

# --------------------------------------------------------------------------
# Tires / brakes
# --------------------------------------------------------------------------
TIRE_POSITIONS: Final = ["Front Left", "Front Right", "Rear Left", "Rear Right"]
BRAKE_AXLES: Final = ["Front", "Rear"]
CONDITION_GOOD: Final = "Good"
CONDITION_FAIR: Final = "Fair"
CONDITION_NEEDS_SERVICE: Final = "Needs Service"
CONDITION_REPLACE: Final = "Replace"
BRAKE_CONDITIONS: Final = [
    CONDITION_GOOD,
    CONDITION_FAIR,
    CONDITION_NEEDS_SERVICE,
    CONDITION_REPLACE,
]

# --------------------------------------------------------------------------
# Attachments
# --------------------------------------------------------------------------
ALLOWED_ATTACHMENT_MIME_TYPES: Final[dict[str, tuple[str, ...]]] = {
    "image/jpeg": (".jpg", ".jpeg"),
    "image/png": (".png",),
    "image/webp": (".webp",),
    "application/pdf": (".pdf",),
}
ALLOWED_ATTACHMENT_EXTENSIONS: Final[tuple[str, ...]] = (
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".pdf",
)
MAX_ATTACHMENT_BYTES: Final = 20 * 1024 * 1024  # 20 MiB

# --------------------------------------------------------------------------
# Services
# --------------------------------------------------------------------------
SERVICE_ADD_SERVICE_RECORD: Final = "add_service_record"
SERVICE_UPDATE_SERVICE_RECORD: Final = "update_service_record"
SERVICE_DELETE_SERVICE_RECORD: Final = "delete_service_record"
SERVICE_ADD_MAINTENANCE_ITEM: Final = "add_maintenance_item"
SERVICE_COMPLETE_MAINTENANCE: Final = "complete_maintenance"
SERVICE_ADD_SCHEDULE: Final = "add_schedule"
SERVICE_UPDATE_SCHEDULE: Final = "update_schedule"
SERVICE_DELETE_SCHEDULE: Final = "delete_schedule"
SERVICE_RESET_MAINTENANCE_SCHEDULE: Final = "reset_maintenance_schedule"
SERVICE_ADD_ATTACHMENT: Final = "add_attachment"
SERVICE_ADD_CATEGORY: Final = "add_category"
SERVICE_ADD_TIRE_RECORD: Final = "add_tire_record"
SERVICE_ADD_BRAKE_RECORD: Final = "add_brake_record"
SERVICE_SET_MILEAGE: Final = "set_mileage"
SERVICE_SEARCH_SERVICE_RECORDS: Final = "search_service_records"
SERVICE_EXPORT_DATA: Final = "export_data"
SERVICE_IMPORT_DATA: Final = "import_data"
SERVICE_BACKUP_DATABASE: Final = "backup_database"

# Read/write services used by the Lovelace card
SERVICE_GET_DATA: Final = "get_data"
SERVICE_GET_SERVICE_RECORD: Final = "get_service_record"
SERVICE_UPDATE_MAINTENANCE_ITEM: Final = "update_maintenance_item"
SERVICE_DELETE_MAINTENANCE_ITEM: Final = "delete_maintenance_item"
SERVICE_UPDATE_TIRE_RECORD: Final = "update_tire_record"
SERVICE_DELETE_TIRE_RECORD: Final = "delete_tire_record"
SERVICE_UPDATE_BRAKE_RECORD: Final = "update_brake_record"
SERVICE_DELETE_BRAKE_RECORD: Final = "delete_brake_record"
SERVICE_DELETE_CATEGORY: Final = "delete_category"

# Service call attribute names
ATTR_VEHICLE_ID: Final = "vehicle_id"
ATTR_ENTRY_ID: Final = "entry_id"
ATTR_SERVICE_RECORD_ID: Final = "service_record_id"
ATTR_SCHEDULE_ID: Final = "schedule_id"
ATTR_SERVICE_DATE: Final = "service_date"
ATTR_MILEAGE: Final = "mileage"
ATTR_TITLE: Final = "title"
ATTR_DESCRIPTION: Final = "description"
ATTR_SERVICE_PROVIDER: Final = "service_provider"
ATTR_LOCATION: Final = "location"
ATTR_LABOR_COST: Final = "labor_cost"
ATTR_PARTS_COST: Final = "parts_cost"
ATTR_TOTAL_COST: Final = "total_cost"
ATTR_NOTES: Final = "notes"
ATTR_ITEMS: Final = "items"
ATTR_CATEGORY: Final = "category"
ATTR_NAME: Final = "name"
ATTR_STATUS: Final = "status"
ATTR_DATE_COMPLETED: Final = "date_completed"
ATTR_INTERVAL_MILES: Final = "interval_miles"
ATTR_INTERVAL_DAYS: Final = "interval_days"
ATTR_ENABLED: Final = "enabled"
ATTR_SOURCE: Final = "source"
ATTR_FILE_PATH: Final = "file_path"
ATTR_QUERY: Final = "query"
ATTR_FORMAT: Final = "format"
ATTR_YEAR: Final = "year"
ATTR_SORT: Final = "sort"
ATTR_LIMIT: Final = "limit"
ATTR_MODE: Final = "mode"
ATTR_ITEM_ID: Final = "item_id"
ATTR_TIRE_ID: Final = "tire_id"
ATTR_BRAKE_ID: Final = "brake_id"
ATTR_CATEGORY_ID: Final = "category_id"
ATTR_COST: Final = "cost"

EXPORT_FORMAT_JSON: Final = "json"
EXPORT_FORMAT_CSV: Final = "csv"
EXPORT_FORMATS: Final = [EXPORT_FORMAT_JSON, EXPORT_FORMAT_CSV]

IMPORT_MODE_MERGE: Final = "merge"
IMPORT_MODE_SKIP_DUPLICATES: Final = "skip_duplicates"
IMPORT_MODES: Final = [IMPORT_MODE_MERGE, IMPORT_MODE_SKIP_DUPLICATES]

SORT_NEWEST: Final = "newest"
SORT_OLDEST: Final = "oldest"
SORT_COST_DESC: Final = "highest_cost"
SORT_COST_ASC: Final = "lowest_cost"
SORT_MILEAGE_DESC: Final = "highest_mileage"
SORT_MILEAGE_ASC: Final = "lowest_mileage"
SORT_OPTIONS: Final = [
    SORT_NEWEST,
    SORT_OLDEST,
    SORT_COST_DESC,
    SORT_COST_ASC,
    SORT_MILEAGE_DESC,
    SORT_MILEAGE_ASC,
]

#: Fired when maintenance data changes so dashboards/automations can react.
EVENT_DATA_CHANGED: Final = f"{DOMAIN}_data_changed"
IMPORT_MODE_MERGE: Final = "merge"
IMPORT_MODE_SKIP_DUPLICATES: Final = "skip_duplicates"
IMPORT_MODES: Final = [IMPORT_MODE_MERGE, IMPORT_MODE_SKIP_DUPLICATES]
