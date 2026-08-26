"""SQLite repository for the Tesla Maintenance Tracker.

Every method here is synchronous and thread safe. Home Assistant callers must
run them through ``hass.async_add_executor_job`` so the event loop is never
blocked - see :class:`..coordinator.TeslaMaintenanceCoordinator`.

This layer has no Home Assistant imports, which keeps it fully unit testable.
"""

from __future__ import annotations

import logging
import shutil
import sqlite3
import threading
from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from ..const import (
    DEFAULT_CATEGORIES,
    SORT_COST_ASC,
    SORT_COST_DESC,
    SORT_MILEAGE_ASC,
    SORT_MILEAGE_DESC,
    SORT_NEWEST,
    SORT_OLDEST,
    SOURCE_DEFAULT,
    STARTER_SCHEDULES,
)
from ..maintenance_logic import compute_next_due
from .models import (
    Attachment,
    BrakeRecord,
    Category,
    MaintenanceItem,
    MaintenanceSchedule,
    ServiceRecord,
    TireRecord,
    TireRotation,
    Vehicle,
)
from .schema import apply_schema

_LOGGER = logging.getLogger(__name__)

_SORT_SQL: dict[str, str] = {
    SORT_NEWEST: "service_date DESC, id DESC",
    SORT_OLDEST: "service_date ASC, id ASC",
    SORT_COST_DESC: "total_cost DESC",
    SORT_COST_ASC: "total_cost ASC",
    SORT_MILEAGE_DESC: "mileage DESC",
    SORT_MILEAGE_ASC: "mileage ASC",
}


class RepositoryError(Exception):
    """Raised when a repository operation cannot be completed."""


def _now() -> str:
    """Return the current UTC timestamp as an ISO string."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def _today() -> str:
    """Return today's date as an ISO string."""
    return date.today().isoformat()


