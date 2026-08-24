"""Export and import of maintenance data.

Exports are written to ``<config>/tesla_maintenance/exports/``. JSON keeps the
complete structure (including every note) and is what the importer consumes.
CSV is a flattened, spreadsheet friendly view of the service history.
"""

from __future__ import annotations

import csv
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .database.repository import MaintenanceRepository, RepositoryError

_LOGGER = logging.getLogger(__name__)

EXPORT_SCHEMA_VERSION = 1

CSV_COLUMNS = [
    "date",
    "mileage",
    "service",
    "category",
    "provider",
    "location",
    "labor_cost",
    "parts_cost",
    "total_cost",
    "custom",
    "notes",
    "item_notes",
]


def _timestamp() -> str:
    """Return a filename-safe UTC timestamp."""
    return datetime.now(UTC).strftime("%Y%m%d_%H%M%S")


def build_export_payload(
    repository: MaintenanceRepository, vehicle_id: int | None = None
) -> dict[str, Any]:
    """Build the full export structure for one vehicle or for all of them."""
    vehicle_ids = (
        [vehicle_id]
        if vehicle_id is not None
        else [vehicle.id for vehicle in repository.list_vehicles() if vehicle.id]
    )
    return {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "exported_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "vehicles": [
            repository.export_vehicle(int(identifier)) for identifier in vehicle_ids
        ],
    }


def export_json(
    repository: MaintenanceRepository,
    exports_dir: Path,
    vehicle_id: int | None = None,
) -> str:
    """Write a complete JSON export and return the file path."""
    payload = build_export_payload(repository, vehicle_id)
    exports_dir.mkdir(parents=True, exist_ok=True)
    target = exports_dir / f"tesla_maintenance_{_timestamp()}.json"
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    _LOGGER.info("Wrote JSON export to %s", target)
    return str(target)


def export_csv(
    repository: MaintenanceRepository,
    exports_dir: Path,
    vehicle_id: int | None = None,
) -> str:
    """Write a flattened CSV of the service history and return the file path.

    One row per maintenance item, plus a row for any service record that has no
    items attached, so nothing is lost. Custom items are included and flagged.
    """
    payload = build_export_payload(repository, vehicle_id)
    exports_dir.mkdir(parents=True, exist_ok=True)
    target = exports_dir / f"tesla_maintenance_{_timestamp()}.csv"

    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["vehicle", *CSV_COLUMNS])
        writer.writeheader()
        for vehicle_payload in payload["vehicles"]:
            vehicle_name = vehicle_payload["vehicle"]["name"]
            for record in vehicle_payload["service_records"]:
                base = {
                    "vehicle": vehicle_name,
                    "date": record["service_date"],
                    "mileage": record["mileage"],
                    "provider": record["service_provider"],
                    "location": record["location"],
                    "labor_cost": record["labor_cost"],
                    "parts_cost": record["parts_cost"],
                    "total_cost": record["total_cost"],
                    "notes": record["notes"],
                }
                items = record.get("items") or []
                if not items:
                    writer.writerow(
                        {
                            **base,
                            "service": record["title"],
                            "category": "",
                            "custom": "",
                            "item_notes": "",
                        }
                    )
                    continue
                for item in items:
                    writer.writerow(
                        {
                            **base,
                            "service": item["name"],
                            "category": item["category"],
                            "custom": "yes" if item["is_custom"] else "no",
                            "item_notes": item["notes"],
                        }
                    )
    _LOGGER.info("Wrote CSV export to %s", target)
    return str(target)


def validate_import_payload(payload: Any) -> list[dict[str, Any]]:
    """Validate an import payload and return its vehicle blocks.

    Raises :class:`ValueError` with a readable message when the payload is not a
    Tesla Maintenance Tracker export.
    """
    if not isinstance(payload, dict):
        raise ValueError("Import file must contain a JSON object")
    if "vehicles" not in payload:
        raise ValueError("Import file has no 'vehicles' section")
    vehicles = payload["vehicles"]
    if not isinstance(vehicles, list) or not vehicles:
        raise ValueError("Import file contains no vehicles")

    version = payload.get("schema_version", EXPORT_SCHEMA_VERSION)
    if not isinstance(version, int) or version > EXPORT_SCHEMA_VERSION:
        raise ValueError(
            f"Import file schema version {version} is newer than this integration "
            f"supports ({EXPORT_SCHEMA_VERSION})"
        )

    for block in vehicles:
        if not isinstance(block, dict) or "vehicle" not in block:
            raise ValueError("Each vehicle block must contain a 'vehicle' object")
        for key in ("service_records", "schedules", "tires", "brakes"):
            value = block.get(key, [])
            if value and not isinstance(value, list):
                raise ValueError(f"'{key}' must be a list")
    return vehicles


def import_json(
    repository: MaintenanceRepository,
    file_path: str | Path,
    vehicle_id: int,
    *,
    skip_duplicates: bool = True,
) -> dict[str, int]:
    """Restore an export file into an existing vehicle.

    The file is fully validated before a single row is written, and existing
    records are never overwritten.
    """
    path = Path(file_path)
    if not path.is_file():
        raise ValueError(f"Import file not found: {path}")
    if path.stat().st_size > 50 * 1024 * 1024:
        raise ValueError("Import file is too large (limit 50 MB)")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as err:
        raise ValueError(f"Import file is not valid JSON: {err}") from err

    vehicles = validate_import_payload(payload)
    totals: dict[str, int] = {}
    for block in vehicles:
        try:
            counts = repository.import_vehicle(
                block, vehicle_id, skip_duplicates=skip_duplicates
            )
        except RepositoryError as err:
            raise ValueError(f"Import failed: {err}") from err
        for key, value in counts.items():
            totals[key] = totals.get(key, 0) + value
    _LOGGER.info("Import complete: %s", totals)
    return totals
