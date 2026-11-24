"""Config and options flow for Powerbill Forecast."""

from __future__ import annotations

import re
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_CURRENCY,
    CONF_FT_ENTITY,
    CONF_FT_SOURCE,
    CONF_FT_VALUE,
    CONF_METER_TYPE,
    CONF_RESET_DAY,
    CONF_SERVICE_FEE,
    CONF_SOURCE,
    CONF_TARIFF,
    CONF_TIERS,
    CONF_VAT,
    DEFAULT_NAME,
    DEFAULT_RESET_DAY,
    DEFAULT_TARIFF,
    DOMAIN,
    FT_SOURCE_ENTITY,
    FT_SOURCE_FIXED,
    FT_SOURCE_PEA,
    METER_CYCLE,
    METER_LIFETIME,
)
from .tariff import PRESETS, format_tiers, parse_tiers

CONF_NAME = "name"


def _default_ft_source(hass, values: dict[str, Any]) -> str:
    """Thailand: the official PEA value. Elsewhere a fixed value (usually 0). Old setups keep their entity."""
    if values.get(CONF_FT_ENTITY):
        return FT_SOURCE_ENTITY
    if values.get(CONF_SOURCE) and CONF_FT_SOURCE not in values:  # configured with 0.1.0b1
        return FT_SOURCE_FIXED if values.get(CONF_FT_VALUE) else FT_SOURCE_PEA
    return FT_SOURCE_PEA if (hass.config.country or "TH") == "TH" else FT_SOURCE_FIXED


def _schema(hass, values: dict[str, Any], with_name: bool) -> vol.Schema:
    def sv(key: str) -> dict[str, Any]:
        val = values.get(key)
        return {"suggested_value": val} if val not in (None, "") else {}

    fields: dict[Any, Any] = {}
    if with_name:
        fields[vol.Required(CONF_NAME, default=values.get(CONF_NAME, DEFAULT_NAME))] = selector.TextSelector()
    fields.update(
        {
            vol.Required(CONF_SOURCE, default=values.get(CONF_SOURCE, vol.UNDEFINED)): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="energy")
            ),
            vol.Required(CONF_METER_TYPE, default=values.get(CONF_METER_TYPE, METER_CYCLE)): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[METER_CYCLE, METER_LIFETIME],
                    translation_key="meter_type",
                    mode=selector.SelectSelectorMode.LIST,
                )
            ),
            vol.Required(CONF_RESET_DAY, default=values.get(CONF_RESET_DAY, DEFAULT_RESET_DAY)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=1, max=31, step=1, mode=selector.NumberSelectorMode.BOX)
            ),
            vol.Required(CONF_TARIFF, default=values.get(CONF_TARIFF, DEFAULT_TARIFF)): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[selector.SelectOptionDict(value=k, label=p.name) for k, p in PRESETS.items()],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(CONF_TIERS, description=sv(CONF_TIERS)): selector.TextSelector(
                selector.TextSelectorConfig(multiline=True)
            ),
            vol.Optional(CONF_SERVICE_FEE, description=sv(CONF_SERVICE_FEE)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=100000, step="any", mode=selector.NumberSelectorMode.BOX)
            ),
            vol.Optional(CONF_VAT, description=sv(CONF_VAT)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=100, step="any", unit_of_measurement="%", mode=selector.NumberSelectorMode.BOX)
            ),
            vol.Optional(CONF_CURRENCY, description=sv(CONF_CURRENCY)): selector.TextSelector(),
            vol.Required(CONF_FT_SOURCE, default=values.get(CONF_FT_SOURCE, _default_ft_source(hass, values))): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[FT_SOURCE_PEA, FT_SOURCE_ENTITY, FT_SOURCE_FIXED],
                    translation_key="ft_source",
                    mode=selector.SelectSelectorMode.LIST,
                )
            ),
            vol.Optional(CONF_FT_ENTITY, description=sv(CONF_FT_ENTITY)): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["sensor", "input_number", "number"])
            ),
            vol.Optional(CONF_FT_VALUE, description=sv(CONF_FT_VALUE)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=-100, max=100, step="any", mode=selector.NumberSelectorMode.BOX)
            ),
        }
    )
    return vol.Schema(fields)


_CURRENCY = re.compile(r"[A-Z]{3}")  # ISO 4217 code


def _validate(user_input: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    errors: dict[str, str] = {}
    data = {k: v for k, v in user_input.items() if v not in (None, "")}
    data[CONF_RESET_DAY] = int(data.get(CONF_RESET_DAY, DEFAULT_RESET_DAY))
    tiers = (data.get(CONF_TIERS) or "").strip()
    if data.get(CONF_TARIFF) == "custom":
        if not tiers:
            errors[CONF_TIERS] = "tiers_required"
        else:
            try:
                data[CONF_TIERS] = format_tiers(parse_tiers(tiers))
            except ValueError:
                errors[CONF_TIERS] = "invalid_tiers"
    else:
        data.pop(CONF_TIERS, None)
    if data.get(CONF_FT_SOURCE) == FT_SOURCE_ENTITY and not data.get(CONF_FT_ENTITY):
        errors[CONF_FT_ENTITY] = "ft_entity_required"
    if data.get(CONF_FT_SOURCE) != FT_SOURCE_ENTITY:
        data.pop(CONF_FT_ENTITY, None)
    if CONF_CURRENCY in data:
        data[CONF_CURRENCY] = str(data[CONF_CURRENCY]).strip().upper()
        if not _CURRENCY.fullmatch(data[CONF_CURRENCY]):
            errors[CONF_CURRENCY] = "invalid_currency"
    return data, errors


class PowerbillConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up a bill forecast for one energy meter."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        values: dict[str, Any] = user_input or {}
        if user_input is not None:
            data, errors = _validate(user_input)
            if not errors:
                await self.async_set_unique_id(data[CONF_SOURCE])
                self._abort_if_unique_id_configured()
                title = data.pop(CONF_NAME, DEFAULT_NAME)
                return self.async_create_entry(title=title, data=data)
        return self.async_show_form(step_id="user", data_schema=_schema(self.hass, values, True), errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return PowerbillOptionsFlow()


class PowerbillOptionsFlow(OptionsFlow):
    """Change tariff, cycle day, Ft and the meter later."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        current = dict(self.config_entry.options) if self.config_entry.options else dict(self.config_entry.data)
        if user_input is not None:
            data, errors = _validate(user_input)
            if not errors:
                return self.async_create_entry(title="", data=data)
            current = user_input
        return self.async_show_form(step_id="init", data_schema=_schema(self.hass, current, False), errors=errors)
