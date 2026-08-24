"""Tests for the SQLite repository."""

from __future__ import annotations

import pytest
from custom_components.tesla_maintenance.database.models import (
    BrakeRecord,
    MaintenanceItem,
    MaintenanceSchedule,
    ServiceRecord,
    TireRecord,
)
from custom_components.tesla_maintenance.database.repository import (
    MaintenanceRepository,
    RepositoryError,
)


def test_create_vehicle_seeds_default_categories(repository, vehicle):
    assert vehicle.id is not None
    names = {category.name for category in repository.list_categories(vehicle.id)}
    assert "Brakes" in names
    assert "Other" in names
    assert len(names) == 16


def test_get_or_create_is_idempotent_and_preserves_data(repository, vehicle):
    repository.add_service_record(
        ServiceRecord(vehicle_id=vehicle.id, service_date="2026-01-05", total_cost=100)
    )
    again = repository.get_or_create_vehicle("entry-1", "Renamed Tesla")
    assert again.id == vehicle.id
    assert again.name == "Renamed Tesla"
    # Re-running setup must never drop history.
    assert repository.service_count(vehicle.id) == 1


def test_update_and_delete_vehicle(repository, vehicle):
    repository.update_vehicle(vehicle.id, {"notes": "Bought used"})
    assert repository.get_vehicle(vehicle.id).notes == "Bought used"
    repository.delete_vehicle(vehicle.id)
    assert repository.get_vehicle(vehicle.id) is None


def test_multiple_vehicles_are_isolated(repository):
    first = repository.get_or_create_vehicle("entry-a", "Model 3")
    second = repository.get_or_create_vehicle("entry-b", "Model Y")
    repository.add_service_record(
        ServiceRecord(vehicle_id=first.id, service_date="2026-02-01", total_cost=200)
    )
    assert repository.service_count(first.id) == 1
    assert repository.service_count(second.id) == 0
    assert repository.total_cost(second.id) == 0


def test_service_record_with_items_and_notes(repository, vehicle):
    record_id = repository.add_service_record(
        ServiceRecord(
            vehicle_id=vehicle.id,
            service_date="2026-08-20",
            mileage=42580,
            title="Annual service",
            service_provider="Tesla Service Center",
            labor_cost=40,
            parts_cost=25,
            notes="Technician recommended checking alignment.",
        ),
        [
            MaintenanceItem(
                vehicle_id=vehicle.id, name="Tire Rotation", category="Tires", cost=65
            )
        ],
    )
    record = repository.get_service_record(record_id)
    assert record.total_cost == 65
    assert record.notes.startswith("Technician")
    assert record.items[0].name == "Tire Rotation"
    # Recording a service advances stored mileage.
    assert repository.get_vehicle(vehicle.id).current_mileage == 42580


def test_notes_are_searchable(repository, vehicle):
    repository.add_service_record(
        ServiceRecord(
            vehicle_id=vehicle.id,
            service_date="2026-03-01",
            notes="Technician recommended checking alignment.",
        )
    )
    repository.add_service_record(
        ServiceRecord(vehicle_id=vehicle.id, service_date="2026-04-01", notes="Nothing")
    )
    results = repository.list_service_records(vehicle.id, query="alignment")
    assert len(results) == 1
    assert "alignment" in results[0].notes


def test_search_matches_item_notes(repository, vehicle):
    repository.add_service_record(
        ServiceRecord(vehicle_id=vehicle.id, service_date="2026-03-01"),
        [
            MaintenanceItem(
                vehicle_id=vehicle.id,
                name="Ceramic Coating",
                category="Exterior",
                notes="Two year warranty",
            )
        ],
    )
    assert repository.list_service_records(vehicle.id, query="warranty")
    assert repository.list_service_records(vehicle.id, query="ceramic")


def test_filters_and_sorting(repository, vehicle):
    repository.add_service_record(
        ServiceRecord(
            vehicle_id=vehicle.id,
            service_date="2025-05-01",
            mileage=10000,
            total_cost=300,
            service_provider="Independent EV",
        )
    )
    repository.add_service_record(
        ServiceRecord(
            vehicle_id=vehicle.id,
            service_date="2026-05-01",
            mileage=20000,
            total_cost=100,
            service_provider="Tesla Service Center",
        )
    )
    assert len(repository.list_service_records(vehicle.id, year=2025)) == 1
    assert len(repository.list_service_records(vehicle.id, provider="Tesla")) == 1
    assert len(repository.list_service_records(vehicle.id, min_cost=200)) == 1
    newest = repository.list_service_records(vehicle.id, sort="newest")[0]
    assert newest.service_date == "2026-05-01"
    cheapest = repository.list_service_records(vehicle.id, sort="lowest_cost")[0]
    assert cheapest.total_cost == 100


def test_custom_maintenance_item_lifecycle(repository, vehicle):
    item_id = repository.add_maintenance_item(
        MaintenanceItem(
            vehicle_id=vehicle.id,
            name="Frunk strut replacement",
            category="Exterior",
            is_custom=True,
            cost=90,
            notes="Both struts",
        )
    )
    repository.update_maintenance_item(item_id, {"cost": 120, "notes": "Both struts, OEM"})
    item = repository.get_maintenance_item(item_id)
    assert item.cost == 120
    assert item.is_custom
    assert "OEM" in item.notes
    repository.delete_maintenance_item(item_id)
    assert repository.get_maintenance_item(item_id) is None


