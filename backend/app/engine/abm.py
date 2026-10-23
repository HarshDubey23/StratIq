"""Agent-based market simulation ("live market") on the 615-parameter Agent Genome.

Synthetic people are placed on the map in proportion to real population density
(WorldPop totals distributed over OSM buildings). Each one receives a 615-parameter
genome (``engine/genome.py``): real-geometry measurements (distance and travel time to
every mapped business), 16 correlated latent traits conditioned on the agent's age and
income segment, and 553 generated parameters - hour-by-hour availability, 40 attribute
importances and 40 minimum expectations, 48 media-channel parameters, price psychology,
mobility, retention, category affinities, lifestyle and constraints.

The simulation then runs day by day:

* awareness of the new business spreads through paid media (each agent's exposure,
  trust and response on 16 channels x the category's media mix), word of mouth from
  customers in the same zone (sender propensity x receiver susceptibility) and signage;
* in-market agents choose with their own random utility: price vs their own WTP and
  caps, quality, travel (distance, time, value of time, friction), opening-hours fit,
  40 attribute importances x business attributes, expectation gaps, trust/novelty and
  ~120 lifestyle modulators - plus a personal outside option and personal noise scale;
* membership businesses hold members who reconsider monthly with a personal churn hazard;
* capacity limits turn customers away, and a turned-away agent remembers it.

Before the run, demand is optionally calibrated against incumbents ("revealed demand"):
businesses that exist and survive need customers, so if the model leaves nearby
incumbents far below a survival floor, participation is scaled up (bounded, reported).

This is a stochastic, assumption-driven model. Every agent is synthetic; one agent
represents ``scale`` residents. Not a forecast guarantee.
"""
from __future__ import annotations

import math
import time
from collections import OrderedDict
from dataclasses import dataclass

import numpy as np

from ..categories.archetypes import Archetype
from . import genome as gm
from .model import BusinessInputs, Competitor, ResolvedParams, Zone

AGE_BANDS = ["0-4", "5-9", "10-14", "15-19", "20-24", "25-29", "30-34", "35-39", "40-44", "45-49", "50-54", "55-59", "60-64", "65-69", "70-74", "75-79", "80+"]
AGE_MID = np.array([2, 7, 12, 17, 22, 27, 32, 37, 42, 47, 52, 57, 62, 67, 72, 77, 84], float)
# Fallback age structure (assumption, roughly an Indian urban pyramid) used only if WorldPop age–sex is unavailable.
DEFAULT_AGE = np.array([0.075, 0.080, 0.085, 0.088, 0.092, 0.092, 0.085, 0.077, 0.068, 0.060, 0.052, 0.043, 0.035, 0.027, 0.019, 0.012, 0.010])

# Category affinity by age group: child (0-14), young (15-29), mid (30-49), senior (50+). Assumptions.
AFFINITY = {
    # children (0-14) are not decision-makers: their household's purchases are carried by adult agents (mean is renormalised)
    "membership": (0.0, 1.6, 1.0, 0.45),
    "dine_in": (0.0, 1.4, 1.1, 0.6),
    "takeaway": (0.0, 1.5, 1.05, 0.45),
    "retail": (0.0, 1.0, 1.1, 1.0),
    "appointment": (0.0, 1.1, 1.1, 1.0),
    "lodging": (0.0, 1.1, 1.25, 0.7),
}
FEMALE_AFFINITY = {"membership": 0.8, "dine_in": 1.0, "takeaway": 0.95, "retail": 1.05, "appointment": 1.2, "lodging": 0.95}
MODE_NAMES = [m[0] for m in gm.MODES]
# (name, base share, base share, base share, distance-tolerance multiplier, speed km/h): baseline of the genome's mode choice
MODE_BASE = [0.30, 0.30, 0.08, 0.10, 0.12, 0.05, 0.05]
MODES = [(m[0], b, b, b, m[2], m[1]) for m, b in zip(gm.MODES, MODE_BASE)]

# Day-of-week demand pattern (Mon..Sun), mean 1. Assumption from typical Indian urban retail/food footfall:
# food peaks Fri-Sun, salons/appointments on Saturday, hotels at weekends. Launch day is a Monday.
DOW = {
    "takeaway": (0.88, 0.86, 0.90, 0.95, 1.10, 1.21, 1.10),
    "dine_in": (0.85, 0.84, 0.88, 0.94, 1.12, 1.25, 1.12),
    "retail": (0.95, 0.93, 0.95, 0.98, 1.03, 1.12, 1.04),
    "appointment": (0.90, 0.92, 0.95, 1.00, 1.05, 1.20, 0.98),
    "lodging": (0.85, 0.85, 0.90, 0.95, 1.15, 1.25, 1.05),
    "membership": (1, 1, 1, 1, 1, 1, 1),
}

