# Tesla Maintenance Tracker

A Home Assistant custom integration for tracking real vehicle maintenance:
service history, schedules, costs, notes, receipts, tires and brakes — stored
in a local SQLite database that survives restarts, updates and Tesla outages.

> **This integration does not connect to Tesla.** It has no Tesla API client and
> never asks for credentials, tokens or a Tesla login. It reads mileage and
> other telemetry from Tesla entities that your *existing* Tesla integration
> already publishes to Home Assistant — entities you pick yourself from a
> dropdown. You can also skip Tesla entirely and enter mileage by hand.

```
Existing Tesla Integration
        ↓
Home Assistant Tesla Entities
        ↓
Tesla Maintenance Tracker      ← this project
        ↓
Maintenance Database (SQLite)
        ↓
Dashboard / History / Analytics / Notifications
```

## Features

- Service history with a large, searchable **notes** field on every record
- **Custom maintenance items** and **custom categories** — you are never forced
  to pick "Other"
- Recurring schedules by mileage, by time, or both; whichever comes first wins
- Statuses: `OK`, `DUE_SOON`, `DUE`, `OVERDUE`, `COMPLETED`, `DISABLED`, with
  configurable warning thresholds (default 500 mi / 30 days)
- Tire tracking (brand, size, tread, DOT, cost, rotations) and brake tracking
  (condition, pad thickness, rotor condition, inspections)
- Cost analytics: lifetime, per year, per month, per category, per provider,
  average annual, average per service, cost per mile
- Attachments: receipts, photos and documents (JPG/PNG/WEBP/PDF), validated and
  stored on disk
- JSON and CSV export, plus validated JSON import/restore that never overwrites
  existing records
- Notifications, an upcoming-maintenance calendar, and automation blueprints
- Multiple vehicles — one config entry per vehicle, fully isolated data
- Mobile-first dashboard using built-in cards only (no custom card dependencies)

## Requirements

- Home Assistant **2025.1.0** or newer (developed and tested against 2025.1)
- Python 3.12+ (whatever your Home Assistant runs on)
- Optional: any Tesla integration that exposes an odometer entity

## Installation

### HACS (custom repository)

1. HACS → Integrations → three-dot menu → **Custom repositories**
2. Add your repository URL, category **Integration**
3. Install **Tesla Maintenance Tracker**, then restart Home Assistant
4. Settings → Devices & Services → **Add Integration** → *Tesla Maintenance
   Tracker*

### Manual

1. Copy `custom_components/tesla_maintenance/` into your `<config>/custom_components/`
2. Restart Home Assistant
3. Add the integration from Settings → Devices & Services

Full details, including the four-step setup wizard, are in
[docs/installation.md](docs/installation.md).

## Where your data lives

```
<config>/
└── tesla_maintenance/
    ├── maintenance.db      SQLite database (all records, notes, costs)
    ├── attachments/        receipts, photos, documents by service record
    ├── exports/            JSON and CSV exports
    └── backups/            database copies
```

Nothing is written to `.storage`, nothing is written inside the integration
source directory, and no user data is ever committed to Git. Because everything
lives under `<config>/`, standard Home Assistant backups include it. See
[docs/backups.md](docs/backups.md).

## Entities

One device per vehicle. Entity ids follow the vehicle name, so a vehicle called
"My Tesla" produces `sensor.my_tesla_current_mileage` and so on.

| Sensors | |
|---|---|
| `current_mileage` | `total_maintenance_cost` |
| `maintenance_cost_this_year` | `last_service_date` |
| `last_service_mileage` | `next_service_mileage` |
| `distance_until_service` | `days_until_service` |
| `maintenance_items_due` | `maintenance_items_overdue` |
| `total_service_records` | `average_annual_maintenance_cost` |
| `cost_per_mile` | `maintenance_health` |
| `tire_condition` | `brake_condition` |
| `battery_condition` | `tesla_telemetry` |

Binary sensors: `maintenance_due`, `maintenance_overdue`, `tire_service_due`,
`brake_service_due`, `tesla_telemetry_connected`.
Also: a `calendar` of upcoming maintenance, a `number` for manual mileage, and
buttons for export/backup/refresh.

## Actions (services)

`add_service_record`, `update_service_record`, `delete_service_record`,
`add_maintenance_item`, `complete_maintenance`, `add_schedule`,
`update_schedule`, `delete_schedule`, `reset_maintenance_schedule`,
`add_attachment`, `add_category`, `add_tire_record`, `add_brake_record`,
`set_mileage`, `search_service_records`, `export_data`, `import_data`,
`backup_database`.

All are documented with UI forms in Developer Tools → Actions.

## Dashboard

Import [`dashboards/tesla_maintenance.yaml`](dashboards/tesla_maintenance.yaml)
into a new dashboard and replace the `my_tesla` entity prefix with your own.
For a working "Add Service" form, install
[`dashboards/examples/add_service_form_package.yaml`](dashboards/examples/add_service_form_package.yaml).

## Repository hosting (GitHub or Gitea)

This is a plain Git repository. The integration itself has no dependency on
GitHub, Gitea, or any CI system.

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin <repository-url>
git push -u origin main
```

That `<repository-url>` can be GitHub, a hosted Gitea, or a self-hosted Gitea.
GitHub workflows live in `.github/workflows/`; a Gitea Actions workflow for lint
and tests lives in `.gitea/workflows/`. Hassfest and the HACS action are
GitHub-hosted actions and are deliberately not mirrored to Gitea.

Before publishing, update `documentation` and `issue_tracker` in
`custom_components/tesla_maintenance/manifest.json` to point at your repository.

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements_test.txt
pytest tests -q
ruff check custom_components tests
```

## Documentation

- [Installation](docs/installation.md)
- [Configuration](docs/configuration.md)
- [Tesla entity mapping](docs/entity-mapping.md)
- [Maintenance and schedules](docs/maintenance.md)
- [Custom maintenance](docs/custom-maintenance.md)
- [Notes](docs/notes.md)
- [Notifications](docs/notifications.md)
- [Backups, export and import](docs/backups.md)
- [Troubleshooting](docs/troubleshooting.md)

## A note on maintenance intervals

Any starter schedules this integration creates are labelled **Default** — they
are this application's own convenience values, not official Tesla requirements.
The **Tesla Recommendation** label exists only for intervals *you* explicitly
choose to mark that way after verifying them against Tesla's own documentation
for your vehicle.

## Licence

MIT — see [LICENSE](LICENSE). Not affiliated with, endorsed by, or sponsored by
Tesla, Inc. No Tesla logos or proprietary assets are used.
