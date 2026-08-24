"""Maintenance scheduling and status calculations.

Pure functions with no Home Assistant dependency so the rules can be tested in
isolation. All dates are ISO ``YYYY-MM-DD`` strings.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from .const import (
    HEALTH_ATTENTION,
    HEALTH_GOOD,
    HEALTH_OVERDUE,
    HEALTH_UNKNOWN,
    STATUS_DISABLED,
    STATUS_DUE,
    STATUS_DUE_SOON,
    STATUS_OK,
    STATUS_OVERDUE,
)
from .database.models import MaintenanceSchedule

#: Higher is worse. Used to pick the threshold that triggers first.
_SEVERITY: dict[str, int] = {
    STATUS_DISABLED: -1,
    STATUS_OK: 0,
    STATUS_DUE_SOON: 1,
    STATUS_DUE: 2,
    STATUS_OVERDUE: 3,
}


def parse_date(value: str | date | None) -> date | None:
    """Parse an ISO date string, tolerating full ISO timestamps."""
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def add_days(start: date, days: int) -> date:
    """Return ``start`` shifted by ``days``."""
    return start + timedelta(days=days)


def compute_next_due(
    schedule: MaintenanceSchedule,
) -> tuple[float | None, str | None]:
    """Return ``(next_due_mileage, next_due_date)`` for a schedule.

    A schedule may be mileage based, time based, or both. When both are set the
    caller decides which fires first - see :func:`evaluate_schedule`.
    """
    next_mileage: float | None = None
    next_date: str | None = None

    if schedule.interval_miles and schedule.last_service_mileage is not None:
        next_mileage = float(schedule.last_service_mileage) + float(
            schedule.interval_miles
        )

    if schedule.interval_days:
        base = parse_date(schedule.last_service_date)
        if base is not None:
            next_date = add_days(base, int(schedule.interval_days)).isoformat()

    return next_mileage, next_date


@dataclass(slots=True)
class ScheduleStatus:
    """The evaluated state of a single maintenance schedule."""

    schedule_id: int | None
    item_name: str
    category: str
    source: str
    status: str
    miles_remaining: float | None
    days_remaining: int | None
    next_due_mileage: float | None
    next_due_date: str | None
    enabled: bool
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Return a serialisable representation for entity attributes."""
        return {
            "schedule_id": self.schedule_id,
            "item_name": self.item_name,
            "category": self.category,
            "source": self.source,
            "status": self.status,
            "miles_remaining": self.miles_remaining,
            "days_remaining": self.days_remaining,
            "next_due_mileage": self.next_due_mileage,
            "next_due_date": self.next_due_date,
            "enabled": self.enabled,
            "notes": self.notes,
        }


def _status_from_remaining(remaining: float, threshold: float) -> str:
    """Map a remaining distance/time to a status."""
    if remaining < 0:
        return STATUS_OVERDUE
    if remaining == 0:
        return STATUS_DUE
    if remaining <= threshold:
        return STATUS_DUE_SOON
    return STATUS_OK


def evaluate_schedule(
    schedule: MaintenanceSchedule,
    current_mileage: float | None,
    today: date | None = None,
    warn_miles: float = 500,
    warn_days: int = 30,
) -> ScheduleStatus:
    """Evaluate one schedule against current mileage and today's date.

    Whichever threshold (mileage or time) triggers first determines the status.
    Missing telemetry never invents a value - the corresponding side simply does
    not contribute to the result.
    """
    today = today or date.today()
    next_mileage, next_date = compute_next_due(schedule)
    # Prefer stored values when present so historical rows stay stable.
    next_mileage = (
        schedule.next_due_mileage if schedule.next_due_mileage is not None else next_mileage
    )
    next_date = schedule.next_due_date or next_date

    miles_remaining: float | None = None
    days_remaining: int | None = None
    statuses: list[str] = []

    if next_mileage is not None and current_mileage is not None:
        miles_remaining = round(float(next_mileage) - float(current_mileage), 1)
        statuses.append(_status_from_remaining(miles_remaining, warn_miles))

    parsed_due = parse_date(next_date)
    if parsed_due is not None:
        days_remaining = (parsed_due - today).days
        statuses.append(_status_from_remaining(days_remaining, warn_days))

    if not schedule.enabled:
        status = STATUS_DISABLED
    elif not statuses:
        status = STATUS_OK
    else:
        status = max(statuses, key=lambda item: _SEVERITY[item])

    return ScheduleStatus(
        schedule_id=schedule.id,
        item_name=schedule.item_name,
        category=schedule.category,
        source=schedule.source,
        status=status,
        miles_remaining=miles_remaining,
        days_remaining=days_remaining,
        next_due_mileage=next_mileage,
        next_due_date=next_date,
        enabled=bool(schedule.enabled),
        notes=schedule.notes,
    )


def evaluate_schedules(
    schedules: list[MaintenanceSchedule],
    current_mileage: float | None,
    today: date | None = None,
    warn_miles: float = 500,
    warn_days: int = 30,
) -> list[ScheduleStatus]:
    """Evaluate every schedule, sorted by urgency then by how soon it is due."""
    results = [
        evaluate_schedule(schedule, current_mileage, today, warn_miles, warn_days)
        for schedule in schedules
    ]
    return sorted(results, key=_sort_key)


def _sort_key(status: ScheduleStatus) -> tuple[int, float]:
    """Sort most urgent first, then by whichever threshold is nearest."""
    severity = -_SEVERITY[status.status]
    candidates = [
        value
        for value in (status.miles_remaining, status.days_remaining)
        if value is not None
    ]
    nearest = min(candidates) if candidates else float("inf")
    return (severity, nearest)


def overall_health(statuses: list[ScheduleStatus]) -> str:
    """Roll individual schedule statuses up into a single health value."""
    active = [item for item in statuses if item.status != STATUS_DISABLED]
    if not active:
        return HEALTH_UNKNOWN
    if any(item.status == STATUS_OVERDUE for item in active):
        return HEALTH_OVERDUE
    if any(item.status in (STATUS_DUE, STATUS_DUE_SOON) for item in active):
        return HEALTH_ATTENTION
    return HEALTH_GOOD


def next_service(statuses: list[ScheduleStatus]) -> ScheduleStatus | None:
    """Return the schedule that will come due first, if any."""
    candidates = [
        item
        for item in statuses
        if item.status != STATUS_DISABLED
        and (item.miles_remaining is not None or item.days_remaining is not None)
    ]
    if not candidates:
        return None
    return min(candidates, key=_sort_key)
