"""Dataclass models for the Tesla Maintenance Tracker database.

These are plain dataclasses with no Home Assistant dependency, which keeps the
storage layer independently testable.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Any, Self, TypeVar

T = TypeVar("T", bound="BaseModel")


@dataclass(slots=True)
class BaseModel:
    """Common conversion helpers for all models."""

    def to_dict(self) -> dict[str, Any]:
        """Return the model as a plain dictionary."""
        return asdict(self)

    @classmethod
    def from_row(cls, row: Any) -> Self:
        """Build a model from a sqlite3.Row (or any mapping-like object)."""
        known = {f.name for f in fields(cls)}
        data = {key: row[key] for key in row.keys() if key in known}
        return cls(**data)


@dataclass(slots=True)
class Vehicle(BaseModel):
    """A tracked vehicle. One config entry maps to one vehicle."""

    id: int | None = None
    config_entry_id: str | None = None
    name: str = ""
    vin: str | None = None
    model: str | None = None
    year: int | None = None
    current_mileage: float = 0.0
    purchase_date: str | None = None
    notes: str = ""
    created_at: str | None = None
    updated_at: str | None = None

    def redacted(self) -> dict[str, Any]:
        """Return the vehicle without the VIN, for logging and diagnostics."""
        data = asdict(self)
        data["vin"] = "**REDACTED**" if self.vin else None
        return data


@dataclass(slots=True)
class ServiceRecord(BaseModel):
    """A single visit to a shop, or a single piece of work performed."""

    id: int | None = None
    vehicle_id: int = 0
    service_date: str = ""
    mileage: float | None = None
    title: str = ""
    description: str = ""
    service_provider: str = ""
    location: str = ""
    labor_cost: float = 0.0
    parts_cost: float = 0.0
    total_cost: float = 0.0
    notes: str = ""
    created_at: str | None = None
    updated_at: str | None = None
    items: list[MaintenanceItem] = field(default_factory=list)
    attachments: list[Attachment] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return the record with nested items and attachments expanded."""
        # ``slots=True`` rebuilds the class, so zero-argument super() is not
        # usable here - asdict() handles the nested dataclasses directly.
        data = asdict(self)
        data["items"] = [item.to_dict() for item in self.items]
        data["attachments"] = [att.to_dict() for att in self.attachments]
        return data


@dataclass(slots=True)
class MaintenanceItem(BaseModel):
    """A piece of work. May be a default item or a fully custom one."""

    id: int | None = None
    service_record_id: int | None = None
    vehicle_id: int = 0
    category: str = "Other"
    name: str = ""
    status: str = "COMPLETED"
    mileage: float | None = None
    date_completed: str | None = None
    cost: float = 0.0
    is_custom: bool = False
    notes: str = ""
    created_at: str | None = None
    updated_at: str | None = None


@dataclass(slots=True)
class MaintenanceSchedule(BaseModel):
    """A recurring maintenance interval for a vehicle."""

    id: int | None = None
    vehicle_id: int = 0
    item_name: str = ""
    category: str = "Other"
    interval_miles: int | None = None
    interval_days: int | None = None
    last_service_date: str | None = None
    last_service_mileage: float | None = None
    next_due_date: str | None = None
    next_due_mileage: float | None = None
    enabled: bool = True
    source: str = "User Defined"
    notes: str = ""
    created_at: str | None = None
    updated_at: str | None = None


@dataclass(slots=True)
class TireRecord(BaseModel):
    """A tire fitted at a wheel position."""

    id: int | None = None
    vehicle_id: int = 0
    position: str = ""
    brand: str = ""
    model: str = ""
    size: str = ""
    installation_date: str | None = None
    installation_mileage: float | None = None
    current_tread_depth: float | None = None
    original_tread_depth: float | None = None
    dot_date: str | None = None
    purchase_cost: float = 0.0
    replacement_cost: float = 0.0
    active: bool = True
    notes: str = ""
    created_at: str | None = None
    updated_at: str | None = None


@dataclass(slots=True)
class TireRotation(BaseModel):
    """A recorded tire rotation event."""

    id: int | None = None
    vehicle_id: int = 0
    rotation_date: str = ""
    mileage: float | None = None
    pattern: str = ""
    notes: str = ""
    created_at: str | None = None


@dataclass(slots=True)
class BrakeRecord(BaseModel):
    """A brake inspection result for one axle."""

    id: int | None = None
    vehicle_id: int = 0
    axle: str = "Front"
    condition: str = "Good"
    pad_thickness: float | None = None
    rotor_condition: str = ""
    inspection_date: str | None = None
    inspection_mileage: float | None = None
    notes: str = ""
    created_at: str | None = None
    updated_at: str | None = None


@dataclass(slots=True)
class Attachment(BaseModel):
    """A receipt, photo or document stored on disk."""

    id: int | None = None
    service_record_id: int | None = None
    vehicle_id: int = 0
    filename: str = ""
    mime_type: str = ""
    path: str = ""
    size_bytes: int = 0
    created_at: str | None = None


@dataclass(slots=True)
class Category(BaseModel):
    """A maintenance category. Defaults are seeded; users can add their own."""

    id: int | None = None
    vehicle_id: int | None = None
    name: str = ""
    is_default: bool = False
    created_at: str | None = None
