"""Pure tariff maths for Powerbill Forecast (no Home Assistant imports, unit-testable)."""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from datetime import date, datetime, timedelta
from html import unescape as html_unescape

INF = float("inf")


@dataclass(frozen=True)
class Tier:
    """One step of a progressive tariff: rate applies up to `limit` kWh per billing cycle."""

    limit: float  # cumulative upper bound in kWh, INF for the last step
    rate: float  # price per kWh


@dataclass(frozen=True)
class Preset:
    """A ready-made tariff."""

    name: str
    tiers: tuple[Tier, ...]
    service_fee: float
    vat: float
    currency: str


# Thailand uses one national residential tariff for PEA and MEA.
# Progressive rates of the ERC, valid from the September 2026 bills (first 200 kWh at 3.00 THB).
_TH_SMALL = (
    Tier(15, 2.3488),
    Tier(25, 2.9882),
    Tier(200, 3.0000),
    Tier(400, 4.1584),
    Tier(INF, 4.3583),
)
_TH_LARGE = (Tier(200, 3.0000), Tier(400, 4.1584), Tier(INF, 4.3583))

PRESETS: dict[str, Preset] = {
    "pea_1_1": Preset("PEA 1.1.1 Residential (up to 150 kWh/month)", _TH_SMALL, 8.19, 7.0, "THB"),
    "pea_1_2": Preset("PEA 1.1.2 Residential (over 150 kWh/month)", _TH_LARGE, 24.62, 7.0, "THB"),
    "mea_1_1": Preset("MEA 1.1 Residential (up to 150 kWh/month)", _TH_SMALL, 8.19, 7.0, "THB"),
    "mea_1_2": Preset("MEA 1.2 Residential (over 150 kWh/month)", _TH_LARGE, 24.62, 7.0, "THB"),
    "custom": Preset("Custom tariff", (Tier(INF, 0.30),), 0.0, 0.0, ""),
}

CURRENCY_SYMBOLS = {
    "THB": "฿", "EUR": "€", "USD": "$", "GBP": "£", "JPY": "¥", "CNY": "¥", "INR": "₹",
    "PHP": "₱", "VND": "₫", "KRW": "₩", "IDR": "Rp", "MYR": "RM", "SGD": "S$", "AUD": "A$",
    "CAD": "C$", "CHF": "CHF", "ZAR": "R", "BRL": "R$", "MXN": "$", "PKR": "₨", "LKR": "Rs",
}


def parse_tiers(text: str) -> tuple[Tier, ...]:
    """Parse '150=3.2484, 400=4.2218, *=4.4217' into tiers.

    Each entry is `<upper kWh>=<price>`; the last entry may use `*` (or be a bare price) for
    "everything above". Separators: comma, semicolon or new line.
    """
    tiers: list[Tier] = []
    raw = [p.strip() for p in text.replace(";", ",").replace("\n", ",").split(",")]
    for part in (p for p in raw if p):
        if "=" in part:
            lim_s, rate_s = (x.strip() for x in part.split("=", 1))
        else:
            lim_s, rate_s = "*", part
        limit = INF if lim_s in ("*", "", "inf", "max") else float(lim_s)
        tiers.append(Tier(limit, float(rate_s)))
    if not tiers:
        raise ValueError("no tiers")
    tiers.sort(key=lambda t: t.limit)
    if any(a.limit >= b.limit for a, b in zip(tiers, tiers[1:])):
        raise ValueError("tier limits must be unique")
    if tiers[0].limit <= 0:
        raise ValueError("tier limits must be positive")
    if tiers[-1].limit != INF:
        tiers.append(Tier(INF, tiers[-1].rate))
    return tuple(tiers)


def format_tiers(tiers: tuple[Tier, ...]) -> str:
    """Inverse of parse_tiers."""
    return ", ".join(f"{'*' if t.limit == INF else f'{t.limit:g}'}={t.rate:g}" for t in tiers)


def _r2(value: float) -> float:
    """Round to satang like a paper bill (half up, not banker's rounding)."""
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def compute_bill(
    kwh: float,
    tiers: tuple[Tier, ...],
    ft: float = 0.0,
    service_fee: float = 0.0,
    vat: float = 0.0,
) -> dict:
    """Bill for `kwh` in one billing cycle: per-tier energy, Ft surcharge, fee and VAT."""
    kwh = max(0.0, float(kwh))
    vat_f = 1 + vat / 100
    rows = []
    lower = 0.0
    energy = 0.0
    current = 1
    for idx, tier in enumerate(tiers, start=1):
        used = max(0.0, min(kwh, tier.limit) - lower)
        cost = used * tier.rate
        energy += cost
        if kwh > lower or idx == 1:
            current = idx
        rows.append(
            {
                "index": idx,
                "from": lower,
                "to": None if tier.limit == INF else tier.limit,
                "rate": tier.rate,
                "kwh": round(used, 4),
                "cost": round(cost, 4),
            }
        )
        lower = tier.limit
    cur = tiers[current - 1]
    next_tier = tiers[current] if current < len(tiers) else None
    # every line is rounded to satang first, then added up - exactly like the utility prints it
    energy = _r2(energy)
    ft_cost = _r2(kwh * ft)
    fee = _r2(service_fee)
    subtotal = _r2(energy + ft_cost + fee)
    vat_cost = _r2(subtotal * vat / 100)
    total = _r2(subtotal + vat_cost)
    return {
        "kwh": round(kwh, 4),
        "tiers": rows,
        "energy": energy,
        "ft": ft_cost,
        "service_fee": fee,
        "subtotal": subtotal,
        "vat": vat_cost,
        "total": total,
        "current_tier": current,
        "tier_count": len(tiers),
        "kwh_to_next_tier": None if next_tier is None else round(cur.limit - kwh, 3),
        "next_rate": None if next_tier is None else next_tier.rate,
        "marginal_price": round((cur.rate + ft) * vat_f, 4),
        "next_marginal_price": None if next_tier is None else round((next_tier.rate + ft) * vat_f, 4),
        "average_price": round(total / kwh, 4) if kwh > 0 else None,
    }


