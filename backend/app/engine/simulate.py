"""Simulation orchestrator: deterministic run, Monte Carlo, sensitivity, synthetic agents."""
from __future__ import annotations

import math
import time
from dataclasses import replace

import numpy as np
from scipy.stats import spearmanr

from ..categories.archetypes import Archetype
from .finance import EXCLUDED, INCLUDED, economics, fixed_costs
from .model import (
    MODEL_VERSION, UNCERTAIN_PARAMS, BusinessInputs, Competitor, ResolvedParams, Zone,
    build_arrays, run_choice,
)

PARAM_LABELS = {
    "participation": "Share of residents in this market",
    "frequency": "Purchase frequency",
    "beta_price": "Price sensitivity",
    "beta_quality": "Quality sensitivity",
    "distance_decay": "Distance sensitivity",
    "awareness_base": "Baseline awareness of a new business",
    "competitor_quality": "Assumed competitor quality",
    "competitor_price_ratio": "Assumed competitor prices",
    "wtp_sigma": "Spread of willingness to pay",
    "outside_utility": "Pull of alternatives outside the model",
    "variable_cost_ratio": "Variable cost ratio",
}


def _f(x, nd: int = 2):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    if math.isnan(x) or math.isinf(x):
        return None
    return round(x, nd)


class SimulationError(ValueError):
    pass