DEFAULTS = {
    "wom_rate": 0.015, "signage_radius": 0.35, "signage_daily": 0.04, "noise_scale": 0.6, "habit_build": 0.25, "habit_cap": 1.2,
    "congestion_penalty": 1.0, "congestion_memory": 14, "monthly_churn": 0.08, "switch_threshold": 0.35,
    "taste_sd": 0.45, "beta_time": 1.2, "beta_attr": 2.2, "beta_exp": 2.0,
    "calibrate_incumbents": 1.0, "survival_floor": 0.4, "calibration_max": 2.5,
}


# Each agent scores every rival individually; memory grows ~7 MB per rival at 10,000 agents. In dense markets
# (300+ cafés from OpenStreetMap + Foursquare) the agents weigh the nearest rivals individually; far ones barely
# matter to anyone's choice. The aggregate choice model still uses every rival.
MAX_AGENT_COMPETITORS = 80


def agent_competitors(biz: BusinessInputs, comps: list[Competitor], k: int = MAX_AGENT_COMPETITORS) -> list[Competitor]:
    if len(comps) <= k:
        return list(comps)
    from .geo import haversine_km
    d = haversine_km(biz.lat, biz.lng, np.array([c.lat for c in comps]), np.array([c.lng for c in comps]))
    keep = set(np.argsort(d)[:k].tolist())
    return [c for i, c in enumerate(comps) if i in keep]  # original order, so indices are stable across rebuilds


def _age_dist(age_sex: dict | None) -> tuple[np.ndarray, np.ndarray, str]:
    """Return (P(band), P(female | band), source)."""
    if age_sex and age_sex.get("bands"):
        m = np.array([b["male"] for b in age_sex["bands"]], float)
        fem = np.array([b["female"] for b in age_sex["bands"]], float)
        tot = m + fem
        if tot.sum() > 0 and len(tot) == len(AGE_BANDS):
            return tot / tot.sum(), np.divide(fem, tot, out=np.full_like(tot, 0.48), where=tot > 0), "worldpop"
    return DEFAULT_AGE / DEFAULT_AGE.sum(), np.full(len(AGE_BANDS), 0.48), "default_assumption"


def _age_group(age: np.ndarray) -> np.ndarray:
    return np.select([age < 15, age < 30, age < 50], [0, 1, 2], 3)


@dataclass
class Population:
    """Everything that is a deterministic function of the inputs and seed (no day-by-day dynamics)."""
    N: int
    scale: float
    zi: np.ndarray
    lat: np.ndarray
    lng: np.ndarray
    age: np.ndarray
    female: np.ndarray
    seg: np.ndarray
    gen: gm.Genome
    F: np.ndarray
    meta: dict
    up: gm.UtilityParts
    p_in_base: np.ndarray
    freq: np.ndarray
    age_src: str
    names: list[str]
    comps: list


