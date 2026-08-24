# Maintenance and schedules

## Schedules

A schedule repeats an item by mileage, by time, or by both.

Create one with the `tesla_maintenance.add_schedule` action:

```yaml
action: tesla_maintenance.add_schedule
data:
  name: Tire Rotation
  category: Tires
  interval_miles: 6250
```

```yaml
action: tesla_maintenance.add_schedule
data:
  name: Cabin Air Filter
  category: Filters
  interval_days: 730      # every 2 years
```

Supplying both makes it "whichever comes first".

### Baselines

`last_service_mileage` defaults to the vehicle's current mileage and
`last_service_date` defaults to today. Override either to backdate a schedule:

```yaml
action: tesla_maintenance.add_schedule
data:
  name: Brake Fluid
  interval_days: 730
  last_service_date: "2025-06-01"
```

### Next due

- `next_due_mileage = last_service_mileage + interval_miles`
- `next_due_date = last_service_date + interval_days`

## Statuses

| Status | Meaning |
|---|---|
| `OK` | Beyond both warning thresholds |
| `DUE_SOON` | Within the mileage or day threshold |
| `DUE` | Exactly at the threshold |
| `OVERDUE` | Past it |
| `COMPLETED` | Recorded as done |
| `DISABLED` | Schedule turned off |

Defaults: 500 miles and 30 days, both configurable. When a schedule has both
kinds of interval, the more severe of the two statuses wins.

If mileage is unknown, the mileage side simply does not contribute — no status
is invented from missing data.

## Schedule sources

Every schedule carries a source, shown wherever it appears:

- **Default** — created by this integration as a convenience
- **User Defined** — created by you
- **Tesla Recommendation** — only if *you* explicitly choose this label

Nothing is ever automatically labelled a Tesla recommendation. Please only apply
that label to intervals you have verified in Tesla's own documentation for your
specific vehicle.

## Completing maintenance

```yaml
action: tesla_maintenance.complete_maintenance
data:
  schedule_id: 3
  mileage: 46000
  cost: 65
  notes: Rotated front to back.
```

This rolls the schedule forward from the new baseline and, by default, also logs
a service record. Set `create_service_record: false` to only advance the
schedule.

Adding a service record whose item name matches a schedule advances that
schedule automatically — matching is case-insensitive.

## Editing and disabling

```yaml
action: tesla_maintenance.update_schedule
data:
  schedule_id: 3
  interval_miles: 7500
  enabled: false
```

`reset_maintenance_schedule` resets the baseline without creating a record.
`delete_schedule` removes the schedule and leaves all service history intact.

## Default categories

Battery, Brakes, Tires, Suspension, Steering, Fluids, Filters, Electrical, HVAC,
Exterior, Interior, Drive Unit, Software, Safety, Inspection, Other. Add your
own at any time — see [custom-maintenance.md](custom-maintenance.md).

## Forecasting

`sensor.<vehicle>_next_service_mileage`, `distance_until_service` and
`days_until_service` describe the schedule that comes due first, with the item
name, category and **source** in their attributes. The calendar entity shows
every date-based schedule. Mileage-only schedules have no calendar date and are
omitted rather than guessed at.
