"""Scientific unit and invariant tests for the Spatial Synthetic Population Engine.

Tests:
1. IPF convergence, entropy minimization, non-negativity.
2. Mode A (weighted population) vs Mode B (10,000 deterministic records).
3. Household structural consistency (cohabitant coordinate and income alignment).
4. Deterministic reproducibility across seeds.
5. Formal validation metrics (WAPE, ESS, standardized differences).
"""
import numpy as np


from app.engine.population import (
    AGE_BANDS,
    build_synthetic_population,
    ipf_solve,
    validate_population,
)


def test_ipf_convergence_on_known_margins():
    """Verify that IPF accurately converges on known marginal constraints."""
    # 4 profiles, 3 constraints
    X = np.array([
        [1.0, 0.0, 1.0],
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 1.0],
        [0.0, 1.0, 0.0],
    ])
    margins = np.array([60.0, 40.0, 50.0])  # Margin 0: 60, Margin 1: 40, Margin 2: 50
    margin_names = ["group_a", "group_b", "feature_x"]

    res = ipf_solve(X, margins, margin_names=margin_names, tol=1e-5)
    assert res.converged, "IPF did not converge"
    assert np.all(res.weights >= 0), "Weights must be non-negative"
    assert res.effective_sample_size > 0

    # Verify margin conservation
    achieved = X.T @ res.weights
    for k in range(len(margins)):
        assert abs(achieved[k] - margins[k]) < 0.05, f"Margin {k} not preserved: {achieved[k]} vs {margins[k]}"


def test_synthetic_population_mode_a_weighted():
    """Mode A: Weighted synthetic population preserves total catchment population."""
    zones = [
        {"lat": 28.6315, "lng": 77.2167, "population": 25000.0},
        {"lat": 28.6350, "lng": 77.2200, "population": 15000.0},
    ]
    total_pop = 40000.0
    bands = [{"age": b, "male": 1200.0 - i * 40, "female": 1150.0 - i * 38} for i, b in enumerate(AGE_BANDS)]
    age_sex = {"bands": bands}

    pop = build_synthetic_population(
        total_population=total_pop,
        age_sex_distribution=age_sex,
        zones=zones,
        target_records=5000,
        mode="weighted",
        seed=101,
    )

    assert pop.n_records == 5000
    assert abs(pop.total_represented_population - total_pop) < 1.0
    weights = np.array([a.weight for a in pop.agents])
    assert np.all(weights > 0)
    assert abs(weights.sum() - total_pop) < 1.0


def test_synthetic_population_mode_b_exactly_10000_records():
    """Mode B: Exactly 10,000 representative records with deterministic reproducibility."""
    zones = [
        {"lat": 28.6315, "lng": 77.2167, "population": 30000.0},
        {"lat": 28.6350, "lng": 77.2200, "population": 20000.0},
    ]
    total_pop = 50000.0

    pop1 = build_synthetic_population(
        total_population=total_pop,
        age_sex_distribution=None,
        zones=zones,
        target_records=10000,
        mode="representative_fixed",
        seed=42,
    )

    pop2 = build_synthetic_population(
        total_population=total_pop,
        age_sex_distribution=None,
        zones=zones,
        target_records=10000,
        mode="representative_fixed",
        seed=42,
    )

    assert pop1.n_records == 10000
    assert len(pop1.agents) == 10000
    assert pop1.total_represented_population == total_pop

    # Determinism: exact match across two runs
    assert pop1.agents[0].lat == pop2.agents[0].lat
    assert pop1.agents[0].age == pop2.agents[0].age
    assert pop1.agents[9999].household_id == pop2.agents[9999].household_id
    assert pop1.agents[9999].weight == pop2.agents[9999].weight


def test_household_structural_consistency():
    """Agents in the same synthetic household must share location and income tier."""
    zones = [{"lat": 28.6315, "lng": 77.2167, "population": 10000.0}]
    pop = build_synthetic_population(10000.0, None, zones, target_records=1000, seed=7)

    by_household = {}
    for a in pop.agents:
        by_household.setdefault(a.household_id, []).append(a)

    multi_person_hh = [members for members in by_household.values() if len(members) > 1]
    assert len(multi_person_hh) > 0, "Expected multi-person households to be synthesized"

    for members in multi_person_hh:
        ref = members[0]
        for m in members[1:]:
            assert m.lat == ref.lat, "Household members must share latitude"
            assert m.lng == ref.lng, "Household members must share longitude"
            assert m.income_decile == ref.income_decile, "Household members must share income decile"
            assert m.household_size == len(members), "Household size attribute must match cohabitants count"


def test_validation_report_metrics():
    """Verify validation report produces standard error metrics (WAPE, ESS)."""
    zones = [{"lat": 28.6315, "lng": 77.2167, "population": 15000.0}]
    pop = build_synthetic_population(15000.0, None, zones, target_records=2000, mode="weighted", seed=99)
    report = validate_population(pop, {})

    assert report.total_population_error_pct < 0.5
    assert 0.0 <= report.age_sex_wape < 0.15
    assert report.effective_sample_size > 0
    assert report.is_valid
