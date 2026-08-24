"""Tests for the config flow and options flow."""

from __future__ import annotations

from unittest.mock import patch

from custom_components.tesla_maintenance.const import (
    CONF_BATTERY_LEVEL_ENTITY,
    CONF_CREATE_DEFAULT_SCHEDULES,
    CONF_CURRENCY,
    CONF_DISTANCE_UNIT,
    CONF_MANUAL_MILEAGE,
    CONF_MILEAGE_SOURCE,
    CONF_NOTIFICATIONS_ENABLED,
    CONF_NOTIFY_ON_DUE,
    CONF_NOTIFY_ON_OVERDUE,
    CONF_ODOMETER_ENTITY,
    CONF_VEHICLE_MODEL,
    CONF_VEHICLE_NAME,
    CONF_WARN_DAYS,
    CONF_WARN_MILES,
    DOMAIN,
    MILEAGE_SOURCE_ENTITY,
    MILEAGE_SOURCE_MANUAL,
)
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import MOCK_CONFIG, ODOMETER_ENTITY

MAINTENANCE_INPUT = {
    CONF_DISTANCE_UNIT: "mi",
    CONF_CURRENCY: "USD",
    CONF_WARN_MILES: 500,
    CONF_WARN_DAYS: 30,
    CONF_CREATE_DEFAULT_SCHEDULES: True,
}
NOTIFY_INPUT = {
    CONF_NOTIFICATIONS_ENABLED: True,
    CONF_NOTIFY_ON_DUE: True,
    CONF_NOTIFY_ON_OVERDUE: True,
}


async def test_full_flow_with_tesla_entity(hass, tmp_path):
    """The four-step flow completes and stores the selected entities."""
    hass.states.async_set(ODOMETER_ENTITY, "42580")

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_VEHICLE_NAME: "Model Y", CONF_VEHICLE_MODEL: "Model Y"},
    )
    assert result["step_id"] == "tesla"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_MILEAGE_SOURCE: MILEAGE_SOURCE_ENTITY,
            CONF_ODOMETER_ENTITY: ODOMETER_ENTITY,
            CONF_BATTERY_LEVEL_ENTITY: "sensor.tesla_battery",
        },
    )
    assert result["step_id"] == "maintenance"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], MAINTENANCE_INPUT
    )
    assert result["step_id"] == "notifications"

    with patch.object(hass.config, "config_dir", str(tmp_path)):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], NOTIFY_INPUT
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Model Y"
    assert result["data"][CONF_ODOMETER_ENTITY] == ODOMETER_ENTITY
    assert result["data"][CONF_BATTERY_LEVEL_ENTITY] == "sensor.tesla_battery"
    # No credential fields exist anywhere in the stored configuration.
    assert not any(
        key in result["data"] for key in ("token", "refresh_token", "password", "email")
    )


async def test_tesla_step_requires_an_odometer(hass):
    """Choosing the entity source without an entity raises a form error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_VEHICLE_NAME: "Model 3"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MILEAGE_SOURCE: MILEAGE_SOURCE_ENTITY}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_ODOMETER_ENTITY: "odometer_required"}


async def test_manual_mileage_requires_a_value(hass):
    """Manual mode without a reading raises a form error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_VEHICLE_NAME: "Model 3"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MILEAGE_SOURCE: MILEAGE_SOURCE_MANUAL}
    )
    assert result["errors"] == {CONF_MANUAL_MILEAGE: "manual_mileage_required"}


async def test_manual_mileage_flow_completes_without_any_tesla_entity(hass, tmp_path):
    """The integration is usable with no Tesla entities at all."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_VEHICLE_NAME: "Manual Tesla"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_MILEAGE_SOURCE: MILEAGE_SOURCE_MANUAL, CONF_MANUAL_MILEAGE: 12345},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], MAINTENANCE_INPUT
    )
    with patch.object(hass.config, "config_dir", str(tmp_path)):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], NOTIFY_INPUT
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_MANUAL_MILEAGE] == 12345
    assert CONF_ODOMETER_ENTITY not in result["data"]


async def test_duplicate_vehicle_is_aborted(hass, tmp_path):
    """Setting up the same vehicle name twice aborts."""
    entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, title="Test Tesla", unique_id="tesla_maintenance_test tesla"
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_VEHICLE_NAME: "Test Tesla"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_MILEAGE_SOURCE: MILEAGE_SOURCE_MANUAL, CONF_MANUAL_MILEAGE: 1},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], MAINTENANCE_INPUT
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], NOTIFY_INPUT
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options_flow_shows_menu(hass, integration):
    """The options flow offers the four editable sections."""
    result = await hass.config_entries.options.async_init(integration.entry_id)
    assert result["type"] is FlowResultType.MENU
    assert set(result["menu_options"]) == {
        "vehicle",
        "tesla",
        "maintenance",
        "notifications",
    }


async def test_options_flow_remaps_entities_without_losing_data(hass, integration):
    """Changing the odometer mapping keeps every maintenance record."""
    from custom_components.tesla_maintenance.database.models import ServiceRecord

    runtime = integration.runtime_data
    await hass.async_add_executor_job(
        runtime.repository.add_service_record,
        ServiceRecord(
            vehicle_id=runtime.vehicle_id,
            service_date="2026-01-01",
            total_cost=250,
            notes="Keep me through a remap.",
        ),
    )

    hass.states.async_set("sensor.new_odometer", "50000")
    result = await hass.config_entries.options.async_init(integration.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "tesla"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_MILEAGE_SOURCE: MILEAGE_SOURCE_ENTITY,
            CONF_ODOMETER_ENTITY: "sensor.new_odometer",
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert integration.options[CONF_ODOMETER_ENTITY] == "sensor.new_odometer"

    runtime = integration.runtime_data
    records = await hass.async_add_executor_job(
        runtime.repository.list_service_records, runtime.vehicle_id
    )
    assert len(records) == 1
    assert records[0].notes == "Keep me through a remap."


async def test_options_flow_updates_thresholds(hass, integration):
    """Warning thresholds are editable after setup."""
    result = await hass.config_entries.options.async_init(integration.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "maintenance"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_DISTANCE_UNIT: "km",
            CONF_CURRENCY: "EUR",
            CONF_WARN_MILES: 1000,
            CONF_WARN_DAYS: 60,
            CONF_CREATE_DEFAULT_SCHEDULES: False,
        },
    )
    await hass.async_block_till_done()

    assert integration.options[CONF_WARN_MILES] == 1000
    assert integration.runtime_data.coordinator.currency == "EUR"