def build_population(arch: Archetype, zones: list[Zone], comps: list[Competitor], biz: BusinessInputs, params: ResolvedParams,
                     ref_price: float, *, n_agents: int, seed: int, age_sex: dict | None, spacing_km: float, profile: dict | None,
                     offer: dict | None, overrides: dict | None, month0: int, days: int) -> Population:
    P = params.values
    D = {**DEFAULTS, **{k: v for k, v in (overrides or {}).items() if k in DEFAULTS}}
    comps = agent_competitors(biz, comps)
    rng = np.random.default_rng(seed + 101)
    pop = np.array([max(0.0, z.population) for z in zones])
    act = np.array([max(0.0, z.activity) for z in zones])
    W = pop + (act * P.get("activity_equivalent", 120.0) if arch.demand_base == "residents_and_activity" else 0.0)
    if W.sum() <= 0:
        raise ValueError("No population to place agents")
    N = int(n_agents)
    scale = float(W.sum() / N)
    zi = rng.choice(len(zones), size=N, p=W / W.sum())
    zlat = np.array([z.lat for z in zones])
    zlng = np.array([z.lng for z in zones])
    jit = spacing_km / 2.2
    lat = zlat[zi] + rng.uniform(-1, 1, N) * jit / 110.574
    lng = zlng[zi] + rng.uniform(-1, 1, N) * jit / (111.32 * math.cos(math.radians(float(np.mean(zlat)))))
    band_p, fem_p, age_src = _age_dist(age_sex)
    band = rng.choice(len(AGE_BANDS), size=N, p=band_p)
    age = np.clip(AGE_MID[band] + rng.uniform(-2, 2, N), 0, 95)
    female = rng.random(N) < fem_p[band]
    seg_share = np.array([s.share for s in arch.segments])
    seg = rng.choice(len(arch.segments), size=N, p=seg_share / seg_share.sum())

    blat = np.array([biz.lat] + [c.lat for c in comps])
    blng = np.array([biz.lng] + [c.lng for c in comps])
    seg_dt = np.array([s.distance_tolerance for s in arch.segments])[seg]
    gen = gm.generate(np.random.default_rng(seed + 7), age=age, female=female, seg_keys=[s.key for s in arch.segments], seg=seg,
                      zone_pop=pop, zone_act=act, lat=lat, lng=lng, zi=zi, blat=blat, blng=blng, circuity=P["circuity"],
                      max_km=P["max_km"], seg_dt=seg_dt)
    hs = max(P["marketing_half_saturation"], 1.0)
    a_target = P["awareness_base"] + (1 - P["awareness_base"]) * (1 - 2 ** (-max(biz.marketing_spend, 0) / hs))
    F, meta = gm.business_features(arch.key, biz, comps, ref_price, P["competitor_quality"], profile, a_target, offer)
    # competitor prices unknown -> assumed ratio x reference
    meta["prices"] = np.array([biz.price] + [c.price if c.price else ref_price * P["competitor_price_ratio"] for c in comps], float)
    F[:, gm.FI["price_rel"]] = np.log(meta["prices"] / ref_price)
    F[:, gm.FI["premium"]] = np.clip(meta["prices"] / ref_price - 1.0, 0, 2)
    F[:, gm.FI["budget"]] = np.clip(1.0 - meta["prices"] / ref_price, 0, 1)
    meta["a_target"] = a_target
    meta["blat"], meta["blng"] = blat, blng
    seg_psens = np.array([s.price_sensitivity for s in arch.segments])[seg]
    up = gm.assemble_utility(arch.key, gen, F, meta, P, ref_price, seg_psens, lin_target_sd=D["taste_sd"], beta_time=D["beta_time"],
                             beta_attr=D["beta_attr"], beta_exp=D["beta_exp"])
    up.outside = up.outside + gm.outside_substitutes(arch.key, gen.G)

    # participation: archetype mean x age/sex affinity x personal index (genome), mean preserved
    aff_tab = np.array(AFFINITY[arch.key])
    affinity = aff_tab[_age_group(age)] * np.where(female, FEMALE_AFFINITY[arch.key], 1.0)
    affinity = affinity / max(1e-9, affinity.mean())
    base = np.clip(P["participation"] * affinity, 1e-4, 0.95)
    idx = gm.participation_index(arch.key, gen.G, month0, days)
    logit = np.log(base / (1 - base)) + idx
    p_in = 1 / (1 + np.exp(-logit))
    p_in = np.clip(p_in * (base.mean() / max(p_in.mean(), 1e-9)), 0, 0.97)
    if arch.key == "membership":
        freq = np.ones(N)
    else:
        r = np.random.default_rng(seed + 13)
        f0 = r.gamma(4.0, P["frequency"] / 4.0, N) * np.exp(0.25 * idx)
        if arch.key in ("retail", "takeaway"):
            f0 *= (gen.G[:, gm.KI["ev_household_size"]] / 4.2) ** 0.3
        freq = np.clip(f0 * (P["frequency"] / max(f0.mean(), 1e-9)), 0.1, 30)
    names = ["Your business"] + [c.name for c in comps]
    return Population(N, scale, zi, lat, lng, age, female, seg, gen, F, meta, up, p_in, freq, age_src, names, comps)


def _calibrate(pop: Population, arch: Archetype, D: dict, radius_km: float | None) -> dict:
    """Revealed-demand floor: incumbents that exist need customers. Scale participation if they look starved."""
    J = pop.up.total.shape[1]
    out = {"applied": False, "multiplier": 1.0, "method": "revealed-demand floor from incumbents (assumption-anchored)"}
    if not D["calibrate_incumbents"] or J < 3:
        out["reason"] = "fewer than 2 incumbents" if J < 3 else "disabled"
        return out
    V = pop.up.total[:, 1:]  # incumbents only: the market before you open
    noise = pop.up.noise[:, None]
    ex = np.exp(np.clip(V / noise, -50, 50))
    ex = np.where(np.isfinite(V), ex, 0)
    den = np.exp(np.clip(pop.up.outside / pop.up.noise, -50, 50)) + ex.sum(1)
    Pij = ex / den[:, None]
    demand = pop.scale * (pop.p_in_base * pop.freq) @ Pij  # units / month per incumbent from inside the catchment
    cap_default = arch.capacity_units({})
    floor = D["survival_floor"] * cap_default
    inner = np.arange(J - 1)
    if radius_km:
        from .geo import haversine_km
        d_site = haversine_km(pop.meta["blat"][0], pop.meta["blng"][0], pop.meta["blat"][1:], pop.meta["blng"][1:])
        inner = np.where(d_site <= 0.6 * radius_km)[0]
    if inner.size < 2:
        out["reason"] = "fewer than 2 incumbents in the inner catchment"
        return out
    med = float(np.median(demand[inner]))
    out.update({"incumbents_used": int(inner.size), "median_incumbent_units": round(med, 1), "survival_floor_units": round(floor, 1)})
    if med <= 0:
        out["reason"] = "incumbents receive no modeled demand"
        return out
    if med < floor:
        m = float(min(D["calibration_max"], floor / med))
        out.update({"applied": True, "multiplier": round(m, 3), "reason": "incumbents below survival floor; participation scaled up"})
    else:
        out["reason"] = "incumbents already above survival floor; no change"
    return out


