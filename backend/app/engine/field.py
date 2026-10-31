"""Ground-truth field research -> model evidence.

A StrataIQ field researcher (matched to the project's industry) visits the catchment and records:

* ``interview``  — street-intercept interviews: does the person use this category, how often, the most they would pay,
  how far they travel for it;
* ``competitor`` — a visited competitor: observed price and quality (these become Competitor rows, see api/field.py);
* ``footfall``   — a timed people count at the candidate site;
* ``rent``       — a quoted rent for the site.

Interviews are turned into evidence for four agent parameters, each with an interval so Monte Carlo keeps the sampling
uncertainty. The evidence tuple shape is the one ``ResolvedParams.from_archetype`` already accepts:
``(value, low, high, status, source)``. Field evidence overrides published/derived evidence; explicit user overrides
still win. Thresholds are deliberately conservative: a parameter is only replaced when enough answers support it.

Intercept samples are not random samples of the catchment (people near the site are over-represented), so every
source string says so, and the intervals are 90 % intervals that widen with small n.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

Z90 = 1.6449
MIN_N = {"participation": 8, "frequency": 5, "max_km": 6, "wtp_sigma": 6}
BIAS_NOTE = "street-intercept sample near the site, not a random sample of the catchment"


@dataclass
class FieldSummary:
    evidence: dict[str, tuple[float, float, float, str, str]]
    counts: dict[str, int]
    interviews: dict
    footfall: dict | None
    rent: dict | None
    competitor_prices: list[float]
    notes: list[str]

    def public(self) -> dict:
        return {
            "params": {k: {"value": round(v[0], 4), "low": round(v[1], 4), "high": round(v[2], 4), "status": v[3], "source": v[4]}
                       for k, v in self.evidence.items()},
            "counts": self.counts, "interviews": self.interviews, "footfall": self.footfall, "rent": self.rent,
            "competitor_prices": {"n": len(self.competitor_prices),
                                  "median": round(float(np.median(self.competitor_prices)), 2) if self.competitor_prices else None},
            "notes": self.notes,
        }


def wilson(k: int, n: int, z: float = Z90) -> tuple[float, float]:
    if n <= 0:
        return 0.0, 1.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def _num(x) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) and v >= 0 else None


def field_evidence(records: list[dict], frequency_fixed: bool = False) -> FieldSummary:
    """records: [{"kind": str, "data": dict}]. ``frequency_fixed`` is True for archetypes whose frequency is structural
    (memberships, lodging) so interview visit counts must not replace it."""
    by: dict[str, list[dict]] = {}
    for r in records:
        by.setdefault(r.get("kind", ""), []).append(r.get("data") or {})
    ev: dict[str, tuple[float, float, float, str, str]] = {}
    notes: list[str] = []

    iv = by.get("interview", [])
    n = len(iv)
    users = [d for d in iv if d.get("uses_category") is True]
    k = len(users)
    out_iv: dict = {"n": n, "users": k}
    if n >= MIN_N["participation"]:
        lo, hi = wilson(k, n)
        p = min(0.95, max(0.005, k / n))
        ev["participation"] = (p, max(0.002, lo), min(0.98, max(hi, p)), "field",
                               f"Field interviews: {k} of {n} use the category ({BIAS_NOTE})")
    elif n:
        notes.append(f"{n} interview(s) so far: {MIN_N['participation']} needed before participation is replaced.")

    freqs = [v for v in (_num(d.get("visits_per_month")) for d in users) if v is not None and v <= 60]
    out_iv["visits_per_month_mean"] = round(float(np.mean(freqs)), 2) if freqs else None
    if not frequency_fixed and len(freqs) >= MIN_N["frequency"]:
        m = float(np.mean(freqs))
        se = float(np.std(freqs, ddof=1)) / math.sqrt(len(freqs)) if len(freqs) > 1 else m * 0.3
        if m > 0:
            ev["frequency"] = (m, max(0.1, m - Z90 * se), m + Z90 * se, "field",
                               f"Field interviews: mean of {len(freqs)} users' stated visits per month ({BIAS_NOTE})")

    dists = [v for v in (_num(d.get("travel_km")) for d in users) if v is not None and 0 < v <= 50]
    out_iv["travel_km_p80"] = round(float(np.percentile(dists, 80)), 2) if dists else None
    if len(dists) >= MIN_N["max_km"]:
        p80 = float(np.percentile(dists, 80))
        ev["max_km"] = (max(0.3, p80), max(0.2, float(np.percentile(dists, 60))), max(p80, float(np.percentile(dists, 95))), "field",
                        f"Field interviews: 80th percentile of {len(dists)} stated travel distances")

    prices = [v for v in (_num(d.get("max_price")) for d in iv) if v is not None and v > 0]
    out_iv["max_price_median"] = round(float(np.median(prices)), 2) if prices else None
    if len(prices) >= MIN_N["wtp_sigma"]:
        s = float(np.std(np.log(prices), ddof=1))
        s = min(1.0, max(0.15, s))
        ev["wtp_sigma"] = (s, s * 0.8, s * 1.25, "field",
                           f"Field interviews: log-spread of {len(prices)} stated maximum prices")

    modes: dict[str, int] = {}
    for d in users:
        m = str(d.get("travel_mode") or "").strip()
        if m:
            modes[m] = modes.get(m, 0) + 1
    out_iv["travel_modes"] = modes

    ff = by.get("footfall", [])
    rates = [c / mins * 60 for c, mins in ((_num(d.get("count")), _num(d.get("minutes"))) for d in ff) if c is not None and mins]
    footfall = {"sessions": len(rates), "people_per_hour": round(float(np.mean(rates)), 1)} if rates else None
    if footfall:
        notes.append("Footfall is recorded as evidence for your decision; the model does not convert it into demand.")

    rents = [v for v in (_num(d.get("monthly_rent")) for d in by.get("rent", [])) if v]
    rent = {"quotes": len(rents), "median": round(float(np.median(rents)), 2), "min": min(rents), "max": max(rents)} if rents else None

    cprices = [v for v in (_num(d.get("price")) for d in by.get("competitor", [])) if v]
    counts = {k2: len(v) for k2, v in by.items()}
    return FieldSummary(ev, counts, out_iv, footfall, rent, cprices, notes)
