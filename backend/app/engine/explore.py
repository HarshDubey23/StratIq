"""Decision search on top of the choice model: where to open, and which strategy to run.

Both searches use the same customer-choice model as every scenario (point estimates, no Monte Carlo) so thousands
of options can be compared in about a second; the best ones are then re-checked with Monte Carlo risk and, on demand,
with the 10,000-agent simulation.

Capacity is not free: when capacity is scaled, payroll and utilities scale with it, rent rises by half the increase
(more space or a second shift), and startup cost rises by 35% of the original per 100% added. These are documented
assumptions, shown with every result.
"""
from __future__ import annotations

import math
from dataclasses import replace

import numpy as np

from ..categories.archetypes import Archetype
from .finance import economics, fixed_costs
from .geo import distance_matrix_km, haversine_km
from .model import BusinessInputs, Competitor, MarketArrays, ResolvedParams, Zone, build_arrays, run_choice

CAPACITY_COST_NOTE = ("Scaling capacity by s multiplies payroll and utilities by s, rent by 1 + (s - 1)/2 and adds "
                      "35% of startup cost per 100% added. Assumptions — replace with real quotes.")


def scaled_business(arch: Archetype, biz: BusinessInputs, s: float) -> BusinessInputs:
    """The business with throughput scaled by s, and the costs that come with it."""
    if abs(s - 1.0) < 1e-9:
        return biz
    cap = dict(biz.capacity or {})
    for f in arch.capacity_fields:
        base = cap.get(f.key, f.default)
        if base is not None and "days" not in f.key:
            cap[f.key] = float(base) * s
            break
    return replace(biz, capacity=cap, payroll=biz.payroll * s, utilities=biz.utilities * s,
                   rent=biz.rent * (1 + 0.5 * (s - 1)), startup_cost=biz.startup_cost * (1 + 0.35 * max(0.0, s - 1)))


def _vcu(biz: BusinessInputs, pv: dict, price: float) -> float:
    if biz.variable_cost_per_unit is not None and biz.variable_cost_per_unit >= 0:
        return float(biz.variable_cost_per_unit)
    return price * float(pv["variable_cost_ratio"][0])


def _econ(arch: Archetype, b: BusinessInputs, demand: float, pv: dict) -> dict:
    capacity = float(arch.capacity_units(b.capacity))
    units = min(demand, capacity)
    fx = fixed_costs(b.rent, b.payroll, b.utilities, b.other_fixed, b.marketing_spend)
    e = economics(units, b.price, _vcu(b, pv, b.price), fx["total"], b.startup_cost, capacity)
    pb = float(e["payback_months"])
    return {"demand": round(demand, 1), "units": round(units, 1), "capacity": round(capacity, 1), "revenue": round(float(e["revenue"])),
            "profit": round(float(e["operating_profit"])), "fixed_cost": round(fx["total"]),
            "payback_months": None if not math.isfinite(pb) else round(pb, 1), "startup_cost": round(b.startup_cost)}


def risk(arch: Archetype, m: MarketArrays, b: BusinessInputs, params: ResolvedParams, draws: int = 300, seed: int = 7) -> dict:
    """Monte Carlo over the uncertain behaviour assumptions for one option: chance of a loss month and P10/P90 profit."""
    rng = np.random.default_rng(seed)
    pd = params.draws(draws, rng)
    if b.variable_cost_per_unit is None:
        vr = params.ranges["variable_cost_ratio"]
        pd["variable_cost_ratio"] = rng.triangular(vr[0], min(max(params.values["variable_cost_ratio"], vr[0]), vr[1]), vr[1], size=draws)
    prices_arr = m.prices.copy()
    prices_arr[0] = b.price
    r = run_choice(arch, replace(m, prices=prices_arr), b, pd)
    capacity = float(arch.capacity_units(b.capacity))
    units = np.minimum(r["units_by_alt"][:, 0], capacity)
    vcu = np.full(draws, float(b.variable_cost_per_unit)) if b.variable_cost_per_unit is not None else b.price * pd["variable_cost_ratio"]
    fx = fixed_costs(b.rent, b.payroll, b.utilities, b.other_fixed, b.marketing_spend)["total"]
    profit = units * (b.price - vcu) - fx
    return {"prob_loss": round(float((profit < 0).mean()), 3), "profit_p10": round(float(np.percentile(profit, 10))),
            "profit_p90": round(float(np.percentile(profit, 90)))}


