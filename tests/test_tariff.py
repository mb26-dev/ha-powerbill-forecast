"""Tests for the tariff maths. Run: python tests/test_tariff.py"""

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "custom_components" / "powerbill_forecast" / "tariff.py"
_spec = importlib.util.spec_from_file_location("tariff", _PATH)
tariff = importlib.util.module_from_spec(_spec)
sys.modules["tariff"] = tariff
_spec.loader.exec_module(tariff)

BKK = timezone(timedelta(hours=7))


def approx(a, b, tol=0.01):
    assert abs(a - b) <= tol, f"{a} != {b}"


def test_pea_large_bill():
    p = tariff.PRESETS["pea_1_2"]
    bill = tariff.compute_bill(447.5331, p.tiers, ft=0.1623, service_fee=p.service_fee, vat=p.vat)
    # 150*3.2484 + 250*4.2218 + 47.5331*4.4217
    approx(bill["energy"], 487.26 + 1055.45 + 210.18)
    approx(bill["ft"], 72.63)
    approx(bill["total"], 1979.65, 0.05)
    assert bill["current_tier"] == 3
    assert bill["kwh_to_next_tier"] is None
    approx(bill["marginal_price"], (4.4217 + 0.1623) * 1.07, 0.0001)


def test_pea_small_bill():
    p = tariff.PRESETS["pea_1_1"]
    bill = tariff.compute_bill(120, p.tiers, ft=0.0, service_fee=p.service_fee, vat=7)
    energy = 15 * 2.3488 + 10 * 2.9882 + 10 * 3.2405 + 65 * 3.6237 + 20 * 3.7171
    approx(bill["energy"], energy)
    assert bill["current_tier"] == 5
    approx(bill["kwh_to_next_tier"], 30)


def test_boundary_and_zero():
    tiers = tariff.PRESETS["pea_1_2"].tiers
    assert tariff.compute_bill(150, tiers)["current_tier"] == 1
    assert tariff.compute_bill(150.01, tiers)["current_tier"] == 2
    zero = tariff.compute_bill(0, tiers, service_fee=24.62, vat=7)
    approx(zero["total"], 26.34)
    assert zero["average_price"] is None


def test_parse_tiers():
    t = tariff.parse_tiers("400=4.2218; 150=3.2484\n*=4.4217")
    assert [x.limit for x in t] == [150, 400, tariff.INF]
    assert tariff.parse_tiers("0.31") == (tariff.Tier(tariff.INF, 0.31),)
    assert tariff.parse_tiers("100=0.2")[-1] == tariff.Tier(tariff.INF, 0.2)
    assert tariff.format_tiers(t) == "150=3.2484, 400=4.2218, *=4.4217"
    for bad in ("", "100=1, 100=2", "0=1"):
        try:
            tariff.parse_tiers(bad)
        except ValueError:
            continue
        raise AssertionError(bad)


def test_cycle_bounds():
    s, e = tariff.cycle_bounds(datetime(2026, 11, 21, 13, 0, tzinfo=BKK), 24)
    assert (s.date().isoformat(), e.date().isoformat()) == ("2026-10-24", "2026-11-24")
    s, e = tariff.cycle_bounds(datetime(2026, 11, 24, 0, 0, tzinfo=BKK), 24)
    assert (s.day, s.month, e.day, e.month) == (24, 11, 24, 12)
    s, e = tariff.cycle_bounds(datetime(2026, 12, 30, tzinfo=BKK), 24)
    assert (e.year, e.month) == (2027, 1)
    s, e = tariff.cycle_bounds(datetime(2027, 2, 28, 10, tzinfo=BKK), 31)
    assert (s.month, s.day, e.month, e.day) == (2, 28, 3, 31)
    s, e = tariff.cycle_bounds(datetime(2026, 1, 5, tzinfo=BKK), 1)
    assert (s.month, s.day, e.month, e.day) == (1, 1, 2, 1)
    ps, pe = tariff.previous_cycle(datetime(2026, 10, 24, tzinfo=BKK), 24)
    assert (ps.month, ps.day, pe.month, pe.day) == (9, 24, 10, 24)


def test_forecast():
    start, end = datetime(2026, 10, 24, tzinfo=BKK), datetime(2026, 11, 24, tzinfo=BKK)
    now = datetime(2026, 11, 21, 12, tzinfo=BKK)
    f = tariff.forecast_kwh(447.5, start, end, now)
    approx(f["days_remaining"], 2.5)
    approx(f["kwh"], 447.5 + 447.5 / 28.5 * 2.5, 0.01)
    f2 = tariff.forecast_kwh(447.5, start, end, now, recent_daily=20)
    assert f2["kwh"] > f["kwh"]
    early = tariff.forecast_kwh(3, start, end, start + timedelta(hours=6), fallback_daily=12.5)
    approx(early["daily_rate"], 12.5)
    assert tariff.days_until(10, 5) == 2
    assert tariff.days_until(None, 5) is None


def test_parse_pea_ft():
    page = (
        '<div class="field"><h3 class="text-center mb-5">Current Ft (Sep - Dec 2026)<br>'
        '<span class="text-primary">0.1623</span> THB/Unit</h3></div>'
    )
    assert tariff.parse_pea_ft(page) == (0.1623, "Sep - Dec 2026")
    assert tariff.parse_pea_ft("<h3>Current Ft (Jan - Apr 2027)<br><span>-0.0521</span> THB/Unit</h3>") == (
        -0.0521,
        "Jan - Apr 2027",
    )
    assert tariff.parse_pea_ft("<p>maintenance</p>") is None
    assert tariff.parse_pea_ft("<h3>Current Ft (Sep - Dec 2026)<br><span>99</span> THB/Unit</h3>") is None


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
