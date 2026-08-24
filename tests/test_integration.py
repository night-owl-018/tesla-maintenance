"""Tests for entities, telemetry handling, services and unloading."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from custom_components.tesla_maintenance.const import (
    CONF_MANUAL_MILEAGE,
    CONF_MILEAGE_SOURCE,
    CONF_ODOMETER_ENTITY,
    CONF_VEHICLE_NAME,
    DOMAIN,
    MILEAGE_SOURCE_MANUAL,
    SOURCE_USER,
    STATUS_OVERDUE,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import MOCK_CONFIG, ODOMETER_ENTITY


def _state(hass, suffix: str):
    """Return the state object for one of the vehicle's entities."""
    return hass.states.get(f"sensor.test_tesla_{suffix}")


# ---------------------------------------------------------------- setup


async def test_entry_loads_and_creates_entities(hass, integration):
    assert integration.state is ConfigEntryState.LOADED
    assert _state(hass, "current_mileage").state == "42580.0"
    assert _state(hass, "maintenance_items_due").state == "0"
    assert _state(hass, "total_service_records").state == "0"
    assert hass.states.get("binary_sensor.test_tesla_maintenance_due").state == "off"
    assert hass.states.get("calendar.test_tesla_upcoming_maintenance") is not None
    assert hass.states.get("number.test_tesla_manual_mileage") is not None


async def test_device_registry_entry_created_without_vin(hass, integration):
    from homeassistant.helpers import device_registry as dr

    registry = dr.async_get(hass)
    device = registry.async_get_device(identifiers={(DOMAIN, integration.entry_id)})
    assert device is not None
    assert device.manufacturer == "Tesla"
    assert "VIN" not in str(device.model or "")


async def test_all_services_are_registered(hass, integration):
    for service in (
        "add_service_record",
        "update_service_record",
        "delete_service_record",
        "add_maintenance_item",
        "complete_maintenance",
        "reset_maintenance_schedule",
        "add_attachment",
        "add_category",
        "add_tire_record",
        "add_brake_record",
        "search_service_records",
        "export_data",
        "import_data",
        "backup_database",
    ):
        assert hass.services.has_service(DOMAIN, service), service


async def test_storage_directories_are_created(hass, integration, tmp_path):
    root = tmp_path / "tesla_maintenance"
    assert (root / "maintenance.db").is_file()
    for sub in ("attachments", "exports", "backups"):
        assert (root / sub).is_dir()
    # Nothing is written into .storage.
    assert not (tmp_path / ".storage" / "tesla_maintenance").exists()


# ---------------------------------------------------------------- telemetry


async def test_unavailable_odometer_retains_last_known_mileage(hass, integration):
    hass.states.async_set(ODOMETER_ENTITY, STATE_UNAVAILABLE)
    await integration.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()

    assert _state(hass, "current_mileage").state == "42580.0"
    assert _state(hass, "tesla_telemetry").state == "Unavailable"
    # History remains fully available during an outage.
    assert (
        _state(hass, "tesla_telemetry").attributes["maintenance_database"] == "Available"
    )


async def test_non_numeric_odometer_is_ignored(hass, integration):
    hass.states.async_set(ODOMETER_ENTITY, "not a number")
    await integration.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert _state(hass, "current_mileage").state == "42580.0"


async def test_odometer_updates_are_tracked(hass, integration):
    hass.states.async_set(ODOMETER_ENTITY, "43000")
    await hass.async_block_till_done()
    await integration.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert _state(hass, "current_mileage").state == "43000.0"


async def test_optional_entities_report_not_configured(hass, integration):
    optional = _state(hass, "tesla_telemetry").attributes["optional_entities"]
    assert optional["battery_level_entity"]["status"] == "Not configured"
    assert optional["tpms_front_left_entity"]["status"] == "Not configured"


async def test_manual_mileage_mode_works_without_any_tesla_entity(hass, tmp_path):
    config = {
        **{k: v for k, v in MOCK_CONFIG.items() if k != CONF_ODOMETER_ENTITY},
        CONF_MILEAGE_SOURCE: MILEAGE_SOURCE_MANUAL,
        CONF_MANUAL_MILEAGE: 12345,
        CONF_VEHICLE_NAME: "Manual Tesla",
    }
    entry = MockConfigEntry(domain=DOMAIN, data=config, title="Manual Tesla")
    entry.add_to_hass(hass)

    with patch.object(hass.config, "config_dir", str(tmp_path)):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get("sensor.manual_tesla_current_mileage").state == "12345.0"


