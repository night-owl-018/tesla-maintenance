# Installation

## Requirements

- Home Assistant 2025.1.0 or newer
- Optionally, an existing Tesla integration that exposes an odometer entity.
  The Maintenance Tracker works without one — see Manual Mileage below.

## Install through HACS

1. Open HACS → **Integrations**.
2. Three-dot menu → **Custom repositories**.
3. Paste your repository URL and choose category **Integration**.
4. Find **Tesla Maintenance Tracker** and click **Download**.
5. Restart Home Assistant.

## Install manually

1. Copy the folder `custom_components/tesla_maintenance/` into
   `<config>/custom_components/tesla_maintenance/`.
2. Confirm `<config>/custom_components/tesla_maintenance/manifest.json` exists.
3. Restart Home Assistant.

## Add your vehicle

**Settings → Devices & Services → Add Integration → Tesla Maintenance Tracker.**

The wizard has four steps.

### 1. Vehicle Information

Name, model, year, VIN and purchase date. Only the name is required. The VIN is
optional and is never logged, never sent anywhere, and is redacted from
diagnostics.

### 2. TESLA VEHICLE INTEGRATION

This step connects the tracker to your **existing** Tesla entities. It does not
connect to Tesla. See [entity-mapping.md](entity-mapping.md).

Choose a mileage source:

- **Tesla Home Assistant entity** — pick your odometer entity from the dropdown.
- **Manual mileage** — enter the current reading; no Tesla entities needed.

All other entities (battery, range, charging, TPMS, location, climate) are
genuinely optional.

### 3. Maintenance Settings

Distance unit, currency, warning thresholds (default 500 miles / 30 days), and
whether to create starter schedules. Starter schedules are labelled **Default**
— they are this integration's convenience values, not Tesla requirements.

### 4. Notification Settings

Enable or disable notifications and choose a notify action such as
`notify.mobile_app_your_phone`. Leave it blank for persistent notifications.

## After setup

A device is created for the vehicle with all sensors, binary sensors, a
calendar, a manual mileage number, and export/backup buttons. Data directories
are created automatically at `<config>/tesla_maintenance/`.

Next: import the [dashboard](../dashboards/tesla_maintenance.yaml).

## Multiple vehicles

Repeat **Add Integration** for each vehicle. Each config entry gets its own
vehicle row, its own records, schedules, tires, brakes, costs and attachments.
They share one database file but are fully isolated by vehicle id.

## Uninstalling

Deleting the config entry removes the device and entities but **deliberately
leaves your maintenance data in place** at `<config>/tesla_maintenance/`. Delete
that folder yourself if you truly want the history gone — export it first if
there is any doubt.
