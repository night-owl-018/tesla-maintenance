# Custom maintenance

You are never forced to select "Other". Any work you can name can be recorded,
categorised, costed, noted, attached to and — if you want — repeated.

## Adding a custom item

```yaml
action: tesla_maintenance.add_maintenance_item
data:
  name: Frunk strut replacement
  category: Exterior
  date_completed: "2026-08-20"
  mileage: 42580
  cost: 90
  service_provider: Independent EV Shop
  notes: Both struts replaced, OEM parts.
  is_custom: true
```

If no `service_record_id` is given, a service record is created for the item so
it appears in history, search, costs and analytics automatically. To attach it
to an existing visit, pass `service_record_id`.

Run this from **Developer Tools → Actions**, which renders a full form from the
action definition, or use the ready-made mobile form in
`dashboards/examples/add_service_form_package.yaml`.

## Creating a category on the fly

The `category` field creates the category if it does not exist. There is no
separate step:

```yaml
action: tesla_maintenance.add_maintenance_item
data:
  name: Ceramic coating
  category: Ceramic Coating     # created automatically
  cost: 900
```

You can also create one directly:

```yaml
action: tesla_maintenance.add_category
data:
  name: Ceramic Coating
```

Custom categories are stored in the database, persist across restarts, reloads
and updates, and appear in every later form and filter. Default categories are
protected from deletion; your own can be deleted freely.

## Making it recurring

```yaml
action: tesla_maintenance.add_maintenance_item
data:
  name: Ceramic coating refresh
  category: Ceramic Coating
  cost: 900
  create_schedule: true
  interval_days: 730          # every 2 years
```

Use `interval_miles`, `interval_days`, or both. At least one is required when
`create_schedule` is true, otherwise the action fails with a clear error.

Schedules created this way are always labelled **User Defined** — never
presented as a Tesla recommendation.

## Things people actually track

Frunk strut replacement · windshield washer nozzle · door handle repair · charge
port repair · wheel alignment · suspension repair · paint correction · glass
replacement · interior repair · accessory installation · aftermarket
modification · detail service · ceramic coating · window tint · anything else
you name.

## Where custom items show up

Custom items are first-class records. They appear in service history, search
(including their notes), category and provider filters, cost calculations,
analytics, the vehicle's history, and both JSON and CSV exports — where they are
flagged with `custom = yes`.

## Editing and deleting

Update the parent service record with `update_service_record`, or delete it with
`delete_service_record` (which removes its items and attachment rows too).
Repository-level helpers exist for updating and deleting individual items and
are exercised by the test suite.