def test_custom_categories_persist_and_defaults_protected(repository, vehicle):
    category = repository.add_category(vehicle.id, "Ceramic Coating")
    assert category.is_default == 0
    names = {item.name for item in repository.list_categories(vehicle.id)}
    assert "Ceramic Coating" in names

    default = next(
        item for item in repository.list_categories(vehicle.id) if item.name == "Brakes"
    )
    repository.delete_category(default.id)
    assert "Brakes" in {
        item.name for item in repository.list_categories(vehicle.id)
    }
    repository.delete_category(category.id)
    assert "Ceramic Coating" not in {
        item.name for item in repository.list_categories(vehicle.id)
    }


def test_add_category_rejects_empty(repository, vehicle):
    with pytest.raises(RepositoryError):
        repository.add_category(vehicle.id, "   ")


def test_schedule_requires_an_interval(repository, vehicle):
    with pytest.raises(RepositoryError):
        repository.add_schedule(
            MaintenanceSchedule(vehicle_id=vehicle.id, item_name="Nothing")
        )


def test_schedule_next_due_calculation(repository, vehicle):
    repository.force_set_mileage(vehicle.id, 40000)
    schedule_id = repository.add_schedule(
        MaintenanceSchedule(
            vehicle_id=vehicle.id,
            item_name="Tire Rotation",
            category="Tires",
            interval_miles=6250,
        )
    )
    schedule = repository.get_schedule(schedule_id)
    assert schedule.last_service_mileage == 40000
    assert schedule.next_due_mileage == 46250


def test_service_record_advances_matching_schedule(repository, vehicle):
    repository.force_set_mileage(vehicle.id, 40000)
    schedule_id = repository.add_schedule(
        MaintenanceSchedule(
            vehicle_id=vehicle.id, item_name="Tire Rotation", interval_miles=6250
        )
    )
    repository.add_service_record(
        ServiceRecord(vehicle_id=vehicle.id, service_date="2026-08-20", mileage=46000),
        [MaintenanceItem(vehicle_id=vehicle.id, name="tire rotation")],
    )
    schedule = repository.get_schedule(schedule_id)
    assert schedule.last_service_mileage == 46000
    assert schedule.next_due_mileage == 52250


def test_reset_schedule(repository, vehicle):
    repository.force_set_mileage(vehicle.id, 1000)
    schedule_id = repository.add_schedule(
        MaintenanceSchedule(
            vehicle_id=vehicle.id, item_name="Cabin Air Filter", interval_days=730
        )
    )
    assert repository.reset_schedule(schedule_id, service_date="2026-01-01")
    schedule = repository.get_schedule(schedule_id)
    assert schedule.next_due_date == "2028-01-01"
    assert repository.reset_schedule(999999) is False


def test_mileage_never_moves_backwards(repository, vehicle):
    repository.set_current_mileage(vehicle.id, 1000)
    repository.set_current_mileage(vehicle.id, 500)
    assert repository.get_vehicle(vehicle.id).current_mileage == 1000
    # Manual corrections may still override.
    repository.force_set_mileage(vehicle.id, 500)
    assert repository.get_vehicle(vehicle.id).current_mileage == 500


def test_tires_and_rotations(repository, vehicle):
    tire_id = repository.add_tire_record(
        TireRecord(
            vehicle_id=vehicle.id,
            position="Front Left",
            brand="Michelin",
            current_tread_depth=8,
            original_tread_depth=10,
            purchase_cost=280,
            notes="Fitted with new TPMS sensor",
        )
    )
    tires = repository.list_tire_records(vehicle.id)
    assert len(tires) == 1
    assert tires[0].notes.startswith("Fitted")
    repository.update_tire_record(tire_id, {"current_tread_depth": 6})
    assert repository.list_tire_records(vehicle.id)[0].current_tread_depth == 6
    repository.delete_tire_record(tire_id)
    assert repository.list_tire_records(vehicle.id) == []


def test_brakes_latest_per_axle(repository, vehicle):
    repository.add_brake_record(
        BrakeRecord(
            vehicle_id=vehicle.id,
            axle="Front",
            condition="Good",
            inspection_date="2025-01-01",
        )
    )
    repository.add_brake_record(
        BrakeRecord(
            vehicle_id=vehicle.id,
            axle="Front",
            condition="Fair",
            inspection_date="2026-01-01",
            notes="Slight lip on rotors",
        )
    )
    latest = repository.latest_brake_records(vehicle.id)
    assert latest["Front"].condition == "Fair"
    assert latest["Front"].notes == "Slight lip on rotors"


def test_cascade_delete_removes_children(repository, vehicle):
    record_id = repository.add_service_record(
        ServiceRecord(vehicle_id=vehicle.id, service_date="2026-01-01"),
        [MaintenanceItem(vehicle_id=vehicle.id, name="Brake Fluid")],
    )
    repository.delete_service_record(record_id)
    assert repository.list_maintenance_items(vehicle.id, service_record_id=record_id) == []


def test_backup_creates_readable_copy(repository, vehicle, tmp_path):
    repository.add_service_record(
        ServiceRecord(vehicle_id=vehicle.id, service_date="2026-01-01", total_cost=50)
    )
    destination = tmp_path / "backups" / "copy.db"
    repository.backup(destination)

    restored = MaintenanceRepository(destination)
    restored.connect()
    try:
        assert restored.total_cost(vehicle.id) == 50
    finally:
        restored.close()


def test_database_survives_reconnect(tmp_path):
    path = tmp_path / "maintenance.db"
    first = MaintenanceRepository(path)
    first.connect()
    vehicle = first.get_or_create_vehicle("entry-1", "Model Y")
    first.add_service_record(
        ServiceRecord(
            vehicle_id=vehicle.id, service_date="2026-01-01", notes="Persisted note"
        )
    )
    first.close()

    second = MaintenanceRepository(path)
    second.connect()
    try:
        records = second.list_service_records(vehicle.id)
        assert records[0].notes == "Persisted note"
    finally:
        second.close()
