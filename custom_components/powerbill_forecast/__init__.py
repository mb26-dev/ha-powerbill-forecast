"""Powerbill Forecast - tiered tariff energy costs and bill forecast for Home Assistant."""

from __future__ import annotations

from pathlib import Path

import voluptuous as vol

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import (
    CARD_FILE,
    CONF_FT_SOURCE,
    DOMAIN,
    FT_SOURCE_PEA,
    SERVICE_BUILD_REPORT,
    URL_FRONTEND,
    VERSION,
)
from .coordinator import PowerbillCoordinator
from .ft import PeaFtProvider
from .report import build_report

PLATFORMS = [Platform.SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

REPORT_SCHEMA = vol.Schema(
    {
        vol.Optional("config_entry_id"): cv.string,
        vol.Optional("cycle", default="previous"): vol.In(["previous", "current"]),
    }
)

FT_KEY = "pea_ft"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Serve the dashboard card and register the report action once."""
    hass.data.setdefault(DOMAIN, {})
    frontend_dir = Path(__file__).parent / "frontend"
    await hass.http.async_register_static_paths([StaticPathConfig(URL_FRONTEND, str(frontend_dir), False)])
    add_extra_js_url(hass, f"{URL_FRONTEND}/{CARD_FILE}?v={VERSION}")

    async def _build_report(call: ServiceCall) -> ServiceResponse:
        entries = [
            e for e in hass.config_entries.async_entries(DOMAIN) if e.state is ConfigEntryState.LOADED
        ]
        wanted = call.data.get("config_entry_id")
        if wanted:
            entries = [e for e in entries if e.entry_id == wanted]
        if not entries:
            raise ServiceValidationError("No loaded Powerbill Forecast found for this request")
        coordinator: PowerbillCoordinator = hass.data[DOMAIN][entries[0].entry_id]
        if not coordinator.data:
            raise ServiceValidationError("Powerbill Forecast has no data yet")
        report = build_report(coordinator.data, call.data["cycle"], VERSION)
        if report is None:
            raise ServiceValidationError("There is no finished billing cycle yet - try cycle: current")
        return report

    hass.services.async_register(
        DOMAIN, SERVICE_BUILD_REPORT, _build_report, schema=REPORT_SCHEMA, supports_response=SupportsResponse.ONLY
    )
    return True


async def _ft_provider(hass: HomeAssistant) -> PeaFtProvider:
    provider: PeaFtProvider | None = hass.data[DOMAIN].get(FT_KEY)
    if provider is None:
        provider = PeaFtProvider(hass)
        hass.data[DOMAIN][FT_KEY] = provider
        await provider.async_start()
    provider.users += 1
    return provider


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up one bill forecast."""
    opts = dict(entry.options) if entry.options else dict(entry.data)
    provider = await _ft_provider(hass) if opts.get(CONF_FT_SOURCE) == FT_SOURCE_PEA else None
    coordinator = PowerbillCoordinator(hass, entry, provider)
    await coordinator.async_setup()
    await coordinator.async_config_entry_first_refresh()
    hass.data[DOMAIN][entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        coordinator: PowerbillCoordinator | None = hass.data[DOMAIN].pop(entry.entry_id, None)
        provider: PeaFtProvider | None = hass.data[DOMAIN].get(FT_KEY)
        if coordinator and coordinator.ft_provider and provider:
            provider.users -= 1
            if provider.users <= 0:
                provider.async_stop()
                hass.data[DOMAIN].pop(FT_KEY, None)
    return unloaded
