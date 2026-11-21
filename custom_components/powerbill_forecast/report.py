"""Bill report e-mail in the design of the card (pure functions, no Home Assistant imports).

E-mail clients are picky: only tables, inline styles, rgba() colours, no flexbox, no CSS variables.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from html import escape
from typing import Any

PALETTE = ["#22d3ee", "#2dd4bf", "#4ade80", "#facc15", "#fb923c", "#f97316", "#ef4444"]

BG = "#070b16"
CARD = "#0d1526"
PANEL = "#111c33"
LINE = "rgba(148,163,184,0.18)"
TEXT = "#e2e8f0"
MUTED = "#94a3b8"
GOLD = "#fde047"
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


def _money(v: float | None, sym: str, d: int = 2) -> str:
    if v is None:
        return "-"
    return f"{sym}{_num(v, d)}" if len(sym) <= 2 else f"{_num(v, d)} {sym}"


def _day(iso: str) -> date:
    return datetime.fromisoformat(iso).date()


def _period(start_iso: str, end_iso: str) -> str:
    start = _day(start_iso)
    last = _day(end_iso) - timedelta(days=1)
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
        }
    return data.get("previous")


def _stairs(bill: dict[str, Any], tiers: list[dict[str, Any]], sym: str) -> str:
    n = len(tiers)
    rates = [t["rate"] for t in tiers]
    lo, hi = min(rates), max(rates)
    cells, labels = [], []
    for i, (t, row) in enumerate(zip(tiers, bill["tiers"])):
        color = tier_color(i, n)
        h = 34 + (round((t["rate"] - lo) / (hi - lo) * 70) if hi > lo else 0) + i * 6
        used = row["kwh"] > 0
        active = bill["current_tier"] == i + 1
        span = (t["to"] - row["from"]) if t["to"] is not None else None
        fill = 100 if span is None and used else (min(100, round(row["kwh"] / span * 100)) if span else 0)
        glow = f"box-shadow:0 0 14px {_rgba(color, 0.7)};" if active else ""
        fill_h = round(h * fill / 100)
        empty_h = h - fill_h
        block = (
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'style="border:1px solid {color};border-radius:4px;{glow}">'
            + (f'<tr><td height="{empty_h}" style="height:{empty_h}px;background:{_rgba(color, 0.08)};font-size:0;line-height:0;">&nbsp;</td></tr>' if empty_h else "")
            + (f'<tr><td height="{fill_h}" style="height:{fill_h}px;background:{color};font-size:0;line-height:0;">&nbsp;</td></tr>' if fill_h else "")
            + "</table>"
        )
        cells.append(f'<td valign="bottom" style="padding:0 3px;">{block}</td>')
        rng = f"{_num(row['from'], 0)}+" if t["to"] is None else f"{_num(row['from'] + (1 if row['from'] else 0), 0)}-{_num(t['to'], 0)}"
        weight = "700" if active else "400"
        labels.append(
            f'<td align="center" style="padding:6px 2px 0;font-size:11px;color:{TEXT if active else MUTED};font-weight:{weight};">'
            f'{rng}<br><span style="color:{color};font-weight:700;">{_money(t["rate"], sym, 2 if n > 4 else 4)}</span>'
            f'<br><span style="color:{MUTED};">{_num(row["kwh"], 1)} kWh</span></td>'
        )
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>{"".join(cells)}</tr>'
        f'<tr>{"".join(labels)}</tr></table>'
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
        color = tier_color(idx, n)
        h = max(2, round(d["kwh"] / top * 56))
        cells.append(
            f'<td valign="bottom" style="padding:0 1px;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
            f'<tr><td height="{h}" title="{d["date"]}: {d["kwh"]:.1f} kWh" style="height:{h}px;background:{color};border-radius:2px 2px 0 0;font-size:0;line-height:0;">&nbsp;</td></tr></table></td>'
        )
    avg = sum(d["kwh"] for d in days) / len(days)
    return (
        f'<div style="font-size:12px;color:{MUTED};margin:18px 0 6px;">Daily energy &middot; average {_num(avg, 1)} kWh/day</div>'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="height:58px;"><tr>{"".join(cells)}</tr></table>'
    )


def _row(label: str, kwh: str, rate: str, amount: str, strong: bool = False, color: str = TEXT) -> str:
    weight = "800" if strong else "400"
    border = f"border-top:1px solid {_rgba('#facc15', 0.45)};" if strong else f"border-top:1px solid {LINE};"
    size = "14px" if strong else "12px"
    return (
        f'<tr><td style="padding:7px 8px;{border}color:{color};font-size:{size};font-weight:{weight};">{label}</td>'
        f'<td align="right" style="padding:7px 8px;{border}color:{TEXT};font-size:{size};font-weight:{weight};">{kwh}</td>'
        f'<td align="right" style="padding:7px 8px;{border}color:{MUTED};font-size:12px;">{rate}</td>'
        f'<td align="right" style="padding:7px 8px;{border}color:{color if strong else TEXT};font-size:{size};font-weight:{weight};white-space:nowrap;">{amount}</td></tr>'
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
    color = tier_color(bill["current_tier"] - 1, n)
    period = _period(snap["cycle_start"], snap["cycle_end"])
    month = _day(snap["cycle_end"]) - timedelta(days=1)
    running = which == "current"
    name = escape(data.get("name") or "Powerbill Forecast")
    subject = f"⚡ Electricity bill {month:%B %Y}: {_money(bill['total'], sym)}" + (" (so far)" if running else "")

    # comparison with the cycle before
    compare = ""
    if snap.get("before_total"):
        diff = bill["total"] - snap["before_total"]
        pct = diff / snap["before_total"] * 100
        up = diff > 0
        c = "#f87171" if up else "#4ade80"
        arrow = "&#9650;" if up else "&#9660;"
        compare = (
            f'<span style="color:{c};font-weight:700;">{arrow} {_num(abs(pct), 0)}%</span>'
            f' <span style="color:{MUTED};">vs. {_money(snap["before_total"], sym)} / {_num(snap.get("before_kwh"), 0)} kWh</span>'
        )

    rows = []
    for i, r in enumerate(bill["tiers"]):
        if r["kwh"] <= 0:
            continue
        dot = f'<span style="display:inline-block;width:8px;height:8px;border-radius:4px;background:{tier_color(i, n)};margin-right:6px;"></span>'
        rows.append(_row(f"{dot}Tier {i + 1}", _num(r["kwh"], 2), _money(r["rate"], sym, 4), _money(r["cost"], sym)))
    rows.append(_row("Energy", _num(bill["kwh"], 2), "", _money(bill["energy"], sym)))
    ft_label = "Ft surcharge" + (f' <span style="color:{MUTED};font-size:11px;">({escape(snap["ft_period"])})</span>' if snap.get("ft_period") else "")
    if snap.get("ft"):
        rows.append(_row(ft_label, _num(bill["kwh"], 2), _money(snap["ft"], sym, 4), _money(bill["ft"], sym)))
    rows.append(_row("Service fee", "", "", _money(bill["service_fee"], sym)))
    rows.append(_row("Subtotal", "", "", _money(bill["subtotal"], sym)))
    if data.get("vat"):
        rows.append(_row(f"VAT {_num(data['vat'], 0)}%", "", "", _money(bill["vat"], sym)))
    rows.append(_row("Total", _num(bill["kwh"], 2), "", _money(bill["total"], sym), strong=True, color=GOLD))

    forecast = ""
    if running and snap.get("forecast_bill"):
        fb = snap["forecast_bill"]
        fc_color = tier_color(fb["current_tier"] - 1, n)
        forecast = (
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:14px;background:{PANEL};border:1px solid {_rgba("#facc15", 0.3)};border-radius:12px;">'
            f'<tr><td style="padding:12px 14px;font-size:12px;color:{MUTED};">FORECAST AT THE METER READING</td>'
            f'<td align="right" style="padding:12px 14px;font-size:20px;font-weight:800;color:{fc_color};">{_money(fb["total"], sym)}'
            f'<div style="font-size:11px;color:{MUTED};font-weight:400;">{_num(fb["kwh"], 0)} kWh &middot; tier {fb["current_tier"]}/{n}</div></td></tr></table>'
        )

    avg = bill.get("average_price")
    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>{escape(subject)}</title></head>
<body style="margin:0;padding:0;background:{BG};font-family:{FONT};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{BG};padding:14px 8px;"><tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:640px;background:{CARD};border:1px solid {_rgba('#38bdf8', 0.35)};border-radius:16px;">
<tr><td style="padding:18px 18px 8px;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
    <td style="font-size:18px;font-weight:700;color:{TEXT};"><span style="color:{GOLD};">&#9889;</span> {name}</td>
    <td align="right"><span style="display:inline-block;padding:4px 10px;border-radius:999px;border:1px solid {color};background:{_rgba(color, 0.15)};color:{color};font-size:11px;font-weight:700;white-space:nowrap;">{"RUNNING CYCLE" if running else "BILL REPORT"}</span></td>
  </tr></table>
  <div style="font-size:12px;color:{MUTED};margin-top:4px;">{period} &middot; {escape(snap.get("tariff") or "")}</div>
</td></tr>
<tr><td style="padding:8px 18px 0;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
    <td width="58%" valign="top" style="background:{PANEL};border:1px solid {_rgba(color, 0.45)};border-radius:14px;padding:14px;">
      <div style="font-size:11px;letter-spacing:1px;color:{MUTED};">{"BILL SO FAR" if running else "TOTAL TO PAY"}</div>
      <div style="font-size:32px;font-weight:800;color:{color};line-height:1.2;">{_money(bill["total"], sym)}</div>
      <div style="font-size:12px;margin-top:2px;">{compare}</div>
    </td>
    <td width="4%"></td>
    <td width="38%" valign="top" style="background:{PANEL};border:1px solid {LINE};border-radius:14px;padding:14px;">
      <div style="font-size:11px;letter-spacing:1px;color:{MUTED};">ENERGY</div>
      <div style="font-size:20px;font-weight:800;color:{TEXT};line-height:1.3;white-space:nowrap;">{_num(bill["kwh"], 1)} kWh</div>
      <div style="font-size:12px;color:{MUTED};">&Oslash; {_money(avg, sym)}/kWh &middot; tier {bill["current_tier"]}/{n}</div>
    </td>
  </tr></table>
  {forecast}
</td></tr>
<tr><td style="padding:18px 18px 0;">
  <div style="font-size:12px;color:{MUTED};margin-bottom:8px;">Tier staircase</div>
  {_stairs(bill, tiers, sym)}
  {_daily(snap, tiers)}
</td></tr>
<tr><td style="padding:18px 18px 6px;">
  <div style="font-size:12px;color:{MUTED};margin-bottom:6px;">Bill details - compare with your paper bill</div>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
    <tr><td style="padding:4px 8px;color:{MUTED};font-size:11px;">Item</td><td align="right" style="padding:4px 8px;color:{MUTED};font-size:11px;">kWh</td><td align="right" style="padding:4px 8px;color:{MUTED};font-size:11px;">Rate</td><td align="right" style="padding:4px 8px;color:{MUTED};font-size:11px;">Amount</td></tr>
    {"".join(rows)}
  </table>
</td></tr>
<tr><td style="padding:12px 18px 18px;font-size:10px;color:#64748b;border-top:1px solid {LINE};">
  Calculated by Powerbill Forecast{f" {escape(version)}" if version else ""} from your energy meter in Home Assistant. The utility's own meter reading and rounding decide the final amount.
</td></tr>
</table></td></tr></table></body></html>"""

    lines = [
        subject,
        period,
        f"Energy: {_num(bill['kwh'], 2)} kWh (tier {bill['current_tier']}/{n})",
        *(f"Tier {r['index']}: {_num(r['kwh'], 2)} kWh x {r['rate']} = {_num(r['cost'])}" for r in bill["tiers"] if r["kwh"] > 0),
        f"Ft: {_num(bill['ft'])}" if snap.get("ft") else "",
        f"Service fee: {_num(bill['service_fee'])}",
        f"VAT: {_num(bill['vat'])}" if data.get("vat") else "",
        f"Total: {_money(bill['total'], sym)}",
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
    }