def simulate(arch: Archetype, zones: list[Zone], comps: list[Competitor], biz: BusinessInputs,
             overrides: dict | None = None, *, mc_draws: int = 800, seed: int = 42,
             with_sensitivity: bool = True, n_agents: int = 1500,
             travel_km: np.ndarray | None = None,
             travel_time_min: np.ndarray | None = None,
             evidence: dict | None = None, seg_share_z: np.ndarray | None = None) -> dict:
    t0 = time.perf_counter()
    try:
        params = ResolvedParams.from_archetype(arch, overrides, evidence)
        m = build_arrays(arch, zones, comps, biz, params, travel_km, travel_time_min, seg_share_z)
    except ValueError as e:
        raise SimulationError(str(e)) from e
    capacity = float(arch.capacity_units(biz.capacity))
    vc_user = biz.variable_cost_per_unit is not None and biz.variable_cost_per_unit >= 0
    fixed = fixed_costs(biz.rent, biz.payroll, biz.utilities, biz.other_fixed, biz.marketing_spend)

    def vc_for(price: float, ratio):
        return np.full_like(np.asarray(ratio, float), float(biz.variable_cost_per_unit)) if vc_user else price * np.asarray(ratio, float)

    def det(values: dict | None = None, b: BusinessInputs | None = None, mult_units: float = 1.0) -> dict:
        b = b or biz
        if b is not biz:  # keep the market's reference price fixed while sweeping own inputs
            b = replace(b, reference_price=m.ref_price)
        pv = params.draws(1, None)
        for k, v in (values or {}).items():
            pv[k] = np.full(1, v, float)
        mm = m if (b.lat, b.lng, b.price, b.quality) == (biz.lat, biz.lng, biz.price, biz.quality) else build_arrays(arch, zones, comps, b, params, travel_km, travel_time_min, seg_share_z)

        r = run_choice(arch, mm, b, pv)
        demand = float(r["units_by_alt"][0, 0]) * mult_units
        units = min(demand, capacity)
        fx = fixed_costs(b.rent, b.payroll, b.utilities, b.other_fixed, b.marketing_spend)
        vcu = float(b.variable_cost_per_unit) if vc_user else b.price * float(pv["variable_cost_ratio"][0])
        e = economics(units, b.price, vcu, fx["total"], b.startup_cost, capacity)
        return {"demand": demand, "units": units, "profit": float(e["operating_profit"]), "revenue": float(e["revenue"]), "r": r}

    # ---------- deterministic baseline ----------
    pv = params.draws(1, None)
    r = run_choice(arch, m, biz, pv, keep_detail=True)
    demand = float(r["units_by_alt"][0, 0])
    units = min(demand, capacity)
    vc_unit = float(vc_for(biz.price, pv["variable_cost_ratio"])[0])
    econ = {k: float(np.asarray(v).ravel()[0]) for k, v in economics(units, biz.price, vc_unit, fixed["total"], biz.startup_cost, capacity).items()}
    in_market = float(r["in_market_units"][0])
    comp_units = r["units_by_alt"][0, 1:]
    captured_total = float(r["units_by_alt"][0].sum())

    P, N = r["P"][0], r["N"][0]  # [Z,S,J], [Z,S]
    zone_user = (N * P[:, :, 0]).sum(axis=1)
    zone_n = N.sum(axis=1)
    zone_cap = np.divide(zone_user, zone_n, out=np.zeros_like(zone_user), where=zone_n > 0)

    competitors_out = []
    for j, c in enumerate(comps, start=1):
        competitors_out.append({
            "id": c.id, "name": c.name, "source": c.source,
            "modeled_units": _f(comp_units[j - 1], 1),
            "modeled_share_of_in_market": _f(comp_units[j - 1] / in_market if in_market else 0, 4),
            "price_used": _f(r["prices"][0, j]), "price_status": "known" if m.price_known[j] else "assumed",
            "quality_used": _f(m.quality[j] if m.quality_known[j] else pv["competitor_quality"][0], 2),
            "quality_status": "known" if m.quality_known[j] else "assumed",
            "distance_km": _f(m.dist_km.min(axis=0)[j], 2),
        })

    # ---------- synthetic agents (for visualisation; NOT real people) ----------
    rng_a = np.random.default_rng(seed + 1)
    agents = []
    total_n = float(N.sum())
    if n_agents > 0 and total_n > 0:
        flat = (N / total_n).ravel()
        idx = rng_a.choice(flat.size, size=n_agents, p=flat)
        S = N.shape[1]
        zi, si = idx // S, idx % S
        probs = np.concatenate([P[zi, si, :], (1 - P[zi, si, :].sum(axis=1))[:, None]], axis=1)
        probs = np.clip(probs, 0, None)
        probs /= probs.sum(axis=1, keepdims=True)
        cum = probs.cumsum(axis=1)
        u = rng_a.random(n_agents)[:, None]
        choice = (u > cum).sum(axis=1)  # index; J means outside option
        J = P.shape[2]
        jitter = rng_a.normal(0, 0.0012, size=(n_agents, 2))
        for k in range(n_agents):
            z = zones[zi[k]]
            ch = int(choice[k])
            agents.append([round(z.lat + jitter[k, 0], 5), round(z.lng + jitter[k, 1], 5), int(si[k]), ch if ch < J else -1])

    # ---------- Monte Carlo ----------
    mc = None
    drivers = []
    if mc_draws and mc_draws > 1:
        rng = np.random.default_rng(seed)
        pd = params.draws(mc_draws, rng)
        vr = params.ranges["variable_cost_ratio"]
        if not vc_user:
            pd["variable_cost_ratio"] = rng.triangular(vr[0], min(max(params.values["variable_cost_ratio"], vr[0]), vr[1]), vr[1], size=mc_draws)
        out = run_choice(arch, m, biz, pd)
        d_units = out["units_by_alt"][:, 0]
        q_units = np.minimum(d_units, capacity)
        vcs = vc_for(biz.price, pd["variable_cost_ratio"])
        e = economics(q_units, biz.price, vcs, fixed["total"], biz.startup_cost, capacity)
        prof = e["operating_profit"]
        hist_counts, hist_edges = np.histogram(prof, bins=24)
        mc = {
            "draws": int(mc_draws), "seed": int(seed),
            "profit": {"mean": _f(prof.mean()), "p10": _f(np.percentile(prof, 10)), "p50": _f(np.percentile(prof, 50)), "p90": _f(np.percentile(prof, 90))},
            "units": {"mean": _f(q_units.mean(), 1), "p10": _f(np.percentile(q_units, 10), 1), "p50": _f(np.percentile(q_units, 50), 1), "p90": _f(np.percentile(q_units, 90), 1)},
            "revenue": {"p10": _f(np.percentile(e["revenue"], 10)), "p50": _f(np.percentile(e["revenue"], 50)), "p90": _f(np.percentile(e["revenue"], 90))},
            "prob_loss": _f((prof < 0).mean(), 4),
            "prob_capacity_bound": _f((d_units >= capacity).mean(), 4),
            "histogram": {"counts": hist_counts.tolist(), "edges": [_f(x) for x in hist_edges]},
            "note": "Probabilities are conditional on the model and its assumed parameter ranges. They are not calibrated real-world probabilities.",
        }
        keys = [k for k in (*UNCERTAIN_PARAMS, "variable_cost_ratio") if k in pd and np.ptp(pd[k]) > 0]
        if np.ptp(prof) > 0:
            for k in keys:
                rho = spearmanr(pd[k], prof).statistic
                if rho is not None and not np.isnan(rho):
                    drivers.append({"param": k, "label": PARAM_LABELS.get(k, k), "spearman_rho": _f(rho, 3)})
            drivers.sort(key=lambda x: -abs(x["spearman_rho"]))

    # ---------- sensitivity ----------
    sensitivity = None
    if with_sensitivity:
        base_profit = econ["operating_profit"]
        tornado = []
        for k in UNCERTAIN_PARAMS + ("variable_cost_ratio",):
            if k == "variable_cost_ratio" and vc_user:
                continue
            lo, hi = params.ranges[k]
            if hi <= lo:
                continue
            p_lo, p_hi = det({k: lo})["profit"], det({k: hi})["profit"]
            tornado.append({"param": k, "label": PARAM_LABELS.get(k, k), "low_value": _f(lo, 4), "high_value": _f(hi, 4),
                            "profit_at_low": _f(p_lo), "profit_at_high": _f(p_hi), "swing": _f(abs(p_hi - p_lo)),
                            "status": params.status[k]})
        tornado.sort(key=lambda x: -(x["swing"] or 0))
        price_curve = []
        for mult in np.linspace(0.6, 1.6, 15):
            b2 = replace(biz, price=float(biz.price * mult))
            d2 = det(b=b2)
            price_curve.append({"price": _f(b2.price), "units": _f(d2["units"], 1), "revenue": _f(d2["revenue"]), "profit": _f(d2["profit"])})
        hs = params.values["marketing_half_saturation"]
        spends = sorted(set([0.0, *np.linspace(0, max(4 * hs, 2 * biz.marketing_spend), 9).tolist(), float(biz.marketing_spend)]))
        marketing_curve = []
        for s_ in spends:
            d2 = det(b=replace(biz, marketing_spend=float(s_)))
            marketing_curve.append({"spend": _f(s_), "units": _f(d2["units"], 1), "profit": _f(d2["profit"])})
        stress = []
        for label, kwargs in (
            ("Demand 20% lower than modeled", {"mult_units": 0.8}),
            ("Rent 20% higher", {"b": replace(biz, rent=biz.rent * 1.2)}),
            ("Competitors 15% cheaper", {"values": {"competitor_price_ratio": params.values["competitor_price_ratio"] * 0.85}}),
            ("Slow awareness (half the marketing effect)", {"values": {"marketing_half_saturation": hs * 2}}),
            ("Competitors stronger (quality +0.15)", {"values": {"competitor_quality": min(1.0, params.values["competitor_quality"] + 0.15)}}),
        ):
            d2 = det(**kwargs)
            stress.append({"label": label, "units": _f(d2["units"], 1), "profit": _f(d2["profit"]), "delta_profit": _f(d2["profit"] - base_profit)})
        # Break-even threshold on the most important behavioural assumption (bisection; profit is
        # non-decreasing in participation because demand scales linearly with it).
        thresholds = {}
        lo_p, hi_p = 1e-4, 0.9
        f_lo, f_hi = det({"participation": lo_p})["profit"], det({"participation": hi_p})["profit"]
        if f_lo < 0 < f_hi:
            for _ in range(40):
                mid = (lo_p + hi_p) / 2
                if det({"participation": mid})["profit"] < 0:
                    lo_p = mid
                else:
                    hi_p = mid
            thresholds["participation_break_even"] = _f(hi_p, 5)
        elif f_lo >= 0:
            thresholds["participation_break_even"] = 0.0
        else:
            thresholds["participation_break_even"] = None  # capacity or margin prevents break-even
        sensitivity = {"tornado": tornado, "price_curve": price_curve, "marketing_curve": marketing_curve,
                       "stress_tests": stress, "thresholds": thresholds}

    seg_afford = r["afford_user_by_segment"][0]
    result = {
        "model_version": MODEL_VERSION,
        "archetype": arch.key,
        "unit_label": arch.unit_label,
        "summary": {
            "in_market_units": _f(in_market, 1),
            "modeled_demand_units": _f(demand, 1),
            "units_sold": _f(units, 1),
            "capacity_units": _f(capacity, 1),
            "capacity_bound": demand > capacity,
            "capture_of_in_market": _f(demand / in_market if in_market else 0, 4),
            "captured_by_all_modeled": _f(captured_total / in_market if in_market else 0, 4),
            "awareness": _f(r["awareness_user"][0], 4),
            "price": _f(biz.price),
            "reference_price": _f(m.ref_price), "reference_price_status": m.ref_price_status,
            "variable_cost_per_unit": _f(vc_unit), "variable_cost_status": "user" if vc_user else "assumption",
        },
        "finance": {
            "period": "month",
            "revenue": _f(econ["revenue"]), "variable_cost": _f(econ["variable_cost"]),
            "fixed_cost": _f(econ["fixed_cost"]), "fixed_breakdown": {k: _f(v) for k, v in fixed.items()},
            "operating_profit": _f(econ["operating_profit"]), "unit_margin": _f(econ["unit_margin"]),
            "break_even_units": _f(econ["break_even_units"], 1), "break_even_utilization": _f(econ["break_even_utilization"], 4),
            "utilization": _f(econ["utilization"], 4), "startup_cost": _f(biz.startup_cost),
            "payback_months": _f(econ["payback_months"], 1),
            "included": INCLUDED, "excluded": EXCLUDED,
        },
        "segments": [
            {"key": s.key, "label": s.label, "share": s.share, "affordability_at_price": _f(seg_afford[i], 4),
             "in_market_units": _f(N[:, i].sum() * pv["frequency"][0], 1),
             "units_to_user": _f((N[:, i] * P[:, i, 0]).sum() * pv["frequency"][0], 1)}
            for i, s in enumerate(arch.segments)
        ],
        "competitors": competitors_out,
        "zones": [{"lat": _f(z.lat, 5), "lng": _f(z.lng, 5), "weight": _f(m.weight[i], 1), "capture": _f(zone_cap[i], 4)} for i, z in enumerate(zones)],
        "agents": {"columns": ["lat", "lng", "segment", "choice"], "rows": agents,
                   "choice_legend": {"0": "your business", "1..n": "competitor index (1-based, matches competitors[])", "-1": "outside option / none"},
                   "note": "Synthetic agents are a visual sample of the modeled demand distribution. They are not real people."},
        "monte_carlo": mc,
        "drivers": drivers,
        "sensitivity": sensitivity,
        "parameters": {k: {"value": _f(params.values[k], 4), "low": _f(params.ranges[k][0], 4), "high": _f(params.ranges[k][1], 4),
                           "status": params.status[k], "label": PARAM_LABELS.get(k, k),
                           "description": arch.params[k].description if k in arch.params else "Resident-equivalents per mapped activity point."}
                       for k in params.values},
        "limitations": [
            "Demand is a model estimate from population, assumed participation and assumed behaviour parameters; it has not been validated against observed sales for this location.",
            "Distances are straight-line distance x circuity factor unless a routing engine result was available." if travel_km is None else "Distances come from a routing engine.",
            "Competitors not present in the data sources are invisible to the model; add any you know about.",
            "Capacity overflow is not reassigned to competitors; competitor capacity is unknown.",
            *arch.limitations,
        ],
        "duration_ms": None,
    }
    result["duration_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    return result
