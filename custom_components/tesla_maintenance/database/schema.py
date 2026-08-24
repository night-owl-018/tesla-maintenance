"""SQLite schema definition and migrations.

The schema is versioned with ``PRAGMA user_version``. Migrations are applied in
order and are always additive - user data is never dropped.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS vehicles (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    config_entry_id   TEXT UNIQUE,
    name              TEXT NOT NULL,
    vin               TEXT,
    model             TEXT,
    year              INTEGER,
    current_mileage   REAL NOT NULL DEFAULT 0,
    purchase_date     TEXT,
    notes             TEXT NOT NULL DEFAULT '',
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS service_records (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_id        INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    service_date      TEXT NOT NULL,
    mileage           REAL,
    title             TEXT NOT NULL DEFAULT '',
    description       TEXT NOT NULL DEFAULT '',
    service_provider  TEXT NOT NULL DEFAULT '',
    location          TEXT NOT NULL DEFAULT '',
    labor_cost        REAL NOT NULL DEFAULT 0,
    parts_cost        REAL NOT NULL DEFAULT 0,
    total_cost        REAL NOT NULL DEFAULT 0,
    notes             TEXT NOT NULL DEFAULT '',
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_service_vehicle_date
    ON service_records(vehicle_id, service_date DESC);

CREATE TABLE IF NOT EXISTS maintenance_items (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    service_record_id INTEGER REFERENCES service_records(id) ON DELETE CASCADE,
    vehicle_id        INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    category          TEXT NOT NULL DEFAULT 'Other',
    name              TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'COMPLETED',
    mileage           REAL,
    date_completed    TEXT,
    cost              REAL NOT NULL DEFAULT 0,
    is_custom         INTEGER NOT NULL DEFAULT 0,
    notes             TEXT NOT NULL DEFAULT '',
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_items_vehicle ON maintenance_items(vehicle_id);
CREATE INDEX IF NOT EXISTS idx_items_record ON maintenance_items(service_record_id);

CREATE TABLE IF NOT EXISTS maintenance_schedules (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_id            INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    item_name             TEXT NOT NULL,
    category              TEXT NOT NULL DEFAULT 'Other',
    interval_miles        INTEGER,
    interval_days         INTEGER,
    last_service_date     TEXT,
    last_service_mileage  REAL,
    next_due_date         TEXT,
    next_due_mileage      REAL,
    enabled               INTEGER NOT NULL DEFAULT 1,
    source                TEXT NOT NULL DEFAULT 'User Defined',
    notes                 TEXT NOT NULL DEFAULT '',
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_schedules_vehicle ON maintenance_schedules(vehicle_id);

CREATE TABLE IF NOT EXISTS tire_records (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_id            INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    position              TEXT NOT NULL,
    brand                 TEXT NOT NULL DEFAULT '',
    model                 TEXT NOT NULL DEFAULT '',
    size                  TEXT NOT NULL DEFAULT '',
    installation_date     TEXT,
    installation_mileage  REAL,
    current_tread_depth   REAL,
    original_tread_depth  REAL,
    dot_date              TEXT,
    purchase_cost         REAL NOT NULL DEFAULT 0,
    replacement_cost      REAL NOT NULL DEFAULT 0,
    active                INTEGER NOT NULL DEFAULT 1,
    notes                 TEXT NOT NULL DEFAULT '',
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tires_vehicle ON tire_records(vehicle_id);

CREATE TABLE IF NOT EXISTS tire_rotations (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_id     INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    rotation_date  TEXT NOT NULL,
    mileage        REAL,
    pattern        TEXT NOT NULL DEFAULT '',
    notes          TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rotations_vehicle ON tire_rotations(vehicle_id);

CREATE TABLE IF NOT EXISTS brake_records (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_id          INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    axle                TEXT NOT NULL,
    condition           TEXT NOT NULL DEFAULT 'Good',
    pad_thickness       REAL,
    rotor_condition     TEXT NOT NULL DEFAULT '',
    inspection_date     TEXT,
    inspection_mileage  REAL,
    notes               TEXT NOT NULL DEFAULT '',
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_brakes_vehicle ON brake_records(vehicle_id);

CREATE TABLE IF NOT EXISTS attachments (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    service_record_id  INTEGER REFERENCES service_records(id) ON DELETE CASCADE,
    vehicle_id         INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    filename           TEXT NOT NULL,
    mime_type          TEXT NOT NULL DEFAULT '',
    path               TEXT NOT NULL,
    size_bytes         INTEGER NOT NULL DEFAULT 0,
    created_at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_attachments_record ON attachments(service_record_id);

CREATE TABLE IF NOT EXISTS categories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_id  INTEGER REFERENCES vehicles(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    is_default  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    UNIQUE(vehicle_id, name)
);
"""

#: version -> migration callable. Version 1 is the base schema, so there is
#: nothing to migrate yet. Future versions append here.
MIGRATIONS: dict[int, Callable[[sqlite3.Connection], None]] = {}


def apply_schema(conn: sqlite3.Connection) -> None:
    """Create the base schema and run any pending migrations."""
    conn.executescript(SCHEMA_SQL)
    current = conn.execute("PRAGMA user_version").fetchone()[0]

    if current == 0:
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        conn.commit()
        return

    for version in sorted(MIGRATIONS):
        if version > current:
            MIGRATIONS[version](conn)
            conn.execute(f"PRAGMA user_version = {version}")
    conn.commit()
