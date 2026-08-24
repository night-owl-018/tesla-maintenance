# Notes

Notes are a first-class feature, not an afterthought. Every meaningful record
carries one.

## Where you can write notes

| Record | Field |
|---|---|
| Service record | Large multiline `notes` |
| Vehicle | General `notes` |
| Maintenance item | Optional `notes` |
| Maintenance schedule | Optional `notes` |
| Tire record | `notes` |
| Brake record | `notes` |

Example:

```yaml
action: tesla_maintenance.add_service_record
data:
  service_date: "2026-08-20"
  mileage: 42580
  service_provider: Tesla Service Center
  labor_cost: 65
  notes: >-
    Technician recommended replacing the rear tires within the next 5,000
    miles. Front tires still have good tread.
```

## Notes are searchable

Service history search matches note contents. Searching `alignment` finds a
record whose note reads "Technician recommended checking alignment."

```yaml
action: tesla_maintenance.search_service_records
data:
  query: alignment
```

The search covers the record's title, description, provider, location and
**notes**, plus the names and notes of every maintenance item attached to it.
Matching is case-insensitive substring matching.

Combine with filters:

```yaml
action: tesla_maintenance.search_service_records
data:
  query: tire
  year: 2026
  category: Tires
  sort: highest_cost
  limit: 25
```

Sort options: `newest`, `oldest`, `highest_cost`, `lowest_cost`,
`highest_mileage`, `lowest_mileage`.

## Notes are durable

Notes are stored in SQLite at `<config>/tesla_maintenance/maintenance.db` and
survive Home Assistant restarts, integration reloads, Home Assistant updates,
HACS updates, and Tesla integration or entity outages.

## Notes are editable

```yaml
action: tesla_maintenance.update_service_record
data:
  service_record_id: 12
  notes: Updated note text.
```

## Notes are exported and backed up

Both the JSON export (complete structure) and the CSV export (`notes` and
`item_notes` columns) include note text, and the database file itself is inside
the Home Assistant backup path.
