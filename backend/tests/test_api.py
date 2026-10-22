"""End-to-end API flow against a real PostgreSQL+PostGIS database.

External providers are replaced with recorded fixtures so the test is deterministic.
"""
import json
from pathlib import Path

import pytest

from app.providers import osm
from app.services import market as mk

pytestmark = pytest.mark.db
FX = Path(__file__).parent / "fixtures"


async def fake_agesex(polygon, cache=None):
    bands = [{"age": a, "male": 1000.0 - i * 40, "female": 950.0 - i * 38} for i, a in enumerate(
        ["0-4", "5-9", "10-14", "15-19", "20-24", "25-29", "30-34", "35-39", "40-44", "45-49", "50-54", "55-59", "60-64", "65-69", "70-74", "75-79", "80+"])]
    return {"bands": bands}, {"source": "worldpop", "name": "WorldPop age-sex"}
LAT, LNG = 28.6315, 77.2167


@pytest.fixture(autouse=True)
def stub_providers(monkeypatch):
    gyms = json.loads((FX / "overpass_gyms.json").read_text())
    blds = json.loads((FX / "overpass_buildings.json").read_text())

    async def fake_pois(lat, lng, radius_m, filters, cache=None, **kw):
        return osm.parse_pois(gyms), {"source": "osm_overpass", "name": "OSM", "retrieved_at": "2026-10-22T10:00:00+00:00"}

    async def fake_bld(lat, lng, radius_m, cache=None):
        return osm.parse_building_centers(blds), {"source": "osm_overpass", "name": "OSM", "retrieved_at": "2026-10-22T10:00:00+00:00"}

    async def fake_pop(polygon, cache=None):
        return 60000.0, {"source": "worldpop", "name": "WorldPop", "retrieved_at": "2026-10-22T10:00:00+00:00"}

    async def fake_geocode(q, limit=6, cache=None, country_codes=None):
        return osm.parse_nominatim(json.loads((FX / "nominatim_search.json").read_text())), {"source": "osm_nominatim"}

    monkeypatch.setattr(mk.osm, "fetch_pois", fake_pois)
    monkeypatch.setattr(mk.osm, "fetch_buildings", fake_bld)
    monkeypatch.setattr(mk.population, "worldpop_total", fake_pop)
    monkeypatch.setattr(mk.population, "worldpop_age_sex", fake_agesex)
    monkeypatch.setattr(osm, "geocode", fake_geocode)


def signup(client, email="founder@example.com"):
    r = client.post("/api/v1/auth/signup", json={"email": email, "password": "correct-horse-1", "name": "Founder"})
    assert r.status_code == 201, r.text
    return r


def project_payload(client):
    cat = client.post("/api/v1/categories/resolve", json={"query": "gym", "use_ai": False}).json()
    return {
        "name": "My gym", "objective": "start_new", "decision_goal": "profit", "category": cat,
        "profile": {"description": "Neighbourhood gym"},
        "location": {"label": "Location A", "address": "Test", "lat": LAT, "lng": LNG, "catchment": {"mode": "radius", "radius_km": 2.5}},
        "baseline": {"price": 1800, "quality": 0.6, "marketing_spend": 15000, "capacity": {"max_members": 400}, "rent": 60000,
                     "payroll": 80000, "utilities": 15000, "other_fixed": 10000, "startup_cost": 1500000},
    }


def test_auth_required_and_validation(client):
    assert client.get("/api/v1/projects").status_code == 401
    r = client.post("/api/v1/auth/signup", json={"email": "bad", "password": "short"})
    assert r.status_code == 422 and r.json()["detail"] == "Validation failed"


def test_full_judge_journey(client):
    signup(client)
    assert client.get("/api/v1/auth/me").json()["email"] == "founder@example.com"
    assert client.get("/api/v1/market/search", params={"q": "Connaught Place"}).json()["results"][0]["name"] == "Connaught Place"

    p = client.post("/api/v1/projects", json=project_payload(client)).json()
    pid, lid = p["id"], p["locations"][0]["id"]

    # running before loading market data fails honestly
    proj = client.get(f"/api/v1/projects/{pid}").json()
    base = next(s for s in proj["scenarios"] if s["is_baseline"])
    r = client.post(f"/api/v1/scenarios/{base['id']}/runs")
    assert r.status_code == 422

    snap = client.post(f"/api/v1/projects/{pid}/locations/{lid}/refresh", params={"wait": True}).json()
    assert snap["population"]["source"] == "worldpop" and len(snap["zones"]) > 10
    market = client.get(f"/api/v1/projects/{pid}/market", params={"location_id": lid}).json()
    assert len(market["competitors"]) == 3
    assert all(c["price_status"] == "unknown" for c in market["competitors"])

    run1 = client.post(f"/api/v1/scenarios/{base['id']}/runs")
    assert run1.status_code == 201, run1.text
    res1 = run1.json()["results"]
    assert res1["summary"]["reference_price_status"] == "assumption_baseline_price"
    assert res1["monte_carlo"]["draws"] > 100

    # reproducible: same inputs -> same hash and same numbers
    run1b = client.post(f"/api/v1/scenarios/{base['id']}/runs").json()
    assert run1b["input_hash"] == run1.json()["input_hash"]
    assert run1b["results"]["finance"] == res1["finance"]

    alt = client.post(f"/api/v1/projects/{pid}/scenarios", json={"name": "Lower price", "clone_from": base["id"]}).json()
    inputs = dict(alt["inputs"], price=1500)
    client.patch(f"/api/v1/scenarios/{alt['id']}", json={"inputs": inputs})
    res2 = client.post(f"/api/v1/scenarios/{alt['id']}/runs").json()["results"]
    assert res2["summary"]["modeled_demand_units"] > res1["summary"]["modeled_demand_units"]

    # adding a user-observed competitor next door lowers demand
    c = client.post(f"/api/v1/projects/{pid}/competitors", json={"name": "Observed gym", "lat": LAT + 0.001, "lng": LNG, "price": 1400, "is_hypothetical": False}).json()
    assert c["source"] == "user" and c["price_status"] == "user"
    res3 = client.post(f"/api/v1/scenarios/{alt['id']}/runs").json()["results"]
    assert res3["summary"]["modeled_demand_units"] < res2["summary"]["modeled_demand_units"]
    assert res3["summary"]["reference_price_status"] == "derived_from_competitor_prices"

    cmp = client.get(f"/api/v1/projects/{pid}/compare").json()
    assert len([r for r in cmp["rows"] if r.get("metrics")]) == 2

    d = client.get(f"/api/v1/projects/{pid}/decisions", params={"goal": "low_risk"}).json()
    assert d["verdict"] in {"potentially_viable", "financially_challenging", "high_uncertainty", "more_evidence_required"}
    assert d["ranking"] and d["risks"]

    rep = client.post(f"/api/v1/projects/{pid}/reports", params={"share": True}).json()
    shared = client.get(f"/api/v1/shared/reports/{rep['share_token']}").json()
    assert shared["content"]["project"]["name"] == "My gym"

    assert client.post(f"/api/v1/projects/{pid}/actual-outcomes", json={"period": "2026-11", "units": 120}).status_code == 201
    mon = client.get(f"/api/v1/projects/{pid}/monitor").json()
    assert mon["actuals"][0]["error"] is not None


