"""Storage layer for the Tesla Maintenance Tracker.

Nothing in this package imports Home Assistant, so it can be exercised by plain
unit tests and reused outside of Home Assistant if needed.
"""

from .models import (
    Attachment,
    BrakeRecord,
    Category,
    MaintenanceItem,
    MaintenanceSchedule,
    ServiceRecord,
    TireRecord,
    TireRotation,
    Vehicle,
)
from .repository import MaintenanceRepository, RepositoryError
from .schema import SCHEMA_VERSION

__all__ = [
    "SCHEMA_VERSION",
    "Attachment",
    "BrakeRecord",
    "Category",
    "MaintenanceItem",
    "MaintenanceRepository",
    "MaintenanceSchedule",
    "RepositoryError",
    "ServiceRecord",
    "TireRecord",
    "TireRotation",
    "Vehicle",
]
