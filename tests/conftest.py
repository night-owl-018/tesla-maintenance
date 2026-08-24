"""Shared fixtures for the Tesla Maintenance Tracker tests."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Make custom_components importable as a top-level package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from custom_components.tesla_maintenance.const import (
    CONF_CREATE_DEFAULT_SCHEDULES,
    CONF_CURRENCY,
    CONF_DISTANCE_UNIT,
    CONF_MILEAGE_SOURCE,
    CONF_NOTIFICATIONS_ENABLED,
    CONF_ODOMETER_ENTITY,
    CONF_VEHICLE_MODEL,
    CONF_VEHICLE_NAME,
    CONF_WARN_DAYS,
    CONF_WARN_MILES,
    DOMAIN,
    MILEAGE_SOURCE_ENTITY,
)
from custom_components.tesla_maintenance.database.repository import (
    MaintenanceRepository,
)

ODOMETER_ENTITY = "sensor.test_tesla_odometer"

MOCK_CONFIG = {
    CONF_VEHICLE_NAME: "Test Tesla",
    CONF_VEHICLE_MODEL: "Model Y",
    CONF_MILEAGE_SOURCE: MILEAGE_SOURCE_ENTITY,
    CONF_ODOMETER_ENTITY: ODOMETER_ENTITY,
    CONF_DISTANCE_UNIT: "mi",
    CONF_CURRENCY: "USD",
    CONF_WARN_MILES: 500,
    CONF_WARN_DAYS: 30,
    CONF_CREATE_DEFAULT_SCHEDULES: False,
    CONF_NOTIFICATIONS_ENABLED: False,
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the custom integration in every test."""
    return enable_custom_integrations


@pytest.fixture
def repository(tmp_path: Path):
    """Return a connected repository backed by a temporary database."""
    repo = MaintenanceRepository(tmp_path / "maintenance.db")
    repo.connect()
    yield repo
    repo.close()


@pytest.fixture
def vehicle(repository: MaintenanceRepository):
    """Return a seeded vehicle."""
    return repository.get_or_create_vehicle("entry-1", "Test Tesla", model="Model Y")


@pytest.fixture
async def integration(hass, tmp_path):
    """Set up the integration against a temporary config directory."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    hass.states.async_set(ODOMETER_ENTITY, "42580")

    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, title="Test Tesla")
    entry.add_to_hass(hass)

    with patch.object(hass.config, "config_dir", str(tmp_path)):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        yield entry
