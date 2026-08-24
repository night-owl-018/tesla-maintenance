"""Tests for JSON/CSV export, import/restore, and cost analytics."""

from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path

import pytest
from custom_components.tesla_maintenance.database.models import (
    BrakeRecord,
    MaintenanceItem,
    MaintenanceSchedule,
    ServiceRecord,
    TireRecord,
)
from custom_components.tesla_maintenance.exporter import (
    build_export_payload,
    export_csv,
    export_json,
    import_json,
    validate_import_payload,
)

THIS_YEAR = date.today().year


@pytest.fixture
def populated(repository, vehicle):
    """Return a vehicle with history, a custom item, schedule, tires and brakes."""
    repository.add_service_record(
        ServiceRecord(
            vehicle_id=vehicle.id,
            service_date=f"{THIS_YEAR}-03-15",
            mileage=40000,
            title="Tire rotation",
            service_provider="Tesla Service Center",
            labor_cost=65,
            parts_cost=0,
            notes="Front right tire showing slightly more wear.",
        ),
        [
            MaintenanceItem(
                vehicle_id=vehicle.id, name="Tire Rotation", category="Tires", cost=65
            )
        ],
    )
    repository.add_service_record(
        ServiceRecord(
            vehicle_id=vehicle.id,
            service_date=f"{THIS_YEAR - 1}-05-01",
            mileage=20000,
            title="Ceramic coating",
            service_provider="Detail Shop",
            total_cost=900,
            notes="Two year warranty on the coating.",
        ),
        [
            MaintenanceItem(
                vehicle_id=vehicle.id,
                name="Ceramic Coating",
                category="Exterior",
                cost=900,
                is_custom=True,
                notes="Ceramic Pro 9H",
            )
        ],
    )
    repository.add_schedule(
        MaintenanceSchedule(
            vehicle_id=vehicle.id,
            item_name="Tire Rotation",
            category="Tires",
            interval_miles=6250,
            source="User Defined",
        )
    )
    repository.add_tire_record(
        TireRecord(vehicle_id=vehicle.id, position="Front Left", purchase_cost=280)
    )
    repository.add_brake_record(
        BrakeRecord(vehicle_id=vehicle.id, axle="Front", condition="Good")
    )
    repository.add_category(vehicle.id, "Ceramic Coating")
    return vehicle


def test_analytics_totals(repository, populated):
    analytics = repository.analytics(populated.id)
    assert analytics["total_cost"] == 965
    assert analytics["cost_this_year"] == 65
    assert analytics["cost_last_year"] == 900
    assert analytics["service_count"] == 2
    assert analytics["average_service_cost"] == 482.5
    assert analytics["cost_by_category"]["Exterior"] == 900
    assert analytics["cost_by_provider"]["Detail Shop"] == 900
    assert analytics["tire_cost"] == 280


def test_cost_per_mile_uses_real_mileage(repository, populated):
    repository.force_set_mileage(populated.id, 40000)
    analytics = repository.analytics(populated.id)
    assert analytics["cost_per_mile"] == round(965 / 40000, 4)


def test_analytics_returns_none_when_there_is_no_data(repository, vehicle):
    analytics = repository.analytics(vehicle.id)
    assert analytics["total_cost"] == 0
    assert analytics["average_service_cost"] is None
    assert analytics["average_annual_cost"] is None
    assert analytics["cost_per_mile"] is None


def test_cost_by_year_and_month(repository, populated):
    by_year = repository.cost_by_year(populated.id)
    assert by_year[str(THIS_YEAR)] == 65
    assert by_year[str(THIS_YEAR - 1)] == 900
    by_month = repository.cost_by_month(populated.id, months=24)
    assert f"{THIS_YEAR}-03" in by_month


