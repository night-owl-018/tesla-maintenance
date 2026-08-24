"""The Tesla Maintenance Tracker integration.

Maintenance records are owned by this integration and stored locally. Tesla
telemetry is read from entities that an existing Tesla integration already
provides - this integration never contacts Tesla and never handles credentials.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    ATTACHMENTS_DIRNAME,
    BACKUPS_DIRNAME,
    CONF_CREATE_DEFAULT_SCHEDULES,
    CONF_PURCHASE_DATE,
    CONF_VEHICLE_MODEL,
    CONF_VEHICLE_NAME,
    CONF_VEHICLE_YEAR,
    CONF_VIN,
    DATA_DIR_NAME,
    DB_FILENAME,
    DOMAIN,
    EXPORTS_DIRNAME,
)
from .coordinator import TeslaMaintenanceCoordinator
from .database.repository import MaintenanceRepository
from .services import async_register_services, async_unregister_services

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CALENDAR,
    Platform.NUMBER,
    Platform.SENSOR,
]


@dataclass(slots=True)
class TeslaMaintenanceRuntime:
    """Objects shared between platforms for a single config entry."""

    coordinator: TeslaMaintenanceCoordinator
    repository: MaintenanceRepository
    vehicle_id: int
    storage_dir: Path

    @property
    def attachments_dir(self) -> Path:
        """Return the attachments directory for this install."""
        return self.storage_dir / ATTACHMENTS_DIRNAME

    @property
    def exports_dir(self) -> Path:
        """Return the exports directory for this install."""
        return self.storage_dir / EXPORTS_DIRNAME

    @property
    def backups_dir(self) -> Path:
        """Return the database backup directory for this install."""
        return self.storage_dir / BACKUPS_DIRNAME


type TeslaMaintenanceConfigEntry = ConfigEntry[TeslaMaintenanceRuntime]


def _prepare_storage(config_dir: str) -> Path:
    """Create ``<config>/tesla_maintenance/`` and its subdirectories."""
    root = Path(config_dir) / DATA_DIR_NAME
    for sub in ("", ATTACHMENTS_DIRNAME, EXPORTS_DIRNAME, BACKUPS_DIRNAME):
        (root / sub).mkdir(parents=True, exist_ok=True)
    return root


async def async_setup_entry(
    hass: HomeAssistant, entry: TeslaMaintenanceConfigEntry
) -> bool:
    """Set up a vehicle from a config entry."""
    storage_dir = await hass.async_add_executor_job(_prepare_storage, hass.config.path())
    repository = MaintenanceRepository(storage_dir / DB_FILENAME)

    try:
        await hass.async_add_executor_job(repository.connect)
    except Exception as err:
        raise ConfigEntryNotReady(f"Could not open the maintenance database: {err}") from err

    settings = {**entry.data, **entry.options}

    def _bootstrap() -> int:
        """Create or reuse the vehicle row and seed defaults once."""
        vehicle = repository.get_or_create_vehicle(
            entry.entry_id,
            settings.get(CONF_VEHICLE_NAME, entry.title),
            vin=settings.get(CONF_VIN) or None,
            model=settings.get(CONF_VEHICLE_MODEL) or None,
            year=settings.get(CONF_VEHICLE_YEAR) or None,
            purchase_date=settings.get(CONF_PURCHASE_DATE) or None,
        )
        vehicle_id = int(vehicle.id or 0)
        if settings.get(CONF_CREATE_DEFAULT_SCHEDULES) and not repository.list_schedules(
            vehicle_id
        ):
            repository.seed_starter_schedules(vehicle_id, vehicle.current_mileage or 0)
        return vehicle_id

    vehicle_id = await hass.async_add_executor_job(_bootstrap)

    coordinator = TeslaMaintenanceCoordinator(
        hass, entry, repository, vehicle_id, storage_dir
    )
    await coordinator.async_setup()
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = TeslaMaintenanceRuntime(
        coordinator=coordinator,
        repository=repository,
        vehicle_id=vehicle_id,
        storage_dir=storage_dir,
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    async_register_services(hass)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: TeslaMaintenanceConfigEntry
) -> bool:
    """Unload a config entry and close its database connection."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        runtime = entry.runtime_data
        await hass.async_add_executor_job(runtime.repository.close)
    remaining = [
        loaded
        for loaded in hass.config_entries.async_loaded_entries(DOMAIN)
        if loaded.entry_id != entry.entry_id
    ]
    if not remaining:
        async_unregister_services(hass)
    return unloaded


async def async_reload_entry(
    hass: HomeAssistant, entry: TeslaMaintenanceConfigEntry
) -> None:
    """Reload the entry after options change.

    Only telemetry configuration lives in the config entry, so reloading can
    never affect stored maintenance data.
    """
    await hass.config_entries.async_reload(entry.entry_id)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle removal of a config entry.

    The maintenance database is deliberately left in place: removing the
    integration must not destroy years of service history. The files stay under
    ``<config>/tesla_maintenance/`` for the user to keep, export, or delete.
    """
    _LOGGER.info(
        "Config entry removed. Maintenance data has been kept at %s",
        Path(hass.config.path()) / DATA_DIR_NAME,
    )
