# Tesla entity mapping

## What this is

The Maintenance Tracker reads telemetry from entities that **another**
integration already provides. It contains no Tesla API client, requests no
credentials, tokens or OAuth flow, and hardcodes no entity ids. You select your
own entities from Home Assistant entity pickers.

```
Existing Tesla Integration → Home Assistant entities → Maintenance Tracker
```

Telemetry is a convenience. Your maintenance database does not depend on it.

## Required: odometer

The only required mapping, and only when the mileage source is
**Tesla Home Assistant entity**. Any `sensor`, `number` or `input_number` whose
state is numeric will do — it does not matter which Tesla integration produced
it.

The selected odometer drives:

- Current mileage
- Service mileage defaults
- Miles since last service, miles until maintenance
- Due and overdue calculations
- Cost per mile
- Maintenance forecasting

### Outage behaviour

If the odometer becomes `unavailable`, `unknown`, or reports a non-numeric
value, the last known good mileage is retained. Stored mileage only ever moves
forward from telemetry, so a resetting or misbehaving entity cannot corrupt your
history. Nothing is deleted and no schedule is reset.

You can always correct mileage by hand with the `number.<vehicle>_manual_mileage`
entity or the `tesla_maintenance.set_mileage` action.

## Optional entities

All genuinely optional; the integration works with none of them configured.

| Mapping | Typical domain |
|---|---|
| Battery level | `sensor` |
| Battery range | `sensor` |
| Charging state | `sensor`, `binary_sensor`, `select` |
| Vehicle state | `sensor`, `binary_sensor`, `device_tracker` |
| Location | `device_tracker`, `zone`, `sensor` |
| Latitude / Longitude | `sensor` |
| Climate state | `climate`, `sensor`, `binary_sensor` |
| Tire pressure FL/FR/RL/RR | `sensor` |

### Seeing their status

The `sensor.<vehicle>_tesla_telemetry` entity has an `optional_entities`
attribute listing each mapping as **Connected**, **Unavailable** or
**Not configured**. The dashboard Settings view renders this as:

```
✓ Battery Level        Connected
✓ Battery Range        Connected
— Charging State       Not configured
— Tire Pressure        Not configured
```

## Manual mileage mode

Choose **Manual mileage** as the source and enter a reading. No Tesla entity is
required at any point, and every feature except live telemetry works normally.

## Changing mappings later

Configure → **Tesla entity mapping**. Change or clear any entity. Switching
between Tesla-entity and manual mode is also done here.

This never deletes service records, notes, costs, attachments, tires, brakes or
schedules — mapping lives in the config entry, records live in the database.

## Privacy

Location, latitude and longitude mappings are redacted from diagnostics, and
their values are never written to the log. The VIN is likewise redacted and is
never published to the device registry.
