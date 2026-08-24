"""Tests for maintenance scheduling and status rules."""

from __future__ import annotations

from datetime import date

from custom_components.tesla_maintenance.const import (
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
from custom_components.tesla_maintenance.database.models import MaintenanceSchedule
from custom_components.tesla_maintenance.maintenance_logic import (
    compute_next_due,
    evaluate_schedule,
    evaluate_schedules,
    next_service,
    overall_health,
    parse_date,
)

TODAY = date(2026, 8, 23)


def _schedule(**kwargs) -> MaintenanceSchedule:
    defaults = {
        "id": 1,
        "vehicle_id": 1,
        "item_name": "Tire Rotation",
        "category": "Tires",
    }
    return MaintenanceSchedule(**{**defaults, **kwargs})


def test_parse_date_handles_timestamps_and_junk():
    assert parse_date("2026-08-23T10:00:00+00:00") == date(2026, 8, 23)
    assert parse_date("") is None
    assert parse_date(None) is None
    assert parse_date("not-a-date") is None


def test_compute_next_due_mileage_and_time():
    schedule = _schedule(
        interval_miles=6250,
        last_service_mileage=40000,
        interval_days=365,
        last_service_date="2026-01-01",
    )
    mileage, due_date = compute_next_due(schedule)
    assert mileage == 46250
    assert due_date == "2027-01-01"


def test_compute_next_due_without_baseline_returns_none():
    mileage, due_date = compute_next_due(_schedule(interval_miles=6250))
    assert mileage is None
    assert due_date is None


def test_mileage_interval_statuses():
    schedule = _schedule(interval_miles=6250, last_service_mileage=40000)
    assert evaluate_schedule(schedule, 41000, TODAY).status == STATUS_OK
    assert evaluate_schedule(schedule, 46000, TODAY).status == STATUS_DUE_SOON
    assert evaluate_schedule(schedule, 46250, TODAY).status == STATUS_DUE
    overdue = evaluate_schedule(schedule, 47000, TODAY)
    assert overdue.status == STATUS_OVERDUE
    assert overdue.miles_remaining == -750


def test_date_interval_statuses():
    schedule = _schedule(
        item_name="Cabin Air Filter", interval_days=30, last_service_date="2026-08-01"
    )
    # Due 2026-08-31: eight days away with a 30 day warning window.
    result = evaluate_schedule(schedule, None, TODAY)
    assert result.status == STATUS_DUE_SOON
    assert result.days_remaining == 8

    late = _schedule(interval_days=30, last_service_date="2026-06-01")
    assert evaluate_schedule(late, None, TODAY).status == STATUS_OVERDUE


def test_whichever_threshold_comes_first_wins():
    # Mileage is comfortable, but the date has already passed.
    schedule = _schedule(
        interval_miles=6250,
        last_service_mileage=40000,
        interval_days=365,
        last_service_date="2025-01-01",
    )
    result = evaluate_schedule(schedule, 40100, TODAY)
    assert result.status == STATUS_OVERDUE
    assert result.miles_remaining == 6150
    assert result.days_remaining < 0


def test_custom_warning_thresholds_are_respected():
    schedule = _schedule(interval_miles=6250, last_service_mileage=40000)
    assert evaluate_schedule(schedule, 44000, TODAY, warn_miles=500).status == STATUS_OK
    assert (
        evaluate_schedule(schedule, 44000, TODAY, warn_miles=3000).status
        == STATUS_DUE_SOON
    )


def test_disabled_schedule_reports_disabled():
    schedule = _schedule(interval_miles=6250, last_service_mileage=40000, enabled=False)
    assert evaluate_schedule(schedule, 99999, TODAY).status == STATUS_DISABLED


def test_missing_mileage_does_not_invent_a_status():
    schedule = _schedule(interval_miles=6250, last_service_mileage=40000)
    result = evaluate_schedule(schedule, None, TODAY)
    assert result.status == STATUS_OK
    assert result.miles_remaining is None
    assert result.days_remaining is None


def test_evaluate_schedules_sorts_most_urgent_first():
    schedules = [
        _schedule(id=1, item_name="Healthy", interval_miles=10000, last_service_mileage=40000),
        _schedule(id=2, item_name="Overdue", interval_miles=1000, last_service_mileage=40000),
        _schedule(id=3, item_name="Soon", interval_miles=1500, last_service_mileage=40000),
    ]
    results = evaluate_schedules(schedules, 41200, TODAY)
    assert [item.item_name for item in results] == ["Overdue", "Soon", "Healthy"]


def test_overall_health_rollup():
    good = [_schedule(id=1, interval_miles=10000, last_service_mileage=40000)]
    assert overall_health(evaluate_schedules(good, 40100, TODAY)) == HEALTH_GOOD

    attention = [_schedule(id=1, interval_miles=1000, last_service_mileage=40000)]
    assert overall_health(evaluate_schedules(attention, 40600, TODAY)) == HEALTH_ATTENTION

    late = [_schedule(id=1, interval_miles=1000, last_service_mileage=40000)]
    assert overall_health(evaluate_schedules(late, 42000, TODAY)) == HEALTH_OVERDUE

    assert overall_health([]) == HEALTH_UNKNOWN


def test_next_service_picks_the_nearest_threshold():
    schedules = [
        _schedule(id=1, item_name="Far", interval_miles=10000, last_service_mileage=40000),
        _schedule(id=2, item_name="Near", interval_miles=2000, last_service_mileage=40000),
    ]
    result = next_service(evaluate_schedules(schedules, 41000, TODAY))
    assert result.item_name == "Near"
    assert result.miles_remaining == 1000


def test_next_service_none_without_data():
    assert next_service([]) is None
