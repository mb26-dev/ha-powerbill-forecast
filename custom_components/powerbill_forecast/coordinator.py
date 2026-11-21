"""Data engine: reads the meter, the recorder statistics and the tariff, builds the forecast."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import (
    statistic_during_period,
    statistics_during_period,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CLOSE_DELAY_HOURS,
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
    DEFAULT_RESET_DAY,
    DEFAULT_TARIFF,
    DOMAIN,
    EVENT_CYCLE_CLOSED,
    FT_SOURCE_ENTITY,
    FT_SOURCE_FIXED,
    FT_SOURCE_PEA,
    METER_CYCLE,
    METER_LIFETIME,
    RECENT_DAYS,
    UPDATE_MINUTES,
)
from .tariff import (
    CURRENCY_SYMBOLS,
    INF,
    PRESETS,
    compute_bill,
    cycle_bounds,
    days_until,
    forecast_kwh,
    parse_tiers,
    previous_cycle,
)

if TYPE_CHECKING:
    from .ft import PeaFtProvider

_LOGGER = logging.getLogger(__name__)

_UNIT_FACTOR = {"wh": 0.001, "kwh": 1.0, "mwh": 1000.0}


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class PowerbillCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Recalculate on every meter change (debounced) and every few minutes."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, ft_provider: PeaFtProvider | None) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(minutes=UPDATE_MINUTES),
        )
        # the options form stores the complete set, so cleared fields really disappear
        opts = dict(entry.options) if entry.options else dict(entry.data)
        self.title = entry.title
        self.source: str = opts[CONF_SOURCE]
        self.meter_type: str = opts.get(CONF_METER_TYPE, METER_CYCLE)
        self.reset_day: int = int(opts.get(CONF_RESET_DAY, DEFAULT_RESET_DAY))
        preset_key = opts.get(CONF_TARIFF, DEFAULT_TARIFF)
        preset = PRESETS.get(preset_key, PRESETS[DEFAULT_TARIFF])
        self.tariff_key = preset_key
        self.tariff_name = preset.name
        tiers_text = (opts.get(CONF_TIERS) or "").strip()
        self.tiers = parse_tiers(tiers_text) if preset_key == "custom" and tiers_text else preset.tiers
        fee = _num(opts.get(CONF_SERVICE_FEE))
        vat = _num(opts.get(CONF_VAT))
        self.service_fee = preset.service_fee if fee is None else fee
        self.vat = preset.vat if vat is None else vat
        self.currency = (opts.get(CONF_CURRENCY) or preset.currency or hass.config.currency or "").upper()
        self.symbol = CURRENCY_SYMBOLS.get(self.currency, self.currency)
        self.ft_entity: str | None = opts.get(CONF_FT_ENTITY) or None
        self.ft_value = _num(opts.get(CONF_FT_VALUE)) or 0.0
        # configurations from 0.1.0b1 have no source yet: an entity wins, else the fixed value
        self.ft_source: str = opts.get(CONF_FT_SOURCE) or (FT_SOURCE_ENTITY if self.ft_entity else FT_SOURCE_FIXED)
        self.ft_provider = ft_provider if self.ft_source == FT_SOURCE_PEA else None

        self._store: Store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")
        self._saved: dict[str, Any] = {}
        self._prev_cache: tuple[str, float | None] | None = None

    async def async_setup(self) -> None:
        """Load the saved state and follow the meter, the Ft entity and the PEA Ft."""
        self._saved = await self._store.async_load() or {}
        watched = [self.source] + ([self.ft_entity] if self.ft_source == FT_SOURCE_ENTITY and self.ft_entity else [])

        @callback
        def _changed(_event: Event[EventStateChangedData] | None = None) -> None:
            self.hass.async_create_task(self.async_request_refresh())

        self.config_entry.async_on_unload(async_track_state_change_event(self.hass, watched, _changed))
        if self.ft_provider:
            self.config_entry.async_on_unload(self.ft_provider.async_add_listener(_changed))

    async def _save(self) -> None:
        await self._store.async_save(self._saved)

    # ------------------------------------------------------------------ helpers

    def _meter_kwh(self) -> float | None:
        state = self.hass.states.get(self.source)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None
        value = _num(state.state)
        if value is None:
            return None
        unit = str(state.attributes.get("unit_of_measurement", "kWh")).lower()
        return value * _UNIT_FACTOR.get(unit, 1.0)

    def _unit_factor(self) -> float:
        state = self.hass.states.get(self.source)
        unit = str(state.attributes.get("unit_of_measurement", "kWh")).lower() if state else "kwh"
        return _UNIT_FACTOR.get(unit, 1.0)

    def _ft(self) -> dict[str, Any]:
        """Current Ft per kWh with where it came from."""
        if self.ft_source == FT_SOURCE_PEA and self.ft_provider and self.ft_provider.value is not None:
            return {**self.ft_provider.as_dict(), "source": "pea"}
        if self.ft_source == FT_SOURCE_ENTITY and self.ft_entity:
            state = self.hass.states.get(self.ft_entity)
            value = _num(state.state) if state else None
            if value is not None:
                return {"value": value, "period": None, "source": "entity", "entity": self.ft_entity}
        info: dict[str, Any] = {"value": self.ft_value, "period": None, "source": "fixed"}
        if self.ft_source != FT_SOURCE_FIXED:
            info["error"] = "configured Ft source has no value yet - using the fixed value"
        return info

    async def _change(self, start: datetime, end: datetime) -> float | None:
        """Energy used between start and end according to the long-term statistics."""
        try:
            result = await get_instance(self.hass).async_add_executor_job(
                statistic_during_period, self.hass, start, end, self.source, {"change"}, None
            )
        except Exception as err:  # noqa: BLE001 - statistics are optional
            _LOGGER.debug("No statistics change for %s: %s", self.source, err)
            return None
        value = _num((result or {}).get("change"))
        return None if value is None else value * self._unit_factor()

    async def _daily(self, start: datetime, end: datetime) -> list[dict[str, Any]]:
        """Daily consumption inside a cycle from the long-term statistics."""
        try:
            result = await get_instance(self.hass).async_add_executor_job(
                statistics_during_period, self.hass, start, end, {self.source}, "day", None, {"change"}
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("No daily statistics for %s: %s", self.source, err)
            return []
        factor = self._unit_factor()
        first, last = dt_util.as_local(start).date(), dt_util.as_local(end).date()
        days = []
        for row in result.get(self.source, []):
            ts = row.get("start")
            when = dt_util.utc_from_timestamp(ts) if isinstance(ts, (int, float)) else ts
            if when is None:
                continue
            day = dt_util.as_local(when).date()
            if not first <= day < last:  # the recorder also returns the day that starts at `end`
                continue
            days.append(
                {
                    "date": day.isoformat(),
                    "kwh": round(max(0.0, (_num(row.get("change")) or 0.0) * factor), 3),
                }
            )
        return days

    async def _previous_kwh(self, start: datetime) -> float | None:
        prev_start, prev_end = previous_cycle(start, self.reset_day)
        key = prev_start.isoformat()
        if self._prev_cache and self._prev_cache[0] == key and self._prev_cache[1] is not None:
            return self._prev_cache[1]
        value = await self._change(prev_start, prev_end)
        if (value is None or value <= 0) and self.meter_type == METER_CYCLE:
            state = self.hass.states.get(self.source)
            value = _num(state.attributes.get("last_period")) if state else None
            if value is not None:
                value *= self._unit_factor()
        self._prev_cache = (key, value)
        return value

    async def _cycle_kwh(self, meter: float, start: datetime, now: datetime) -> float:
        if self.meter_type != METER_LIFETIME:
            return max(0.0, meter)
        key = start.isoformat()
        baseline = _num(self._saved.get("baseline"))
        if self._saved.get("cycle_start") != key or baseline is None:
            # count back to the cycle start with the statistics (first start mid-cycle,
            # or Home Assistant was down at the cycle change); without statistics start at zero
            used = await self._change(start, now)
            baseline = meter - max(0.0, used) if used is not None else meter
            self._saved.update({"cycle_start": key, "baseline": baseline, "last_kwh": 0.0})
            await self._save()
        if meter < baseline:  # the meter itself was reset or replaced
            last = _num(self._saved.get("last_kwh")) or 0.0
            baseline = meter - last
            self._saved["baseline"] = baseline
            await self._save()
        kwh = max(0.0, meter - baseline)
        self._saved["last_kwh"] = kwh
        return kwh

    async def _closed_cycle(self, start: datetime, now: datetime, ft: dict[str, Any]) -> dict[str, Any] | None:
        """Freeze the finished cycle once (the 'paper bill'), then announce it."""
        prev_start, prev_end = previous_cycle(start, self.reset_day)
        key = prev_start.isoformat()
        closed = self._saved.get("closed")
        if closed and closed.get("cycle_start") == key:
            return closed
        if now < start + timedelta(hours=CLOSE_DELAY_HOURS):
            return closed
        kwh = await self._previous_kwh(start)
        if kwh is None:
            return closed
        snapshot = {
            "cycle_start": key,
            "cycle_end": prev_end.isoformat(),
            "kwh": round(kwh, 3),
            "ft": ft.get("value") or 0.0,
            "ft_period": ft.get("period"),
            "tariff": self.tariff_name,
            "bill": compute_bill(kwh, self.tiers, ft.get("value") or 0.0, self.service_fee, self.vat),
            "daily": await self._daily(prev_start, prev_end),
            "closed_at": now.isoformat(),
            "before_kwh": closed.get("kwh") if closed else None,
            "before_total": closed["bill"]["total"] if closed else None,
        }
        first_run = "closed" not in self._saved
        self._saved["closed"] = snapshot
        await self._save()
        if not first_run:  # no report for a cycle that ended before the integration was set up
            self.hass.bus.async_fire(
                EVENT_CYCLE_CLOSED,
                {
                    "entry_id": self.config_entry.entry_id,
                    "name": self.title,
                    "cycle_start": snapshot["cycle_start"],
                    "cycle_end": snapshot["cycle_end"],
                    "kwh": snapshot["kwh"],
                    "total": snapshot["bill"]["total"],
                    "currency": self.currency,
                },
            )
            _LOGGER.info("Billing cycle %s closed: %s kWh, %s %s", key, snapshot["kwh"], snapshot["bill"]["total"], self.currency)
        return snapshot

    # ------------------------------------------------------------------ update

    async def _async_update_data(self) -> dict[str, Any]:
        meter = self._meter_kwh()
        if meter is None:
            if self.data:
                return self.data
            raise UpdateFailed(f"{self.source} has no numeric value yet")

        now = dt_util.now()
        start, end = cycle_bounds(now, self.reset_day)
        kwh = await self._cycle_kwh(meter, start, now)
        ft_info = self._ft()
        ft = ft_info["value"] or 0.0

        daily = await self._daily(start, end)
        today = now.date().isoformat()
        full_days = [d for d in daily if d["date"] != today]
        if self.meter_type == METER_CYCLE or daily:
            # today = live meter minus the finished days (statistics lag behind the meter)
            today_kwh = max(0.0, kwh - sum(d["kwh"] for d in full_days))
            daily = [*full_days, {"date": today, "kwh": round(today_kwh, 3)}]
        recent = full_days[-RECENT_DAYS:]
        recent_daily = sum(d["kwh"] for d in recent) / len(recent) if len(recent) >= 2 else None

        closed = await self._closed_cycle(start, now, ft_info)
        prev_start, prev_end = previous_cycle(start, self.reset_day)
        if closed and closed.get("cycle_start") == prev_start.isoformat():
            previous = closed
        else:
            prev_kwh = await self._previous_kwh(start)
            previous = None
            if prev_kwh:
                previous = {
                    "cycle_start": prev_start.isoformat(),
                    "cycle_end": prev_end.isoformat(),
                    "kwh": round(prev_kwh, 3),
                    "ft": ft,
                    "ft_period": ft_info.get("period"),
                    "tariff": self.tariff_name,
                    "bill": compute_bill(prev_kwh, self.tiers, ft, self.service_fee, self.vat),
                    "daily": [],
                }
        prev_days = (prev_end - prev_start).total_seconds() / 86400
        fallback = previous["kwh"] / prev_days if previous and prev_days > 0 else None

        bill = compute_bill(kwh, self.tiers, ft, self.service_fee, self.vat)
        fc = forecast_kwh(kwh, start, end, now, recent_daily, fallback)
        fbill = compute_bill(fc["kwh"], self.tiers, ft, self.service_fee, self.vat)

        return {
            "name": self.title,
            "tariff": self.tariff_name,
            "tariff_key": self.tariff_key,
            "currency": self.currency,
            "symbol": self.symbol,
            "ft": ft,
            "ft_period": ft_info.get("period"),
            "ft_info": ft_info,
            "service_fee": self.service_fee,
            "vat": self.vat,
            "tiers": [
                {"index": i, "to": None if t.limit == INF else t.limit, "rate": t.rate}
                for i, t in enumerate(self.tiers, start=1)
            ],
            "cycle_start": start.isoformat(),
            "cycle_end": end.isoformat(),
            "kwh": round(kwh, 3),
            "bill": bill,
            "forecast": fc,
            "forecast_bill": fbill,
            "previous_kwh": previous["kwh"] if previous else None,
            "previous_total": previous["bill"]["total"] if previous else None,
            "previous": previous,
            "days_to_next_tier": days_until(bill["kwh_to_next_tier"], fc["daily_rate"]),
            "recent_daily": None if recent_daily is None else round(recent_daily, 3),
            "daily": daily,
            "updated": now.isoformat(),
        }
