"""Bill report e-mail laid out like a paper electricity bill (pure functions, no Home Assistant imports).

E-mail clients are picky: only tables, inline styles, rgba() colours, no flexbox, no CSS variables.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from html import escape
from typing import Any

PALETTE = ["#22d3ee", "#2dd4bf", "#4ade80", "#facc15", "#fb923c", "#f97316", "#ef4444"]

LOGO_URL = "https://raw.githubusercontent.com/mb26-dev/ha-powerbill-forecast/main/custom_components/powerbill_forecast/brand/icon.png"

PAGE = "#e8edf3"
PAPER = "#ffffff"
INK = "#0f172a"
MUTED = "#64748b"
LABEL_BG = "#ecfeff"
LABEL_INK = "#0e7490"
LINE = "#e2e8f0"
BAND = "#0b1220"
ACCENT = "#06b6d4"
TOTAL_BG = "#fefce8"
TOTAL_LINE = "#eab308"
FONT = "Segoe UI,Roboto,Helvetica,Arial,sans-serif"


def tier_color(i: int, n: int) -> str:
    """Same colour ramp as the card: cyan -> green -> yellow -> orange -> red."""
    if n <= 1:
        return PALETTE[0]
    pos = i / (n - 1) * (len(PALETTE) - 1)
    a = int(pos)
    b = min(len(PALETTE) - 1, a + 1)
    f = pos - a
    ca = [int(PALETTE[a][k : k + 2], 16) for k in (1, 3, 5)]
    cb = [int(PALETTE[b][k : k + 2], 16) for k in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * f):02x}" for x, y in zip(ca, cb))


def _rgba(hex_color: str, alpha: float) -> str:
    r, g, b = (int(hex_color[k : k + 2], 16) for k in (1, 3, 5))
    return f"rgba({r},{g},{b},{alpha})"


def _num(v: float | None, d: int = 2) -> str:
    if v is None:
        return "-"
    return f"{v:,.{d}f}"


def _money(v: float | None, sym: str, d: int = 2, html: bool = True) -> str:
    """Amount with the currency symbol; the symbol is escaped for HTML (it can be any text the user typed)."""
    if v is None:
        return "-"
    s = escape(sym) if html else sym
    return f"{s}{_num(v, d)}" if len(sym) <= 2 else f"{_num(v, d)} {s}"


def _day(iso: str) -> date:
    return datetime.fromisoformat(iso).date()


def _last_day(end_iso: str) -> date:
    """Last day of the cycle: the day before a midnight change, the reading day for a meter reading."""
    end = datetime.fromisoformat(end_iso)
    return end.date() - timedelta(days=1) if (end.hour, end.minute, end.second) == (0, 0, 0) else end.date()


def _reading_label(end_iso: str) -> str:
    end = datetime.fromisoformat(end_iso)
    if (end.hour, end.minute, end.second) == (0, 0, 0):
        return f"{end:%d/%m/%Y}"
    return f"{end:%d/%m/%Y %H:%M}"


def _period(start_iso: str, end_iso: str) -> str:
    start = _day(start_iso)
    last = _last_day(end_iso)
    if start.year == last.year:
        return f"{start:%d %b} - {last:%d %b %Y}"
    return f"{start:%d %b %Y} - {last:%d %b %Y}"


def _snapshot(data: dict[str, Any], which: str) -> dict[str, Any] | None:
    if which == "current":
        return {
            "cycle_start": data["cycle_start"],
            "cycle_end": data["cycle_end"],
            "kwh": data["kwh"],
            "ft": data["ft"],
            "ft_period": data.get("ft_period"),
            "tariff": data["tariff"],
            "bill": data["bill"],
            "daily": data.get("daily") or [],
            "before_kwh": data.get("previous_kwh"),
            "before_total": data.get("previous_total"),
            "forecast_bill": data["forecast_bill"],
            "forecast": data["forecast"],
            "history": data.get("history") or [],
        }
    snap = data.get("previous")
    if snap and not snap.get("history"):
        snap = {**snap, "history": [h for h in data.get("history") or [] if not h.get("running")]}
    return snap


def _label_cell(label: str, value: str, width: str) -> str:
    return (
        f'<td width="{width}" valign="top" style="padding:3px;">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border:1px solid {LINE};border-radius:6px;">'
        f'<tr><td style="background:{LABEL_BG};color:{LABEL_INK};font-size:10px;font-weight:700;letter-spacing:.5px;padding:4px 7px;border-radius:6px 6px 0 0;">{label}</td></tr>'
        f'<tr><td style="color:{INK};font-size:14px;font-weight:700;padding:6px 7px;white-space:nowrap;">{value}</td></tr>'
        "</table></td>"
    )


def _charge_row(label: str, detail: str, amount: str, strong: bool = False) -> str:
    weight = "800" if strong else "400"
    size = "14px" if strong else "13px"
    border = f"border-top:2px solid {INK};" if strong else f"border-top:1px solid {LINE};"
    return (
        f'<tr><td style="padding:7px 8px;{border}color:{INK};font-size:{size};font-weight:{weight};">{label}</td>'
        f'<td align="right" style="padding:7px 8px;{border}color:{MUTED};font-size:12px;white-space:nowrap;">{detail}</td>'
        f'<td align="right" style="padding:7px 8px;{border}color:{INK};font-size:{size};font-weight:{weight};white-space:nowrap;">{amount}</td></tr>'
    )


def _history(rows: list[dict[str, Any]]) -> str:
    rows = rows[:6]
    if not rows:
        return ""
    head = "".join(
        f'<td align="center" style="padding:5px 4px;border:1px solid {LINE};font-size:11px;color:{INK};font-weight:700;background:{LABEL_BG if r.get("running") else PAPER};">'
        f'{_day(r["date"] + "T00:00:00"):%d %b %y}</td>'
        for r in rows
    )
    vals = "".join(
        f'<td align="center" style="padding:6px 4px;border:1px solid {LINE};font-size:13px;color:{INK};">{_num(r["kwh"], 0)}</td>'
        for r in rows
    )
    label = f'style="padding:5px 6px;border:1px solid {LINE};font-size:10px;font-weight:700;color:{LABEL_INK};background:{LABEL_BG};white-space:nowrap;"'
    return (
        f'<div style="font-size:12px;font-weight:700;color:{INK};margin:18px 0 6px;">Usage history</div>'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">'
        f"<tr><td {label}>Reading date</td>{head}</tr>"
        f"<tr><td {label}>Consumption (kWh)</td>{vals}</tr></table>"
    )


def _daily(snap: dict[str, Any], tiers: list[dict[str, Any]]) -> str:
    days = snap.get("daily") or []
    if not days:
        return ""
    n = len(tiers)
    top = max((d["kwh"] for d in days), default=0) or 1
    cum = 0.0
    cells = []
    for d in days:
        cum += d["kwh"]
        idx = n - 1
        for k, t in enumerate(tiers):
            if t["to"] is None or cum <= t["to"]:
                idx = k
                break
        h = max(2, round(d["kwh"] / top * 44))
        cells.append(
            f'<td valign="bottom" style="padding:0 1px;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
            f'<tr><td height="{h}" title="{d["date"]}: {d["kwh"]:.1f} kWh" style="height:{h}px;background:{tier_color(idx, n)};border-radius:2px 2px 0 0;font-size:0;line-height:0;">&nbsp;</td></tr></table></td>'
        )
    avg = sum(d["kwh"] for d in days) / len(days)
    return (
        f'<div style="font-size:12px;font-weight:700;color:{INK};margin:18px 0 6px;">Daily energy '
        f'<span style="font-weight:400;color:{MUTED};">&middot; average {_num(avg, 1)} kWh/day, coloured by tier</span></div>'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="height:46px;"><tr>{"".join(cells)}</tr></table>'
    )


def build_report(data: dict[str, Any], which: str = "previous", version: str = "") -> dict[str, Any] | None:
    """Subject, HTML and plain text of the bill report for the finished ('previous') or running cycle."""
    snap = _snapshot(data, which)
    if not snap:
        return None
    sym = data.get("symbol") or ""
    tiers = data["tiers"]
    n = len(tiers)
    bill = snap["bill"]
    period = _period(snap["cycle_start"], snap["cycle_end"])
    month = _last_day(snap["cycle_end"])
    running = which == "current"
    name = escape(data.get("name") or "Powerbill Forecast")
    tariff_name = escape(snap.get("tariff") or "")
    subject = f"⚡ Electricity bill {month:%B %Y}: {_money(bill['total'], sym, html=False)}" + (" (so far)" if running else "")

    info_top = "".join(
        [
            _label_cell("TARIFF", tariff_name.split(" Residential")[0] or "-", "25%"),
            _label_cell("BILL PERIOD", f"{month:%m/%Y}", "25%"),
            # date only: a long, non-wrapping box widens the mail and some clients (Gmail on tablets) then squeeze the charts
            _label_cell("METER READING DATE", f"{datetime.fromisoformat(snap['cycle_end']):%d/%m/%Y}" + (" (next)" if running else ""), "25%"),
            _label_cell("CONSUMPTION", f"{_num(bill['kwh'], 2)} kWh", "25%"),
        ]
    )
    info_bottom = "".join(
        [
            _label_cell("CYCLE", period, "50%"),
            _label_cell("TIER REACHED", f"{bill['current_tier']} of {n}", "25%"),
            _label_cell("AVERAGE PRICE", f"{_money(bill.get('average_price'), sym)}/kWh", "25%"),
        ]
    )

    meter_check = ""
    read_at = _reading_label(snap["cycle_end"])
    parts = [] if running or " " not in read_at else [f"Meter read {read_at}"]
    if snap.get("utility_kwh") is not None and snap.get("ha_kwh"):
        dev = (snap["ha_kwh"] - snap["utility_kwh"]) / snap["utility_kwh"] * 100 if snap["utility_kwh"] else 0.0
        parts.append(
            f'utility meter <b style="color:{INK};">{_num(snap["utility_kwh"], 2)} kWh</b>'
            f' &middot; Home Assistant <b style="color:{INK};">{_num(snap["ha_kwh"], 2)} kWh</b> ({dev:+.1f}%)'
        )
    if parts:
        meter_check = f'<div style="font-size:11px;color:{MUTED};margin:6px 3px 0;">{" &middot; ".join(parts)}</div>'

    rows = []
    tier_lines = []
    for i, r in enumerate(bill["tiers"]):
        if r["kwh"] <= 0:
            continue
        dot = f'<span style="display:inline-block;width:7px;height:7px;border-radius:4px;background:{tier_color(i, n)};margin-right:5px;"></span>'
        upper = "+" if r["to"] is None else f"-{_num(r['to'], 0)}"
        tier_lines.append(
            f'<tr><td style="padding:2px 8px 2px 22px;color:{MUTED};font-size:11px;">{dot}Units {_num(r["from"] + 1, 0)}{upper}</td>'
            f'<td align="right" style="padding:2px 8px;color:{MUTED};font-size:11px;white-space:nowrap;">{_num(r["kwh"], 2)} kWh &times; {_num(r["rate"], 4)}</td>'
            f'<td align="right" style="padding:2px 8px;color:{MUTED};font-size:11px;white-space:nowrap;">{_num(r["cost"])}</td></tr>'
        )
    rows.append(_charge_row("Energy charge", f"{_num(bill['kwh'], 2)} kWh", _num(bill["energy"])))
    rows.extend(tier_lines)
    rows.append(_charge_row("Monthly service charge", "", _num(bill["service_fee"])))
    if snap.get("ft"):
        ft_detail = f"{_num(snap['ft'], 4)} {escape(sym)}/kWh" + (f" &middot; {escape(snap['ft_period'])}" if snap.get("ft_period") else "")
        rows.append(_charge_row("Ft (fuel adjustment)", ft_detail, _num(bill["ft"])))
    rows.append(_charge_row("Total electricity charge", "", _num(bill["subtotal"])))
    if data.get("vat"):
        rows.append(_charge_row(f"VAT {_num(data['vat'], 0)}%", "", _num(bill["vat"])))
    rows.append(_charge_row("Total amount", "", _money(bill["total"], sym), strong=True))

    compare = ""
    if snap.get("before_total"):
        diff = bill["total"] - snap["before_total"]
        pct = diff / snap["before_total"] * 100
        c = "#dc2626" if diff > 0 else "#16a34a"
        arrow = "&#9650;" if diff > 0 else "&#9660;"
        compare = (
            f'<div style="font-size:12px;color:{MUTED};margin-top:6px;">'
            f'<span style="color:{c};font-weight:700;">{arrow} {_num(abs(pct), 0)}%</span> vs. previous bill '
            f'{_money(snap["before_total"], sym)} ({_num(snap.get("before_kwh"), 0)} kWh)</div>'
        )

    forecast = ""
    if running and snap.get("forecast_bill"):
        fb = snap["forecast_bill"]
        forecast = (
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:10px;border:1px dashed {ACCENT};border-radius:8px;">'
            f'<tr><td style="padding:10px 12px;font-size:12px;color:{LABEL_INK};font-weight:700;">FORECAST AT THE METER READING</td>'
            f'<td align="right" style="padding:10px 12px;font-size:18px;font-weight:800;color:{INK};white-space:nowrap;">{_money(fb["total"], sym)}'
            f'<div style="font-size:11px;color:{MUTED};font-weight:400;">{_num(fb["kwh"], 0)} kWh &middot; tier {fb["current_tier"]}/{n}</div></td></tr></table>'
        )

    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>{escape(subject)}</title></head>
<body style="margin:0;padding:0;background:{PAGE};font-family:{FONT};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{PAGE};padding:16px 8px;"><tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:640px;background:{PAPER};border:1px solid #cbd5e1;border-radius:6px;">
<tr><td height="14" style="height:14px;background:{BAND};border-radius:6px 6px 0 0;font-size:0;line-height:0;">&nbsp;</td></tr>
<tr><td style="padding:16px 18px 6px;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
    <td width="52" valign="middle"><img src="{LOGO_URL}" width="44" height="44" alt="Powerbill Forecast" style="display:block;border:0;border-radius:10px;"></td>
    <td valign="middle" style="padding-left:8px;">
      <div style="font-size:17px;font-weight:800;color:{INK};">{name}</div>
      <div style="font-size:11px;color:{MUTED};">Home Assistant &middot; {tariff_name}</div>
    </td>
    <td align="right" valign="middle">
      <div style="font-size:20px;font-weight:800;color:{INK};letter-spacing:.5px;">ELECTRICITY BILL</div>
      <div style="font-size:11px;color:{LABEL_INK};font-weight:700;">{"RUNNING CYCLE - ESTIMATE" if running else "ESTIMATE FROM YOUR METER"}</div>
    </td>
  </tr></table>
</td></tr>
<tr><td style="padding:6px 15px 0;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>{info_top}</tr></table>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>{info_bottom}</tr></table>
  {meter_check}
</td></tr>
<tr><td style="padding:14px 18px 0;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
    <tr><td style="padding:4px 8px;color:{MUTED};font-size:11px;">Item</td><td align="right" style="padding:4px 8px;color:{MUTED};font-size:11px;">Detail</td><td align="right" style="padding:4px 8px;color:{MUTED};font-size:11px;">Amount ({escape(data.get("currency") or sym)})</td></tr>
    {"".join(rows)}
  </table>
</td></tr>
<tr><td style="padding:12px 18px 0;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{TOTAL_BG};border:2px solid {TOTAL_LINE};border-radius:8px;">
    <tr><td style="padding:12px 14px;font-size:13px;font-weight:800;color:{INK};">{"BILL SO FAR" if running else "TOTAL AMOUNT TO PAY"}<div style="font-size:11px;font-weight:400;color:{MUTED};">{period}</div></td>
    <td align="right" style="padding:12px 14px;font-size:26px;font-weight:800;color:{INK};white-space:nowrap;">{_money(bill["total"], sym)}</td></tr>
  </table>
  {compare}
  {forecast}
</td></tr>
<tr><td style="padding:0 18px;">
  {_history(snap.get("history") or [])}
  {_daily(snap, tiers)}
</td></tr>
<tr><td style="padding:16px 18px 18px;">
  <div style="border-top:1px solid {LINE};padding-top:10px;font-size:10px;color:{MUTED};">
    Calculated by Powerbill Forecast{f" {escape(version)}" if version else ""} from your own energy meter in Home Assistant. This is an estimate, not an invoice -
    the utility's meter reading and rounding decide the amount you pay.
  </div>
</td></tr>
</table></td></tr></table></body></html>"""

    lines = [
        subject,
        f"Bill period {month:%m/%Y} · meter reading {_reading_label(snap['cycle_end'])} · {period}",
        f"Consumption: {_num(bill['kwh'], 2)} kWh (tier {bill['current_tier']}/{n})",
        f"Energy charge: {_num(bill['energy'])}",
        *(f"  {_num(r['kwh'], 2)} kWh x {r['rate']} = {_num(r['cost'])}" for r in bill["tiers"] if r["kwh"] > 0),
        f"Monthly service charge: {_num(bill['service_fee'])}",
        f"Ft {snap['ft']}: {_num(bill['ft'])}" if snap.get("ft") else "",
        f"Total electricity charge: {_num(bill['subtotal'])}",
        f"VAT: {_num(bill['vat'])}" if data.get("vat") else "",
        f"Total amount: {_money(bill['total'], sym, html=False)}",
        f"Meter check: utility {_num(snap['utility_kwh'], 2)} kWh, Home Assistant {_num(snap['ha_kwh'], 2)} kWh"
        if snap.get("utility_kwh") is not None and snap.get("ha_kwh")
        else "",
        "Usage history: " + ", ".join(f"{h['date']} {_num(h['kwh'], 0)} kWh" for h in (snap.get("history") or [])[:6]) if snap.get("history") else "",
    ]
    return {
        "subject": subject,
        "html": html,
        "text": "\n".join(line for line in lines if line),
        "cycle_start": snap["cycle_start"],
        "cycle_end": snap["cycle_end"],
        "kwh": bill["kwh"],
        "total": bill["total"],
        "currency": data.get("currency"),
        "closed_at": snap.get("closed_at"),
    }