class MaintenanceRepository:
    """Thread-safe data access for the maintenance database."""

    def __init__(self, db_path: str | Path) -> None:
        """Store the database path. Call :meth:`connect` before use."""
        self.db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------
    def connect(self) -> None:
        """Open the database, creating the file and schema when needed."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        apply_schema(conn)
        self._conn = conn
        _LOGGER.debug("Maintenance database ready at %s", self.db_path)

    def close(self) -> None:
        """Close the database connection."""
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        """Return the live connection, or raise if it was never opened."""
        if self._conn is None:
            raise RepositoryError("Database is not connected")
        return self._conn

    def backup(self, destination: str | Path) -> str:
        """Write a consistent copy of the database to ``destination``."""
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            target = sqlite3.connect(destination)
            try:
                self.conn.backup(target)
            finally:
                target.close()
        return str(destination)

    # ------------------------------------------------------------------
    # Low-level helpers
    # ------------------------------------------------------------------
    def _execute(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            cursor = self.conn.execute(sql, params)
            self.conn.commit()
            return cursor

    def _query(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self.conn.execute(sql, params).fetchall()

    def _query_one(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Row | None:
        with self._lock:
            return self.conn.execute(sql, params).fetchone()

    @staticmethod
    def _apply_updates(
        table: str, allowed: Iterable[str], updates: dict[str, Any]
    ) -> tuple[str, list[Any]]:
        """Build a safe UPDATE statement from a whitelist of column names."""
        allowed_set = set(allowed)
        columns = [key for key in updates if key in allowed_set]
        if not columns:
            raise RepositoryError(f"No updatable fields supplied for {table}")
        assignments = ", ".join(f"{column} = ?" for column in columns)
        values = [updates[column] for column in columns]
        return assignments, values

    # ------------------------------------------------------------------
    # Vehicles
    # ------------------------------------------------------------------
    def get_or_create_vehicle(
        self,
        config_entry_id: str,
        name: str,
        *,
        vin: str | None = None,
        model: str | None = None,
        year: int | None = None,
        purchase_date: str | None = None,
        notes: str = "",
        seed_defaults: bool = True,
    ) -> Vehicle:
        """Return the vehicle for a config entry, creating it if needed.

        Reconfiguring the integration reuses the existing row, so maintenance
        data is never lost when Tesla entity mappings change.
        """
        existing = self._query_one(
            "SELECT * FROM vehicles WHERE config_entry_id = ?", (config_entry_id,)
        )
        if existing is not None:
            vehicle = Vehicle.from_row(existing)
            self.update_vehicle(
                vehicle.id,
                {
                    "name": name,
                    "vin": vin if vin is not None else vehicle.vin,
                    "model": model if model is not None else vehicle.model,
                    "year": year if year is not None else vehicle.year,
                    "purchase_date": purchase_date or vehicle.purchase_date,
                },
            )
            return self.get_vehicle(vehicle.id)  # type: ignore[arg-type]

        now = _now()
        cursor = self._execute(
            """
            INSERT INTO vehicles (
                config_entry_id, name, vin, model, year, current_mileage,
                purchase_date, notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, ?)
            """,
            (config_entry_id, name, vin, model, year, purchase_date, notes, now, now),
        )
        vehicle_id = int(cursor.lastrowid or 0)
        if seed_defaults:
            self.seed_default_categories(vehicle_id)
        _LOGGER.debug("Created vehicle row id=%s", vehicle_id)
        return self.get_vehicle(vehicle_id)  # type: ignore[return-value]

    def get_vehicle(self, vehicle_id: int) -> Vehicle | None:
        """Return one vehicle by id."""
        row = self._query_one("SELECT * FROM vehicles WHERE id = ?", (vehicle_id,))
        return Vehicle.from_row(row) if row else None

    def get_vehicle_by_entry(self, config_entry_id: str) -> Vehicle | None:
        """Return the vehicle attached to a config entry."""
        row = self._query_one(
            "SELECT * FROM vehicles WHERE config_entry_id = ?", (config_entry_id,)
        )
        return Vehicle.from_row(row) if row else None

    def list_vehicles(self) -> list[Vehicle]:
        """Return every vehicle, oldest first."""
        return [
            Vehicle.from_row(row)
            for row in self._query("SELECT * FROM vehicles ORDER BY id")
        ]

    def update_vehicle(self, vehicle_id: int, updates: dict[str, Any]) -> None:
        """Update vehicle fields. Unknown keys are ignored."""
        allowed = (
            "name",
            "vin",
            "model",
            "year",
            "current_mileage",
            "purchase_date",
            "notes",
        )
        assignments, values = self._apply_updates("vehicles", allowed, updates)
        self._execute(
            f"UPDATE vehicles SET {assignments}, updated_at = ? WHERE id = ?",
            [*values, _now(), vehicle_id],
        )

    def delete_vehicle(self, vehicle_id: int) -> None:
        """Delete a vehicle and everything that belongs to it."""
        self._execute("DELETE FROM vehicles WHERE id = ?", (vehicle_id,))

    def set_current_mileage(self, vehicle_id: int, mileage: float) -> None:
        """Persist the latest known mileage.

        The value only ever moves forward, so a Tesla entity that briefly
        reports ``unknown`` or resets cannot wipe the cached odometer reading.
        """
        vehicle = self.get_vehicle(vehicle_id)
        if vehicle is None:
            raise RepositoryError(f"Unknown vehicle {vehicle_id}")
        if mileage <= (vehicle.current_mileage or 0):
            return
        self.update_vehicle(vehicle_id, {"current_mileage": float(mileage)})

    def force_set_mileage(self, vehicle_id: int, mileage: float) -> None:
        """Set mileage unconditionally, for manual corrections."""
        self.update_vehicle(vehicle_id, {"current_mileage": float(mileage)})

    # ------------------------------------------------------------------
    # Categories
    # ------------------------------------------------------------------
    def seed_default_categories(self, vehicle_id: int) -> None:
        """Insert the built-in categories for a new vehicle."""
        now = _now()
        with self._lock:
            self.conn.executemany(
                """
                INSERT OR IGNORE INTO categories (vehicle_id, name, is_default, created_at)
                VALUES (?, ?, 1, ?)
                """,
                [(vehicle_id, name, now) for name in DEFAULT_CATEGORIES],
            )
            self.conn.commit()

    def list_categories(self, vehicle_id: int) -> list[Category]:
        """Return the categories available to a vehicle, defaults first."""
        rows = self._query(
            """
            SELECT * FROM categories
            WHERE vehicle_id = ? OR vehicle_id IS NULL
            ORDER BY is_default DESC, name COLLATE NOCASE
            """,
            (vehicle_id,),
        )
        return [Category.from_row(row) for row in rows]

    def add_category(self, vehicle_id: int, name: str) -> Category:
        """Create a custom category. Existing names are returned unchanged."""
        name = name.strip()
        if not name:
            raise RepositoryError("Category name cannot be empty")
        self._execute(
            """
            INSERT OR IGNORE INTO categories (vehicle_id, name, is_default, created_at)
            VALUES (?, ?, 0, ?)
            """,
            (vehicle_id, name, _now()),
        )
        row = self._query_one(
            "SELECT * FROM categories WHERE vehicle_id = ? AND name = ?",
            (vehicle_id, name),
        )
        return Category.from_row(row)  # type: ignore[arg-type]

    def delete_category(self, category_id: int) -> None:
        """Delete a custom category. Default categories are protected."""
        self._execute(
            "DELETE FROM categories WHERE id = ? AND is_default = 0", (category_id,)
        )

    # ------------------------------------------------------------------
    # Service records
    # ------------------------------------------------------------------
    def add_service_record(
        self,
        record: ServiceRecord,
        items: list[MaintenanceItem] | None = None,
    ) -> int:
        """Insert a service record plus any maintenance items it covers."""
        if not record.service_date:
            record.service_date = _today()
        if not record.total_cost:
            record.total_cost = round(
                float(record.labor_cost or 0) + float(record.parts_cost or 0), 2
            )
        now = _now()
        cursor = self._execute(
            """
            INSERT INTO service_records (
                vehicle_id, service_date, mileage, title, description,
                service_provider, location, labor_cost, parts_cost, total_cost,
                notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.vehicle_id,
                record.service_date,
                record.mileage,
                record.title,
                record.description,
                record.service_provider,
                record.location,
                float(record.labor_cost or 0),
                float(record.parts_cost or 0),
                float(record.total_cost or 0),
                record.notes,
                now,
                now,
            ),
        )
        record_id = int(cursor.lastrowid or 0)

        for item in items or []:
            item.service_record_id = record_id
            item.vehicle_id = record.vehicle_id
            if item.mileage is None:
                item.mileage = record.mileage
            if not item.date_completed:
                item.date_completed = record.service_date
            self.add_maintenance_item(item)

        # Recording work also advances any matching schedule. Matching checks
        # both the item names and the record's own title, since a record can
        # be logged with a free-text title and no items attached.
        matched_names = {item.name.lower() for item in items or []}
        for item in items or []:
            self.mark_schedule_serviced(
                record.vehicle_id,
                item.name,
                service_date=record.service_date,
                mileage=record.mileage,
            )
        if record.title and record.title.lower() not in matched_names:
            self.mark_schedule_serviced(
                record.vehicle_id,
                record.title,
                service_date=record.service_date,
                mileage=record.mileage,
            )

        if record.mileage:
            self.set_current_mileage(record.vehicle_id, float(record.mileage))
            )

        if record.mileage:
            self.set_current_mileage(record.vehicle_id, float(record.mileage))
        return record_id

    def get_service_record(self, record_id: int) -> ServiceRecord | None:
        """Return one service record with its items and attachments."""
        row = self._query_one("SELECT * FROM service_records WHERE id = ?", (record_id,))
        if row is None:
            return None
        record = ServiceRecord.from_row(row)
        record.items = self.list_maintenance_items(service_record_id=record_id)
        record.attachments = self.list_attachments(record_id)
        return record

    def update_service_record(self, record_id: int, updates: dict[str, Any]) -> None:
        """Update fields on an existing service record."""
        allowed = (
            "service_date",
            "mileage",
            "title",
            "description",
            "service_provider",
            "location",
            "labor_cost",
            "parts_cost",
            "total_cost",
            "notes",
        )
        assignments, values = self._apply_updates("service_records", allowed, updates)
        self._execute(
            f"UPDATE service_records SET {assignments}, updated_at = ? WHERE id = ?",
            [*values, _now(), record_id],
        )

    def delete_service_record(self, record_id: int) -> None:
        """Delete a service record and its items/attachment rows."""
        self._execute("DELETE FROM service_records WHERE id = ?", (record_id,))

    def list_service_records(
        self,
        vehicle_id: int | None = None,
        *,
        query: str | None = None,
        year: int | None = None,
        category: str | None = None,
        provider: str | None = None,
        item_name: str | None = None,
        min_cost: float | None = None,
        max_cost: float | None = None,
        sort: str = SORT_NEWEST,
        limit: int | None = None,
        include_children: bool = True,
    ) -> list[ServiceRecord]:
        """Search and filter service history.

        ``query`` performs a case-insensitive substring match across the title,
        description, provider, location, **notes**, and the names and notes of
        the maintenance items attached to the record.
        """
        sql = ["SELECT DISTINCT sr.* FROM service_records sr"]
        params: list[Any] = []
        needs_items = bool(query or category or item_name)
        if needs_items:
            sql.append("LEFT JOIN maintenance_items mi ON mi.service_record_id = sr.id")

        where: list[str] = []
        if vehicle_id is not None:
            where.append("sr.vehicle_id = ?")
            params.append(vehicle_id)
        if query:
            pattern = f"%{query.lower()}%"
            where.append(
                "("
                "LOWER(sr.title) LIKE ? OR LOWER(sr.description) LIKE ? OR "
                "LOWER(sr.notes) LIKE ? OR LOWER(sr.service_provider) LIKE ? OR "
                "LOWER(sr.location) LIKE ? OR LOWER(COALESCE(mi.name, '')) LIKE ? OR "
                "LOWER(COALESCE(mi.notes, '')) LIKE ?"
                ")"
            )
            params.extend([pattern] * 7)
        if year is not None:
            where.append("substr(sr.service_date, 1, 4) = ?")
            params.append(str(year))
        if category:
            where.append("mi.category = ?")
            params.append(category)
        if item_name:
            where.append("LOWER(mi.name) = ?")
            params.append(item_name.lower())
        if provider:
            where.append("LOWER(sr.service_provider) LIKE ?")
            params.append(f"%{provider.lower()}%")
        if min_cost is not None:
            where.append("sr.total_cost >= ?")
            params.append(min_cost)
        if max_cost is not None:
            where.append("sr.total_cost <= ?")
            params.append(max_cost)

        if where:
            sql.append("WHERE " + " AND ".join(where))
        order = _SORT_SQL.get(sort, _SORT_SQL[SORT_NEWEST])
        sql.append(f"ORDER BY {order.replace('service_date', 'sr.service_date')}")
        if limit:
            sql.append("LIMIT ?")
            params.append(int(limit))

        rows = self._query(" ".join(sql), params)
        records = [ServiceRecord.from_row(row) for row in rows]
        if include_children:
            for record in records:
                record.items = self.list_maintenance_items(service_record_id=record.id)
                record.attachments = self.list_attachments(record.id)
        return records

    # ------------------------------------------------------------------
    # Maintenance items
    # ------------------------------------------------------------------
    def add_maintenance_item(self, item: MaintenanceItem) -> int:
        """Insert a maintenance item, custom or default."""
        if not item.name.strip():
            raise RepositoryError("Maintenance item name cannot be empty")
        now = _now()
        cursor = self._execute(
            """
            INSERT INTO maintenance_items (
                service_record_id, vehicle_id, category, name, status, mileage,
                date_completed, cost, is_custom, notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.service_record_id,
                item.vehicle_id,
                item.category,
                item.name.strip(),
                item.status,
                item.mileage,
                item.date_completed,
                float(item.cost or 0),
                1 if item.is_custom else 0,
                item.notes,
                now,
                now,
            ),
        )
        return int(cursor.lastrowid or 0)

    def get_maintenance_item(self, item_id: int) -> MaintenanceItem | None:
        """Return one maintenance item."""
        row = self._query_one("SELECT * FROM maintenance_items WHERE id = ?", (item_id,))
        return MaintenanceItem.from_row(row) if row else None

    def update_maintenance_item(self, item_id: int, updates: dict[str, Any]) -> None:
        """Update a maintenance item, including custom ones."""
        allowed = (
            "service_record_id",
            "category",
            "name",
            "status",
            "mileage",
            "date_completed",
            "cost",
            "is_custom",
            "notes",
        )
        assignments, values = self._apply_updates("maintenance_items", allowed, updates)
        self._execute(
            f"UPDATE maintenance_items SET {assignments}, updated_at = ? WHERE id = ?",
            [*values, _now(), item_id],
        )

    def delete_maintenance_item(self, item_id: int) -> None:
        """Delete a maintenance item."""
        self._execute("DELETE FROM maintenance_items WHERE id = ?", (item_id,))

    def list_maintenance_items(
        self,
        vehicle_id: int | None = None,
        *,
        service_record_id: int | None = None,
        category: str | None = None,
        custom_only: bool = False,
    ) -> list[MaintenanceItem]:
        """List maintenance items with optional filters."""
        where: list[str] = []
        params: list[Any] = []
        if vehicle_id is not None:
            where.append("vehicle_id = ?")
            params.append(vehicle_id)
        if service_record_id is not None:
            where.append("service_record_id = ?")
            params.append(service_record_id)
        if category:
            where.append("category = ?")
            params.append(category)
        if custom_only:
            where.append("is_custom = 1")
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        rows = self._query(
            f"SELECT * FROM maintenance_items {clause} "
            "ORDER BY COALESCE(date_completed, created_at) DESC, id DESC",
            params,
        )
        return [MaintenanceItem.from_row(row) for row in rows]

    def list_item_names(self, vehicle_id: int) -> list[str]:
        """Return every distinct item name recorded for a vehicle."""
        rows = self._query(
            "SELECT DISTINCT name FROM maintenance_items WHERE vehicle_id = ? "
            "ORDER BY name COLLATE NOCASE",
            (vehicle_id,),
        )
        return [row["name"] for row in rows]

    # ------------------------------------------------------------------
    # Schedules
    # ------------------------------------------------------------------
    def seed_starter_schedules(self, vehicle_id: int, baseline_mileage: float = 0) -> None:
        """Create the optional starter schedules, marked as ``Default``.

        These are this application's defaults. They are never labelled as Tesla
        recommendations.
        """
        existing = {
            schedule.item_name.lower() for schedule in self.list_schedules(vehicle_id)
        }
        for item_name, category, miles, days in STARTER_SCHEDULES:
            if item_name.lower() in existing:
                continue
            self.add_schedule(
                MaintenanceSchedule(
                    vehicle_id=vehicle_id,
                    item_name=item_name,
                    category=category,
                    interval_miles=miles,
                    interval_days=days,
                    last_service_mileage=baseline_mileage if miles else None,
                    last_service_date=_today() if days else None,
                    source=SOURCE_DEFAULT,
                )
            )

    def add_schedule(self, schedule: MaintenanceSchedule) -> int:
        """Insert a schedule and compute its next due thresholds."""
        if not schedule.item_name.strip():
            raise RepositoryError("Schedule item name cannot be empty")
        if not schedule.interval_miles and not schedule.interval_days:
            raise RepositoryError(
                "A recurring schedule needs a mileage interval, a time interval, or both"
            )
        if schedule.interval_miles and schedule.last_service_mileage is None:
            vehicle = self.get_vehicle(schedule.vehicle_id)
            schedule.last_service_mileage = vehicle.current_mileage if vehicle else 0.0
        if schedule.interval_days and not schedule.last_service_date:
            schedule.last_service_date = _today()

        next_mileage, next_date = compute_next_due(schedule)
        schedule.next_due_mileage = next_mileage
        schedule.next_due_date = next_date
        now = _now()
        cursor = self._execute(
            """
            INSERT INTO maintenance_schedules (
                vehicle_id, item_name, category, interval_miles, interval_days,
                last_service_date, last_service_mileage, next_due_date,
                next_due_mileage, enabled, source, notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                schedule.vehicle_id,
                schedule.item_name.strip(),
                schedule.category,
                schedule.interval_miles,
                schedule.interval_days,
                schedule.last_service_date,
                schedule.last_service_mileage,
                schedule.next_due_date,
                schedule.next_due_mileage,
                1 if schedule.enabled else 0,
                schedule.source,
                schedule.notes,
                now,
                now,
            ),
        )
        return int(cursor.lastrowid or 0)

    def get_schedule(self, schedule_id: int) -> MaintenanceSchedule | None:
        """Return one schedule."""
        row = self._query_one(
            "SELECT * FROM maintenance_schedules WHERE id = ?", (schedule_id,)
        )
        return MaintenanceSchedule.from_row(row) if row else None

    def list_schedules(
        self, vehicle_id: int | None = None, *, enabled_only: bool = False
    ) -> list[MaintenanceSchedule]:
        """List schedules for a vehicle."""
        where: list[str] = []
        params: list[Any] = []
        if vehicle_id is not None:
            where.append("vehicle_id = ?")
            params.append(vehicle_id)
        if enabled_only:
            where.append("enabled = 1")
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        rows = self._query(
            f"SELECT * FROM maintenance_schedules {clause} ORDER BY item_name COLLATE NOCASE",
            params,
        )
        return [MaintenanceSchedule.from_row(row) for row in rows]

    def update_schedule(self, schedule_id: int, updates: dict[str, Any]) -> None:
        """Update a schedule and recompute its next due thresholds."""
        allowed = (
            "item_name",
            "category",
            "interval_miles",
            "interval_days",
            "last_service_date",
            "last_service_mileage",
            "next_due_date",
            "next_due_mileage",
            "enabled",
            "source",
            "notes",
        )
        assignments, values = self._apply_updates("maintenance_schedules", allowed, updates)
        self._execute(
            f"UPDATE maintenance_schedules SET {assignments}, updated_at = ? WHERE id = ?",
            [*values, _now(), schedule_id],
        )
        if not {"next_due_date", "next_due_mileage"} & set(updates):
            self._recompute_schedule(schedule_id)

    def _recompute_schedule(self, schedule_id: int) -> None:
        """Recalculate stored next-due values from the intervals."""
        schedule = self.get_schedule(schedule_id)
        if schedule is None:
            return
        next_mileage, next_date = compute_next_due(schedule)
        self._execute(
            "UPDATE maintenance_schedules SET next_due_mileage = ?, next_due_date = ?, "
            "updated_at = ? WHERE id = ?",
            (next_mileage, next_date, _now(), schedule_id),
        )

    def delete_schedule(self, schedule_id: int) -> None:
        """Delete a schedule."""
        self._execute("DELETE FROM maintenance_schedules WHERE id = ?", (schedule_id,))

    def mark_schedule_serviced(
        self,
        vehicle_id: int,
        item_name: str,
        *,
        service_date: str | None = None,
        mileage: float | None = None,
    ) -> bool:
        """Advance the schedule that matches ``item_name``, if one exists."""
        row = self._query_one(
            "SELECT * FROM maintenance_schedules WHERE vehicle_id = ? "
            "AND LOWER(item_name) = LOWER(?)",
            (vehicle_id, item_name),
        )
        if row is None:
            return False
        schedule = MaintenanceSchedule.from_row(row)
        return self.reset_schedule(
            schedule.id,  # type: ignore[arg-type]
            service_date=service_date,
            mileage=mileage,
        )

    def reset_schedule(
        self,
        schedule_id: int,
        *,
        service_date: str | None = None,
        mileage: float | None = None,
    ) -> bool:
        """Mark a schedule as just serviced and roll its next due forward."""
        schedule = self.get_schedule(schedule_id)
        if schedule is None:
            return False
        if mileage is None:
            vehicle = self.get_vehicle(schedule.vehicle_id)
            mileage = vehicle.current_mileage if vehicle else None
        schedule.last_service_date = service_date or _today()
        if mileage is not None:
            schedule.last_service_mileage = float(mileage)
        next_mileage, next_date = compute_next_due(schedule)
        self._execute(
            """
            UPDATE maintenance_schedules
            SET last_service_date = ?, last_service_mileage = ?,
                next_due_date = ?, next_due_mileage = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                schedule.last_service_date,
                schedule.last_service_mileage,
                next_date,
                next_mileage,
                _now(),
                schedule_id,
            ),
        )
        return True

    # ------------------------------------------------------------------
    # Tires
    # ------------------------------------------------------------------
    def add_tire_record(self, tire: TireRecord) -> int:
        """Insert a tire record."""
        now = _now()
        cursor = self._execute(
            """
            INSERT INTO tire_records (
                vehicle_id, position, brand, model, size, installation_date,
                installation_mileage, current_tread_depth, original_tread_depth,
                dot_date, purchase_cost, replacement_cost, active, notes,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tire.vehicle_id,
                tire.position,
                tire.brand,
                tire.model,
                tire.size,
                tire.installation_date,
                tire.installation_mileage,
                tire.current_tread_depth,
                tire.original_tread_depth,
                tire.dot_date,
                float(tire.purchase_cost or 0),
                float(tire.replacement_cost or 0),
                1 if tire.active else 0,
                tire.notes,
                now,
                now,
            ),
        )
        return int(cursor.lastrowid or 0)

    def list_tire_records(
        self, vehicle_id: int, *, active_only: bool = False
    ) -> list[TireRecord]:
        """List tires for a vehicle."""
        clause = "AND active = 1" if active_only else ""
        rows = self._query(
            f"SELECT * FROM tire_records WHERE vehicle_id = ? {clause} "
            "ORDER BY position, installation_date DESC",
            (vehicle_id,),
        )
        return [TireRecord.from_row(row) for row in rows]

    def update_tire_record(self, tire_id: int, updates: dict[str, Any]) -> None:
        """Update a tire record."""
        allowed = (
            "position",
            "brand",
            "model",
            "size",
            "installation_date",
            "installation_mileage",
            "current_tread_depth",
            "original_tread_depth",
            "dot_date",
            "purchase_cost",
            "replacement_cost",
            "active",
            "notes",
        )
        assignments, values = self._apply_updates("tire_records", allowed, updates)
        self._execute(
            f"UPDATE tire_records SET {assignments}, updated_at = ? WHERE id = ?",
            [*values, _now(), tire_id],
        )

    def delete_tire_record(self, tire_id: int) -> None:
        """Delete a tire record."""
        self._execute("DELETE FROM tire_records WHERE id = ?", (tire_id,))

    def add_tire_rotation(self, rotation: TireRotation) -> int:
        """Record a tire rotation event."""
        cursor = self._execute(
            """
            INSERT INTO tire_rotations (vehicle_id, rotation_date, mileage, pattern, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                rotation.vehicle_id,
                rotation.rotation_date or _today(),
                rotation.mileage,
                rotation.pattern,
                rotation.notes,
                _now(),
            ),
        )
        return int(cursor.lastrowid or 0)

    def list_tire_rotations(self, vehicle_id: int) -> list[TireRotation]:
        """List tire rotations, most recent first."""
        rows = self._query(
            "SELECT * FROM tire_rotations WHERE vehicle_id = ? "
            "ORDER BY rotation_date DESC, id DESC",
            (vehicle_id,),
        )
        return [TireRotation.from_row(row) for row in rows]

    # ------------------------------------------------------------------
    # Brakes
    # ------------------------------------------------------------------
    def add_brake_record(self, brake: BrakeRecord) -> int:
        """Insert a brake inspection record."""
        now = _now()
        cursor = self._execute(
            """
            INSERT INTO brake_records (
                vehicle_id, axle, condition, pad_thickness, rotor_condition,
                inspection_date, inspection_mileage, notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                brake.vehicle_id,
                brake.axle,
                brake.condition,
                brake.pad_thickness,
                brake.rotor_condition,
                brake.inspection_date or _today(),
                brake.inspection_mileage,
                brake.notes,
                now,
                now,
            ),
        )
        return int(cursor.lastrowid or 0)

    def list_brake_records(self, vehicle_id: int) -> list[BrakeRecord]:
        """List brake inspections, most recent first."""
        rows = self._query(
            "SELECT * FROM brake_records WHERE vehicle_id = ? "
            "ORDER BY inspection_date DESC, id DESC",
            (vehicle_id,),
        )
        return [BrakeRecord.from_row(row) for row in rows]

    def latest_brake_records(self, vehicle_id: int) -> dict[str, BrakeRecord]:
        """Return the most recent inspection per axle."""
        latest: dict[str, BrakeRecord] = {}
        for record in self.list_brake_records(vehicle_id):
            latest.setdefault(record.axle, record)
        return latest

    def update_brake_record(self, brake_id: int, updates: dict[str, Any]) -> None:
        """Update a brake record."""
        allowed = (
            "axle",
            "condition",
            "pad_thickness",
            "rotor_condition",
            "inspection_date",
            "inspection_mileage",
            "notes",
        )
        assignments, values = self._apply_updates("brake_records", allowed, updates)
        self._execute(
            f"UPDATE brake_records SET {assignments}, updated_at = ? WHERE id = ?",
            [*values, _now(), brake_id],
        )

    def delete_brake_record(self, brake_id: int) -> None:
        """Delete a brake record."""
        self._execute("DELETE FROM brake_records WHERE id = ?", (brake_id,))

    # ------------------------------------------------------------------
    # Attachments
    # ------------------------------------------------------------------
    def add_attachment(self, attachment: Attachment) -> int:
        """Insert an attachment row. The file itself is written elsewhere."""
        cursor = self._execute(
            """
            INSERT INTO attachments (
                service_record_id, vehicle_id, filename, mime_type, path,
                size_bytes, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                attachment.service_record_id,
                attachment.vehicle_id,
                attachment.filename,
                attachment.mime_type,
                attachment.path,
                int(attachment.size_bytes or 0),
                _now(),
            ),
        )
        return int(cursor.lastrowid or 0)

    def list_attachments(
        self, service_record_id: int | None = None, vehicle_id: int | None = None
    ) -> list[Attachment]:
        """List attachments for a record or a whole vehicle."""
        where: list[str] = []
        params: list[Any] = []
        if service_record_id is not None:
            where.append("service_record_id = ?")
            params.append(service_record_id)
        if vehicle_id is not None:
            where.append("vehicle_id = ?")
            params.append(vehicle_id)
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        rows = self._query(
            f"SELECT * FROM attachments {clause} ORDER BY id", params
        )
        return [Attachment.from_row(row) for row in rows]

    def get_attachment(self, attachment_id: int) -> Attachment | None:
        """Return one attachment row."""
        row = self._query_one("SELECT * FROM attachments WHERE id = ?", (attachment_id,))
        return Attachment.from_row(row) if row else None

    def delete_attachment(self, attachment_id: int) -> None:
        """Delete an attachment row."""
        self._execute("DELETE FROM attachments WHERE id = ?", (attachment_id,))

    # ------------------------------------------------------------------
    # Analytics
    # ------------------------------------------------------------------
    def total_cost(self, vehicle_id: int, year: int | None = None) -> float:
        """Return total spend, optionally limited to one calendar year."""
        sql = "SELECT COALESCE(SUM(total_cost), 0) AS total FROM service_records WHERE vehicle_id = ?"
        params: list[Any] = [vehicle_id]
        if year is not None:
            sql += " AND substr(service_date, 1, 4) = ?"
            params.append(str(year))
        row = self._query_one(sql, params)
        return round(float(row["total"]) if row else 0.0, 2)

    def cost_by_year(self, vehicle_id: int) -> dict[str, float]:
        """Return spend grouped by calendar year."""
        rows = self._query(
            "SELECT substr(service_date, 1, 4) AS year, SUM(total_cost) AS total "
            "FROM service_records WHERE vehicle_id = ? GROUP BY year ORDER BY year",
            (vehicle_id,),
        )
        return {row["year"]: round(float(row["total"] or 0), 2) for row in rows}

    def cost_by_month(self, vehicle_id: int, months: int = 12) -> dict[str, float]:
        """Return spend grouped by month, most recent ``months`` buckets."""
        rows = self._query(
            "SELECT substr(service_date, 1, 7) AS month, SUM(total_cost) AS total "
            "FROM service_records WHERE vehicle_id = ? GROUP BY month ORDER BY month DESC "
            "LIMIT ?",
            (vehicle_id, months),
        )
        return {
            row["month"]: round(float(row["total"] or 0), 2) for row in reversed(rows)
        }

    def cost_by_category(self, vehicle_id: int) -> dict[str, float]:
        """Return spend grouped by maintenance category.

        Item level costs are used where present; otherwise the record total is
        split evenly across the items it covers.
        """
        rows = self._query(
            """
            SELECT mi.category AS category,
                   SUM(
                       CASE WHEN mi.cost > 0 THEN mi.cost
                            ELSE COALESCE(sr.total_cost, 0) / (
                                SELECT COUNT(*) FROM maintenance_items x
                                WHERE x.service_record_id = mi.service_record_id
                            )
                       END
                   ) AS total
            FROM maintenance_items mi
            LEFT JOIN service_records sr ON sr.id = mi.service_record_id
            WHERE mi.vehicle_id = ?
            GROUP BY mi.category
            ORDER BY total DESC
            """,
            (vehicle_id,),
        )
        return {
            row["category"]: round(float(row["total"] or 0), 2)
            for row in rows
            if row["category"]
        }

    def cost_by_provider(self, vehicle_id: int) -> dict[str, float]:
        """Return spend grouped by service provider."""
        rows = self._query(
            "SELECT service_provider AS provider, SUM(total_cost) AS total "
            "FROM service_records WHERE vehicle_id = ? AND service_provider != '' "
            "GROUP BY provider ORDER BY total DESC",
            (vehicle_id,),
        )
        return {row["provider"]: round(float(row["total"] or 0), 2) for row in rows}

    def service_count(self, vehicle_id: int) -> int:
        """Return the number of service records."""
        row = self._query_one(
            "SELECT COUNT(*) AS count FROM service_records WHERE vehicle_id = ?",
            (vehicle_id,),
        )
        return int(row["count"]) if row else 0

    def last_service(self, vehicle_id: int) -> ServiceRecord | None:
        """Return the most recent service record."""
        records = self.list_service_records(
            vehicle_id, sort=SORT_NEWEST, limit=1, include_children=False
        )
        return records[0] if records else None

    def first_service_date(self, vehicle_id: int) -> str | None:
        """Return the earliest service date on record."""
        row = self._query_one(
            "SELECT MIN(service_date) AS first FROM service_records WHERE vehicle_id = ?",
            (vehicle_id,),
        )
        return row["first"] if row and row["first"] else None

    def analytics(self, vehicle_id: int) -> dict[str, Any]:
        """Return the full analytics bundle for a vehicle.

        Values that cannot be derived from real data are returned as ``None``
        so the UI can say "Not enough data yet" instead of showing a made up
        number.
        """
        vehicle = self.get_vehicle(vehicle_id)
        current_mileage = vehicle.current_mileage if vehicle else 0.0
        count = self.service_count(vehicle_id)
        lifetime = self.total_cost(vehicle_id)
        this_year = date.today().year
        by_year = self.cost_by_year(vehicle_id)

        first = self.first_service_date(vehicle_id)
        average_annual: float | None = None
        if first and lifetime:
            first_date = date.fromisoformat(first[:10])
            days = max((date.today() - first_date).days, 1)
            average_annual = round(lifetime / (days / 365.25), 2)

        cost_per_mile: float | None = None
        if lifetime and current_mileage and current_mileage > 0:
            cost_per_mile = round(lifetime / float(current_mileage), 4)

        tires = self.list_tire_records(vehicle_id)
        tire_cost = round(sum(float(tire.purchase_cost or 0) for tire in tires), 2)
        brake_cost = round(
            sum(
                float(record.total_cost or 0)
                for record in self.list_service_records(vehicle_id, category="Brakes")
            ),
            2,
        )

        return {
            "total_cost": lifetime,
            "cost_this_year": self.total_cost(vehicle_id, this_year),
            "cost_last_year": self.total_cost(vehicle_id, this_year - 1),
            "average_annual_cost": average_annual,
            "average_service_cost": round(lifetime / count, 2) if count else None,
            "cost_per_mile": cost_per_mile,
            "cost_by_year": by_year,
            "cost_by_month": self.cost_by_month(vehicle_id),
            "cost_by_category": self.cost_by_category(vehicle_id),
            "cost_by_provider": self.cost_by_provider(vehicle_id),
            "service_count": count,
            "first_service_date": first,
            "tire_cost": tire_cost,
            "brake_cost": brake_cost,
            "current_mileage": current_mileage,
        }

    # ------------------------------------------------------------------
    # Export / import
    # ------------------------------------------------------------------
    def export_vehicle(self, vehicle_id: int) -> dict[str, Any]:
        """Return a complete, restorable snapshot of one vehicle."""
        vehicle = self.get_vehicle(vehicle_id)
        if vehicle is None:
            raise RepositoryError(f"Unknown vehicle {vehicle_id}")
        return {
            "vehicle": vehicle.to_dict(),
            "service_records": [
                record.to_dict()
                for record in self.list_service_records(vehicle_id, sort=SORT_OLDEST)
            ],
            "maintenance_items": [
                item.to_dict() for item in self.list_maintenance_items(vehicle_id)
            ],
            "schedules": [
                schedule.to_dict() for schedule in self.list_schedules(vehicle_id)
            ],
            "tires": [tire.to_dict() for tire in self.list_tire_records(vehicle_id)],
            "tire_rotations": [
                rotation.to_dict() for rotation in self.list_tire_rotations(vehicle_id)
            ],
            "brakes": [brake.to_dict() for brake in self.list_brake_records(vehicle_id)],
            "attachments": [
                attachment.to_dict()
                for attachment in self.list_attachments(vehicle_id=vehicle_id)
            ],
            "categories": [
                category.to_dict() for category in self.list_categories(vehicle_id)
            ],
            "analytics": self.analytics(vehicle_id),
        }

    def import_vehicle(
        self, payload: dict[str, Any], vehicle_id: int, *, skip_duplicates: bool = True
    ) -> dict[str, int]:
        """Restore an exported payload into an existing vehicle.

        Existing rows are never overwritten. A service record is treated as a
        duplicate when its date, mileage and total cost all match an existing
        row.
        """
        counts = {
            "service_records": 0,
            "maintenance_items": 0,
            "schedules": 0,
            "tires": 0,
            "brakes": 0,
            "categories": 0,
            "skipped": 0,
        }
        existing_keys = {
            (record.service_date, record.mileage, record.total_cost)
            for record in self.list_service_records(vehicle_id, include_children=False)
        }

        for raw in payload.get("service_records", []):
            record = ServiceRecord(
                vehicle_id=vehicle_id,
                service_date=str(raw.get("service_date") or ""),
                mileage=_as_float(raw.get("mileage")),
                title=str(raw.get("title") or ""),
                description=str(raw.get("description") or ""),
                service_provider=str(raw.get("service_provider") or ""),
                location=str(raw.get("location") or ""),
                labor_cost=_as_float(raw.get("labor_cost")) or 0.0,
                parts_cost=_as_float(raw.get("parts_cost")) or 0.0,
                total_cost=_as_float(raw.get("total_cost")) or 0.0,
                notes=str(raw.get("notes") or ""),
            )
            if not record.service_date:
                counts["skipped"] += 1
                continue
            key = (record.service_date, record.mileage, record.total_cost)
            if skip_duplicates and key in existing_keys:
                counts["skipped"] += 1
                continue
            items = [
                MaintenanceItem(
                    vehicle_id=vehicle_id,
                    category=str(item.get("category") or "Other"),
                    name=str(item.get("name") or ""),
                    status=str(item.get("status") or "COMPLETED"),
                    mileage=_as_float(item.get("mileage")),
                    date_completed=item.get("date_completed"),
                    cost=_as_float(item.get("cost")) or 0.0,
                    is_custom=bool(item.get("is_custom")),
                    notes=str(item.get("notes") or ""),
                )
                for item in raw.get("items", [])
                if str(item.get("name") or "").strip()
            ]
            self.add_service_record(record, items)
            existing_keys.add(key)
            counts["service_records"] += 1
            counts["maintenance_items"] += len(items)

        for raw in payload.get("categories", []):
            name = str(raw.get("name") or "").strip()
            if name and not raw.get("is_default"):
                self.add_category(vehicle_id, name)
                counts["categories"] += 1

        existing_schedules = {
            schedule.item_name.lower() for schedule in self.list_schedules(vehicle_id)
        }
        for raw in payload.get("schedules", []):
            name = str(raw.get("item_name") or "").strip()
            if not name or (skip_duplicates and name.lower() in existing_schedules):
                counts["skipped"] += 1
                continue
            try:
                self.add_schedule(
                    MaintenanceSchedule(
                        vehicle_id=vehicle_id,
                        item_name=name,
                        category=str(raw.get("category") or "Other"),
                        interval_miles=_as_int(raw.get("interval_miles")),
                        interval_days=_as_int(raw.get("interval_days")),
                        last_service_date=raw.get("last_service_date"),
                        last_service_mileage=_as_float(raw.get("last_service_mileage")),
                        enabled=bool(raw.get("enabled", True)),
                        source=str(raw.get("source") or "User Defined"),
                        notes=str(raw.get("notes") or ""),
                    )
                )
            except RepositoryError:
                counts["skipped"] += 1
                continue
            existing_schedules.add(name.lower())
            counts["schedules"] += 1

        for raw in payload.get("tires", []):
            self.add_tire_record(
                TireRecord(
                    vehicle_id=vehicle_id,
                    position=str(raw.get("position") or ""),
                    brand=str(raw.get("brand") or ""),
                    model=str(raw.get("model") or ""),
                    size=str(raw.get("size") or ""),
                    installation_date=raw.get("installation_date"),
                    installation_mileage=_as_float(raw.get("installation_mileage")),
                    current_tread_depth=_as_float(raw.get("current_tread_depth")),
                    original_tread_depth=_as_float(raw.get("original_tread_depth")),
                    dot_date=raw.get("dot_date"),
                    purchase_cost=_as_float(raw.get("purchase_cost")) or 0.0,
                    replacement_cost=_as_float(raw.get("replacement_cost")) or 0.0,
                    active=bool(raw.get("active", True)),
                    notes=str(raw.get("notes") or ""),
                )
            )
            counts["tires"] += 1

        for raw in payload.get("brakes", []):
            self.add_brake_record(
                BrakeRecord(
                    vehicle_id=vehicle_id,
                    axle=str(raw.get("axle") or "Front"),
                    condition=str(raw.get("condition") or "Good"),
                    pad_thickness=_as_float(raw.get("pad_thickness")),
                    rotor_condition=str(raw.get("rotor_condition") or ""),
                    inspection_date=raw.get("inspection_date"),
                    inspection_mileage=_as_float(raw.get("inspection_mileage")),
                    notes=str(raw.get("notes") or ""),
                )
            )
            counts["brakes"] += 1

        # Attachment metadata is restored only when the file is still present.
        for raw in payload.get("attachments", []):
            path = str(raw.get("path") or "")
            if path and Path(path).is_file():
                self.add_attachment(
                    Attachment(
                        vehicle_id=vehicle_id,
                        filename=str(raw.get("filename") or Path(path).name),
                        mime_type=str(raw.get("mime_type") or ""),
                        path=path,
                        size_bytes=_as_int(raw.get("size_bytes")) or 0,
                    )
                )

        vehicle_payload = payload.get("vehicle") or {}
        if vehicle_payload.get("notes"):
            current = self.get_vehicle(vehicle_id)
            if current is not None and not current.notes:
                self.update_vehicle(vehicle_id, {"notes": vehicle_payload["notes"]})
        return counts

    def copy_file(self, source: str | Path, destination: str | Path) -> None:
        """Copy a file, creating parent directories as needed."""
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def _as_float(value: Any) -> float | None:
    """Best-effort float conversion that never raises."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    """Best-effort int conversion that never raises."""
    result = _as_float(value)
    return int(result) if result is not None else None
