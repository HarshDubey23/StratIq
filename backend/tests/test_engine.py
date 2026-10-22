"""Unit and invariant tests for the numerical engine (no network, no DB)."""
import math

import numpy as np

from app.categories.archetypes import ARCHETYPES
from app.engine.finance import economics
from app.engine.geo import circle_polygon, haversine_km, hex_grid, points_in_polygon
from app.engine.model import BusinessInputs, Competitor, ResolvedParams, Zone, awareness, build_arrays, run_choice
from app.engine.simulate import simulate

LAT, LNG = 28.6315, 77.2167  # arbitrary test coordinates


def make_zones(n_pop=40000.0):
    pts = hex_grid(LAT, LNG, 3.0, 0.4)
    return [Zone(lat, lng, n_pop / len(pts), activity=1 if i % 7 == 0 else 0) for i, (lat, lng) in enumerate(pts)]


def make_comps(k=3, price=None):
    return [Competitor(f"c{i}", f"Comp {i}", LAT + 0.01 * (i + 1), LNG - 0.008 * i, price=price) for i in range(k)]


def biz(**kw):
    base = dict(lat=LAT, lng=LNG, price=1800, quality=0.6, marketing_spend=15000, reference_price=1600,
                capacity={"max_members": 400}, rent=60000, payroll=80000, utilities=15000, other_fixed=10000,
                startup_cost=1500000)
    base.update(kw)
    return BusinessInputs(**base)


def test_haversine_known_distance():
    # One degree of latitude ~ 111.2 km
    assert abs(haversine_km(0, 0, 1, 0) - 111.19) < 0.2


def test_hex_grid_within_radius_and_point_in_polygon():
    pts = hex_grid(LAT, LNG, 2.0, 0.5)
    d = haversine_km(LAT, LNG, np.array([p[0] for p in pts]), np.array([p[1] for p in pts]))
    assert d.max() <= 2.05 and len(pts) > 20
    ring = circle_polygon(LAT, LNG, 1.0)
    inside = points_in_polygon([(LAT, LNG), (LAT + 0.05, LNG)], [ring])
    assert inside == [True, False]


def test_choice_probabilities_are_valid():
    arch = ARCHETYPES["membership"]
    params = ResolvedParams.from_archetype(arch)
    m = build_arrays(arch, make_zones(), make_comps(), biz(), params)
    r = run_choice(arch, m, biz(), params.draws(1, None), keep_detail=True)
    P = r["P"][0]
    assert np.all(P >= 0)
    assert np.all(P.sum(axis=2) < 1.0)  # outside option always keeps some probability
    assert r["units_by_alt"][0].sum() <= r["in_market_units"][0] + 1e-6


def test_awareness_saturates():
    base, hs = np.array([0.25]), np.array([25000.0])
    assert awareness(0, base, hs)[0] == 0.25
    assert abs(awareness(25000, base, hs)[0] - 0.625) < 1e-9
    assert awareness(1e9, base, hs)[0] <= 1.0


def test_finance_identities():
    e = economics(300, 1500, 300, 200000, 1200000, 400)
    assert e["revenue"] == 450000
    assert e["operating_profit"] == 450000 - 90000 - 200000
    assert abs(e["break_even_units"] - 200000 / 1200) < 1e-9
    assert abs(e["payback_months"] - 1200000 / 160000) < 1e-9
    e2 = economics(10, 100, 120, 5000, 0, 100)
    assert math.isinf(float(e2["break_even_units"]))


def test_higher_price_lowers_demand_ceteris_paribus():
    arch = ARCHETYPES["membership"]
    zones, comps = make_zones(), make_comps()
    lo = simulate(arch, zones, comps, biz(price=1500), mc_draws=0, with_sensitivity=False, n_agents=0)
    hi = simulate(arch, zones, comps, biz(price=1800), mc_draws=0, with_sensitivity=False, n_agents=0)
    assert lo["summary"]["modeled_demand_units"] > hi["summary"]["modeled_demand_units"]


def test_adding_competitor_reduces_demand():
    arch = ARCHETYPES["membership"]
    zones = make_zones()
    a = simulate(arch, zones, make_comps(2), biz(), mc_draws=0, with_sensitivity=False, n_agents=0)
    extra = make_comps(2) + [Competitor("new", "Hypothetical gym", LAT + 0.002, LNG + 0.002, source="user")]
    b = simulate(arch, zones, extra, biz(), mc_draws=0, with_sensitivity=False, n_agents=0)
    assert b["summary"]["modeled_demand_units"] < a["summary"]["modeled_demand_units"]


