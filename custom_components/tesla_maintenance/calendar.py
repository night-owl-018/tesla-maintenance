"""Calendar showing upcoming, date-based maintenance.

Only schedules with a real due date appear. Mileage-only schedules have no
calendar date and are deliberately omitted rather than guessed at.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import TeslaMaintenanceCoordinator
from .entity import TeslaMaintenanceEntity
from .maintenance_logic import ScheduleStatus, parse_date

if TYPE_CHECKING:
    from . import TeslaMaintenanceConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TeslaMaintenanceConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the maintenance calendar."""
    async_add_entities([TeslaMaintenanceCalendar(entry.runtime_data.coordinator)])


class TeslaMaintenanceCalendar(TeslaMaintenanceEntity, CalendarEntity):
    """Upcoming maintenance as calendar events."""

    _attr_translation_key = "maintenance"
    _attr_icon = "mdi:calendar-wrench"

    def __init__(self, coordinator: TeslaMaintenanceCoordinator) -> None:
        """Initialise the calendar."""
        super().__init__(coordinator, "maintenance_calendar")

    def _events(self) -> list[CalendarEvent]:
        """Build events from every date-based schedule."""
        events: list[CalendarEvent] = []
        for status in self.coordinator.data.schedule_statuses:
            due = parse_date(status.next_due_date)
            if due is None or not status.enabled:
                continue
            events.append(
                CalendarEvent(
                    summary=status.item_name,
                    start=due,
                    end=due + timedelta(days=1),
                    description=self._describe(status),
                )
            )
        return sorted(events, key=lambda event: event.start)

    @staticmethod
    def _describe(status: ScheduleStatus) -> str:
        """Return a readable description including the schedule source."""
        parts = [f"Category: {status.category}", f"Source: {status.source}"]
        if status.miles_remaining is not None:
            parts.append(f"Mileage remaining: {status.miles_remaining:.0f}")
        if status.notes:
            parts.append(f"Notes: {status.notes}")
        return " | ".join(parts)

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next upcoming event."""
        today = dt_util.now().date()
        upcoming = [event for event in self._events() if event.end > today]
        return upcoming[0] if upcoming else None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Return events within a window."""
        start = start_date.date()
        end = end_date.date()
        return [
            event for event in self._events() if event.start < end and event.end > start
        ]
