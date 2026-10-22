"""Agent-based market simulation ("live market").

Synthetic people are placed on the map in proportion to real population density
(WorldPop totals distributed over OSM buildings), each with an individual profile
drawn from the factor registry: age and sex (WorldPop age–sex structure where
available), segment, willingness to pay, price/quality sensitivity, travel mode and
distance tolerance, digital adoption, social influence, loyalty and category
affinity. The simulation then runs day by day:

* awareness of a new business spreads through paid reach (scaled by digital
  adoption), word of mouth from customers in the same zone, and storefront signage;
* in-market agents make purchase decisions with their own random-utility choice
  (price vs their own WTP, quality, distance, habit, congestion memory, taste noise),
  including a "none of these" option;
* membership businesses hold members, who reconsider monthly and may churn or switch;
* capacity limits turn customers away, and a turned-away agent remembers it.

This is a stochastic, assumption-driven model. Every agent is synthetic; the
population of agents is a scaled sample (each represents ``scale`` residents).
"""
from __future__ import annotations

import math
import time

import numpy as np

from ..categories.archetypes import Archetype
from .geo import haversine_km
from .model import BusinessInputs, Competitor, ResolvedParams, Zone

AGE_BANDS = ["0-4", "5-9", "10-14", "15-19", "20-24", "25-29", "30-34", "35-39", "40-44", "45-49", "50-54", "55-59", "60-64", "65-69", "70-74", "75-79", "80+"]
AGE_MID = np.array([2, 7, 12, 17, 22, 27, 32, 37, 42, 47, 52, 57, 62, 67, 72, 77, 84], float)
# Fallback age structure (assumption, roughly an Indian urban pyramid) used only if WorldPop age–sex is unavailable.
DEFAULT_AGE = np.array([0.075, 0.080, 0.085, 0.088, 0.092, 0.092, 0.085, 0.077, 0.068, 0.060, 0.052, 0.043, 0.035, 0.027, 0.019, 0.012, 0.010])

# Category affinity by age group: child (0-14), young (15-29), mid (30-49), senior (50+). Assumptions.
AFFINITY = {
    "membership": (0.15, 1.6, 1.0, 0.45),
    "dine_in": (0.5, 1.4, 1.1, 0.6),
    "takeaway": (0.4, 1.5, 1.05, 0.45),
    "retail": (0.5, 1.0, 1.1, 1.0),
    "appointment": (0.5, 1.1, 1.1, 1.0),
    "lodging": (0.1, 1.1, 1.25, 0.7),
}
FEMALE_AFFINITY = {"membership": 0.8, "dine_in": 1.0, "takeaway": 0.95, "retail": 1.05, "appointment": 1.2, "lodging": 0.95}
# Travel modes: (name, share budget, share mainstream, share premium, distance tolerance multiplier, speed km/h)
MODES = [
    ("walk", 0.36, 0.24, 0.12, 0.55, 4.5),
    ("two_wheeler", 0.30, 0.34, 0.22, 1.25, 18.0),
    ("car", 0.02, 0.10, 0.38, 1.4, 16.0),
    ("auto", 0.10, 0.10, 0.10, 1.1, 14.0),
    ("bus", 0.14, 0.10, 0.04, 0.95, 11.0),
    ("metro", 0.04, 0.08, 0.10, 1.2, 25.0),
    ("cycle", 0.04, 0.04, 0.04, 0.8, 10.0),
]
CHANNELS = ["digital", "social", "print", "signage", "wom", "referral", "events", "aggregator"]

DEFAULTS = {
    "wom_rate": 0.015, "signage_radius": 0.35, "signage_daily": 0.04, "noise_scale": 0.6, "habit_build": 0.25, "habit_cap": 1.2,
    "congestion_penalty": 1.0, "congestion_memory": 14, "monthly_churn": 0.08, "switch_threshold": 0.35, "trial_bias": 0.15,
}


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