async def test_number_entity_sets_mileage(hass, integration):
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.test_tesla_manual_mileage", "value": 50000},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert _state(hass, "current_mileage").state == "50000.0"


# ---------------------------------------------------------------- services


async def test_add_service_record_service_updates_sensors(hass, integration):
    response = await hass.services.async_call(
        DOMAIN,
        "add_service_record",
        {
            "service_date": "2026-08-20",
            "mileage": 42580,
            "title": "Tire rotation",
            "service_provider": "Tesla Service Center",
            "labor_cost": 65,
            "notes": "Front right tire showing slightly more wear.",
            "items": [{"name": "Tire Rotation", "category": "Tires"}],
        },
        blocking=True,
        return_response=True,
    )
    await hass.async_block_till_done()

    assert response["service_record_id"] >= 1
    assert _state(hass, "total_service_records").state == "1"
    assert _state(hass, "total_maintenance_cost").state == "65.0"
    assert _state(hass, "last_service_mileage").state == "42580.0"


async def test_custom_maintenance_creates_category_and_schedule(hass, integration):
    """A user-defined item with a brand new category, made recurring."""
    response = await hass.services.async_call(
        DOMAIN,
        "add_maintenance_item",
        {
            "name": "Ceramic coating refresh",
            "category": "Ceramic Coating",
            "cost": 900,
            "notes": "Ceramic Pro 9H",
            "create_schedule": True,
            "interval_days": 730,
        },
        blocking=True,
        return_response=True,
    )
    await hass.async_block_till_done()

    assert response["schedule_id"] is not None
    runtime = integration.runtime_data

    categories = await hass.async_add_executor_job(
        runtime.repository.list_categories, runtime.vehicle_id
    )
    assert "Ceramic Coating" in {category.name for category in categories}

    schedules = await hass.async_add_executor_job(
        runtime.repository.list_schedules, runtime.vehicle_id
    )
    schedule = next(s for s in schedules if s.item_name == "Ceramic coating refresh")
    # User-defined schedules are never labelled as a Tesla recommendation.
    assert schedule.source == SOURCE_USER
    assert schedule.interval_days == 730


async def test_recurring_custom_maintenance_requires_an_interval(hass, integration):
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "add_maintenance_item",
            {"name": "Nothing", "create_schedule": True},
            blocking=True,
        )


async def test_search_finds_note_contents(hass, integration):
    await hass.services.async_call(
        DOMAIN,
        "add_service_record",
        {
            "service_date": "2026-05-01",
            "notes": "Technician recommended checking alignment.",
        },
        blocking=True,
    )
    await hass.async_block_till_done()

    response = await hass.services.async_call(
        DOMAIN,
        "search_service_records",
        {"query": "alignment"},
        blocking=True,
        return_response=True,
    )
    assert response["count"] == 1
    assert "alignment" in response["records"][0]["notes"]


async def test_complete_maintenance_rolls_schedule_forward(hass, integration):
    runtime = integration.runtime_data
    response = await hass.services.async_call(
        DOMAIN,
        "add_schedule",
        {"name": "Tire Rotation", "category": "Tires", "interval_miles": 6250},
        blocking=True,
        return_response=True,
    )
    schedule_id = response["schedule_id"]

    await hass.services.async_call(
        DOMAIN,
        "complete_maintenance",
        {"schedule_id": schedule_id, "mileage": 45000, "cost": 65},
        blocking=True,
    )
    await integration.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()

    schedule = await hass.async_add_executor_job(
        runtime.repository.get_schedule, schedule_id
    )
    assert schedule.last_service_mileage == 45000
    assert schedule.next_due_mileage == 51250
    assert _state(hass, "total_service_records").state == "1"


async def test_overdue_schedule_surfaces_on_sensors(hass, integration):
    await hass.services.async_call(
        DOMAIN,
        "add_schedule",
        {
            "name": "Brake Inspection",
            "category": "Brakes",
            "interval_miles": 1000,
            "last_service_mileage": 40000,
        },
        blocking=True,
    )
    await integration.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()

    assert _state(hass, "maintenance_items_overdue").state == "1"
    assert hass.states.get("binary_sensor.test_tesla_maintenance_overdue").state == "on"
    assert hass.states.get("binary_sensor.test_tesla_brake_service_due").state == "on"
    assert _state(hass, "maintenance_health").state == STATUS_OVERDUE


