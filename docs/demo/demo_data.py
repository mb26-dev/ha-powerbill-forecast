"""Build realistic demo data for the screenshots with the real tariff maths."""

import importlib.util
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("tariff", ROOT / "custom_components/powerbill_forecast/tariff.py")
tariff = importlib.util.module_from_spec(_spec)
sys.modules["tariff"] = tariff
_spec.loader.exec_module(tariff)

BKK = timezone(timedelta(hours=7))
NOW = datetime(2026, 11, 21, 13, 50, tzinfo=BKK)
FT = 0.1623
PREVIOUS_KWH = 386.9454


def card_data(preset_key: str, kwh: float) -> dict:
    preset = tariff.PRESETS[preset_key]
    start, end = tariff.cycle_bounds(NOW, 24)
    rnd = random.Random(3)
    full = (NOW - start).days
    raw = [rnd.uniform(11, 19) for _ in range(full)]
    scale = kwh * 0.97 / sum(raw)
    daily = [{"date": (start + timedelta(days=i)).date().isoformat(), "kwh": round(v * scale, 3)} for i, v in enumerate(raw)]
    daily.append({"date": NOW.date().isoformat(), "kwh": round(kwh - sum(d["kwh"] for d in daily), 3)})
    recent = sum(d["kwh"] for d in daily[-8:-1]) / 7
    fc = tariff.forecast_kwh(kwh, start, end, NOW, recent, PREVIOUS_KWH / 30)
    args = (preset.tiers, FT, preset.service_fee, preset.vat)
    bill = tariff.compute_bill(kwh, *args)
    return {
        "tariff": preset.name,
        "tariff_key": preset_key,
        "currency": "THB",
        "symbol": "฿",
        "ft": FT,
        "service_fee": preset.service_fee,
        "vat": preset.vat,
        "tiers": [
            {"index": i, "to": None if t.limit == tariff.INF else t.limit, "rate": t.rate}
            for i, t in enumerate(preset.tiers, start=1)
        ],
        "cycle_start": start.isoformat(),
        "cycle_end": end.isoformat(),
        "kwh": kwh,
        "bill": bill,
        "forecast": fc,
        "forecast_bill": tariff.compute_bill(fc["kwh"], *args),
        "previous_kwh": PREVIOUS_KWH,
        "previous_total": tariff.compute_bill(PREVIOUS_KWH, *args)["total"],
        "days_to_next_tier": tariff.days_until(bill["kwh_to_next_tier"], fc["daily_rate"]),
        "recent_daily": round(recent, 3),
        "daily": daily,
        "updated": NOW.isoformat(),
    }


def closed_cycle() -> dict:
    """The finished cycle before the demo cycle, for the bill report screenshot."""
    preset = tariff.PRESETS["pea_1_2"]
    start = datetime(2026, 9, 24, tzinfo=BKK)
    rnd = random.Random(5)
    daily = [{"date": (start + timedelta(days=i)).date().isoformat(), "kwh": round(rnd.uniform(9, 17), 2)} for i in range(30)]
    kwh = round(sum(d["kwh"] for d in daily), 3)
    return {
        "cycle_start": start.isoformat(),
        "cycle_end": datetime(2026, 10, 24, tzinfo=BKK).isoformat(),
        "kwh": kwh,
        "ft": FT,
        "ft_period": "Sep - Dec 2026",
        "tariff": preset.name,
        "bill": tariff.compute_bill(kwh, preset.tiers, FT, preset.service_fee, preset.vat),
        "daily": daily,
        "before_kwh": 402.1,
        "before_total": 1789.4,
        "history": [
            {"date": "2026-10-24", "kwh": round(kwh, 1)},
            {"date": "2026-09-24", "kwh": 402.1},
            {"date": "2026-08-24", "kwh": 388.6},
            {"date": "2026-07-24", "kwh": 241.3},
            {"date": "2026-06-24", "kwh": 229.8},
            {"date": "2026-05-24", "kwh": 436.2},
        ],
    }


DEMO = {
    "now": NOW.isoformat(),
    "cards": {
        "top_tier": card_data("pea_1_2", 447.53),
        "tier_two": card_data("pea_1_2", 362.0),
        "small_tariff": card_data("pea_1_1", 118.0),
    },
}
DEMO["cards"]["top_tier"]["name"] = "Powerbill Forecast"
DEMO["cards"]["top_tier"]["ft_period"] = "Sep - Dec 2026"
DEMO["cards"]["top_tier"]["previous"] = closed_cycle()
DEMO["cards"]["top_tier"]["previous_kwh"] = DEMO["cards"]["top_tier"]["previous"]["kwh"]
DEMO["cards"]["top_tier"]["previous_total"] = DEMO["cards"]["top_tier"]["previous"]["bill"]["total"]
