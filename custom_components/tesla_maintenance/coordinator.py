"""Coordinator for the Tesla Maintenance Tracker.

Reads mileage from the user-selected Home Assistant odometer entity (or from
manual entry), then derives maintenance status, forecasts and cost analytics
from the local database.

The coordinator never talks to Tesla. It only reads entity states that another
integration already publishes, and it degrades gracefully when those entities
are missing or unavailable - the maintenance database is always the source of
truth for history.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, State, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    ALL_ENTITY_KEYS,
    CONF_CURRENCY,
    CONF_DISTANCE_UNIT,
    CONF_MANUAL_MILEAGE,
    CONF_MILEAGE_SOURCE,
    CONF_ODOMETER_ENTITY,
    CONF_WARN_DAYS,
    CONF_WARN_MILES,
    DEFAULT_CURRENCY,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DEFAULT_WARN_DAYS,
    DEFAULT_WARN_MILES,
    DISTANCE_UNIT_MILES,
    DOMAIN,
    HEALTH_UNKNOWN,
    MILEAGE_SOURCE_MANUAL,
    OPTIONAL_ENTITY_KEYS,
    STATUS_DUE,
    STATUS_DUE_SOON,
    STATUS_OVERDUE,
)
from .database.models import Vehicle
from .database.repository import MaintenanceRepository
from .maintenance_logic import (
    ScheduleStatus,
    evaluate_schedules,
    next_service,
    overall_health,
)
from .notifications import MaintenanceNotifier

_LOGGER = logging.getLogger(__name__)

_INVALID_STATES = {STATE_UNAVAILABLE, STATE_UNKNOWN, "", "None"}


@dataclass(slots=True)
class TeslaMaintenanceData:
    """Everything the entities and dashboard need for one refresh."""

    vehicle: Vehicle
    current_mileage: float | None
    mileage_source: str
    telemetry_available: bool
    schedule_statuses: list[ScheduleStatus] = field(default_factory=list)
    due_items: list[ScheduleStatus] = field(default_factory=list)
    overdue_items: list[ScheduleStatus] = field(default_factory=list)
    next_due: ScheduleStatus | None = None
    health: str = HEALTH_UNKNOWN
    analytics: dict[str, Any] = field(default_factory=dict)
    last_service: dict[str, Any] | None = None
    tires: list[dict[str, Any]] = field(default_factory=list)
    brakes: dict[str, dict[str, Any]] = field(default_factory=dict)
    optional_entities: dict[str, dict[str, Any]] = field(default_factory=dict)


class TeslaMaintenanceCoordinator(DataUpdateCoordinator[TeslaMaintenanceData]):
    """Keeps maintenance state in sync with mileage and the database."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        repository: MaintenanceRepository,
        vehicle_id: int,
        storage_dir: Path,
    ) -> None:
        """Set up the coordinator for one vehicle."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(minutes=DEFAULT_SCAN_INTERVAL_MINUTES),
            config_entry=entry,
        )
        self.entry = entry
        self.repository = repository
        self.vehicle_id = vehicle_id
        self.storage_dir = storage_dir
        self._last_valid_mileage: float | None = None
        self._notifier = MaintenanceNotifier(hass)

    # ------------------------------------------------------------------
    # Configuration helpers
    # ------------------------------------------------------------------
    @property
    def settings(self) -> dict[str, Any]:
        """Return entry data merged with options, options winning."""
        return {**self.entry.data, **self.entry.options}

    @property
    def odometer_entity_id(self) -> str | None:
        """Return the configured odometer entity, if any."""
        return self.settings.get(CONF_ODOMETER_ENTITY) or None

    @property
    def distance_unit(self) -> str:
        """Return the configured distance unit."""
        return self.settings.get(CONF_DISTANCE_UNIT, DISTANCE_UNIT_MILES)

    @property
    def currency(self) -> str:
        """Return the configured currency code."""
        return self.settings.get(CONF_CURRENCY, DEFAULT_CURRENCY)

    @property
    def warn_miles(self) -> float:
        """Return the mileage warning threshold."""
        return float(self.settings.get(CONF_WARN_MILES, DEFAULT_WARN_MILES))

    @property
    def warn_days(self) -> int:
        """Return the day warning threshold."""
        return int(self.settings.get(CONF_WARN_DAYS, DEFAULT_WARN_DAYS))

    @property
    def tracked_entity_ids(self) -> list[str]:
        """Return every mapped Tesla entity id."""
        settings = self.settings
        return [
            entity_id
            for key in ALL_ENTITY_KEYS
            if (entity_id := settings.get(key))
        ]

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------
    async def async_setup(self) -> None:
        """Subscribe to the mapped Tesla entities so updates arrive promptly."""
        entity_ids = self.tracked_entity_ids
        if not entity_ids:
            return
        self.entry.async_on_unload(
            async_track_state_change_event(
                self.hass, entity_ids, self._handle_tracked_state_change
            )
        )

    @callback
    def _handle_tracked_state_change(self, event: Any) -> None:
        """Refresh when a mapped Tesla entity changes state."""
        self.hass.async_create_task(self.async_refresh())

    # ------------------------------------------------------------------
    # Mileage
    # ------------------------------------------------------------------
    def _read_state(self, entity_id: str | None) -> State | None:
        """Return a state object if the entity exists and reports a value."""
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        if state is None or state.state in _INVALID_STATES:
            return None
        return state

    def _read_odometer(self) -> tuple[float | None, bool]:
        """Return ``(mileage, telemetry_available)``.

        When the odometer entity is missing or unavailable the last known good
        value is kept. Telemetry outages never reset mileage or schedules.
        """
        if self.settings.get(CONF_MILEAGE_SOURCE) == MILEAGE_SOURCE_MANUAL:
            manual = self.settings.get(CONF_MANUAL_MILEAGE)
            if manual is not None:
                return float(manual), True
            return self._last_valid_mileage, True

        state = self._read_state(self.odometer_entity_id)
        if state is None:
            return self._last_valid_mileage, False
        try:
            value = float(state.state)
        except (TypeError, ValueError):
            _LOGGER.debug(
                "Odometer entity %s reported a non-numeric state", self.odometer_entity_id
            )
            return self._last_valid_mileage, False
        if value < 0:
            return self._last_valid_mileage, False
        return value, True

    def _optional_entity_status(self) -> dict[str, dict[str, Any]]:
        """Return the connection status and value of each optional entity."""
        settings = self.settings
        result: dict[str, dict[str, Any]] = {}
        for key, label in OPTIONAL_ENTITY_KEYS:
            entity_id = settings.get(key)
            if not entity_id:
                result[key] = {
                    "label": label,
                    "entity_id": None,
                    "status": "Not configured",
                    "value": None,
                }
                continue
            state = self._read_state(entity_id)
            result[key] = {
                "label": label,
                "entity_id": entity_id,
                "status": "Connected" if state else "Unavailable",
                "value": state.state if state else None,
            }
        return result

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------
    async def _async_update_data(self) -> TeslaMaintenanceData:
        """Read mileage, then rebuild the derived maintenance view."""
        mileage, telemetry_available = self._read_odometer()
        if mileage is not None:
            self._last_valid_mileage = mileage
            await self.hass.async_add_executor_job(
                self.repository.set_current_mileage, self.vehicle_id, mileage
            )
        data = await self.hass.async_add_executor_job(
            self._build_data, telemetry_available
        )
        await self._notifier.async_process(
            data.schedule_statuses,
            self.settings,
            data.vehicle.name,
            self.distance_unit,
        )
        return data

    def _build_data(self, telemetry_available: bool) -> TeslaMaintenanceData:
        """Assemble the coordinator payload. Runs in the executor."""
        repository = self.repository
        vehicle = repository.get_vehicle(self.vehicle_id)
        if vehicle is None:
            raise RuntimeError(f"Vehicle {self.vehicle_id} is missing from the database")

        mileage = vehicle.current_mileage if vehicle.current_mileage else None
        statuses = evaluate_schedules(
            repository.list_schedules(self.vehicle_id),
            mileage,
            date.today(),
            self.warn_miles,
            self.warn_days,
        )
        due = [item for item in statuses if item.status in (STATUS_DUE, STATUS_DUE_SOON)]
        overdue = [item for item in statuses if item.status == STATUS_OVERDUE]
        last = repository.last_service(self.vehicle_id)

        return TeslaMaintenanceData(
            vehicle=vehicle,
            current_mileage=mileage,
            mileage_source=self.settings.get(CONF_MILEAGE_SOURCE, ""),
            telemetry_available=telemetry_available,
            schedule_statuses=statuses,
            due_items=due,
            overdue_items=overdue,
            next_due=next_service(statuses),
            health=overall_health(statuses),
            analytics=repository.analytics(self.vehicle_id),
            last_service=last.to_dict() if last else None,
            tires=[
                tire.to_dict()
                for tire in repository.list_tire_records(self.vehicle_id, active_only=True)
            ],
            brakes={
                axle: record.to_dict()
                for axle, record in repository.latest_brake_records(
                    self.vehicle_id
                ).items()
            },
            optional_entities=self._optional_entity_status(),
        )
