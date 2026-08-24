"""Maintenance notifications.

A notification is sent when a schedule *changes* into a due or overdue state,
so a persistent condition is announced once rather than on every refresh.
Notifications can be turned off entirely in the options flow.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant

from .const import (
    CONF_NOTIFICATIONS_ENABLED,
    CONF_NOTIFY_ON_DUE,
    CONF_NOTIFY_ON_OVERDUE,
    CONF_NOTIFY_SERVICE,
    STATUS_DUE,
    STATUS_DUE_SOON,
    STATUS_OVERDUE,
)

if TYPE_CHECKING:
    from .maintenance_logic import ScheduleStatus

_LOGGER = logging.getLogger(__name__)

NOTIFICATION_TITLE = "Tesla Maintenance"


def build_message(status: ScheduleStatus, vehicle_name: str, unit: str) -> str:
    """Return a human-readable message for a schedule status.

    Only real numbers are used - if a threshold is unknown it is left out.
    """
    name = status.item_name
    if status.status == STATUS_OVERDUE:
        if status.miles_remaining is not None and status.miles_remaining < 0:
            return (
                f"{vehicle_name}: {name} is overdue by "
                f"{abs(status.miles_remaining):,.0f} {unit}."
            )
        if status.days_remaining is not None and status.days_remaining < 0:
            return (
                f"{vehicle_name}: {name} is overdue by "
                f"{abs(status.days_remaining)} days."
            )
        return f"{vehicle_name}: {name} is overdue."

    if status.miles_remaining is not None and status.days_remaining is not None:
        return (
            f"{vehicle_name}: {name} is due in about "
            f"{status.miles_remaining:,.0f} {unit} or {status.days_remaining} days."
        )
    if status.miles_remaining is not None:
        return (
            f"{vehicle_name}: {name} is due in about "
            f"{status.miles_remaining:,.0f} {unit}."
        )
    if status.days_remaining is not None:
        return f"{vehicle_name}: {name} is due in {status.days_remaining} days."
    return f"{vehicle_name}: {name} is due."


class MaintenanceNotifier:
    """Tracks status transitions and sends notifications."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialise with an empty transition history."""
        self.hass = hass
        self._last_status: dict[int, str] = {}

    async def async_process(
        self,
        statuses: list[ScheduleStatus],
        settings: dict[str, Any],
        vehicle_name: str,
        unit: str,
    ) -> None:
        """Send notifications for newly due or overdue schedules."""
        if not settings.get(CONF_NOTIFICATIONS_ENABLED, True):
            # Still track state so re-enabling does not replay old alerts.
            self._remember(statuses)
            return

        notify_due = settings.get(CONF_NOTIFY_ON_DUE, True)
        notify_overdue = settings.get(CONF_NOTIFY_ON_OVERDUE, True)
        service = settings.get(CONF_NOTIFY_SERVICE) or ""

        for status in statuses:
            if status.schedule_id is None:
                continue
            previous = self._last_status.get(status.schedule_id)
            if previous == status.status:
                continue
            should_notify = (
                status.status in (STATUS_DUE, STATUS_DUE_SOON) and notify_due
            ) or (status.status == STATUS_OVERDUE and notify_overdue)
            if should_notify:
                await self._async_send(
                    build_message(status, vehicle_name, unit), service
                )
        self._remember(statuses)

    def _remember(self, statuses: list[ScheduleStatus]) -> None:
        """Record the current status of every schedule."""
        for status in statuses:
            if status.schedule_id is not None:
                self._last_status[status.schedule_id] = status.status

    async def _async_send(self, message: str, service: str) -> None:
        """Deliver a notification, falling back to a persistent notification."""
        if service and "." in service:
            domain, name = service.split(".", 1)
            try:
                await self.hass.services.async_call(
                    domain,
                    name,
                    {"title": NOTIFICATION_TITLE, "message": message},
                    blocking=False,
                )
                return
            except Exception as err:  # pylint: disable=broad-except  - never break a refresh
                _LOGGER.warning(
                    "Could not call notify service %s (%s); falling back to a "
                    "persistent notification",
                    service,
                    err,
                )

        from homeassistant.components import persistent_notification

        persistent_notification.async_create(
            self.hass, message, title=NOTIFICATION_TITLE
        )
