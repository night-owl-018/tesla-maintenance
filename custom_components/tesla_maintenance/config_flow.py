"""Config and options flow for the Tesla Maintenance Tracker.

The Tesla step maps *existing* Home Assistant entities. No Tesla credentials,
tokens or API endpoints are requested anywhere in this flow, and entity ids are
always chosen by the user through an entity selector - never hardcoded.
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_CREATE_DEFAULT_SCHEDULES,
    CONF_CURRENCY,
    CONF_DISTANCE_UNIT,
    CONF_MANUAL_MILEAGE,
    CONF_MILEAGE_SOURCE,
    CONF_NOTIFICATIONS_ENABLED,
    CONF_NOTIFY_ON_DUE,
    CONF_NOTIFY_ON_OVERDUE,
    CONF_NOTIFY_SERVICE,
    CONF_ODOMETER_ENTITY,
    CONF_PURCHASE_DATE,
    CONF_VEHICLE_MODEL,
    CONF_VEHICLE_NAME,
    CONF_VEHICLE_YEAR,
    CONF_VIN,
    CONF_WARN_DAYS,
    CONF_WARN_MILES,
    DEFAULT_CURRENCY,
    DEFAULT_WARN_DAYS,
    DEFAULT_WARN_MILES,
    DISTANCE_UNIT_MILES,
    DISTANCE_UNITS,
    DOMAIN,
    MILEAGE_SOURCE_ENTITY,
    MILEAGE_SOURCE_MANUAL,
    MILEAGE_SOURCES,
    OPTIONAL_ENTITY_KEYS,
)

_LOGGER = logging.getLogger(__name__)

#: Domains offered for each optional mapping. Kept broad on purpose - different
#: Tesla integrations expose these values through different platforms.
_OPTIONAL_ENTITY_DOMAINS: dict[str, list[str]] = {
    "battery_level_entity": ["sensor"],
    "battery_range_entity": ["sensor"],
    "charging_state_entity": ["sensor", "binary_sensor", "select"],
    "vehicle_state_entity": ["sensor", "binary_sensor", "device_tracker"],
    "location_entity": ["device_tracker", "zone", "sensor"],
    "latitude_entity": ["sensor"],
    "longitude_entity": ["sensor"],
    "climate_state_entity": ["climate", "sensor", "binary_sensor"],
    "tpms_front_left_entity": ["sensor"],
    "tpms_front_right_entity": ["sensor"],
    "tpms_rear_left_entity": ["sensor"],
    "tpms_rear_right_entity": ["sensor"],
}


def _vehicle_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    """Return the vehicle information schema."""
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_VEHICLE_NAME, default=defaults.get(CONF_VEHICLE_NAME, "My Tesla")
            ): selector.TextSelector(),
            vol.Optional(
                CONF_VEHICLE_MODEL, default=defaults.get(CONF_VEHICLE_MODEL, "")
            ): selector.TextSelector(),
            vol.Optional(
                CONF_VEHICLE_YEAR,
                description={"suggested_value": defaults.get(CONF_VEHICLE_YEAR)},
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1990, max=2100, step=1, mode=selector.NumberSelectorMode.BOX
                )
            ),
            # The VIN is optional and is never logged or exposed in diagnostics.
            vol.Optional(
                CONF_VIN, default=defaults.get(CONF_VIN, "")
            ): selector.TextSelector(),
            vol.Optional(
                CONF_PURCHASE_DATE,
                description={"suggested_value": defaults.get(CONF_PURCHASE_DATE)},
            ): selector.DateSelector(),
        }
    )


def _tesla_entity_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    """Return the Tesla entity mapping schema.

    Every field is an entity selector so the user picks their own entities from
    whichever Tesla integration they already run.
    """
    defaults = defaults or {}
    fields: dict[Any, Any] = {
        vol.Required(
            CONF_MILEAGE_SOURCE,
            default=defaults.get(CONF_MILEAGE_SOURCE, MILEAGE_SOURCE_ENTITY),
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=MILEAGE_SOURCES,
                translation_key="mileage_source",
                mode=selector.SelectSelectorMode.LIST,
            )
        ),
        vol.Optional(
            CONF_ODOMETER_ENTITY,
            description={"suggested_value": defaults.get(CONF_ODOMETER_ENTITY)},
        ): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=["sensor", "number", "input_number"])
        ),
        vol.Optional(
            CONF_MANUAL_MILEAGE,
            description={"suggested_value": defaults.get(CONF_MANUAL_MILEAGE)},
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0, max=2_000_000, step=1, mode=selector.NumberSelectorMode.BOX
            )
        ),
    }
    for key, _label in OPTIONAL_ENTITY_KEYS:
        fields[
            vol.Optional(key, description={"suggested_value": defaults.get(key)})
        ] = selector.EntitySelector(
            selector.EntitySelectorConfig(domain=_OPTIONAL_ENTITY_DOMAINS[key])
        )
    return vol.Schema(fields)


def _maintenance_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    """Return the maintenance settings schema."""
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_DISTANCE_UNIT,
                default=defaults.get(CONF_DISTANCE_UNIT, DISTANCE_UNIT_MILES),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=DISTANCE_UNITS, translation_key="distance_unit"
                )
            ),
            vol.Required(
                CONF_CURRENCY, default=defaults.get(CONF_CURRENCY, DEFAULT_CURRENCY)
            ): selector.TextSelector(),
            vol.Required(
                CONF_WARN_MILES, default=defaults.get(CONF_WARN_MILES, DEFAULT_WARN_MILES)
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=50000, step=50, mode=selector.NumberSelectorMode.BOX
                )
            ),
            vol.Required(
                CONF_WARN_DAYS, default=defaults.get(CONF_WARN_DAYS, DEFAULT_WARN_DAYS)
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=365, step=1, mode=selector.NumberSelectorMode.BOX
                )
            ),
            vol.Required(
                CONF_CREATE_DEFAULT_SCHEDULES,
                default=defaults.get(CONF_CREATE_DEFAULT_SCHEDULES, True),
            ): selector.BooleanSelector(),
        }
    )


def _notification_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    """Return the notification settings schema."""
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_NOTIFICATIONS_ENABLED,
                default=defaults.get(CONF_NOTIFICATIONS_ENABLED, True),
            ): selector.BooleanSelector(),
            vol.Optional(
                CONF_NOTIFY_SERVICE,
                description={"suggested_value": defaults.get(CONF_NOTIFY_SERVICE, "")},
            ): selector.TextSelector(),
            vol.Required(
                CONF_NOTIFY_ON_DUE, default=defaults.get(CONF_NOTIFY_ON_DUE, True)
            ): selector.BooleanSelector(),
            vol.Required(
                CONF_NOTIFY_ON_OVERDUE, default=defaults.get(CONF_NOTIFY_ON_OVERDUE, True)
            ): selector.BooleanSelector(),
        }
    )


def _validate_tesla_step(user_input: dict[str, Any]) -> dict[str, str]:
    """Validate the mileage source against the supplied fields."""
    errors: dict[str, str] = {}
    source = user_input.get(CONF_MILEAGE_SOURCE)
    if source == MILEAGE_SOURCE_ENTITY and not user_input.get(CONF_ODOMETER_ENTITY):
        errors[CONF_ODOMETER_ENTITY] = "odometer_required"
    if source == MILEAGE_SOURCE_MANUAL and user_input.get(CONF_MANUAL_MILEAGE) is None:
        errors[CONF_MANUAL_MILEAGE] = "manual_mileage_required"
    return errors


def _clean(user_input: dict[str, Any]) -> dict[str, Any]:
    """Drop empty optional values so they are treated as 'not configured'."""
    return {key: value for key, value in user_input.items() if value not in (None, "")}


class TeslaMaintenanceConfigFlow(ConfigFlow, domain=DOMAIN):
    """Guided setup: vehicle -> Tesla entities -> maintenance -> notifications."""

    VERSION = 1

    def __init__(self) -> None:
        """Start with an empty draft configuration."""
        self._data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 1 - vehicle information."""
        if user_input is not None:
            self._data.update(_clean(user_input))
            return await self.async_step_tesla()
        return self.async_show_form(step_id="user", data_schema=_vehicle_schema())

    async def async_step_tesla(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2 - TESLA VEHICLE INTEGRATION (entity mapping)."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate_tesla_step(user_input)
            if not errors:
                self._data.update(_clean(user_input))
                return await self.async_step_maintenance()
        return self.async_show_form(
            step_id="tesla",
            data_schema=_tesla_entity_schema(user_input),
            errors=errors,
        )

    async def async_step_maintenance(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 3 - maintenance settings."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_notifications()
        return self.async_show_form(
            step_id="maintenance", data_schema=_maintenance_schema()
        )

    async def async_step_notifications(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 4 - notification settings, then finish."""
        if user_input is not None:
            self._data.update(user_input)
            title = self._data.get(CONF_VEHICLE_NAME, "Tesla Maintenance")
            await self.async_set_unique_id(f"{DOMAIN}_{title}".lower())
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=title, data=self._data)
        return self.async_show_form(
            step_id="notifications", data_schema=_notification_schema()
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> TeslaMaintenanceOptionsFlow:
        """Return the options flow."""
        return TeslaMaintenanceOptionsFlow()


class TeslaMaintenanceOptionsFlow(OptionsFlow):
    """Edit configuration after setup.

    Only telemetry mapping and preferences are stored here. Maintenance records
    live in SQLite and are never touched by this flow.
    """

    def __init__(self) -> None:
        """Start with an empty set of pending changes."""
        self._updates: dict[str, Any] = {}

    @property
    def _current(self) -> dict[str, Any]:
        """Return the effective configuration."""
        return {**self.config_entry.data, **self.config_entry.options}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the options menu."""
        return self.async_show_menu(
            step_id="init",
            menu_options=["vehicle", "tesla", "maintenance", "notifications"],
        )

    def _save(self, changes: dict[str, Any]) -> ConfigFlowResult:
        """Merge changes into the entry options without dropping other keys."""
        options = {**self.config_entry.options, **changes}
        return self.async_create_entry(title="", data=options)

    async def async_step_vehicle(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit vehicle information."""
        if user_input is not None:
            return self._save(_clean(user_input))
        return self.async_show_form(
            step_id="vehicle", data_schema=_vehicle_schema(self._current)
        )

    async def async_step_tesla(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the Tesla entity mapping.

        Changing or clearing a mapping only changes where telemetry is read
        from. Service history, notes, costs and attachments are unaffected.
        """
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate_tesla_step(user_input)
            if not errors:
                # Explicitly clear any mapping the user emptied.
                changes = {key: user_input.get(key) or None for key in user_input}
                return self._save(changes)
        return self.async_show_form(
            step_id="tesla",
            data_schema=_tesla_entity_schema(user_input or self._current),
            errors=errors,
        )

    async def async_step_maintenance(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit maintenance thresholds, units and currency."""
        if user_input is not None:
            return self._save(user_input)
        return self.async_show_form(
            step_id="maintenance", data_schema=_maintenance_schema(self._current)
        )

    async def async_step_notifications(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit notification settings."""
        if user_input is not None:
            return self._save(user_input)
        return self.async_show_form(
            step_id="notifications", data_schema=_notification_schema(self._current)
        )
