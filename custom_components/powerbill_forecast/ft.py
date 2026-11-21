"""Fuel adjustment (Ft) straight from the official PEA website, shared by all forecasts."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

import aiohttp

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN, EVENT_FT_CHANGED, FT_REFRESH_HOURS
from .tariff import PEA_FT_URL, parse_pea_ft

_LOGGER = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) HomeAssistant PowerbillForecast",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en",
}


class PeaFtProvider:
    """Fetch the current Ft twice a day; keep the last good value across restarts."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._store: Store = Store(hass, 1, f"{DOMAIN}.pea_ft")
        self.value: float | None = None
        self.period: str | None = None
        self.fetched: str | None = None  # last successful download
        self.changed: str | None = None  # when the value last changed
        self.error: str | None = None
        self._listeners: list[Callable[[], None]] = []
        self._unsub: CALLBACK_TYPE | None = None
        self.users = 0

    async def async_start(self) -> None:
        saved = await self._store.async_load() or {}
        self.value = saved.get("value")
        self.period = saved.get("period")
        self.fetched = saved.get("fetched")
        self.changed = saved.get("changed")
        self._unsub = async_track_time_interval(self.hass, self._interval, timedelta(hours=FT_REFRESH_HOURS))
        stale = True
        if self.fetched:
            stale = dt_util.utcnow() - dt_util.parse_datetime(self.fetched) > timedelta(hours=FT_REFRESH_HOURS)
        if self.value is None:
            await self.async_refresh()  # first start: wait for the value so the first bill is right
        elif stale:
            self.hass.async_create_background_task(self.async_refresh(), f"{DOMAIN}_ft_refresh")

    @callback
    def async_stop(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None

    @callback
    def async_add_listener(self, update: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(update)

        def remove() -> None:
            if update in self._listeners:
                self._listeners.remove(update)

        return remove

    async def _interval(self, _now: datetime) -> None:
        await self.async_refresh()

    async def async_refresh(self) -> None:
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(PEA_FT_URL, headers=_HEADERS, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                resp.raise_for_status()
                html = await resp.text()
        except Exception as err:  # noqa: BLE001 - network problems must never break the bill
            self.error = f"download failed: {err}"
            _LOGGER.warning("Ft from PEA not updated (%s) - keeping %s", err, self.value)
            self._notify()
            return
        parsed = parse_pea_ft(html)
        if parsed is None:
            self.error = "PEA page layout not recognised"
            _LOGGER.warning("Ft on the PEA page not found - keeping %s. Please open an issue.", self.value)
            self._notify()
            return
        value, period = parsed
        now = dt_util.utcnow().isoformat()
        old = self.value
        if old is not None and abs(old - value) > 1e-9:
            self.changed = now
            self.hass.bus.async_fire(EVENT_FT_CHANGED, {"old": old, "new": value, "period": period})
            _LOGGER.info("Ft changed from %s to %s THB/kWh (%s)", old, value, period)
        elif old is None:
            self.changed = now
        self.value, self.period, self.fetched, self.error = value, period, now, None
        await self._store.async_save(
            {"value": value, "period": period, "fetched": now, "changed": self.changed}
        )
        self._notify()

    def _notify(self) -> None:
        for update in list(self._listeners):
            update()

    def as_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "period": self.period,
            "fetched": self.fetched,
            "changed": self.changed,
            "error": self.error,
            "source": PEA_FT_URL,
        }
