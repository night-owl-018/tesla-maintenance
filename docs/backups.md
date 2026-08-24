# Backups, export and import

## Where data lives

```
<config>/
└── tesla_maintenance/
    ├── maintenance.db      SQLite database
    ├── attachments/        receipts, photos, documents
    ├── exports/            JSON and CSV exports
    └── backups/            database copies
```

Because this sits under `<config>/`, a standard Home Assistant backup (full or
partial-with-config) includes the database, attachments and exports.

Data is **not** stored in `.storage`, **not** stored inside the integration
source folder, and **never** committed to Git — `.gitignore` blocks database and
data directory names defensively.

## Database backup

Press the **Back up database** button on the vehicle device, or:

```yaml
action: tesla_maintenance.backup_database
```

This uses SQLite's online backup API, so the copy is consistent even if a write
happens mid-backup. Files land in `backups/` as `maintenance_YYYYMMDD_HHMMSS.db`.

## JSON export

```yaml
action: tesla_maintenance.export_data
data:
  format: json
```

The JSON export preserves the complete structure: vehicle, service records with
their nested items and attachments, schedules, tires, tire rotations, brakes,
attachment metadata, categories, analytics — and every note. This is the format
the importer reads.

Add `all_vehicles: true` to export every configured vehicle in one file.

## CSV export

```yaml
action: tesla_maintenance.export_data
data:
  format: csv
```

One row per maintenance item (plus a row for records with no items, so nothing
is lost). Columns: `vehicle`, `date`, `mileage`, `service`, `category`,
`provider`, `location`, `labor_cost`, `parts_cost`, `total_cost`, `custom`,
`notes`, `item_notes`. Custom items are included and flagged.

## Import and restore

```yaml
action: tesla_maintenance.import_data
data:
  file_path: /config/tesla_maintenance/exports/tesla_maintenance_20260820_101500.json
```

Safety behaviour:

1. The whole file is validated before a single row is written. A malformed file,
   a missing `vehicles` section, or a newer schema version is rejected with a
   readable error and changes nothing.
2. Existing data is never overwritten. Import only adds.
3. Duplicates are skipped. A service record matching an existing record's date,
   mileage and total cost is treated as already present, so re-importing the
   same file is a no-op rather than a duplication.
4. Schedules matching an existing item name are skipped.
5. Attachment metadata is restored only when the referenced file is still on
   disk.

The response reports counts of what was imported and skipped.

## Restoring from scratch

1. Reinstall the integration and add the vehicle.
2. Restore `<config>/tesla_maintenance/` from your backup — or, if you only have
   a JSON export, run `import_data` against it.
3. Attachments are restored by copying the `attachments/` folder back before
   importing, so their metadata rows survive validation.

## Manual copies

The database is a plain SQLite file. You may copy `maintenance.db` while Home
Assistant is stopped, or use the backup action while it is running. If copying
by hand, take the `-wal` and `-shm` files too, or use the action instead.