def test_export_payload_preserves_notes_and_custom_items(repository, populated):
    payload = build_export_payload(repository, populated.id)
    block = payload["vehicles"][0]
    assert block["vehicle"]["name"] == "Test Tesla"

    notes = [record["notes"] for record in block["service_records"]]
    assert any("slightly more wear" in note for note in notes)

    custom = [
        item
        for record in block["service_records"]
        for item in record["items"]
        if item["is_custom"]
    ]
    assert custom[0]["name"] == "Ceramic Coating"
    assert custom[0]["notes"] == "Ceramic Pro 9H"
    assert block["schedules"][0]["source"] == "User Defined"


def test_export_json_writes_a_readable_file(repository, populated, tmp_path):
    path = export_json(repository, tmp_path / "exports", populated.id)
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert len(data["vehicles"][0]["service_records"]) == 2


def test_export_csv_includes_required_columns(repository, populated, tmp_path):
    path = export_csv(repository, tmp_path / "exports", populated.id)
    with open(path, encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    for column in (
        "date",
        "mileage",
        "service",
        "category",
        "provider",
        "labor_cost",
        "parts_cost",
        "total_cost",
        "notes",
    ):
        assert column in rows[0]

    services = {row["service"] for row in rows}
    assert "Ceramic Coating" in services  # custom items are included
    assert any("slightly more wear" in row["notes"] for row in rows)
    assert any(row["custom"] == "yes" for row in rows)


def test_validate_import_payload_rejects_bad_input():
    with pytest.raises(ValueError):
        validate_import_payload("not a dict")
    with pytest.raises(ValueError):
        validate_import_payload({})
    with pytest.raises(ValueError):
        validate_import_payload({"vehicles": []})
    with pytest.raises(ValueError):
        validate_import_payload({"vehicles": [{"no_vehicle_key": 1}]})
    with pytest.raises(ValueError):
        validate_import_payload({"schema_version": 99, "vehicles": [{"vehicle": {}}]})


def test_import_restores_into_an_empty_vehicle(repository, populated, tmp_path):
    path = export_json(repository, tmp_path / "exports", populated.id)
    target = repository.get_or_create_vehicle("entry-restore", "Restored Tesla")

    counts = import_json(repository, path, target.id)
    assert counts["service_records"] == 2
    assert counts["schedules"] == 1
    assert counts["tires"] == 1
    assert counts["brakes"] == 1

    restored = repository.list_service_records(target.id)
    assert any("slightly more wear" in record.notes for record in restored)
    assert repository.total_cost(target.id) == 965
    names = {item.name for item in repository.list_maintenance_items(target.id)}
    assert "Ceramic Coating" in names


def test_import_is_idempotent_and_skips_duplicates(repository, populated, tmp_path):
    path = export_json(repository, tmp_path / "exports", populated.id)
    target = repository.get_or_create_vehicle("entry-restore", "Restored Tesla")

    import_json(repository, path, target.id)
    second = import_json(repository, path, target.id)

    assert second["service_records"] == 0
    assert second["skipped"] >= 2
    assert repository.service_count(target.id) == 2


def test_import_never_overwrites_existing_records(repository, populated, tmp_path):
    path = export_json(repository, tmp_path / "exports", populated.id)
    import_json(repository, path, populated.id)
    # Nothing was duplicated or replaced.
    assert repository.service_count(populated.id) == 2
    assert repository.total_cost(populated.id) == 965


def test_import_rejects_missing_and_malformed_files(repository, vehicle, tmp_path):
    with pytest.raises(ValueError):
        import_json(repository, tmp_path / "missing.json", vehicle.id)

    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError):
        import_json(repository, broken, vehicle.id)


def test_import_skips_records_without_a_date(repository, vehicle, tmp_path):
    payload = {
        "schema_version": 1,
        "vehicles": [
            {
                "vehicle": {"name": "X"},
                "service_records": [{"service_date": "", "total_cost": 10}],
            }
        ],
    }
    path = tmp_path / "partial.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    counts = import_json(repository, path, vehicle.id)
    assert counts["service_records"] == 0
    assert counts["skipped"] == 1
