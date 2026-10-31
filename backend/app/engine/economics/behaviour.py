"""Turn the real income layer into the choice model's segments, willingness to pay and participation.

Segments are no longer fixed archetype constants. For a catchment:

* segment share per zone = share of that zone's simulated residents in India's bottom 40 % / middle 40 % / top 20 % of
  monthly per-capita consumption (HCES 2023-24 x Meta RWI rank, see income.py);
* willingness to pay scales with real consumption: WTP_i = p_ref * (x_i / x_ref)^eps_c, where x_ref is urban India's
  median MPCE (HCES 2023-24 Table 3.1, P50) and eps_c is the income elasticity of spending on the category (Engel
  elasticity; health from Dubey 2020, others literature ranges). A segment's median WTP multiplier and the log-spread of
  WTP inside segments (wtp_sigma) are computed from the simulated residents, not chosen;
* participation, where a published penetration rate exists (gym membership, dental visits, private coaching, eating out),
  is anchored to it and scaled by the catchment's income mix: pi_local = pi_india * E_local[(x/x_ref)^eps] / E_india[...].

Every value carries its source and status; anything without published evidence stays an explicit assumption.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from ...categories.archetypes import Archetype, Segment
from .income import CLASS_EDGES, CLASS_KEYS, IncomeContext, curve, national

CLASS_LABELS = ("Bottom 40% of India by spend", "Middle 40%", "Top 20%")
X_REF_NOTE = "urban India median MPCE, HCES 2023-24 Table 3.1"

# Income elasticity of category spending (value, low, high, status, source).
ELASTICITY = {
    "health": (0.25, 0.11, 0.84, "literature", "Dubey (2020) NIPFP WP 324, Tables 3-4: health spending is a necessity in India"),
    "membership": (1.2, 0.9, 1.6, "assumption", "Services are luxuries in India (Nayyar 2009); no published point estimate"),
    "dine_in": (1.2, 0.9, 1.6, "assumption", "Eating out rises faster than income (HCES processed-food share 4.2% -> 9.8% rural, 1999-2024)"),
    "takeaway": (1.0, 0.7, 1.4, "assumption", "No published India estimate"),
    "retail": (0.8, 0.5, 1.1, "assumption", "Mostly necessities; no published India estimate for the store category"),
    "appointment": (1.0, 0.6, 1.4, "assumption", "No published India estimate"),
    "lodging": (1.5, 1.0, 2.0, "assumption", "No published India estimate"),
}
TASTE_SIGMA = (0.3, 0.2, 0.45)  # log-sd of WTP among people with the same consumption (assumption)
HEALTH_KEYS = {"dentist", "clinic", "physio", "diagnostics", "pharmacy", "optician"}

# Published penetration / frequency evidence by category key.
#   kind "share": monthly participation share of all residents (value, low, high)
PARTICIPATION = {
    "gym": ((0.008, 0.006, 0.012), "industry",
            "Deloitte & Health and Fitness Association, India Fitness Market Report 2025: 12.3 m members = 0.8% of population (2024)"),
    "dentist": ((0.0226, 0.015, 0.026), "derived",
                "Talukdar et al. (2022) Health Promot Perspect 12(4): 24% of Indian adults visit a dentist in a year -> 1-(1-0.24)^(1/12) per month"),
}
FREQUENCY = {
    "cafe": ((3.7, 3.0, 6.0), "industry", "NRAI India Food Services Report 2024: urban consumers dine out ~3.7 times a month"),
    "restaurant": ((3.7, 3.0, 6.0), "industry", "NRAI India Food Services Report 2024: urban consumers dine out ~3.7 times a month"),
}
# Private coaching: share of *students* (NSO CMS: Education 2025, Statement 3.1) x school-age share of residents (WorldPop).
COACHING = {"rural": 0.255, "urban": 0.307, "source": "NSO Comprehensive Modular Survey: Education 2025, Statement 3.1 (rural 25.5%, urban 30.7% of students)"}


@dataclass
class BehaviourEvidence:
    segments: tuple[Segment, ...]
    zone_shares: np.ndarray  # [Z, S]
    params: dict[str, tuple[float, float, float, str, str]]  # name -> (value, low, high, status, source)
    elasticity: tuple
    x_ref: float
    summary: dict


def _elasticity(arch: Archetype, category_key: str | None) -> tuple:
    return ELASTICITY["health"] if category_key in HEALTH_KEYS else ELASTICITY[arch.key]


def school_age_share(age_sex: dict | None) -> float | None:
    bands = (age_sex or {}).get("bands") or []
    if len(bands) != 17:
        return None
    tot = sum(b["male"] + b["female"] for b in bands)
    kids = sum(b["male"] + b["female"] for b in bands[1:5])  # 5-9 .. 20-24
    return kids / tot if tot > 0 else None


def build(arch: Archetype, category_key: str | None, ctx: IncomeContext, n_zones: int, *, age_sex: dict | None = None,
          samples_per_zone: int = 300, seed: int = 0) -> BehaviourEvidence:
    rng = np.random.default_rng(seed + 9001)
    zi = np.repeat(np.arange(n_zones), samples_per_zone)
    x, u = ctx.draw(rng, zi)
    eps, eps_lo, eps_hi, eps_status, eps_src = _elasticity(arch, category_key)
    x_ref = _urban_median()
    mult = (x / x_ref) ** eps

    cls = np.digitize(u, CLASS_EDGES[1:-1])  # 0,1,2
    zone_shares = np.zeros((n_zones, 3))
    np.add.at(zone_shares, (zi, cls), 1.0)
    zone_shares /= np.maximum(zone_shares.sum(1, keepdims=True), 1)
    glob = zone_shares.mean(0)

    segs, within = [], []
    by_key = {s.key: s for s in arch.segments}
    for k, key in enumerate(CLASS_KEYS):
        m = mult[cls == k]
        base = by_key.get(key) or arch.segments[min(k, len(arch.segments) - 1)]
        wtp = float(np.median(m)) if m.size else float(base.wtp_multiplier)
        if m.size > 5:
            within.append(np.log(m).std())
        segs.append(Segment(key, CLASS_LABELS[k], float(glob[k]), round(wtp, 4), base.price_sensitivity, base.distance_tolerance))
    s_inc = float(np.mean(within)) if within else 0.0
    sigma = float(np.clip(np.hypot(s_inc, TASTE_SIGMA[0]), 0.12, 0.9))
    lo, hi = np.hypot(s_inc, TASTE_SIGMA[1]), np.hypot(s_inc, TASTE_SIGMA[2])

    params: dict[str, tuple] = {"wtp_sigma": (sigma, float(lo), float(hi), "derived",
                                              f"WTP spread inside a consumption class = sqrt(income part {s_inc:.2f}^2 + taste part "
                                              f"{TASTE_SIGMA[0]}^2). Income part from simulated residents' HCES-based MPCE x elasticity {eps:g}; "
                                              "taste part is an assumption")}
    # national reference for income-scaled participation
    nat = national()
    xn = nat.ppf((np.arange(4000) + 0.5) / 4000)
    lift = float(mult.mean() / ((xn / x_ref) ** eps).mean())
    if category_key in PARTICIPATION:
        (v, lo, hi), status, src = PARTICIPATION[category_key]
        params["participation"] = (v * lift, lo * lift, hi * lift, status,
                                   f"{src}; scaled x{lift:.2f} for this catchment's income mix (elasticity {eps:g})")
    elif category_key == "coaching_centre":
        kids = school_age_share(age_sex)
        if kids:
            v = COACHING[ctx.sector] * kids
            params["participation"] = (v, v * 0.85, v * 1.15, "derived",
                                       f"{COACHING['source']} x school-age share {kids:.1%} of residents (WorldPop age structure)")
    if category_key in FREQUENCY:
        (v, lo, hi), status, src = FREQUENCY[category_key]
        params["frequency"] = (v, lo, hi, status, src)

    nat_u = (np.arange(4000) + 0.5) / 4000
    summary = {
        "method": ctx.method, "state": ctx.state, "sector": ctx.sector, "curve": ctx.curve_key, "curve_fit_error": round(ctx.fit_error, 4),
        "between_tile_loading": ctx.loading, "provenance": ctx.provenance,
        "median_mpce": round(float(np.median(x))), "mean_mpce": round(float(x.mean())),
        "p10_mpce": round(float(np.percentile(x, 10))), "p90_mpce": round(float(np.percentile(x, 90))),
        "india_median_mpce": round(float(nat.ppf(0.5))), "x_ref": round(x_ref), "x_ref_note": X_REF_NOTE,
        "classes": [{"key": k, "label": lab, "share": round(float(glob[i]), 4), "india_share": round(CLASS_EDGES[i + 1] - CLASS_EDGES[i], 2),
                     "mpce_range": [round(float(nat.ppf(max(CLASS_EDGES[i], 1e-3)))), round(float(nat.ppf(min(CLASS_EDGES[i + 1], 0.999))))],
                     "wtp_multiplier": segs[i].wtp_multiplier}
                    for i, (k, lab) in enumerate(zip(CLASS_KEYS, CLASS_LABELS))],
        "elasticity": {"value": eps, "low": eps_lo, "high": eps_hi, "status": eps_status, "source": eps_src},
        "participation_lift": round(lift, 3),
        "histogram": _hist(x),
        "national_histogram": _hist(nat.ppf(nat_u)),
    }
    return BehaviourEvidence(tuple(segs), zone_shares, params, (eps, eps_lo, eps_hi), x_ref, summary)


def _urban_median() -> float:
    return float(curve("urban").median)


HIST_EDGES = [0, 1500, 2000, 2500, 3000, 3500, 4000, 5000, 6000, 7500, 10000, 15000, 25000, 1e9]


def _hist(x: np.ndarray) -> list[dict]:
    h, _ = np.histogram(x, bins=HIST_EDGES)
    h = h / max(h.sum(), 1)
    return [{"lo": HIST_EDGES[i], "hi": HIST_EDGES[i + 1] if HIST_EDGES[i + 1] < 1e8 else None, "share": round(float(v), 4)} for i, v in enumerate(h)]


def apply(arch: Archetype, ev: BehaviourEvidence | None) -> Archetype:
    return arch if ev is None else replace(arch, segments=ev.segments)