# ---------------------------------------------------------------- population cache (agent X-ray / DNA matrix)
_CACHE: OrderedDict = OrderedDict()
_CACHE_MAX = 2


def cache_put(key: str, pop: Population) -> None:
    _CACHE[key] = pop
    _CACHE.move_to_end(key)
    while len(_CACHE) > _CACHE_MAX:
        _CACHE.popitem(last=False)


def cache_get(key: str) -> Population | None:
    p = _CACHE.get(key)
    if p is not None:
        _CACHE.move_to_end(key)
    return p


def run_abm(arch: Archetype, zones: list[Zone], comps: list[Competitor], biz: BusinessInputs, params: ResolvedParams,
            ref_price: float, *, n_agents: int = 10000, days: int = 84, seed: int = 42, age_sex: dict | None = None,
            spacing_km: float = 0.35, frame_every: int = 2, overrides: dict | None = None, profile: dict | None = None,
            offer: dict | None = None, radius_km: float | None = None, month0: int | None = None, cache_key: str | None = None) -> dict:
    t0 = time.perf_counter()
    D = {**DEFAULTS, **{k: v for k, v in (overrides or {}).items() if k in DEFAULTS}}
    month0 = gm.month_now() if month0 is None else month0
    pop = build_population(arch, zones, comps, biz, params, ref_price, n_agents=n_agents, seed=seed, age_sex=age_sex, spacing_km=spacing_km,
                           profile=profile, offer=offer, overrides=overrides, month0=month0, days=days)
    t_gen = time.perf_counter()
    if cache_key:
        cache_put(cache_key, pop)
    G, gen, up = pop.gen.G, pop.gen, pop.up
    KI = gm.KI
    N, J = pop.N, up.total.shape[1]
    scale, zi, age, female, seg = pop.scale, pop.zi, pop.age, pop.female, pop.seg
    membership = arch.key == "membership"
    rng = np.random.default_rng(seed + 211)

    calib = _calibrate(pop, arch, D, radius_km)
    p_in = np.clip(pop.p_in_base * calib["multiplier"], 0, 0.97)
    in_market = rng.random(N) < p_in
    G[:, KI["ev_in_market"]] = in_market

    gget = lambda k: G[:, KI[k]].astype(float)  # noqa: E731
    v_static = up.total
    noise = D["noise_scale"] * up.noise
    outside = up.outside
    ret_idx = gm.mech_index(G, "retention", 0.5)
    soc_idx = gm.mech_index(G, "social", 0.4)
    wom_send = gget("so_wom_propensity") * np.exp(soc_idx)
    wom_recv = gget("so_wom_susceptibility") * np.exp(soc_idx)
    habit_rate = D["habit_build"] * (0.5 + gget("rt_habit_rate"))
    habit_cap = D["habit_cap"] * (0.6 + 0.8 * gget("rt_habit_cap"))
    sat_gap = -up.parts["expectation"][:, 0]  # how far you fall below this agent's minimums
    churn_m = D["monthly_churn"] * np.exp(-ret_idx) * (1 + gget("rt_satisfaction_sens") * np.clip(sat_gap, 0, 2)) * (0.6 + 0.8 * gget("rt_churn_base"))
    churn_m = np.clip(churn_m, 0.005, 0.6)
    switch_keep = np.clip(D["switch_threshold"] + 0.15 + 0.25 * ret_idx, 0.1, 0.9)

    a_target = pop.meta["a_target"]
    daily_paid = -math.log(max(1e-6, 1 - a_target)) / 30.0
    ch_mult = gm.channel_awareness(arch.key, G)
    aware = np.zeros(N, bool)
    aware_day = np.full(N, -1)
    aware_channel = np.full(N, -1)
    near_site = gen.dist[:, 0] <= D["signage_radius"]
    sign_att = D["signage_daily"] * (0.5 + gget("ch_signage_reach"))

    habit = np.zeros((N, J))
    cong = np.zeros(N)
    member_of = np.full(N, -1)
    reconsider = rng.integers(0, 30, N)
    purchases_you = np.zeros(N, int)
    first_you = np.full(N, -1)
    last_choice = np.full(N, -1)
    turned_away = np.zeros(N, int)
    left_you = np.zeros(N, bool)
    churned = 0
    freq = pop.freq

    daily_cap = arch.capacity_units(biz.capacity) / 30.0 / scale if not membership else arch.capacity_units(biz.capacity) / scale
    zone_count = np.bincount(zi, minlength=len(zones)).astype(float)

    series = {k: [] for k in ("units_you", "customers_you", "aware_share", "members_you", "units_comp", "turned_away", "units_none")}
    frames = []
    decisions = 0

    def choose(idx: np.ndarray) -> np.ndarray:
        if idx.size == 0:
            return idx
        v = v_static[idx] + habit[idx] - np.where(np.arange(J)[None, :] == 0, (cong[idx] > 0)[:, None] * D["congestion_penalty"], 0)
        v[:, 0] = np.where(aware[idx], v[:, 0], -np.inf)
        ns = noise[idx]
        u = v + rng.gumbel(0, 1, size=v.shape) * ns[:, None]
        u0 = outside[idx] + rng.gumbel(0, 1, size=idx.size) * ns
        best = np.argmax(u, axis=1)
        bu = u[np.arange(idx.size), best]
        return np.where(bu > u0, best, -1)

    def probs(idx: np.ndarray) -> np.ndarray:
        """Each agent's own multinomial-logit choice probabilities (you, competitors..., outside option last).

        Same utilities and personal noise scale as ``choose``; used to count demand in real units without the
        "one agent = N residents" rounding that makes sampled daily counts jump in big steps."""
        v = v_static[idx] + habit[idx] - np.where(np.arange(J)[None, :] == 0, (cong[idx] > 0)[:, None] * D["congestion_penalty"], 0)
        v[:, 0] = np.where(aware[idx], v[:, 0], -np.inf)
        vv = np.concatenate([v, outside[idx][:, None]], 1) / noise[idx][:, None]
        vv = np.where(np.isfinite(vv), vv, -np.inf)
        mx = np.max(vv, 1, keepdims=True)
        e = np.exp(vv - mx)
        return e / e.sum(1, keepdims=True)

    dow = np.array(DOW.get(arch.key, DOW["retail"]), float)
    dow = dow / dow.mean()
    in_idx = np.where(in_market)[0]
    cap_units_day = arch.capacity_units(biz.capacity) / 30.0 if not membership else None

    for day in range(days):
        cust_zone = np.bincount(zi[purchases_you > 0], weights=wom_send[purchases_you > 0], minlength=len(zones)).astype(float)
        wom_pressure = np.divide(cust_zone, zone_count, out=np.zeros_like(cust_zone), where=zone_count > 0)[zi]
        p_paid = 1 - np.exp(-daily_paid * ch_mult)
        p_wom = np.clip(D["wom_rate"] * wom_recv * wom_pressure * 30, 0, 0.5)
        p_sign = np.where(near_site, sign_att, 0.0)
        r = rng.random(N)
        newly = (~aware) & (r < 1 - (1 - p_paid) * (1 - p_wom) * (1 - p_sign))
        if newly.any():
            idx = np.where(newly)[0]
            w3 = np.stack([p_paid[idx], p_wom[idx], p_sign[idx]], 1) + 1e-12
            cum = np.cumsum(w3 / w3.sum(1, keepdims=True), 1)
            ch = (rng.random(idx.size)[:, None] > cum).sum(1)
            aware_channel[idx] = np.array([0, 2, 1])[np.minimum(ch, 2)]  # 0 paid, 1 signage, 2 wom
            aware[idx] = True
            aware_day[idx] = day
        cong = np.maximum(cong - 1, 0)

        if membership:
            due = np.where(in_market & ((reconsider == day % 30) | (member_of < 0) & (rng.random(N) < 1 / 15)))[0]
            mem_due = due[member_of[due] >= 0]
            churn = mem_due[rng.random(mem_due.size) < churn_m[mem_due]]
            churned += int((member_of[churn] == 0).sum())
            left_you[churn[member_of[churn] == 0]] = True
            member_of[churn] = -1
            choice = choose(due)
            decisions += due.size
            cur = member_of[due]
            keep = (cur >= 0) & (choice != cur) & (rng.random(due.size) < switch_keep[due])
            choice = np.where(keep, cur, choice)
            joining = due[(choice == 0) & (cur != 0)]
            current_members = int((member_of == 0).sum())
            room = int(max(0, math.floor(daily_cap + rng.random()) - current_members))
            if joining.size > room:
                rejected = rng.choice(joining, size=joining.size - room, replace=False)
                choice[np.isin(due, rejected)] = -1
                cong[rejected] = D["congestion_memory"]
                turned_away[rejected] += 1
                n_rej = rejected.size
            else:
                n_rej = 0
            left = due[(cur == 0) & (choice != 0)]
            left_you[left] = True
            member_of[due] = choice
            got = choice >= 0
            newm = due[got]
            habit[newm, choice[got]] = np.minimum(habit[newm, choice[got]] + habit_rate[newm], habit_cap[newm])
            fy = due[(choice == 0) & (first_you[due] < 0)]
            first_you[fy] = day
            purchases_you[due[choice == 0]] += 1
            last_choice[due] = choice
            units_you = int((member_of == 0).sum())
            series["members_you"].append(units_you)
            series["units_you"].append(units_you)
            series["units_comp"].append(int((member_of > 0).sum()))
            series["turned_away"].append(n_rej)
            series["units_none"].append(int((in_market & (member_of < 0)).sum()))
            frame_events = np.where((member_of >= 0) & (rng.random(N) < 3 / 7))[0]
        else:
            m_day = float(dow[day % 7])
            # demand in real units: every in-market agent's purchase rate x its own choice probabilities x residents it stands for
            pr = probs(in_idx) if in_idx.size else np.zeros((0, J + 1))
            w = freq[in_idx] / 30.0 * m_day
            exp_you = scale * float(w @ pr[:, 0]) if in_idx.size else 0.0
            exp_comp = scale * float(w @ pr[:, 1:J].sum(1)) if in_idx.size and J > 1 else 0.0
            exp_none = scale * float(w @ pr[:, J]) if in_idx.size else 0.0
            orders = float(rng.poisson(exp_you)) if exp_you < 1e7 else exp_you  # day-to-day randomness of real orders
            served = min(orders, cap_units_day * float(np.clip(rng.normal(0.97, 0.03), 0.85, 1.0)))  # staffing / rush days: never above the stated limit
            turned = orders - served
            # agent-level events (who buys, from whom) drive habits, word of mouth and the dots on the map
            buyers = np.where(in_market & (rng.random(N) < freq / 30.0 * m_day))[0]
            choice = choose(buyers)
            decisions += buyers.size
            to_you = buyers[choice == 0]
            if turned > 0 and to_you.size:
                k = int(np.floor(to_you.size * turned / max(orders, 1e-9) + rng.random()))
                rejected = rng.choice(to_you, size=min(k, to_you.size), replace=False) if k > 0 else to_you[:0]
            else:
                rejected = to_you[:0]
            if rejected.size:
                choice[np.isin(buyers, rejected)] = -1
                cong[rejected] = D["congestion_memory"]
                turned_away[rejected] += 1
            got = choice >= 0
            b = buyers[got]
            habit[b, choice[got]] = np.minimum(habit[b, choice[got]] + habit_rate[b], habit_cap[b])
            prev = last_choice[buyers]
            left_you[buyers[(prev == 0) & (choice > 0)]] = True
            fy = buyers[(choice == 0) & (first_you[buyers] < 0)]
            first_you[fy] = day
            purchases_you[buyers[choice == 0]] += 1
            last_choice[b] = choice[got]
            # series are kept in "agent units" (x scale on output) so the downstream code is unchanged
            series["units_you"].append(served / scale)
            series["units_comp"].append(float(rng.poisson(exp_comp)) / scale if exp_comp < 1e7 else exp_comp / scale)
            series["units_none"].append(exp_none / scale)
            series["turned_away"].append(turned / scale)
            series["members_you"].append(0)
            series.setdefault("demand_you", []).append(exp_you)
            frame_events = b
        series["customers_you"].append(int((purchases_you > 0).sum()))
        series["aware_share"].append(float(aware[in_market].mean()) if in_market.any() else 0.0)
        if day % frame_every == 0:
            ev = frame_events
            ch_ev = member_of[ev] if membership else last_choice[ev]
            frames.append({"day": day, "a": ev.astype(int).tolist(), "c": ch_ev.astype(int).tolist()})

    # ---------------- outputs ----------------
    units_you_daily = np.array(series["units_you"], float)
    n_months = math.ceil(days / 30)
    if membership:
        monthly_units = [float(units_you_daily[min(len(units_you_daily) - 1, m * 30 + 29)] * scale) for m in range(n_months)]
    else:
        monthly_units = [float(units_you_daily[m * 30:(m + 1) * 30].sum() * scale * (30 / max(1, len(units_you_daily[m * 30:(m + 1) * 30]))))
                         for m in range(n_months)]
    weekly = []
    for w in range(math.ceil(days / 7)):
        sl = slice(w * 7, min(days, (w + 1) * 7))
        u = units_you_daily[sl]
        weekly.append({
            "week": w + 1,
            "units": float((u[-1] if membership else u.sum()) * scale),
            "aware_share": float(series["aware_share"][sl.stop - 1]),
            "customers_cum": float(series["customers_you"][sl.stop - 1] * scale),
            "turned_away": float(np.sum(series["turned_away"][sl]) * scale),
            "comp_units": float((series["units_comp"][sl.stop - 1] if membership else np.sum(series["units_comp"][sl])) * scale),
        })
    steady = monthly_units[-1] if monthly_units else 0.0
    peak = max((x["units"] for x in weekly), default=0)
    ramp_week = next((x["week"] for x in weekly if steady and x["units"] >= 0.8 * (weekly[-1]["units"] or 1)), None)

    final = member_of if membership else last_choice
    cust = purchases_you > 0

    def share(mask, of):
        return float(mask[of].mean()) if of.any() else None

    mode = gen.mode
    cust_modes = {MODE_NAMES[k]: share(mode == k, cust) for k in range(len(MODE_NAMES))}
    cust_segs = {arch.segments[k].key: share(seg == k, cust) for k in range(len(arch.segments))}
    trip = gen.dist[cust, 0]
    choice_counts = np.bincount(np.where(last_choice >= 0, last_choice, J), minlength=J + 1)
    comp_shares = (choice_counts[1:J] / max(1, choice_counts[:J].sum())).tolist()
    ch_names = {0: "paid_media", 1: "signage", 2: "wom"}
    channel_counts = {ch_names[c]: int((aware_channel == c).sum()) for c in (0, 1, 2)}
    wd = np.stack([G[:, KI[f"tm_wd_{h:02d}"]] for h in range(24)], 1)
    peak_h = np.argmax(wd, 1)
    time_pref = np.select([peak_h < 12, peak_h < 21], [0, 1], 2)
    income_z = G[:, KI["lt_income"]]

    # ---- why: population decomposition of the choice (static utility channels)
    groups = {"chose_you": in_market & (final == 0), "chose_competitor": in_market & (final > 0), "chose_none": in_market & (final < 0)}
    best_comp = np.full(N, -1)
    if J > 1:
        vc = np.where(np.isfinite(v_static[:, 1:]), v_static[:, 1:], -1e9)
        best_comp = np.argmax(vc, 1) + 1
    decomp = {}
    for gname, mask in groups.items():
        if not mask.any():
            decomp[gname] = None
            continue
        row = {}
        for ch, arr in up.parts.items():
            you = arr[mask, 0]
            comp = arr[mask, best_comp[mask]] if J > 1 else np.zeros(mask.sum())
            row[ch] = {"you": round(float(np.mean(you)), 3), "best_competitor": round(float(np.mean(comp)), 3),
                       "edge": round(float(np.mean(you - comp)), 3)}
        decomp[gname] = {"n_agents": int(mask.sum()), "channels": row}
    # population-level importance of individual parameters for you vs the agent's best competitor
    lost = in_market & (final != 0) & gen.reach[:, 0]
    top_drivers = []
    if lost.any() and J > 1:
        Zu = gm._zcols(G, gm.UTIL_IDX)[lost]
        bc = best_comp[lost]
        W = up.lin_contrib_w  # P_u x J
        eff = Zu * (W[:, 0][None, :] - W[:, bc].T)  # effect on (you - best competitor); negative hurts you
        mean_eff = eff.mean(0)
        for k in np.argsort(mean_eff)[:12]:
            p = gm.REG[gm.UTIL_IDX[k]]
            top_drivers.append({"key": p.key, "label": p.label, "block": p.block, "feat": p.feat, "mean_effect": round(float(mean_eff[k]), 4)})
    # unreachable and price-excluded counts
    afford = (pop.meta["prices"][0] <= gm_wtp(G, ref_price))
    calib_after = None
    if calib["applied"]:
        calib_after = "participation x" + str(calib["multiplier"])

    agents = {
        "columns": ["lat", "lng", "age", "female", "segment", "mode", "in_market", "aware", "last_choice", "purchases_you", "wtp", "price_sens",
                    "dist_km", "digital", "social", "zone", "time_pref", "income_z", "time_fit_you", "u_you"],
        "rows": [], "modes": MODE_NAMES, "segments": [s.key for s in arch.segments], "time_prefs": ["morning", "evening", "late"],
    }
    wtp_v = gm_wtp(G, ref_price)
    psens_v = G[:, KI["ec_price_sens"]]
    dig = G[:, KI["lt_digital"]]
    soc = G[:, KI["lt_social"]]
    tfy = up.parts["time_fit"][:, 0]
    uy = np.where(np.isfinite(v_static[:, 0]), v_static[:, 0], -99)
    rows = agents["rows"]
    for i in range(N):
        rows.append([round(float(pop.lat[i]), 5), round(float(pop.lng[i]), 5), int(age[i]), int(female[i]), int(seg[i]), int(mode[i]), int(in_market[i]),
                     int(aware[i]), int(final[i]), int(purchases_you[i]), round(float(wtp_v[i])), round(float(psens_v[i]), 2),
                     round(float(gen.dist[i, 0]), 2), round(float(1 / (1 + math.exp(-dig[i]))), 2), round(float(1 / (1 + math.exp(-soc[i]))), 2),
                     int(zi[i]), int(time_pref[i]), round(float(income_z[i]), 2), round(float(tfy[i]), 3), round(float(uy[i]), 2)])

    by_block = {}
    for p in gm.REG:
        by_block[p.block] = by_block.get(p.block, 0) + 1
    return {
        "n_agents": N, "scale": round(scale, 2), "days": days, "seed": seed, "age_source": pop.age_src,
        "in_market_agents": int(in_market.sum()),
        "monthly_units": [round(x, 1) for x in monthly_units], "steady_units": round(steady, 1), "peak_weekly_units": round(peak, 1),
        "ramp_up_week": ramp_week, "weekly": weekly, "frames": frames, "frame_every": frame_every,
        "daily": {"units_you": [round(x * scale, 1) for x in series["units_you"]], "units_comp": [round(x * scale, 1) for x in series["units_comp"]],
                  "aware_share": [round(x, 4) for x in series["aware_share"]], "customers_you": [round(x * scale, 1) for x in series["customers_you"]],
                  "turned_away": [round(x * scale, 1) for x in series["turned_away"]],
                  "demand_you": [round(x, 1) for x in series.get("demand_you", [])]},
        "capacity_per_day": None if membership else round(float(cap_units_day), 1),
        "weekday_pattern": [round(float(x), 3) for x in dow],
        "accounting": ("Daily orders are counted in real units from every in-market agent's own choice probabilities "
                       "(purchase rate x probability of choosing you x residents per agent), then real-order randomness and your daily "
                       "capacity are applied. Dots on the map are individual sampled decisions."),
        "businesses": [{"idx": 0, "name": "Your business", "lat": float(biz.lat), "lng": float(biz.lng)}]
                      + [{"idx": j + 1, "name": c.name, "lat": c.lat, "lng": c.lng} for j, c in enumerate(pop.comps)],
        "competitors_simulated": len(pop.comps), "competitors_total": len(comps),
        "agents": agents,
        "genome": {"size": gm.GENOME_SIZE, "per_agent": gm.GENOME_SIZE, "total_parameters": int(N * gm.GENOME_SIZE), "by_block": by_block,
                   "blocks": gm.BLOCKS, "audit": gm.audit(), "hours_source": pop.meta["hours_source"], "attr_sources": pop.meta["attr_sources"],
                   "your_hours": list(pop.meta["hours"][0]), "month0": month0},
        "calibration": {**calib, "summary": calib_after},
        "decomposition": decomp, "top_drivers_against_you": top_drivers,
        "metrics": {
            "aware_final": round(float(aware[in_market].mean()) if in_market.any() else 0.0, 4),
            "aware_week4": round(series["aware_share"][min(days - 1, 27)], 4),
            "aware_week8": round(series["aware_share"][min(days - 1, 55)], 4),
            "trial_rate": round(float(cust[in_market & aware].mean()) if (in_market & aware).any() else 0.0, 4),
            "repeat_share": round(float((purchases_you[cust] >= 2).mean()) if cust.any() else 0.0, 4),
            "loyal_customers": int((purchases_you >= 3).sum() * scale),
            "mean_purchases": round(float(purchases_you[cust].mean()) if cust.any() else 0.0, 2),
            "customers_total": round(float(cust.sum() * scale), 1),
            "churned": round(churned * scale, 1),
            "left_you": round(float(left_you.sum() * scale), 1),
            "turned_away": round(float((turned_away > 0).sum() * scale), 1),
            "decision_events": int(decisions),
            "mean_trip_km": round(float(trip.mean()), 3) if trip.size else None,
            "p90_trip_km": round(float(np.percentile(trip, 90)), 3) if trip.size else None,
            "share_within_1km": round(float((trip <= 1).mean()), 4) if trip.size else None,
            "share_within_2km": round(float((trip <= 2).mean()), 4) if trip.size else None,
            "customer_modes": cust_modes, "customer_segments": cust_segs,
            "competitor_shares": [round(x, 4) for x in comp_shares],
            "none_share": (round(float(np.sum(series["units_none"]) / max(1e-9, np.sum(series["units_none"]) + np.sum(series["units_comp"])
                                                                          + np.sum(series["units_you"]) + np.sum(series["turned_away"]))), 4)
                           if not membership else None),
            "aware_channels": {k: round(v * scale, 1) for k, v in channel_counts.items()},
            "mean_age": round(float(age.mean()), 1), "female_share": round(float(female.mean()), 4),
            "afford_share": round(float(afford[in_market].mean()) if in_market.any() else 0.0, 4),
            "wtp_p10": round(float(np.percentile(wtp_v, 10))), "wtp_p50": round(float(np.percentile(wtp_v, 50))), "wtp_p90": round(float(np.percentile(wtp_v, 90))),
            "reach_you_share": round(float(gen.reach[in_market, 0].mean()) if in_market.any() else 0.0, 4),
            "mean_time_fit_you": round(float(up.parts["time_fit"][in_market, 0].mean()) if in_market.any() else 0.0, 3),
        },
        "assumptions": dict(D),
        "note": "Synthetic agents placed by real population density, each with a 615-parameter genome; behaviour parameters are documented "
                "assumptions. Not real people; not a forecast guarantee.",
        "timing_ms": {"genome": round((t_gen - t0) * 1000, 1), "total": round((time.perf_counter() - t0) * 1000, 1)},
        "duration_ms": round((time.perf_counter() - t0) * 1000, 1),
    }


def gm_wtp(G: np.ndarray, ref_price: float) -> np.ndarray:
    """Effective willingness to pay (same formula as the price channel)."""
    KI = gm.KI
    g = lambda k: G[:, KI[k]].astype(float)  # noqa: E731
    return ref_price * g("ec_wtp_multiple") * (1 + 0.25 * (g("ec_budget_flex") - 0.5)) * (1 + 0.15 * g("ec_corporate_benefit"))
