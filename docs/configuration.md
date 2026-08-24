# Configuration

Everything is configured through the UI. There are no YAML configuration keys.

## Options flow

**Settings → Devices & Services → Tesla Maintenance Tracker → Configure.**

The menu offers four sections:

| Section | What you can change |
|---|---|
| Vehicle information | Name, model, year, VIN, purchase date |
| Tesla entity mapping | Mileage source, odometer entity, all optional entities |
| Maintenance settings | Distance unit, currency, warning thresholds, starter schedules |
| Notification settings | Enable/disable, notify action, due and overdue alerts |

**Changing any of these never deletes maintenance data.** Telemetry
configuration lives in the config entry; your records live in SQLite. The
vehicle row is keyed to the config entry id, so reconfiguring reuses the same
row and keeps all history, notes, costs and attachments.

## Settings reference

### Distance unit

`mi` or `km`. This is a display unit applied to mileage sensors and intervals.
Changing it does not convert existing stored values — the number you recorded is
the number that stays recorded.

### Currency

Defaults to `USD`. Any currency code is accepted and is used as the unit on cost
sensors.

### Warning thresholds

- **Mileage threshold** (default `500`) — an item becomes `DUE_SOON` this far
  before its next due mileage.
- **Day threshold** (default `30`) — an item becomes `DUE_SOON` this many days
  before its next due date.

For schedules with both mileage and time intervals, whichever threshold triggers
first determines the status.

### Starter maintenance schedules

When enabled, and only when the vehicle has no schedules yet, a small set of
starter schedules is created and labelled **Default**. You can edit, disable or
delete any of them. They are not Tesla requirements.

## Update interval

The coordinator refreshes every 15 minutes, and also immediately whenever one of
your mapped Tesla entities changes state.