# ---------------------------------------------------------------- where to open
def site_scan(arch: Archetype, zones: list[Zone], comps: list[Competitor], biz: BusinessInputs, params: ResolvedParams,
              radius_km: float, max_candidates: int = 160) -> dict:
    """Score candidate sites (populated zone centres inside the catchment) for the same business and strategy."""
    m0 = build_arrays(arch, zones, comps, biz, params)
    b0 = replace(biz, reference_price=m0.ref_price)
    pv = params.draws(1, None)
    zl = np.array([z.lat for z in zones])
    zg = np.array([z.lng for z in zones])
    w = m0.weight
    d_site = haversine_km(biz.lat, biz.lng, zl, zg)
    # Candidates: populated cells in the inner 70% of the catchment (edge sites would see a cut-off market).
    ok = (w > 0) & (d_site <= 0.7 * radius_km)
    idx = np.where(ok)[0]
    if idx.size > max_candidates:
        idx = idx[np.argsort(-w[idx])[:max_candidates]]
    cand = [(float(biz.lat), float(biz.lng), "current")] + [(float(zl[i]), float(zg[i]), "zone") for i in idx]
    comp_d = m0.dist_km[:, 1:]
    clat = np.array([c.lat for c in comps]) if comps else np.zeros(0)
    clng = np.array([c.lng for c in comps]) if comps else np.zeros(0)
    d_c = distance_matrix_km(zl, zg, [c[0] for c in cand], [c[1] for c in cand]) * params.values["circuity"]
    d_c = np.maximum(d_c, 0.15)
    out = []
    for k, (la, ln, kind) in enumerate(cand):
        m = MarketArrays(dist_km=np.concatenate([d_c[:, k:k + 1], comp_d], axis=1), weight=w, prices=m0.prices, price_known=m0.price_known,
                         quality=m0.quality, quality_known=m0.quality_known, ref_price=m0.ref_price, ref_price_status=m0.ref_price_status)
        r = run_choice(arch, m, b0, pv)
        e = _econ(arch, b0, float(r["units_by_alt"][0, 0]), pv)
        dc = haversine_km(la, ln, clat, clng) if comps else np.zeros(0)
        near_pop = float(w[haversine_km(la, ln, zl, zg) <= 1.0].sum())
        out.append({"lat": round(la, 6), "lng": round(ln, 6), "current": kind == "current", **e,
                    "nearest_competitor_km": round(float(dc.min()), 2) if dc.size else None,
                    "competitors_within_500m": int((dc <= 0.5).sum()) if dc.size else 0,
                    "people_within_1km": round(near_pop),
                    "from_current_km": round(float(haversine_km(biz.lat, biz.lng, la, ln)), 2)})
    cur = out[0]
    ranked = sorted(out[1:], key=lambda x: (-x["profit"], -x["demand"]))
    # keep the top sites at least ~350 m apart so the shortlist offers real alternatives
    top: list[dict] = []
    for s in ranked:
        if all(haversine_km(s["lat"], s["lng"], t["lat"], t["lng"]) > 0.35 for t in top):
            top.append(s)
        if len(top) == 5:
            break
    best = top[0] if top else cur
    for site in [cur, *top[:3]]:
        dd = distance_matrix_km(zl, zg, [site["lat"]], [site["lng"]]) * params.values["circuity"]
        mm = replace(m0, dist_km=np.concatenate([np.maximum(dd, 0.15), comp_d], axis=1))
        site["risk"] = risk(arch, mm, b0, params)
    return {"current": cur, "top": top, "candidates": out[1:],
            "uplift_profit": best["profit"] - cur["profit"], "uplift_demand": round(best["demand"] - cur["demand"], 1),
            "method": ("Same business, price, costs and strategy evaluated at every populated cell in the inner 70% of the catchment "
                       "with the customer-choice model. Rent is assumed the same everywhere — check local rents for the shortlisted sites."),
            "radius_km": radius_km}


# ---------------------------------------------------------------- which strategy
def optimize(arch: Archetype, zones: list[Zone], comps: list[Competitor], biz: BusinessInputs, params: ResolvedParams) -> dict:
    """Grid search over price x marketing x capacity for the highest monthly operating profit."""
    m0 = build_arrays(arch, zones, comps, biz, params)
    b0 = replace(biz, reference_price=m0.ref_price)
    pv = params.draws(1, None)
    p0 = float(biz.price)
    prices = sorted({round(p0 * f / 5) * 5 or p0 for f in (0.7, 0.8, 0.88, 0.94, 1.0, 1.06, 1.12, 1.2, 1.3, 1.45)})
    hs = float(params.values.get("marketing_half_saturation", 20000))
    s0 = float(biz.marketing_spend or 0)
    spends = sorted({0.0, s0, *[round(x, -3) for x in (0.25 * hs, 0.5 * hs, hs, 2 * hs, 3 * hs, 2 * s0, 0.5 * s0)]})
    scales = [1.0, 1.25, 1.5, 2.0]
    demand: dict[tuple[float, float], float] = {}
    for pr in prices:
        prices_arr = m0.prices.copy()
        prices_arr[0] = pr
        m = replace(m0, prices=prices_arr)
        for sp in spends:
            r = run_choice(arch, m, replace(b0, price=pr, marketing_spend=sp), pv)
            demand[(pr, sp)] = float(r["units_by_alt"][0, 0])
    grid = []
    for (pr, sp), dem in demand.items():
        for s in scales:
            b = scaled_business(arch, replace(b0, price=pr, marketing_spend=sp), s)
            e = _econ(arch, b, dem, pv)
            grid.append({"price": pr, "marketing_spend": sp, "capacity_scale": s, **e})
    cur = next(g for g in grid if g["price"] == p0 and g["marketing_spend"] == s0 and g["capacity_scale"] == 1.0)
    best = max(grid, key=lambda g: g["profit"])
    # a cheaper-to-build alternative: best without adding capacity
    best_no_cap = max((g for g in grid if g["capacity_scale"] == 1.0), key=lambda g: g["profit"])
    # profit surface price x marketing at the best capacity, for the heat map
    for g in {id(x): x for x in (cur, best, best_no_cap)}.values():
        b = scaled_business(arch, replace(b0, price=g["price"], marketing_spend=g["marketing_spend"]), g["capacity_scale"])
        g["risk"] = risk(arch, m0, b, params)
    surface = [{"price": g["price"], "marketing_spend": g["marketing_spend"], "profit": g["profit"], "units": g["units"]}
               for g in grid if g["capacity_scale"] == best["capacity_scale"]]
    return {"current": cur, "best": best, "best_without_new_capacity": best_no_cap, "surface": surface,
            "prices": prices, "spends": spends, "scales": scales, "evaluated": len(grid),
            "cost_note": CAPACITY_COST_NOTE,
            "method": "Every combination of price, monthly marketing and capacity run through the customer-choice model; profit after costs."}