def _clamped(year: int, month: int, day: int) -> date:
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def cycle_bounds(now: datetime, reset_day: int) -> tuple[datetime, datetime]:
    """Start (inclusive) and end (exclusive) of the billing cycle that contains `now`.

    The cycle starts at local midnight of `reset_day` (clamped to short months).
    `now` must be timezone-aware; the result uses the same tzinfo.
    """
    tz = now.tzinfo
    this = _clamped(now.year, now.month, reset_day)
    if now.date() >= this:
        start_d = this
        ny, nm = (now.year + 1, 1) if now.month == 12 else (now.year, now.month + 1)
        end_d = _clamped(ny, nm, reset_day)
    else:
        end_d = this
        py, pm = (now.year - 1, 12) if now.month == 1 else (now.year, now.month - 1)
        start_d = _clamped(py, pm, reset_day)
    start = datetime(start_d.year, start_d.month, start_d.day, tzinfo=tz)
    end = datetime(end_d.year, end_d.month, end_d.day, tzinfo=tz)
    return start, end


def previous_cycle(start: datetime, reset_day: int) -> tuple[datetime, datetime]:
    """The cycle right before the one starting at `start`."""
    return cycle_bounds(start - timedelta(hours=12), reset_day)


def forecast_kwh(
    kwh: float,
    start: datetime,
    end: datetime,
    now: datetime,
    recent_daily: float | None = None,
    fallback_daily: float | None = None,
) -> dict:
    """Project the consumption at the end of the cycle.

    The daily rate blends the cycle average with the last full days (recent behaviour,
    e.g. air conditioning season). Early in a cycle the previous cycle's average helps.
    """
    total_days = (end - start).total_seconds() / 86400
    elapsed = max(0.0, (now - start).total_seconds() / 86400)
    remaining = max(0.0, total_days - elapsed)
    cycle_daily = kwh / elapsed if elapsed >= 0.5 else None

    parts: list[tuple[float, float]] = []
    if cycle_daily is not None:
        parts.append((cycle_daily, min(1.0, elapsed / 7)))
    if recent_daily is not None:
        parts.append((recent_daily, 1.0))
    if fallback_daily is not None:
        parts.append((fallback_daily, max(0.0, 1 - elapsed / 5)))
    weight = sum(w for _, w in parts)
    daily = sum(v * w for v, w in parts) / weight if weight > 0 else 0.0

    return {
        "kwh": round(kwh + daily * remaining, 3),
        "daily_rate": round(daily, 3),
        "cycle_daily": None if cycle_daily is None else round(cycle_daily, 3),
        "days_total": round(total_days, 3),
        "days_elapsed": round(elapsed, 3),
        "days_remaining": round(remaining, 3),
    }


def days_until(kwh_needed: float | None, daily_rate: float) -> float | None:
    """Days until `kwh_needed` more kWh are used at `daily_rate`."""
    if kwh_needed is None or daily_rate <= 0:
        return None
    return round(kwh_needed / daily_rate, 2)


PEA_FT_URL = "https://www.pea.co.th/en/our-services/tariff/ft"

_TAG = re.compile(r"<[^>]+>")
_FT = re.compile(r"Current\s+Ft\s*\(([^)]{3,40})\)\s*(-?\d+(?:\.\d+)?)\s*(THB|Baht|บาท)", re.IGNORECASE)


def parse_pea_ft(html: str) -> tuple[float, str] | None:
    """Read the current Ft (THB per kWh) and its period from the official PEA Ft page.

    The page shows e.g. 'Current Ft (Sep - Dec 2026)<br><span>0.1623</span> THB/Unit'.
    Returns (value, period) or None when the layout is not recognised.
    """
    text = " ".join(html_unescape(_TAG.sub(" ", html)).split())
    match = _FT.search(text)
    if not match:
        return None
    value = float(match.group(2))
    if not -5 < value < 5:  # a Ft of +-5 THB/kWh would be absurd - the layout changed
        return None
    return value, " ".join(match.group(1).split())
