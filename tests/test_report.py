"""Tests for the bill report e-mail. Run: python tests/test_report.py"""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "docs" / "demo"))
from demo_data import DEMO, tariff  # noqa: E402

_spec = importlib.util.spec_from_file_location("report", ROOT / "custom_components/powerbill_forecast/report.py")
report = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(report)


def _data():
    data = dict(DEMO["cards"]["top_tier"])
    preset = tariff.PRESETS["pea_1_2"]
    data["name"] = "Powerbill Forecast"
    data["previous"] = {
        "cycle_start": "2026-09-24T00:00:00+07:00",
        "cycle_end": "2026-10-24T00:00:00+07:00",
        "kwh": 386.9454,
        "ft": 0.1623,
        "ft_period": "Sep - Dec 2026",
        "tariff": preset.name,
        "bill": tariff.compute_bill(386.9454, preset.tiers, 0.1623, preset.service_fee, preset.vat),
        "daily": [{"date": "2026-09-24", "kwh": 12.5}, {"date": "2026-09-25", "kwh": 14.1}],
        "before_kwh": 402.1,
        "before_total": 1789.4,
        "history": [{"date": "2026-10-24", "kwh": 386.9}, {"date": "2026-09-24", "kwh": 402.1}],
    }
    return data


def test_previous_report():
    rep = report.build_report(_data(), "previous", "0.1.0b2")
    assert rep["subject"].startswith("⚡ Electricity bill October 2026: ฿")
    assert "24 Sep - 23 Oct 2026" in rep["html"]
    assert "Sep - Dec 2026" in rep["html"]
    assert "display:flex" not in rep["html"] and "var(--" not in rep["html"]
    assert f"{rep['total']:,.2f}" in rep["html"]
    assert "Total amount:" in rep["text"]
    assert "ELECTRICITY BILL" in rep["html"] and "Usage history" in rep["html"] and "24 Sep 26" in rep["html"]
    assert "BILL PERIOD" in rep["html"] and "10/2026" in rep["html"] and "24/10/2026" in rep["html"]


def test_current_report_and_missing_previous():
    data = _data()
    rep = report.build_report(data, "current")
    assert "(so far)" in rep["subject"] and "FORECAST AT THE METER READING" in rep["html"]
    data["history"] = [{"date": "2026-11-24", "kwh": 447.5, "running": True}, {"date": "2026-10-24", "kwh": 386.9}]
    prev = dict(data["previous"])
    prev.pop("history")
    data["previous"] = prev
    assert ">387<" in report.build_report(data, "previous")["html"].split("Usage history")[1]
    data["previous"] = None
    assert report.build_report(data, "previous") is None


def test_meter_reading_report_matches_paper_bill():
    """PEA bill 11/2569: read 23/11 12:20, 473 kWh on the bill -> 1,980.82."""
    data = _data()
    preset = tariff.PRESETS["pea_1_2"]
    data["previous"] = {
        **data["previous"],
        "cycle_start": "2026-10-24T00:00:00+07:00",
        "cycle_end": "2026-11-23T12:20:00+07:00",
        "reading": "meter",
        "kwh": 473.0,
        "utility_kwh": 473.0,
        "ha_kwh": 475.12,
        "bill": tariff.compute_bill(473, preset.tiers, 0.1623, preset.service_fee, preset.vat),
    }
    rep = report.build_report(data, "previous")
    assert rep["total"] == 1980.82
    assert "23/11/2026 12:20" in rep["html"] and "24 Oct - 23 Nov 2026" in rep["html"]
    assert rep["subject"].startswith("⚡ Electricity bill November 2026: ฿1,980.82")
    assert "Meter read 23/11/2026 12:20" in rep["html"] and "+0.4%" in rep["html"]
    assert "23/11/2026 12:20</td>" not in rep["html"]  # the box keeps the date only, so the mail does not get wider


def test_tier_colors_match_card():
    assert report.tier_color(0, 3) == "#22d3ee"
    assert report.tier_color(2, 3) == "#ef4444"
    assert report.tier_color(0, 1) == "#22d3ee"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