def run_abm(arch: Archetype, zones: list[Zone], comps: list[Competitor], biz: BusinessInputs, params: ResolvedParams,
            ref_price: float, *, n_agents: int = 6000, days: int = 84, seed: int = 42, age_sex: dict | None = None,
            spacing_km: float = 0.35, frame_every: int = 2, overrides: dict | None = None) -> dict:
    t0 = time.perf_counter()
    rng = np.random.default_rng(seed + 101)
    P = params.values
    D = {**DEFAULTS, **{k: v for k, v in (overrides or {}).items() if k in DEFAULTS}}
    S = len(arch.segments)
    J = 1 + len(comps)
    membership = arch.key == "membership"

    # ---------------- population of agents (real density) ----------------
    pop = np.array([max(0.0, z.population) for z in zones])
    act = np.array([max(0.0, z.activity) for z in zones])
    W = pop + (act * P.get("activity_equivalent", 120.0) if arch.demand_base == "residents_and_activity" else 0.0)
    if W.sum() <= 0:
        raise ValueError("No population to place agents")
    N = int(n_agents)
    scale = float(W.sum() / N)  # resident-equivalents represented by one agent
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
    seg = rng.choice(S, size=N, p=seg_share / seg_share.sum())
    aff_tab = np.array(AFFINITY[arch.key])
    affinity = aff_tab[_age_group(age)] * np.where(female, FEMALE_AFFINITY[arch.key], 1.0)
    affinity = affinity / max(1e-9, affinity.mean())
    p_in = np.clip(P["participation"] * affinity, 0, 0.97)
    in_market = rng.random(N) < p_in

    wtp_mult = np.array([s.wtp_multiplier for s in arch.segments])[seg]
    wtp = ref_price * wtp_mult * np.exp(rng.normal(0, P["wtp_sigma"], N))
    psens = np.array([s.price_sensitivity for s in arch.segments])[seg] * np.exp(rng.normal(0, 0.25, N))
    qsens = np.exp(rng.normal(0, 0.25, N))
    mode_share = np.array([[m[1 + s] for m in MODES] for s in range(3)])
    mode = np.array([rng.choice(len(MODES), p=mode_share[min(s_, 2)] / mode_share[min(s_, 2)].sum()) for s_ in seg])
    mode_tol = np.array([m[4] for m in MODES])[mode]
    seg_dt = np.array([s.distance_tolerance for s in arch.segments])[seg]
    tol = seg_dt * mode_tol
    young = np.clip(1.2 - (age - 15) / 50, 0.15, 1.0)
    digital = np.clip(rng.beta(2.5, 2.0, N) * young * 1.15, 0, 1)
    social = rng.beta(2.0, 2.5, N)
    loyal_prop = rng.beta(2.0, 2.0, N)
    novelty = rng.beta(1.6, 2.4, N)
    freq = np.clip(rng.gamma(4.0, P["frequency"] / 4.0, N), 0.1, 30) if not membership else np.ones(N)
    time_pref = rng.choice(3, size=N, p=[0.38, 0.47, 0.15])

    # ---------------- businesses ----------------
    blat = np.array([biz.lat] + [c.lat for c in comps])
    blng = np.array([biz.lng] + [c.lng for c in comps])
    price = np.array([biz.price] + [c.price if c.price else ref_price * P["competitor_price_ratio"] for c in comps], float)
    qual = np.array([biz.quality] + [c.quality if c.quality is not None else P["competitor_quality"] for c in comps], float)
    dist = haversine_km(lat[:, None], lng[:, None], blat[None, :], blng[None, :]) * P["circuity"]
    dist = np.maximum(dist, 0.1)
    reach = dist <= (P["max_km"] * tol)[:, None]

    # static utility (without noise / habit / congestion)
    afford_pen = np.where(price[None, :] > wtp[:, None], 2.5 * np.log(price[None, :] / wtp[:, None]), 0.0)
    v_static = (P["beta_quality"] * qsens[:, None] * (qual[None, :] - 0.5)
                - P["beta_price"] * psens[:, None] * np.log(price[None, :] / ref_price)
                - (P["distance_decay"] / tol)[:, None] * dist - afford_pen)
    v_static[:, 0] += D["trial_bias"] * novelty
    v_static = np.where(reach, v_static, -np.inf)

    # awareness: competitors known if reachable; you are discovered over time
    hs = max(P["marketing_half_saturation"], 1.0)
    a_target = P["awareness_base"] + (1 - P["awareness_base"]) * (1 - 2 ** (-max(biz.marketing_spend, 0) / hs))
    daily_paid = -math.log(max(1e-6, 1 - a_target)) / 30.0  # hazard so that ~a_target is reached in a month
    dig_norm = digital / max(1e-6, digital.mean())
    aware = np.zeros(N, bool)
    aware_day = np.full(N, -1)
    aware_channel = np.full(N, -1)
    near_site = dist[:, 0] <= D["signage_radius"]

    # dynamic state
    habit = np.zeros((N, J))
    cong = np.zeros(N)  # congestion memory against you (days remaining)
    member_of = np.full(N, -1)
    reconsider = rng.integers(0, 30, N)
    purchases_you = np.zeros(N, int)
    first_you = np.full(N, -1)
    last_choice = np.full(N, -1)
    turned_away = np.zeros(N, int)
    left_you = np.zeros(N, bool)
    churned = 0

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
        g = rng.gumbel(0, D["noise_scale"], size=v.shape)
        u = v + g
        u0 = P["outside_utility"] + rng.gumbel(0, D["noise_scale"], size=idx.size)
        best = np.argmax(u, axis=1)
        bu = u[np.arange(idx.size), best]
        return np.where(bu > u0, best, -1)

    for day in range(days):
        # ---- awareness spread ----
        cust_zone = np.bincount(zi[purchases_you > 0], minlength=len(zones)).astype(float)
        wom_pressure = np.divide(cust_zone, zone_count, out=np.zeros_like(cust_zone), where=zone_count > 0)[zi]
        p_paid = 1 - np.exp(-daily_paid * dig_norm)
        p_wom = np.clip(D["wom_rate"] * social * wom_pressure * 30, 0, 0.5)
        p_sign = np.where(near_site, D["signage_daily"], 0.0)
        r = rng.random(N)
        newly = (~aware) & (r < 1 - (1 - p_paid) * (1 - p_wom) * (1 - p_sign))
        if newly.any():
            idx = np.where(newly)[0]
            weights = np.stack([p_paid[idx], p_wom[idx], p_sign[idx]], 1) + 1e-12
            ch = np.array([rng.choice(3, p=w / w.sum()) for w in weights])
            aware_channel[idx] = np.array([0, 4, 3])[ch]
            aware[idx] = True
            aware_day[idx] = day
        cong = np.maximum(cong - 1, 0)
        frame_events = []

        if membership:
            due = np.where(in_market & ((reconsider == day % 30) | (member_of < 0) & (rng.random(N) < 1 / 15)))[0]
            # churn among current members at their monthly reconsideration
            mem_due = due[member_of[due] >= 0]
            churn = mem_due[rng.random(mem_due.size) < D["monthly_churn"]]
            churned += int((member_of[churn] == 0).sum())
            left_you[churn[member_of[churn] == 0]] = True
            member_of[churn] = -1
            choice = choose(due)
            decisions += due.size
            cur = member_of[due]
            # switching only if clearly better than current (habit already favours current)
            keep = (cur >= 0) & (choice != cur) & (rng.random(due.size) > 0.5)
            choice = np.where(keep, cur, choice)
            # capacity for you
            joining = due[(choice == 0) & (cur != 0)]
            current_members = int((member_of == 0).sum())
            room = int(max(0, math.floor(daily_cap) - current_members))
            if joining.size > room:
                rejected = rng.choice(joining, size=joining.size - room, replace=False)
                choice[np.isin(due, rejected)] = -1
                cong[rejected] = D["congestion_memory"]
                turned_away[rejected] += 1
                series_turned = rejected.size
            else:
                series_turned = 0
            left = due[(cur == 0) & (choice != 0)]
            left_you[left] = True
            member_of[due] = choice
            newm = due[choice >= 0]
            habit[newm, choice[choice >= 0]] = np.minimum(habit[newm, choice[choice >= 0]] + D["habit_build"], D["habit_cap"])
            fy = due[(choice == 0) & (first_you[due] < 0)]
            first_you[fy] = day
            purchases_you[due[choice == 0]] += 1
            last_choice[due] = choice
            units_you = int((member_of == 0).sum())
            units_comp = int((member_of > 0).sum())
            # members "visit" ~3x a week: used for the animation and daily activity
            visiting = np.where((member_of >= 0) & (rng.random(N) < 3 / 7))[0]
            frame_events = visiting
            series["members_you"].append(units_you)
            series["units_you"].append(units_you)
            series["units_comp"].append(units_comp)
            series["turned_away"].append(series_turned)
            series["units_none"].append(int((in_market & (member_of < 0)).sum()))
        else:
            buyers = np.where(in_market & (rng.random(N) < freq / 30.0))[0]
            choice = choose(buyers)
            decisions += buyers.size
            to_you = buyers[choice == 0]
            cap_today = rng.poisson(daily_cap) if daily_cap < 50 else int(round(daily_cap))
            if to_you.size > cap_today:
                rejected = rng.choice(to_you, size=to_you.size - cap_today, replace=False)
                choice[np.isin(buyers, rejected)] = -1
                cong[rejected] = D["congestion_memory"]
                turned_away[rejected] += 1
                n_rej = rejected.size
            else:
                n_rej = 0
            got = choice >= 0
            habit[buyers[got], choice[got]] = np.minimum(habit[buyers[got], choice[got]] + D["habit_build"] * loyal_prop[buyers[got]], D["habit_cap"])
            prev = last_choice[buyers]
            left_you[buyers[(prev == 0) & (choice > 0)]] = True
            fy = buyers[(choice == 0) & (first_you[buyers] < 0)]
            first_you[fy] = day
            purchases_you[buyers[choice == 0]] += 1
            last_choice[buyers[got]] = choice[got]
            series["units_you"].append(int((choice == 0).sum()))
            series["units_comp"].append(int((choice > 0).sum()))
            series["units_none"].append(int((choice < 0).sum()))
            series["turned_away"].append(n_rej)
            series["members_you"].append(0)
            frame_events = buyers[got]
        series["customers_you"].append(int((purchases_you > 0).sum()))
        series["aware_share"].append(float(aware[in_market].mean()) if in_market.any() else 0.0)
        if day % frame_every == 0:
            ev = frame_events
            if membership:
                ch_ev = member_of[ev]
            else:
                ch_ev = last_choice[ev]
            frames.append({"day": day, "a": ev.astype(int).tolist(), "c": ch_ev.astype(int).tolist()})

    # ---------------- outputs ----------------
    units_you_daily = np.array(series["units_you"], float)
    if membership:
        monthly_units = [float(units_you_daily[min(len(units_you_daily) - 1, m * 30 + 29)] * scale) for m in range(math.ceil(days / 30))]
    else:
        monthly_units = [float(units_you_daily[m * 30:(m + 1) * 30].sum() * scale * (30 / max(1, len(units_you_daily[m * 30:(m + 1) * 30])))) for m in range(math.ceil(days / 30))]
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

    cust = purchases_you > 0
    def share(mask, of):
        return float(mask[of].mean()) if of.any() else None

    mode_names = [m[0] for m in MODES]
    cust_modes = {mode_names[k]: share(mode == k, cust) for k in range(len(MODES))}
    cust_segs = {arch.segments[k].key: share(seg == k, cust) for k in range(S)}
    trip = dist[cust, 0]
    choice_counts = np.bincount(np.where(last_choice >= 0, last_choice, J), minlength=J + 1)
    comp_shares = (choice_counts[1:J] / max(1, choice_counts[:J].sum())).tolist()
    channel_counts = {CHANNELS[c]: int((aware_channel == c).sum()) for c in (0, 3, 4)}

    agents = {
        "columns": ["lat", "lng", "age", "female", "segment", "mode", "in_market", "aware", "last_choice", "purchases_you", "wtp", "price_sens", "dist_km", "digital", "social", "zone", "time_pref"],
        "rows": [[round(float(lat[i]), 5), round(float(lng[i]), 5), int(age[i]), int(female[i]), int(seg[i]), int(mode[i]), int(in_market[i]), int(aware[i]),
                  int(member_of[i] if membership else last_choice[i]), int(purchases_you[i]), round(float(wtp[i])), round(float(psens[i]), 2),
                  round(float(dist[i, 0]), 2), round(float(digital[i]), 2), round(float(social[i]), 2), int(zi[i]), int(time_pref[i])] for i in range(N)],
        "modes": mode_names, "segments": [s.key for s in arch.segments], "time_prefs": ["morning", "evening", "late"],
    }
    return {
        "n_agents": N, "scale": round(scale, 2), "days": days, "seed": seed, "age_source": age_src,
        "in_market_agents": int(in_market.sum()),
        "monthly_units": [round(x, 1) for x in monthly_units], "steady_units": round(steady, 1), "peak_weekly_units": round(peak, 1),
        "ramp_up_week": ramp_week, "weekly": weekly, "frames": frames, "frame_every": frame_every,
        "daily": {"units_you": [round(x * scale, 1) for x in series["units_you"]], "units_comp": [round(x * scale, 1) for x in series["units_comp"]],
                  "aware_share": [round(x, 4) for x in series["aware_share"]], "customers_you": [round(x * scale, 1) for x in series["customers_you"]],
                  "turned_away": [round(x * scale, 1) for x in series["turned_away"]]},
        "businesses": [{"idx": 0, "name": "Your business", "lat": float(blat[0]), "lng": float(blng[0])}] + [{"idx": j + 1, "name": c.name, "lat": c.lat, "lng": c.lng} for j, c in enumerate(comps)],
        "agents": agents,
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
            "none_share": round(float(np.sum(series["units_none"]) / max(1, decisions)), 4) if not membership else None,
            "aware_channels": {k: round(v * scale, 1) for k, v in channel_counts.items()},
            "mean_age": round(float(age.mean()), 1), "female_share": round(float(female.mean()), 4),
            "afford_share": round(float((wtp[in_market] >= biz.price).mean()) if in_market.any() else 0.0, 4),
            "wtp_p10": round(float(np.percentile(wtp, 10))), "wtp_p50": round(float(np.percentile(wtp, 50))), "wtp_p90": round(float(np.percentile(wtp, 90))),
        },
        "assumptions": {k: v for k, v in D.items()},
        "note": "Synthetic agents placed by real population density; behaviour parameters are documented assumptions. Not real people; not a forecast guarantee.",
        "duration_ms": round((time.perf_counter() - t0) * 1000, 1),
    }
