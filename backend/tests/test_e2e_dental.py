"""Master End-to-End Scientific Integration Test: Dental Clinic in Indiranagar, Bengaluru.

Validates the complete integrated StratIq pipeline end-to-end:
1. Phase 1: Category Resolution ("dental clinic" -> "dentist") & 6-Tier Competitor Filtering.
2. Phase 2: Factor Registry parameter bindings and evidence classifications.
3. Phase 3: Spatial Synthetic Population Generation with IPF demographic marginal convergence (<2% error).
4. Phase 5: Spatial Distance & Travel-Time Network Matrix Integration.
5. Phase 4: Behavioural Discrete Choice Model evaluation with outside option.
6. Phase 6: Procedure-level Dental Clinical Economics (7 procedures, chair capacity binding, financial identities).
7. Phase 7: Deterministic Cohort Transition Matrix Dynamics (n_{t+1} = n_t * T_t).
"""
from __future__ import annotations

import numpy as np
import pytest

from app.categories.archetypes import get_archetype
from app.categories.competitors import classify_competitor
from app.categories.resolver import resolve_offline
from app.engine.abm import run_cohort_transition_baseline
from app.engine.choice.conditional_logit import ChoiceDataset, ConditionalLogitEstimator
from app.engine.choice.validation import evaluate_holdout
from app.engine.economics.dental import DENTAL_PROCEDURES, DentalClinicEconomics
from app.engine.geo import compute_spatial_matrices
from app.engine.model import BusinessInputs, Competitor, ResolvedParams, Zone, build_arrays, run_choice
from app.engine.population import AGE_BANDS, build_synthetic_population, validate_population
from app.factors.evidence_map import EvidenceStatus
from app.factors.registry import FACTORS

# Indiranagar, Bengaluru Coordinates
INDIRANAGAR_LAT = 12.9784
INDIRANAGAR_LNG = 77.6408



