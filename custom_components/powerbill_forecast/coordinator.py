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
    READING_WINDOW_DAYS,
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
        self._hist_cache: tuple[str, list[dict[str, Any]]] | None = None

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
        start_l, end_l = dt_util.as_local(start), dt_util.as_local(end)
        first, last = start_l.date(), end_l.date()
        start_midnight = start_l == dt_util.start_of_local_day(start_l)
        end_midnight = end_l == dt_util.start_of_local_day(end_l)
        days = []
        for row in result.get(self.source, []):
            ts = row.get("start")
            when = dt_util.utc_from_timestamp(ts) if isinstance(ts, (int, float)) else ts
            if when is None:
                continue
            day = dt_util.as_local(when).date()
            if not first <= day < last:  # the recorder also returns the day that starts at `end`
                continue
            if day == first and not start_midnight:
                continue  # replaced below by the part after the meter reading
            days.append(
                {
                    "date": day.isoformat(),
                    "kwh": round(max(0.0, (_num(row.get("change")) or 0.0) * factor), 3),
                }
            )
        # a cycle that starts or ends at a meter reading during the day: count only its part of that day
        if not start_midnight:
            next_midnight = dt_util.start_of_local_day(start_l + timedelta(days=1))
            part = await self._change(start, min(next_midnight, end))
            if part is not None:
                days.insert(0, {"date": first.isoformat(), "kwh": round(max(0.0, part), 3)})
        if not end_midnight and last != first:
            part = await self._change(dt_util.start_of_local_day(end_l), end)
            if part is not None:
                days.append({"date": last.isoformat(), "kwh": round(max(0.0, part), 3)})
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

    async def _history(self, upto: datetime, count: int = 6) -> list[dict[str, Any]]:
        """kWh of the finished cycles that end at `upto` and before, newest first (like the usage history on a bill)."""
        rows: list[dict[str, Any]] = []
        cursor = upto
        for _ in range(count):
            prev_start, prev_end = previous_cycle(cursor, self.reset_day)
            kwh = await self._change(prev_start, prev_end)
            if kwh is None or kwh <= 0:
                break
            rows.append({"date": dt_util.as_local(prev_end).date().isoformat(), "kwh": round(kwh, 1)})
            cursor = prev_start
        return rows

    @staticmethod
    def _when(value: Any) -> datetime | None:
        if not value:
            return None
        parsed = dt_util.parse_datetime(str(value))
        return dt_util.as_local(parsed) if parsed else None

    def _near(self, value: Any, moment: datetime) -> bool:
        """True when `value` (an ISO time) lies within a few days of `moment`."""
        when = self._when(value)
        return when is not None and abs((when - moment).total_seconds()) < READING_WINDOW_DAYS * 86400

    def _covers(self, closed: dict[str, Any] | None, cycle_end: datetime) -> bool:
        """True when the stored bill ends at this cycle change or later (e.g. a meter reading a day early)."""
        when = self._when((closed or {}).get("cycle_end"))
        return when is not None and when >= cycle_end - timedelta(days=READING_WINDOW_DAYS)

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
        if closed and (closed.get("cycle_start") == key or self._covers(closed, prev_end)):
            return closed  # already closed - automatically or by a meter reading
        if now < start + timedelta(hours=CLOSE_DELAY_HOURS):
            return closed
        last_reading = self._saved.get("last_reading")
        if self._near(last_reading, prev_start) and self._when(last_reading) != prev_start:
            # continue exactly at the previous meter reading
            prev_start = self._when(last_reading)
            kwh = await self._change(prev_start, prev_end)
        else:
            kwh = await self._previous_kwh(start)
        if kwh is None:
            return closed
        history = await self._history(start)
        end_day = dt_util.as_local(prev_end).date().isoformat()
        if history and history[0]["date"] == end_day:
            history[0]["kwh"] = round(kwh, 1)
        else:
            history.insert(0, {"date": end_day, "kwh": round(kwh, 1)})
        snapshot = {
            "cycle_start": prev_start.isoformat(),
            "cycle_end": prev_end.isoformat(),
            "reading": "automatic",
            "kwh": round(kwh, 3),
            "ft": ft.get("value") or 0.0,
            "ft_period": ft.get("period"),
            "tariff": self.tariff_name,
            "bill": compute_bill(kwh, self.tiers, ft.get("value") or 0.0, self.service_fee, self.vat),
            "daily": await self._daily(prev_start, prev_end),
            "history": history[:6],
            "closed_at": now.isoformat(),
            "before_kwh": closed.get("kwh") if closed else None,
            "before_total": closed["bill"]["total"] if closed else None,
        }
        first_run = "closed" not in self._saved
        self._saved["closed"] = snapshot
        self._saved["last_reading"] = prev_end.isoformat()
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

    async def async_meter_reading(self, when: datetime | None = None, utility_kwh: float | None = None) -> dict[str, Any]:
        """Close the billing cycle at the utility's meter reading (date and time printed on the bill).

        The cycle runs from the previous reading to `when`; the energy comes from the long-term statistics
        (5-minute precision for recent days). `utility_kwh` - the consumption printed on the bill - makes the
        bill match the paper bill exactly and is compared with the Home Assistant meter.
        """
        when = dt_util.as_local(when or dt_util.now())
        if when > dt_util.now() + timedelta(minutes=5):
            raise ValueError("the meter reading lies in the future")
        last = self._when(self._saved.get("last_reading"))
        if last and timedelta(days=20) < when - last < timedelta(days=45):
            start = last
        else:
            start = cycle_bounds(when - timedelta(days=3), self.reset_day)[0]
        ha_kwh = await self._change(start, when)
        if ha_kwh is None and utility_kwh is None:
            raise ValueError("no statistics for the energy meter in this period - enter the consumption from the bill")
        kwh = float(utility_kwh) if utility_kwh is not None else ha_kwh
        ft = self._ft()
        closed = self._saved.get("closed")
        if closed and self._near(closed.get("cycle_end"), when):
            # replaces the automatic close of the same cycle - keep its comparison values
            before_kwh, before_total = closed.get("before_kwh"), closed.get("before_total")
        else:
            before_kwh = closed.get("kwh") if closed else None
            before_total = closed["bill"]["total"] if closed else None
        history = await self._history(start)
        history.insert(0, {"date": when.date().isoformat(), "kwh": round(kwh, 1)})
        snapshot = {
            "cycle_start": start.isoformat(),
            "cycle_end": when.isoformat(),
            "reading": "meter",
            "kwh": round(kwh, 3),
            "ha_kwh": None if ha_kwh is None else round(ha_kwh, 3),
            "utility_kwh": None if utility_kwh is None else round(float(utility_kwh), 3),
            "ft": ft.get("value") or 0.0,
            "ft_period": ft.get("period"),
            "tariff": self.tariff_name,
            "bill": compute_bill(kwh, self.tiers, ft.get("value") or 0.0, self.service_fee, self.vat),
            "daily": await self._daily(start, when),
            "history": history[:6],
            "closed_at": dt_util.now().isoformat(),
            "before_kwh": before_kwh,
            "before_total": before_total,
        }
        self._saved["closed"] = snapshot
        self._saved["last_reading"] = when.isoformat()
        await self._save()
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
                "reading": "meter",
            },
        )
        _LOGGER.info("Meter reading %s: %s kWh, %s %s", snapshot["cycle_end"], snapshot["kwh"], snapshot["bill"]["total"], self.currency)
        await self.async_request_refresh()
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
        if closed and (closed.get("cycle_start") == prev_start.isoformat() or self._covers(closed, start)):
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

        hist_key = start.isoformat()
        if not self._hist_cache or self._hist_cache[0] != hist_key:
            self._hist_cache = (hist_key, await self._history(start, 5))
        history = [
            {"date": dt_util.as_local(end).date().isoformat(), "kwh": round(kwh, 1), "running": True},
            *self._hist_cache[1],
        ]

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
            "history": history,
            "days_to_next_tier": days_until(bill["kwh_to_next_tier"], fc["daily_rate"]),
            "recent_daily": None if recent_daily is None else round(recent_daily, 3),
            "daily": daily,
            "updated": now.isoformat(),
        }