def test_other_users_cannot_see_project(client):
    signup(client, "a@example.com")
    pid = client.post("/api/v1/projects", json=project_payload(client)).json()["id"]
    client.post("/api/v1/auth/logout")
    signup(client, "b@example.com")
    assert client.get(f"/api/v1/projects/{pid}").status_code == 404
    assert client.get(f"/api/v1/projects/{pid}/market").status_code == 404
    assert client.get("/api/v1/projects").json() == []


def test_demo_project_runs_offline(client):
    signup(client, "demo@example.com")
    p = client.post("/api/v1/demo").json()
    assert p["is_demo"] is True
    proj = client.get(f"/api/v1/projects/{p['id']}").json()
    for s in proj["scenarios"]:
        r = client.post(f"/api/v1/scenarios/{s['id']}/runs")
        assert r.status_code == 201, r.text
    d = client.get(f"/api/v1/projects/{p['id']}/decisions").json()
    assert len(d["ranking"]) == 2


def test_background_refresh_job(client):
    import time
    signup(client, "bg@example.com")
    p = client.post("/api/v1/projects", json=project_payload(client)).json()
    pid, lid = p["id"], p["locations"][0]["id"]
    r = client.post(f"/api/v1/projects/{pid}/locations/{lid}/refresh")
    assert r.status_code == 202 and r.json()["status"] == "loading"
    sid = r.json()["id"]
    assert client.get(f"/api/v1/projects/{pid}/market", params={"location_id": lid}).json()["loading_snapshot_id"] in (sid, None)
    status = "loading"
    for _ in range(50):
        status = client.get(f"/api/v1/projects/{pid}/snapshots/{sid}").json()["status"]
        if status != "loading":
            break
        time.sleep(0.2)
    assert status in ("complete", "partial")
    m = client.get(f"/api/v1/projects/{pid}/market", params={"location_id": lid}).json()
    assert m["snapshot"]["id"] == sid and m["loading_snapshot_id"] is None and len(m["competitors"]) == 3


def test_agent_genome_xray_matrix_and_survey(client):
    signup(client, "genome@example.com")
    assert client.get("/api/v1/genome/registry").json()["size"] == 615
    p = client.post("/api/v1/demo").json()
    proj = client.get(f"/api/v1/projects/{p['id']}").json()
    base = next(s for s in proj["scenarios"] if s["is_baseline"])
    run = client.post(f"/api/v1/scenarios/{base['id']}/runs").json()
    abm = run["results"]["abm"]
    assert abm["genome"]["per_agent"] == 615 and abm["n_agents"] >= 1000
    rid = run["id"]
    cols = abm["agents"]["columns"]
    near = min(range(len(abm["agents"]["rows"])), key=lambda i: abm["agents"]["rows"][i][cols.index("dist_km")])
    x = client.get(f"/api/v1/simulation-runs/{rid}/agents/{near}")
    assert x.status_code == 200, x.text
    x = x.json()
    assert len(x["genome"]) == 615 and len(x["percentile"]) == 615 and x["options"]
    # rebuilt from stored inputs after the in-memory cache is gone: identical genome
    from app.api import genome as gapi
    from app.engine import abm as abm_mod
    abm_mod._CACHE.clear()
    gapi._PCT.clear()
    x2 = client.get(f"/api/v1/simulation-runs/{rid}/agents/{near}").json()
    assert x2["genome"] == x["genome"]
    m = client.get(f"/api/v1/simulation-runs/{rid}/genome-matrix", params={"rows": 120}).json()
    assert m["cols"] == 615 and m["rows"] > 0 and len(m["blocks"]) == 16
    kit = client.get(f"/api/v1/simulation-runs/{rid}/survey-kit").json()
    assert len(kit["questions"]) >= 10
    assert client.get(f"/api/v1/simulation-runs/{rid}/agents/999999").status_code == 404
    client.post("/api/v1/auth/logout")
    signup(client, "other@example.com")
    assert client.get(f"/api/v1/simulation-runs/{rid}/agents/7").status_code == 404