async def test_tire_and_brake_services(hass, integration):
    await hass.services.async_call(
        DOMAIN,
        "add_tire_record",
        {
            "position": "Front Left",
            "brand": "Michelin",
            "current_tread_depth": 3,
            "notes": "Wearing on the inner edge",
        },
        blocking=True,
    )
    await hass.services.async_call(
        DOMAIN,
        "add_brake_record",
        {"axle": "Front", "condition": "Fair", "pad_thickness": 5},
        blocking=True,
    )
    await integration.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()

    assert _state(hass, "tire_condition").state == "Needs Service"
    assert _state(hass, "brake_condition").state == "Fair"


async def test_conditions_are_unknown_without_records(hass, integration):
    assert _state(hass, "tire_condition").state == "unknown"
    assert _state(hass, "brake_condition").state == "unknown"
    assert _state(hass, "battery_condition").state == "unknown"


async def test_add_attachment_service(hass, integration, tmp_path):
    receipt = tmp_path / "receipt.pdf"
    receipt.write_bytes(b"%PDF-1.4 receipt")

    record = await hass.services.async_call(
        DOMAIN,
        "add_service_record",
        {"service_date": "2026-01-01", "title": "Tires"},
        blocking=True,
        return_response=True,
    )
    response = await hass.services.async_call(
        DOMAIN,
        "add_attachment",
        {"file_path": str(receipt), "service_record_id": record["service_record_id"]},
        blocking=True,
        return_response=True,
    )
    stored = response["path"]
    assert "attachments/service_000001" in stored
    assert (tmp_path / "tesla_maintenance" / "attachments").exists()


async def test_add_attachment_rejects_unsupported_type(hass, integration, tmp_path):
    bad = tmp_path / "payload.exe"
    bad.write_bytes(b"MZ")
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "add_attachment", {"file_path": str(bad)}, blocking=True
        )


async def test_export_and_import_round_trip(hass, integration):
    await hass.services.async_call(
        DOMAIN,
        "add_service_record",
        {"service_date": "2026-02-02", "total_cost": 100, "notes": "Exported note"},
        blocking=True,
    )
    export = await hass.services.async_call(
        DOMAIN, "export_data", {"format": "json"}, blocking=True, return_response=True
    )
    assert export["path"].endswith(".json")

    result = await hass.services.async_call(
        DOMAIN,
        "import_data",
        {"file_path": export["path"]},
        blocking=True,
        return_response=True,
    )
    # Importing the same data back is a no-op rather than a duplicate.
    assert result["imported"]["service_records"] == 0
    assert _state(hass, "total_service_records").state == "1"


async def test_backup_database_service(hass, integration, tmp_path):
    response = await hass.services.async_call(
        DOMAIN, "backup_database", {}, blocking=True, return_response=True
    )
    assert response["path"].endswith(".db")
    assert (tmp_path / "tesla_maintenance" / "backups").is_dir()


async def test_service_rejects_unknown_target(hass, integration):
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "set_mileage", {"vehicle_id": 999, "mileage": 1}, blocking=True
        )


# ---------------------------------------------------------------- unload


async def test_unload_entry_removes_services(hass, integration):
    assert await hass.config_entries.async_unload(integration.entry_id)
    await hass.async_block_till_done()
    assert integration.state is ConfigEntryState.NOT_LOADED
    assert not hass.services.has_service(DOMAIN, "add_service_record")


async def test_reload_preserves_maintenance_data(hass, integration):
    await hass.services.async_call(
        DOMAIN,
        "add_service_record",
        {"service_date": "2026-03-03", "total_cost": 75, "notes": "Survives a reload"},
        blocking=True,
    )
    await hass.async_block_till_done()

    await hass.config_entries.async_reload(integration.entry_id)
    await hass.async_block_till_done()

    assert integration.state is ConfigEntryState.LOADED
    assert _state(hass, "total_service_records").state == "1"
    assert _state(hass, "total_maintenance_cost").state == "75.0"


async def test_diagnostics_redact_the_vin(hass, integration):
    from custom_components.tesla_maintenance.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    hass.config_entries.async_update_entry(
        integration, data={**integration.data, "vin": "5YJ3E1EA7KF000000"}
    )
    await hass.async_block_till_done()

    diagnostics = await async_get_config_entry_diagnostics(hass, integration)
    assert diagnostics["entry"]["data"]["vin"] == "**REDACTED**"
    assert "5YJ3E1EA7KF000000" not in str(diagnostics)
