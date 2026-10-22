"""Attach values to the 615 factor definitions for one project / location / run.

Status of every factor value:
* ``computed``   derived from live data for this location (OSM, WorldPop, geometry)
* ``user``       entered by the user
* ``assumed``    a documented model assumption (default or overridden)
* ``simulated``  produced by the simulation run
* ``pending``    computable, but needs market data or a run first
* ``unavailable`` defined for future data; no source connected (never invented)
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

import numpy as np

from ..categories.archetypes import Archetype
from ..engine.abm import AGE_BANDS, DEFAULTS as ABM_DEFAULTS, MODES
from ..engine.geo import haversine_km
from .registry import BY_KEY, DOMAINS, FACTORS, POI_TYPES, counts

SOURCE_STATUS = {"osm": "computed", "worldpop": "computed", "derived": "computed", "user": "user", "assumption": "assumed", "simulated": "simulated"}


def _r(x, nd=4):
    if x is None:
        return None
    if isinstance(x, (bool, str)):
        return x
    try:
        x = float(x)
    except (TypeError, ValueError):
        return x
    if math.isnan(x) or math.isinf(x):
        return None
    return round(x, nd)


def compute(project, arch: Archetype, loc, snap, competitors: list, scenario_inputs: dict, result: dict | None,
            n_actuals: int = 0, wape: float | None = None) -> dict:
    v: dict[str, object] = {}
    st: dict[str, str] = {}

    def put(key, val, status=None):
        if key in BY_KEY and val is not None:
            v[key] = _r(val) if not isinstance(val, (list, dict)) else val
            if status:
                st[key] = status

    lat, lng = loc.lat, loc.lng
    # ---------------- geography / context POIs ----------------
    failed = {e.get("source") for e in ((snap.errors or []) if snap is not None else [])}
    if snap is not None:
        pts = snap.activity_points or []
        by_kind: dict[str, list] = {}
        for p in pts:
            by_kind.setdefault(p.get("kind"), []).append(p)
        radius = float(snap.population.get("radius_km") or 1)
        area = math.pi * radius ** 2
        for k, _ in ([] if "context" in failed else POI_TYPES):
            arr = by_kind.get(k, [])
            if arr:
                d = haversine_km(lat, lng, np.array([a["lat"] for a in arr]), np.array([a["lng"] for a in arr]))
                put(f"geo_{k}_count_1km", int((d <= 1).sum()))
                put(f"geo_{k}_nearest_km", float(d.min()))
            else:
                put(f"geo_{k}_count_1km", 0)
        nb = snap.population.get("n_buildings") or snap.population.get("buildings_used")
        put("geo_building_count", nb)
        put("geo_building_density", (nb / area) if nb else None)
        put("geo_catchment_area", area)
        put("geo_catchment_radius", radius)
        put("geo_zone_count", len(snap.zones))
        put("geo_zone_spacing", snap.population.get("spacing_km"))
        put("geo_poi_density", (len(pts) / area if area else None) if "context" not in failed else None)
        if pts:
            commercial = sum(1 for p in pts if p["kind"] in ("restaurant", "cafe", "fast_food", "mall", "supermarket", "convenience", "office", "hotel", "marketplace"))
            civic = sum(1 for p in pts if p["kind"] in ("school", "college", "university", "hospital", "clinic", "place_of_worship", "library", "police", "post_office"))
            put("geo_commercial_mix", commercial / len(pts))
            put("geo_civic_mix", civic / len(pts))
        put("geo_activity_points", sum(z.get("activity", 0) for z in snap.zones))
        zp = np.array([z["population"] for z in snap.zones]) if snap.zones else np.array([])
        if zp.size:
            put("geo_zone_pop_p10", np.percentile(zp, 10))
            put("geo_zone_pop_p50", np.percentile(zp, 50))
            put("geo_zone_pop_p90", np.percentile(zp, 90))
            put("geo_zones_populated_share", float((zp > 0).mean()))
        put("geo_buildings_1km", snap.population.get("buildings_1km"))
        put("geo_buildings_2km", snap.population.get("buildings_2km"))

        # ---------------- demographics ----------------
        total = snap.population.get("total")
        psrc = snap.population.get("source")
        put("dem_population", total, "computed" if psrc == "worldpop" else ("user" if psrc == "user" else "assumed"))
        put("dem_nighttime_population", total if psrc == "worldpop" else None)
        put("dem_density", total / area if total else None)
        put("dem_household_size", 4.4, "assumed")
        put("dem_households", total / 4.4 if total else None)
        if zp.size and zp.sum() > 0:
            put("dem_pop_peak_zone", zp.max())
            top = np.sort(zp)[::-1][: max(1, int(len(zp) * 0.2))]
            put("dem_pop_concentration", top.sum() / zp.sum())
        ages = (snap.population.get("age_sex") or {}).get("bands")
        put("dem_age_profile_source", "WorldPop" if ages else "default assumption")
        if ages:
            m = np.array([b["male"] for b in ages])
            fe = np.array([b["female"] for b in ages])
            tot = (m + fe).sum()
            for i, b in enumerate(AGE_BANDS):
                kb = b.replace("-", "_").replace("+", "plus")
                put(f"dem_age_{kb}_male", m[i] / tot)
                put(f"dem_age_{kb}_female", fe[i] / tot)
            share = (m + fe) / tot
            put("dem_sex_ratio", 100 * m.sum() / max(1e-9, fe.sum()))
            put("dem_child_share", share[:3].sum())
            put("dem_youth_share", share[3:6].sum())
            put("dem_working_age_share", share[3:13].sum())
            put("dem_elderly_share", share[13:].sum())
            put("dem_dependency_ratio", (share[:3].sum() + share[13:].sum()) / max(1e-9, share[3:13].sum()))
            cum = np.cumsum(share)
            mid = [2, 7, 12, 17, 22, 27, 32, 37, 42, 47, 52, 57, 62, 67, 72, 77, 84]
            put("dem_median_age", mid[int(np.searchsorted(cum, 0.5))])

        # ---------------- mobility (geometry) ----------------
        put("mob_catchment_method", snap.catchment_method)
        if loc.catchment.get("mode") == "isochrone":
            put("mob_isochrone_minutes", loc.catchment.get("minutes"))
            put("mob_isochrone_profile", loc.catchment.get("profile"))
        bs = by_kind.get("bus_stop", [])
        rs = by_kind.get("rail_station", [])
        pk = by_kind.get("parking", [])

        def within(arr, km):
            if not arr:
                return 0
            return int((haversine_km(lat, lng, np.array([a["lat"] for a in arr]), np.array([a["lng"] for a in arr])) <= km).sum())
        if "context" not in failed:
            put("mob_bus_stops_500m", within(bs, 0.5))
            put("mob_rail_1500m", within(rs, 1.5))
            put("mob_parking_500m", within(pk, 0.5))
        if snap.zones:
            zl = np.array([z["lat"] for z in snap.zones])
            zg = np.array([z["lng"] for z in snap.zones])
            dz = haversine_km(lat, lng, zl, zg)
            for km in (1, 2, 3):
                put(f"mob_pop_within_{km}km", float(zp[dz <= km].sum()))
            lam = arch.params["distance_decay"].value
            put("mob_accessibility_index", float((zp * np.exp(-lam * dz * arch.params["circuity"].value)).sum()))
        put("mob_mobility_note", "Distances are straight-line × circuity unless a travel-time catchment is configured.")

        # ---------------- competition ----------------
        act = [c for c in competitors if c.active]
        comp_ok = "competitors" not in failed or bool(act)
        put("cmp_count", len(act) if comp_ok else None)
        put("cmp_user_added", sum(1 for c in act if c.source == "user"))
        put("cmp_hypothetical", sum(1 for c in act if c.is_hypothetical))
        put("cmp_excluded", sum(1 for c in competitors if not c.active))
        put("cmp_demo_flag", sum(1 for c in act if c.source == "demo"))
        put("cmp_density", len(act) / area if area else None)
        if total:
            put("cmp_per_10k_pop", len(act) / total * 10000)
            if nb:
                put("cmp_buildings_per_1000", nb / (total / 1000))
        if act:
            d = haversine_km(lat, lng, np.array([c.lat for c in act]), np.array([c.lng for c in act]))
            for key, km in (("0_5", 0.5), ("1", 1), ("2", 2), ("3", 3)):
                put(f"cmp_count_{key}km", int((d <= km).sum()))
            put("cmp_nearest_km", d.min())
            put("cmp_mean_distance_km", d.mean())
            osm_c = [c for c in act if c.source == "osm"]
            if osm_c:
                put("cmp_named_share", sum(1 for c in osm_c if not c.name.startswith("Unnamed")) / len(osm_c))
                put("cmp_hours_known_share", sum(1 for c in osm_c if (c.tags or {}).get("opening_hours")) / len(osm_c))
                put("cmp_branded_share", sum(1 for c in osm_c if (c.tags or {}).get("brand")) / len(osm_c))
                put("cmp_website_share", sum(1 for c in osm_c if (c.tags or {}).get("website") or (c.tags or {}).get("contact:website")) / len(osm_c))
                ages_d = [(datetime.now(timezone.utc) - c.source_updated_at).days for c in osm_c if c.source_updated_at]
                if ages_d:
                    put("cmp_median_record_age_days", float(np.median(ages_d)))
                brands = sorted({(c.tags or {}).get("brand") for c in osm_c if (c.tags or {}).get("brand")})
                put("cmp_competitor_brand_list", ", ".join(brands) if brands else "none tagged")
            prices = [c.price for c in act if c.price]
            put("cmp_price_known_count", len(prices))
            put("eco_known_price_share", len(prices) / len(act))
            if prices:
                put("eco_competitor_price_median", float(np.median(prices)))
                put("eco_competitor_price_min", min(prices))
                put("eco_competitor_price_max", max(prices))
            put("cmp_quality_known_share", sum(1 for c in act if c.quality is not None) / len(act))
        elif comp_ok:
            for key in ("0_5", "1", "2", "3"):
                put(f"cmp_count_{key}km", 0)
        put("cmp_coverage_level", (snap.coverage or {}).get("level"))
        put("cmp_osm_tag_filters", len(project.category.get("filters") or []))
        put("cmp_search_method", project.category.get("method"))
        put("cmp_competitor_mix_note", "Competitor data covers mapped businesses only; add unmapped ones on the Market map.")

        # ---------------- external / provenance ----------------
        put("ext_data_retrieved_at", snap.retrieved_at.isoformat())
        osm_base = next((s.get("source_updated_at") for s in snap.sources if s.get("source") == "osm_overpass" and s.get("source_updated_at")), None)
        put("ext_osm_base_time", osm_base)
        put("ext_worldpop_year", 2020 if psrc == "worldpop" else None)
        put("ext_snapshot_status", snap.status)
        put("ext_provider_errors", len(snap.errors or []))
        put("ext_cache_hits", sum(1 for s in snap.sources if s.get("from_cache")))
    put("ext_demo_mode", bool(project.is_demo))
    put("ext_actuals_recorded", n_actuals)
    put("ext_forecast_wape", wape)
    put("ext_validation_status", "Not calibrated on observed sales; invariants unit-tested.")

    # ---------------- user inputs (operations etc.) ----------------
    i = scenario_inputs or {}
    cap = i.get("capacity") or {}
    for k, key in (("price", "ops_price"), ("quality", "ops_quality"), ("rent", "ops_rent"), ("payroll", "ops_payroll"), ("utilities", "ops_utilities"),
                   ("other_fixed", "ops_other_fixed"), ("startup_cost", "ops_startup_cost"), ("variable_cost_per_unit", "ops_variable_cost_unit"),
                   ("marketing_spend", "mkt_spend"), ("reference_price", "eco_reference_price"), ("price", "eco_own_price"), ("seed", "ext_random_seed")):
        put(key, i.get(k))
    for ck, key in (("max_members", "ops_max_members"), ("seats", "ops_seats"), ("turns_per_day", "ops_turns_per_day"), ("open_days_per_month", "ops_open_days"),
                    ("max_orders_per_day", "ops_max_orders_day"), ("max_baskets_per_day", "ops_max_baskets_day"), ("stations", "ops_stations"),
                    ("slots_per_station_per_day", "ops_slots_per_station"), ("rooms", "ops_rooms")):
        put(key, cap.get(ck))
    put("ops_capacity_units", arch.capacity_units(cap) if i else None)
    put("ops_fixed_cost_total", sum(float(i.get(k) or 0) for k in ("rent", "payroll", "utilities", "other_fixed", "marketing_spend")) if i else None)
    put("ops_operating_hours", (project.profile or {}).get("operating_hours") or None)
    put("ops_objective", project.objective)
    put("ops_decision_goal", project.decision_goal)
    put("ops_archetype", arch.label)
    put("ops_category_label", project.category.get("label"))
    put("cmp_differentiation_claims", len((project.profile or {}).get("positioning") or []))
    put("mob_delivery_radius", arch.params["max_km"].value if arch.key == "takeaway" else None, "assumed")

    # ---------------- assumptions (archetype params + ABM defaults) ----------------
    overrides = i.get("param_overrides") or {}
    pmap = {"participation": "beh_participation", "frequency": "beh_frequency", "beta_price": "beh_beta_price", "beta_quality": "beh_beta_quality",
            "outside_utility": "beh_outside_utility", "wtp_sigma": "eco_wtp_sigma", "competitor_price_ratio": "eco_competitor_price_ratio",
            "variable_cost_ratio": "eco_variable_cost_ratio", "distance_decay": "mob_distance_decay", "max_km": "mob_max_km", "circuity": "mob_circuity",
            "awareness_base": "mkt_awareness_base", "marketing_half_saturation": "mkt_half_saturation", "competitor_quality": "cmp_quality_assumed"}
    for pk_, fk in pmap.items():
        if pk_ in arch.params:
            put(fk, overrides.get(pk_, arch.params[pk_].value), "user" if pk_ in overrides else "assumed")
    for sgm in arch.segments:
        put(f"eco_{sgm.key}_share", sgm.share, "assumed")
        put(f"eco_{sgm.key}_wtp_mult", sgm.wtp_multiplier, "assumed")
        put(f"eco_{sgm.key}_price_sens", sgm.price_sensitivity, "assumed")
        put(f"eco_{sgm.key}_distance_tol", sgm.distance_tolerance, "assumed")
    for idx, (mname, sb, sm, sp, tolm, spd) in enumerate(MODES):
        put(f"mob_{mname}_share", round(0.45 * sb + 0.40 * sm + 0.15 * sp, 4), "assumed")
        put(f"mob_{mname}_speed", spd, "assumed")
        put(f"mob_{mname}_tolerance", tolm, "assumed")
    for k_, fk in (("noise_scale", "beh_noise_scale"), ("habit_build", "ret_loyalty_build"), ("habit_cap", "ret_loyalty_cap"), ("trial_bias", "beh_trial_bias"),
                   ("congestion_penalty", "ret_congestion_penalty"), ("congestion_memory", "ret_congestion_memory_days"), ("monthly_churn", "ret_monthly_churn"),
                   ("switch_threshold", "ret_switch_threshold"), ("wom_rate", "mkt_wom_rate"), ("signage_radius", "mkt_signage_radius")):
        put(fk, ABM_DEFAULTS[k_], "assumed")
    put("beh_habit_bonus", ABM_DEFAULTS["habit_cap"], "assumed")
    put("ret_reconsider_days", 30, "assumed")
    put("beh_morning_share", 0.38, "assumed")
    put("beh_evening_share", 0.47, "assumed")
    put("beh_night_share", 0.15, "assumed")
    put("beh_weekend_uplift", 1.0, "assumed")
    from ..engine.abm import AFFINITY, FEMALE_AFFINITY
    af = AFFINITY[arch.key]
    put("beh_affinity_child", af[0], "assumed")
    put("beh_affinity_young", af[1], "assumed")
    put("beh_affinity_mid", af[2], "assumed")
    put("beh_affinity_senior", af[3], "assumed")
    put("beh_female_affinity", FEMALE_AFFINITY[arch.key], "assumed")
    put("beh_peer_effect_radius", (snap.population.get("spacing_km") if snap else None), "assumed")
    put("beh_referral_propensity", 0.5, "assumed")
    put("mob_travel_time_budget", 30, "assumed")
    for ch, w in (("digital", 0.35), ("social", 0.15), ("print", 0.05), ("signage", 0.15), ("wom", 0.2), ("referral", 0.05), ("events", 0.03), ("aggregator", 0.02)):
        put(f"mkt_{ch}_weight", w, "assumed")
    put("mkt_mkt_note", "Paid reach is scaled by each agent's digital adoption; word of mouth spreads within home zones; signage reaches agents within the signage radius.")
    put("ret_retention_note", "Membership agents reconsider monthly with a churn probability; transactional agents build habit with each purchase.")

    # ---------------- simulated outputs ----------------
    if result:
        s_, fin, mc = result["summary"], result["finance"], result.get("monte_carlo") or {}
        put("ops_revenue", fin["revenue"]); put("ops_operating_profit", fin["operating_profit"]); put("ops_break_even_units", fin["break_even_units"])
        put("ops_utilization", fin["utilization"]); put("ops_payback_months", fin["payback_months"]); put("ops_capacity_bound", s_["capacity_bound"])
        put("ops_prob_loss", mc.get("prob_loss")); put("ops_profit_p10", (mc.get("profit") or {}).get("p10")); put("ops_profit_p90", (mc.get("profit") or {}).get("p90"))
        put("ops_model_version", result.get("model_version"))
        put("eco_unit_margin", fin["unit_margin"])
        put("eco_price_index", s_["price"] / s_["reference_price"] if s_.get("reference_price") else None)
        put("eco_reference_price", s_["reference_price"], "user" if s_["reference_price_status"] == "user" else "assumed")
        put("cmp_price_gap", s_["price"] - s_["reference_price"])
        put("cmp_quality_gap", float(i.get("quality", 0.55)) - arch.params["competitor_quality"].value)
        put("cmp_captured_by_all", s_["captured_by_all_modeled"]); put("cmp_leakage", 1 - (s_["captured_by_all_modeled"] or 0))
        for seg in result["segments"]:
            put(f"eco_{seg['key']}_affordability", seg["affordability_at_price"])
        comps_out = result.get("competitors") or []
        shares = [c["modeled_share_of_in_market"] or 0 for c in comps_out] + [s_["capture_of_in_market"] or 0]
        tot_s = sum(shares)
        if tot_s > 0:
            put("cmp_hhi", sum((x / tot_s * 100) ** 2 for x in shares))
            put("cmp_top_share", max(shares) / tot_s)
            put("cmp_your_rank", 1 + sum(1 for x in shares[:-1] if x > shares[-1]))
            put("cmp_competitor_share_spread", float(np.std(shares[:-1])) if len(shares) > 1 else 0)
            put("cmp_threat_index", 1 - shares[-1] / max(shares))
        if comps_out:
            best = max(comps_out, key=lambda c: c["modeled_units"] or 0)
            put("cmp_strongest_competitor", best["name"])
        zc = [z["capture"] for z in result.get("zones", [])]
        if zc:
            put("cmp_white_space_zones", sum(1 for x in zc if x > np.percentile(zc, 75)))
        sens = result.get("sensitivity") or {}
        curve = sens.get("price_curve") or []
        if curve:
            bp = max(curve, key=lambda x: x["profit"] or -1e18)
            put("eco_profit_max_price", bp["price"])
            a, b = curve[len(curve) // 2 - 1], curve[len(curve) // 2 + 1]
            if a["units"] and b["units"] and a["price"] and b["price"]:
                put("eco_price_elasticity_est", ((b["units"] - a["units"]) / ((a["units"] + b["units"]) / 2)) / ((b["price"] - a["price"]) / ((a["price"] + b["price"]) / 2)))
        mcurve = sens.get("marketing_curve") or []
        if mcurve:
            put("mkt_profit_max_spend", max(mcurve, key=lambda x: x["profit"] or -1e18)["spend"])
        total = (snap.population.get("total") if snap else None) or 0
        put("eco_revenue_per_capita", fin["revenue"] / total if total else None)
        put("eco_market_value", (s_["in_market_units"] or 0) * s_["reference_price"])
        put("eco_your_value_share", fin["revenue"] / ((s_["in_market_units"] or 0) * s_["reference_price"]) if s_["in_market_units"] else None)
        put("eco_affordability_gap", s_["price"] - (result.get("abm") or {}).get("metrics", {}).get("wtp_p50", s_["price"]))

        abm = result.get("abm")
        if abm:
            m = abm["metrics"]
            put("dem_agents_n", abm["n_agents"]); put("dem_agent_scale", abm["scale"]); put("dem_in_market_agents", abm["in_market_agents"])
            put("dem_agent_mean_age", m["mean_age"]); put("dem_agent_female_share", m["female_share"])
            put("eco_agent_wtp_median", m["wtp_p50"]); put("eco_agent_wtp_p10", m["wtp_p10"]); put("eco_agent_wtp_p90", m["wtp_p90"])
            put("eco_afford_share", m["afford_share"])
            rows = abm["agents"]["rows"]
            seg_idx = abm["agents"]["columns"].index("segment")
            if rows:
                segs = np.array([r[seg_idx] for r in rows])
                put("eco_income_tier_low", float((segs == 0).mean())); put("eco_income_tier_mid", float((segs == 1).mean())); put("eco_income_tier_high", float((segs == 2).mean()))
            put("beh_trial_rate", m["trial_rate"]); put("beh_repeat_rate", m["repeat_share"]); put("beh_decision_events", m["decision_events"])
            put("beh_choice_share_outside", m.get("none_share"))
            cs = m.get("competitor_shares") or []
            put("beh_choice_share_you", 1 - sum(cs) if cs else None)
            put("beh_switchers_out", m["left_you"])
            for seg_k, val in (m.get("customer_segments") or {}).items():
                put(f"beh_customers_{seg_k}_share", val)
            for mode_k, val in (m.get("customer_modes") or {}).items():
                put(f"mob_{mode_k}_customer_share", val)
            put("mob_mean_trip_km_you", m["mean_trip_km"]); put("mob_p90_trip_km_you", m["p90_trip_km"])
            put("mob_share_within_1km", m["share_within_1km"]); put("mob_share_within_2km", m["share_within_2km"])
            if m["mean_trip_km"]:
                put("mob_mean_trip_min_you", m["mean_trip_km"] / 15 * 60)
            put("mkt_awareness_final", m["aware_final"]); put("mkt_awareness_week4", m["aware_week4"]); put("mkt_awareness_week8", m["aware_week8"])
            put("mkt_aware_to_trial", m["trial_rate"])
            for ch, val in (m.get("aware_channels") or {}).items():
                put(f"mkt_{ch}_aware_agents", val)
            spend = float(i.get("marketing_spend") or 0)
            aware_people = sum((m.get("aware_channels") or {}).values())
            put("mkt_cost_per_aware", spend * 3 / aware_people if aware_people else None)
            put("mkt_cost_per_customer", spend * 3 / m["customers_total"] if m["customers_total"] else None)
            mf = abm.get("monthly_finance") or []
            if mf:
                last = mf[-1]
                put("mkt_mkt_roi", (last["revenue"] - last["units"] * (fin["variable_cost"] / max(1e-9, s_["units_sold"] or 1))) / spend if spend else None)
                for k_, idx in (("ops_month1_units", 0), ("ops_month2_units", 1), ("ops_month3_units", 2)):
                    if idx < len(mf):
                        put(k_, mf[idx]["units"])
                put("ops_cash_burn_ramp", sum(min(0, x["profit"]) for x in mf))
            put("ops_ramp_up_weeks", abm.get("ramp_up_week"))
            put("ops_rejected_demand", m["turned_away"]); put("ret_turned_away", m["turned_away"])
            put("ops_congestion_days", sum(1 for w in abm["weekly"] if w["turned_away"] > 0) * 7)
            put("ret_retained_customers", abm["weekly"][-1]["units"] if abm["weekly"] else None)
            put("ret_churned_customers", m["churned"]); put("ret_repeat_share", m["repeat_share"]); put("ret_loyal_customers", m["loyal_customers"])
            put("ret_mean_purchases", m["mean_purchases"])
            churn_obs = m["churned"] / m["customers_total"] if m["customers_total"] else None
            put("ret_churn_observed", churn_obs)
            put("ret_satisfaction_proxy", 1 - (m["turned_away"] / m["customers_total"]) if m["customers_total"] else None)
            put("ret_customers_week12", abm["weekly"][-1]["units"] if abm["weekly"] else None)
            put("ret_peak_customers", abm["peak_weekly_units"]); put("ret_stable_week", abm.get("ramp_up_week"))
            put("ret_retention_curve_points", len(abm["weekly"]))
            life = (1 / max(churn_obs, 1e-3)) if churn_obs else None
            put("ret_customer_lifetime_months", min(life, 60) if life else None)
            if life:
                put("ret_clv", min(life, 60) * float(fin["unit_margin"] or 0) * (1 if arch.key == "membership" else max(1.0, m["mean_purchases"] / 3)))
            put("ret_first_month_retention", (abm["weekly"][4]["units"] / abm["weekly"][3]["units"]) if len(abm["weekly"]) > 4 and abm["weekly"][3]["units"] else None)
            put("ext_simulation_horizon", abm["days"])
            put("cmp_agents_choosing_comp", sum((m.get("competitor_shares") or [])))
        put("ext_mc_draws", mc.get("draws"))

    # ---------------- assemble ----------------
    out = []
    for fct in FACTORS:
        if fct.key in v:
            status = st.get(fct.key) or SOURCE_STATUS.get(fct.source, "computed")
            out.append({"key": fct.key, "value": v[fct.key], "status": status})
        elif fct.role == "reserved":
            out.append({"key": fct.key, "value": None, "status": "unavailable"})
        else:
            out.append({"key": fct.key, "value": None, "status": "pending"})
    summary: dict[str, int] = {}
    for o in out:
        summary[o["status"]] = summary.get(o["status"], 0) + 1
    return {"definitions": [f.as_dict() for f in FACTORS], "values": out, "summary": summary, "counts": counts(), "domains": DOMAINS}
