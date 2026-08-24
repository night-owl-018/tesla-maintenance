# Notifications

## How they work

After each refresh, any schedule that has **changed** into a due or overdue
state produces a notification. A condition that persists is announced once, not
on every refresh cycle.

Messages use only real figures. If a schedule has no mileage data, the message
does not pretend it does.

```
Tesla Maintenance:
My Tesla: Tire rotation is due in about 350 mi.

Tesla Maintenance:
My Tesla: Cabin air filter is due in 12 days.

Tesla Maintenance:
My Tesla: Brake inspection is overdue by 1,250 mi.
```

## Configuring

**Configure → Notification settings:**

- **Enable notifications** — turn everything off with one switch
- **Notify service** — e.g. `notify.mobile_app_your_phone`; leave blank for
  persistent notifications
- **Notify when maintenance becomes due**
- **Notify when maintenance becomes overdue**

If the configured notify action fails for any reason, the message falls back to
a persistent notification and a warning is logged. A notification failure never
breaks a refresh.

## Automation blueprints

Three blueprints live in `blueprints/automations/`. Copy them to
`<config>/blueprints/automation/tesla_maintenance/` and reload automations, or
import them from the repository URL.

| Blueprint | What it does |
|---|---|
| `maintenance_due.yaml` | Notifies when the due binary sensor turns on, listing each item |
| `maintenance_overdue.yaml` | Notifies on overdue and repeats daily at your chosen time |
| `monthly_summary.yaml` | On the 1st of the month: total cost, cost this year, upcoming, overdue, most recent service |

## Building your own

Everything you need is in entity attributes:

```yaml
triggers:
  - trigger: state
    entity_id: binary_sensor.my_tesla_maintenance_overdue
    to: "on"
actions:
  - action: notify.mobile_app_your_phone
    data:
      message: >-
        {% for item in state_attr('binary_sensor.my_tesla_maintenance_overdue',
        'overdue') %}{{ item.item_name }} is overdue.
        {% endfor %}
```

Useful attributes: `due` and `overdue` on the binary sensors; `schedules` on
`sensor.<vehicle>_maintenance_health`; `items` on the due/overdue count sensors.
Each entry includes `item_name`, `category`, `status`, `source`,
`miles_remaining`, `days_remaining`, `next_due_mileage`, `next_due_date` and
`notes`.

The integration also fires a `tesla_maintenance_data_changed` event whenever
maintenance data is modified, which you can trigger automations on.