def test_full_pipeline_e2e_dental_indiranagar():
    """Execute complete end-to-end scientific pipeline for an Indiranagar Dental Clinic."""

    # -------------------------------------------------------------------------
    # Step 1: Category Resolution & Competitor Filtering (Phase 1)
    # -------------------------------------------------------------------------
    resolution = resolve_offline("dental clinic")
    assert resolution is not None, "Failed to resolve 'dental clinic'"
    assert resolution.key == "dentist"
    assert resolution.archetype == "appointment"
    assert resolution.confidence >= 0.85

    arch = get_archetype(resolution.archetype)
    assert arch.key == "appointment"

    # Multi-tier competitor filtering
    candidate_pois = [
        {"name": "Clove Dental Indiranagar", "tags": {"amenity": "dentist", "healthcare": "dentist"}},
        {"name": "Sabka Dentist CMH Road", "tags": {"amenity": "dentist"}},
        {"name": "Axiss Dental 100ft Road", "tags": {"healthcare": "dentist"}},
        {"name": "Kaya Skin Clinic", "tags": {"amenity": "clinic", "healthcare": "dermatology"}},
        {"name": "Bodycraft Salon & Spa", "tags": {"shop": "beauty", "beauty": "spa"}},
        {"name": "Starbucks Indiranagar", "tags": {"amenity": "cafe"}},
    ]

    filtered_competitors: list[Competitor] = []
    for i, poi in enumerate(candidate_pois):
        cls = classify_competitor("dentist", poi["tags"], poi["name"])
        if cls.is_direct_or_partial:
            # Place competitors around Indiranagar (0.5 to 1.8 km away)
            comp_lat = INDIRANAGAR_LAT + 0.005 * (i + 1)
            comp_lng = INDIRANAGAR_LNG - 0.004 * (i + 1)
            filtered_competitors.append(
                Competitor(id=f"comp_{i}", name=poi["name"], lat=comp_lat, lng=comp_lng, price=1200.0, quality=0.65)
            )

    # Spas, salons, cafes must be strictly excluded; 3 dental clinics retained
    assert len(filtered_competitors) == 3
    assert all("Dental" in c.name or "Dentist" in c.name for c in filtered_competitors)

    # -------------------------------------------------------------------------
    # Step 2: Factor Registry & Evidence Map Verification (Phase 2)
    # -------------------------------------------------------------------------
    factors_by_key = {f.key: f for f in FACTORS}
    clinic_factor = factors_by_key.get("geo_clinic_count_1km")
    assert clinic_factor is not None
    assert clinic_factor.evidence_status == EvidenceStatus.OBSERVED
    assert clinic_factor.domain == "geography"



    # -------------------------------------------------------------------------
    # Step 3: Spatial Synthetic Population via IPF (Phase 3)
    # -------------------------------------------------------------------------
    n_zones = 8
    zone_pops = [3500.0, 4200.0, 2800.0, 5100.0, 3900.0, 4600.0, 3100.0, 4800.0]
    total_catchment_pop = sum(zone_pops)

    # Create demand zones across Indiranagar sectors (100ft Rd, CMH Rd, HAL 2nd Stage, etc.)
    zones: list[Zone] = []
    zone_dicts = []
    for z_idx in range(n_zones):
        z_lat = INDIRANAGAR_LAT + 0.006 * ((z_idx % 3) - 1)
        z_lng = INDIRANAGAR_LNG + 0.006 * ((z_idx // 3) - 1)
        zones.append(Zone(lat=z_lat, lng=z_lng, population=zone_pops[z_idx], activity=10.0))
        zone_dicts.append({"lat": z_lat, "lng": z_lng, "population": zone_pops[z_idx]})

    # Synthetic population IPF calibration against empirical targets
    bands = [{"age": b, "male": 1000.0 - i * 30, "female": 980.0 - i * 28} for i, b in enumerate(AGE_BANDS)]
    synth_pop = build_synthetic_population(
        total_population=total_catchment_pop,
        age_sex_distribution={"bands": bands},
        zones=zone_dicts,
        target_records=5000,
        mode="weighted",
        seed=101,
    )
    assert synth_pop.n_records == 5000
    assert abs(synth_pop.total_represented_population - total_catchment_pop) < 1.0

    target_margins = {f"zone_{i}": zone_pops[i] for i in range(n_zones)}
    report = validate_population(synth_pop, target_margins)
    assert report.is_valid
    assert report.total_population_error_pct < 0.01


    # -------------------------------------------------------------------------
    # Step 4: Spatial Network Travel-Time Matrix Integration (Phase 5)
    # -------------------------------------------------------------------------
    clinic_biz = BusinessInputs(
        lat=INDIRANAGAR_LAT,
        lng=INDIRANAGAR_LNG,
        price=1500.0,
        quality=0.75,
        marketing_spend=25000.0,
        rent=75000.0,
        payroll=120000.0,
        utilities=15000.0,
        other_fixed=10000.0,
        startup_cost=2500000.0,
    )
    params = ResolvedParams.from_archetype(arch)

    m_arrays = build_arrays(arch, zones, filtered_competitors, clinic_biz, params)
    assert m_arrays.dist_km.shape == (n_zones, 1 + len(filtered_competitors))
    assert m_arrays.travel_time_min is not None
    assert np.all(m_arrays.travel_time_min >= 1.0), "Travel times must be positive and floored"
    assert m_arrays.dist_source in {"precomputed_network", "haversine_circuity_fallback"}

    # -------------------------------------------------------------------------
    # Step 5: Discrete Choice Engine Evaluation (Phase 4)
    # -------------------------------------------------------------------------
    pv = params.draws(1, None)
    choice_out = run_choice(arch, m_arrays, clinic_biz, pv, keep_detail=True)

    unconstrained_monthly_demand = float(choice_out["units_by_alt"][0, 0])
    in_market_total = float(choice_out["in_market_units"][0])
    assert unconstrained_monthly_demand > 0.0, "Demand must be strictly positive"
    assert unconstrained_monthly_demand < in_market_total, "Demand cannot exceed total in-market residents"

    # Outside option probability conservation
    P_matrix = choice_out["P"][0]  # [Z, S, J]
    assert np.all(P_matrix >= 0.0)
    assert np.all(P_matrix.sum(axis=2) < 1.0), "Outside good must retain non-zero share"

    # -------------------------------------------------------------------------
    # Step 6: Procedure-Level Dental Clinical Economics (Phase 6)
    # -------------------------------------------------------------------------
    dental_econ = DentalClinicEconomics(
        chairs=3,
        operating_hours_per_day=9,
        open_days_per_month=26,
        rent_per_month=clinic_biz.rent,
        payroll_per_month=clinic_biz.payroll,
        utilities_per_month=clinic_biz.utilities,
        other_fixed_per_month=clinic_biz.other_fixed,
        marketing_per_month=clinic_biz.marketing_spend,
        equipment_capex=clinic_biz.startup_cost,
    )


    econ_res = dental_econ.evaluate(unconstrained_monthly_demand=unconstrained_monthly_demand)
    summary = econ_res["summary"]
    finance = econ_res["finance"]

    # Chair capacity invariants
    avail_chair_mins = dental_econ.available_chair_minutes  # 3 * 9 * 60 * 26 = 42,120 mins
    assert avail_chair_mins == 42120.0
    assert summary["completed_units"] <= unconstrained_monthly_demand
    assert summary["chair_utilization_pct"] <= 100.0


    # Total completed chair minutes strictly bounded by capacity
    completed_chair_mins = sum(p["completed_units"] * p["duration_minutes"] for p in econ_res["procedures"])
    assert completed_chair_mins <= avail_chair_mins + 1.0

    # Exact financial identities
    rev = finance["revenue"]
    vc = finance["variable_cost"]
    contrib = finance["contribution_margin"]
    fc = finance["fixed_cost"]
    profit = finance["operating_profit"]

    assert rev > 0.0
    assert vc > 0.0
    assert abs(contrib - (rev - vc)) < 0.05, "Contribution margin identity violated"
    assert abs(profit - (contrib - fc)) < 0.05, "Operating profit identity violated"

    # -------------------------------------------------------------------------
    # Step 7: Deterministic Cohort Transition Dynamics (Phase 7)
    # -------------------------------------------------------------------------
    cohort_res = run_cohort_transition_baseline(
        total_population=total_catchment_pop,
        days=84,
        p_aware_daily=0.035,
        p_in_market_daily=float(params.values["participation"] * params.values["frequency"] / 30.0),
        p_choice=summary["completed_units"] / max(1.0, unconstrained_monthly_demand),
        p_trial_to_loyal=0.15,
        p_churn_daily=0.08 / 30.0,
        wom_rate=0.015,
    )

    final_cohorts = cohort_res["final_cohorts"]
    assert len(cohort_res["daily_active_customers"]) == 84
    # Mass conservation: sum of cohorts must equal total catchment population
    assert sum(final_cohorts.values()) == pytest.approx(total_catchment_pop, rel=1e-5)
    # Customer growth: active customers at day 84 must be greater than day 1
    assert cohort_res["daily_active_customers"][-1] > cohort_res["daily_active_customers"][0]
    assert cohort_res["steady_state_active"] > 0.0