def test_capacity_constraint_binds():
    arch = ARCHETYPES["membership"]
    r = simulate(arch, make_zones(400000), make_comps(1), biz(capacity={"max_members": 50}), mc_draws=0, with_sensitivity=False, n_agents=0)
    assert r["summary"]["units_sold"] == 50 and r["summary"]["capacity_bound"] is True


def test_marketing_increases_demand():
    arch = ARCHETYPES["takeaway"]
    zones, comps = make_zones(), make_comps()
    cap = {"max_orders_per_day": 5000, "open_days_per_month": 30}
    a = simulate(arch, zones, comps, biz(price=400, reference_price=400, marketing_spend=0, capacity=cap), mc_draws=0, with_sensitivity=False, n_agents=0)
    b = simulate(arch, zones, comps, biz(price=400, reference_price=400, marketing_spend=50000, capacity=cap), mc_draws=0, with_sensitivity=False, n_agents=0)
    assert b["summary"]["modeled_demand_units"] > a["summary"]["modeled_demand_units"]


def test_monte_carlo_is_reproducible_and_ordered():
    arch = ARCHETYPES["dine_in"]
    kw = dict(mc_draws=300, seed=7, with_sensitivity=False, n_agents=50)
    b = biz(price=350, reference_price=300, capacity={"seats": 40, "turns_per_day": 3, "open_days_per_month": 30})
    r1 = simulate(arch, make_zones(), make_comps(), b, **kw)
    r2 = simulate(arch, make_zones(), make_comps(), b, **kw)
    assert r1["monte_carlo"]["profit"] == r2["monte_carlo"]["profit"]
    p = r1["monte_carlo"]["profit"]
    assert p["p10"] <= p["p50"] <= p["p90"]
    assert 0.0 <= r1["monte_carlo"]["prob_loss"] <= 1.0
    assert r1["agents"]["rows"] == r2["agents"]["rows"]


def test_all_archetypes_run_with_sensitivity():
    zones, comps = make_zones(), make_comps(price=500)
    for key, arch in ARCHETYPES.items():
        r = simulate(arch, zones, comps, biz(price=500, reference_price=None, capacity={}), mc_draws=50, n_agents=20)
        assert r["finance"]["revenue"] is not None, key
        assert len(r["sensitivity"]["price_curve"]) == 15
        assert r["summary"]["reference_price_status"] == "derived_from_competitor_prices"


def test_price_sweep_responds_when_reference_unknown():
    arch = ARCHETYPES["membership"]
    r = simulate(arch, make_zones(), make_comps(), biz(reference_price=None), mc_draws=0, n_agents=0)
    units = [p["units"] for p in r["sensitivity"]["price_curve"]]
    assert units[0] > units[-1]


def test_no_zones_raises():
    from app.engine.simulate import SimulationError
    try:
        simulate(ARCHETYPES["membership"], [], [], biz(), mc_draws=0)
    except SimulationError:
        return
    raise AssertionError("expected SimulationError")


def test_decision_layer_ranks_and_flags_gaps():
    from app.engine.recommend import decide
    arch = ARCHETYPES["membership"]
    zones, comps = make_zones(60000), make_comps(3)
    s = [
        {"id": "a", "name": "Baseline", "is_baseline": True, "result": simulate(arch, zones, comps, biz(price=1800), mc_draws=200, n_agents=0)},
        {"id": "b", "name": "Lower price", "result": simulate(arch, zones, comps, biz(price=1500), mc_draws=200, n_agents=0)},
    ]
    d = decide(s, "profit", {"population_method": "dasymetric_buildings", "catchment_method": "radius"}, arch.label)
    assert d["ranking"][0]["rank"] == 1 and len(d["ranking"]) == 2
    assert any(g["key"] == "competitor_prices" for g in d["gaps"])
    assert d["verdict"] in {"potentially_viable", "financially_challenging", "high_uncertainty", "more_evidence_required"}
    d2 = decide(s, "low_risk", {}, arch.label)
    assert d2["ranking"][0]["prob_loss"] <= d2["ranking"][-1]["prob_loss"]
