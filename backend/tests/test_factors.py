"""Factor registry and factor-value computation (offline)."""
from datetime import datetime, timezone
from types import SimpleNamespace

from app.categories.archetypes import ARCHETYPES
from app.engine.abm import run_abm
from app.engine.model import ResolvedParams
from app.engine.simulate import simulate
from app.factors.compute import compute
from app.factors.registry import FACTORS, counts
from tests.test_engine import LAT, LNG, biz, make_comps, make_zones


def test_registry_has_615_unique_factors_in_10_domains():
    c = counts()
    assert c["total"] == 615
    assert len({f.key for f in FACTORS}) == 615
    assert len(c["by_domain"]) == 10
    assert all(f.role in {"agent", "choice", "finance", "output", "context", "reserved"} for f in FACTORS)


def test_abm_places_agents_and_runs():
    arch = ARCHETYPES["membership"]
    r = run_abm(arch, make_zones(60000), make_comps(3), biz(price=1500), ResolvedParams.from_archetype(arch), 1600, n_agents=2000, days=42)
    assert r["n_agents"] == 2000 and abs(r["scale"] - 30.0) < 1e-6
    assert len(r["agents"]["rows"]) == 2000 and len(r["frames"]) == 21
    assert r["monthly_units"][-1] <= 400 + 1e-6  # capacity respected
    assert 0 <= r["metrics"]["aware_final"] <= 1
    r2 = run_abm(arch, make_zones(60000), make_comps(3), biz(price=1500), ResolvedParams.from_archetype(arch), 1600, n_agents=2000, days=42)
    assert r2["monthly_units"] == r["monthly_units"]  # seeded, reproducible


def test_abm_higher_price_fewer_customers():
    arch = ARCHETYPES["takeaway"]
    cap = {"max_orders_per_day": 5000, "open_days_per_month": 30}
    lo = run_abm(arch, make_zones(), make_comps(), biz(price=300, capacity=cap), ResolvedParams.from_archetype(arch), 400, n_agents=3000, days=42)
    hi = run_abm(arch, make_zones(), make_comps(), biz(price=600, capacity=cap), ResolvedParams.from_archetype(arch), 400, n_agents=3000, days=42)
    assert lo["monthly_units"][-1] > hi["monthly_units"][-1]


def test_factor_values_never_invent_reserved_factors():
    arch = ARCHETYPES["membership"]
    zones = make_zones(60000)
    res = simulate(arch, zones, make_comps(3), biz(), mc_draws=100, n_agents=0)
    res["abm"] = run_abm(arch, zones, make_comps(3), biz(), ResolvedParams.from_archetype(arch), 1600, n_agents=1500, days=30)
    res["abm"]["monthly_finance"] = [{"month": 1, "units": 100.0, "capped_units": 100.0, "revenue": 1.0, "profit": -1.0}]
    snap = SimpleNamespace(
        activity_points=[{"lat": LAT + 0.003, "lng": LNG, "name": "S", "kind": "school"}, {"lat": LAT, "lng": LNG + 0.004, "name": "B", "kind": "bus_stop"}],
        population={"radius_km": 3.0, "total": 60000, "source": "worldpop", "spacing_km": 0.4, "n_buildings": 1500},
        zones=[{"lat": z.lat, "lng": z.lng, "population": z.population, "activity": z.activity} for z in zones],
        catchment_method="radius", coverage={"level": "partial"}, retrieved_at=datetime.now(timezone.utc), sources=[], errors=[], status="complete")
    comp = SimpleNamespace(active=True, source="osm", is_hypothetical=False, lat=LAT + 0.01, lng=LNG, name="Gym X", tags={"brand": "X"}, price=None, quality=None,
                           source_updated_at=datetime(2024, 1, 1, tzinfo=timezone.utc))
    project = SimpleNamespace(category={"label": "Gym", "filters": ["a"], "method": "taxonomy"}, profile={}, objective="start_new", decision_goal="profit", is_demo=False)
    loc = SimpleNamespace(lat=LAT, lng=LNG, catchment={"mode": "radius", "radius_km": 3})
    out = compute(project, arch, loc, snap, [comp], {"price": 1800, "quality": 0.6, "capacity": {"max_members": 400}, "rent": 1, "param_overrides": {}}, res)
    defs = {d["key"]: d for d in out["definitions"]}
    assert len(out["values"]) == 615
    for val in out["values"]:
        if defs[val["key"]]["role"] == "reserved":
            assert val["value"] is None and val["status"] == "unavailable"
    assert out["summary"].get("computed", 0) > 60 and out["summary"].get("simulated", 0) > 60
    vals = {x["key"]: x for x in out["values"]}
    assert vals["geo_school_count_1km"]["value"] == 1 and vals["cmp_count"]["value"] == 1
