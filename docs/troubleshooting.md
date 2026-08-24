# Troubleshooting

## Enable debug logging

```yaml
logger:
  default: warning
  logs:
    custom_components.tesla_maintenance: debug
```

Then check **Settings → System → Logs**.

## Mileage is unknown or not updating

1. Check `sensor.<vehicle>_tesla_telemetry`. If it reads **Unavailable**, the
   mapped odometer entity is missing, unavailable, or non-numeric.
2. Open the odometer entity in Developer Tools → States and confirm its state is
   a plain number. Values like `unknown` or `42,580 mi` are not usable.
3. Remap it under Configure → **Tesla entity mapping**.
4. As a fallback, switch to **Manual mileage**, or set a value with the
   `number.<vehicle>_manual_mileage` entity.

Remember: stored mileage only moves forward from telemetry. If your odometer
entity reports a *lower* value than what is stored, it is ignored on purpose.
Use `tesla_maintenance.set_mileage` to force a correction.

## Nothing shows as due

- Maintenance health reads `UNKNOWN` when no schedules exist. Add one with
  `tesla_maintenance.add_schedule`.
- A mileage-based schedule needs known mileage to evaluate.
- Check the schedule is enabled.

## The Tesla integration went down

Nothing is lost. History, notes, attachments, costs and schedules are all in
SQLite and unaffected. The telemetry sensor reports Unavailable, mileage holds
its last known value, and you can keep adding records by hand.

## An attachment was rejected

Only JPG, JPEG, PNG, WEBP and PDF are accepted, up to 20 MB, and the extension
must match the file's MIME type. Filenames are sanitised and any path that would
land outside the attachments folder is refused. Home Assistant must also be able
to read the source path — `/media/...` or `/config/...` are good choices, and
you may need to add the folder to `allowlist_external_dirs`.

## Entity ids do not match the docs

Entity ids are derived from the vehicle name. A vehicle named "My Tesla" gives
`sensor.my_tesla_current_mileage`. Update the dashboard's `my_tesla` prefix to
match, or rename entities in the UI.

## Services are missing after a reload

Actions are registered while at least one config entry is loaded and removed
when the last one unloads. If the entry failed to set up, check the logs for a
database error — the most common cause is `<config>/tesla_maintenance/` not
being writable.

## Running the checks locally

```bash
pip install -r requirements_test.txt
pytest tests -q
ruff check custom_components tests
```

Hassfest can be run against a checkout of Home Assistant core:

```bash
git clone --depth 1 --branch 2025.1.0 https://github.com/home-assistant/core.git
cd core
python -m script.hassfest --integration-path /path/to/custom_components/tesla_maintenance
```

## Reporting a problem

Include your Home Assistant version, the integration version, debug logs, and
the diagnostics download from the device page. Diagnostics automatically redact
the VIN and location mappings. Please do not paste your VIN or tokens.
