"""Provider parsing and market-snapshot assembly (offline, fixtures only)."""
import asyncio
import json
from pathlib import Path


from app.categories.resolver import resolve_offline
from app.engine.geo import circle_polygon
from app.providers import osm
from app.services import market as mk

FX = Path(__file__).parent / "fixtures"


async def fake_agesex(polygon, cache=None):
    bands = [{"age": a, "male": 1000.0 - i * 40, "female": 950.0 - i * 38} for i, a in enumerate(
        ["0-4", "5-9", "10-14", "15-19", "20-24", "25-29", "30-34", "35-39", "40-44", "45-49", "50-54", "55-59", "60-64", "65-69", "70-74", "75-79", "80+"])]
    return {"bands": bands}, {"source": "worldpop", "name": "WorldPop age-sex"}
LAT, LNG = 28.6315, 77.2167




def load(name):
    return json.loads((FX / name).read_text())


def test_parse_pois_dedupes_and_strips_personal_metadata():
    pois = osm.parse_pois(load("overpass_gyms.json"))
    refs = [p["ref"] for p in pois]
    assert refs == ["node/1001", "way/2002", "node/1003"]  # duplicate and centre-less relation dropped
    for p in pois:
        assert "user" not in p["tags"] and "uid" not in p["tags"]
    assert pois[0]["source_updated_at"] == "2025-03-01T10:00:00Z"
    assert pois[2]["name"] == ""


def test_parse_nominatim_skips_bad_rows():
    res = osm.parse_nominatim(load("nominatim_search.json"))
    assert len(res) == 1 and res[0]["name"] == "Connaught Place" and abs(res[0]["lat"] - 28.6315) < 1e-9


def test_overpass_query_shape():
    q = osm.build_poi_query(LAT, LNG, 2500, ['["amenity"="cafe"]', '["cuisine"~"coffee",i]'])
    assert q.startswith("[out:json]") and q.count("nwr[") == 2 and "(around:2500,28.631500,77.216700)" in q
    assert "out center meta" in q


def test_assemble_zones_dasymetric_conserves_population():
    poly = [circle_polygon(LAT, LNG, 2.0)]
    blds = osm.parse_building_centers(load("overpass_buildings.json"))
    zones, meta = mk.assemble_zones(LAT, LNG, poly, 2.0, 50000.0, blds, [(LAT, LNG)])
    assert meta["method"] == "dasymetric_buildings"
    assert abs(sum(z["population"] for z in zones) - 50000.0) < 1.0
    assert sum(z["activity"] for z in zones) == 1


def test_assemble_zones_uniform_and_missing():
    poly = [circle_polygon(LAT, LNG, 1.0)]
    z1, m1 = mk.assemble_zones(LAT, LNG, poly, 1.0, 1000.0, [], None)
    assert m1["method"] == "uniform" and abs(sum(z["population"] for z in z1) - 1000.0) < 0.5
    z2, m2 = mk.assemble_zones(LAT, LNG, poly, 1.0, None, [], None)
    assert m2["method"] == "unavailable" and all(z["population"] == 0 for z in z2)


def test_coverage_levels_are_computed_not_invented():
    cov = mk.assess_coverage(osm.parse_pois(load("overpass_gyms.json")), 50000, 100, 12.0)
    assert cov["level"] == "low"
    cov2 = mk.assess_coverage([], 50000, 5000, 12.0)
    assert cov2["level"] == "good"
    assert mk.assess_coverage([], None, 0, 1)["level"] == "unknown"


def test_build_snapshot_with_stubbed_providers(monkeypatch):
    async def fake_pois(lat, lng, radius_m, filters, cache=None, **kw):
        if any("fitness" in f or "gym" in f for f in filters):
            return osm.parse_pois(load("overpass_gyms.json")), {"source": "osm_overpass", "retrieved_at": "2026-10-22T10:00:00+00:00"}
        return [], {"source": "osm_overpass"}

    async def fake_bld(lat, lng, radius_m, cache=None):
        return osm.parse_building_centers(load("overpass_buildings.json")), {"source": "osm_overpass"}

    async def fake_pop(polygon, cache=None):
        return 42000.0, {"source": "worldpop"}

    monkeypatch.setattr(mk.osm, "fetch_pois", fake_pois)

    monkeypatch.setattr(mk.osm, "fetch_competitors", fake_pois)
    monkeypatch.setattr(mk.osm, "fetch_buildings", fake_bld)
    monkeypatch.setattr(mk.population, "worldpop_total", fake_pop)
    monkeypatch.setattr(mk.population, "worldpop_age_sex", fake_agesex)
    cat = resolve_offline("gym").as_dict()
    snap = asyncio.run(mk.build_snapshot(lat=LAT, lng=LNG, catchment={"mode": "isochrone", "minutes": 10, "radius_km": 2.0},
                                         category=cat, manual_population=None, cache=None))
    # isochrone requested without ORS key -> honest fallback to radius, recorded as an error
    assert snap["catchment_method"] == "radius"
    assert any(e["source"] == "openrouteservice" for e in snap["errors"])
    assert len(snap["competitors"]) == 3
    assert snap["population"]["source"] == "worldpop"
    assert snap["population"]["admin"]["state"] == "Delhi"
    rt = snap["population"]["routing"]
    assert len(rt["car"]["km"]) == len(snap["zones"]) and len(rt["dest_keys"]) == 1 + len(snap["competitors"])
    assert abs(sum(z["population"] for z in snap["zones"]) - 42000) < 1
    assert snap["status"] == "partial"


def test_build_snapshot_population_failure_is_reported(monkeypatch):
    from app.providers.http import ProviderError

    async def fake_pois(*a, **k):
        return [], {"source": "osm_overpass"}

    async def fake_bld(*a, **k):
        return [], {"source": "osm_overpass"}

    async def bad_pop(*a, **k):
        raise ProviderError("worldpop", "timeout")

    monkeypatch.setattr(mk.osm, "fetch_pois", fake_pois)

    monkeypatch.setattr(mk.osm, "fetch_competitors", fake_pois)
    monkeypatch.setattr(mk.osm, "fetch_buildings", fake_bld)
    monkeypatch.setattr(mk.population, "worldpop_total", bad_pop)
    monkeypatch.setattr(mk.population, "worldpop_age_sex", bad_pop)
    snap = asyncio.run(mk.build_snapshot(lat=LAT, lng=LNG, catchment={"mode": "radius", "radius_km": 1.5},
                                         category=resolve_offline("cafe").as_dict(), manual_population=None, cache=None))
    assert snap["population"]["method"] == "unavailable"
    assert any(e["source"] == "population" for e in snap["errors"])


def test_population_fallback_uses_buildings_and_is_flagged(monkeypatch):
    from app.providers.http import ProviderError

    async def fake_pois(*a, **k):
        return [], {"source": "osm_overpass"}

    async def fake_bld(*a, **k):
        return osm.parse_building_centers(load("overpass_buildings.json")), {"source": "osm_overpass"}

    async def bad_pop(*a, **k):
        raise ProviderError("worldpop", "ReadTimeout")

    monkeypatch.setattr(mk.osm, "fetch_pois", fake_pois)

    monkeypatch.setattr(mk.osm, "fetch_competitors", fake_pois)
    monkeypatch.setattr(mk.osm, "fetch_buildings", fake_bld)
    monkeypatch.setattr(mk.population, "worldpop_total", bad_pop)
    monkeypatch.setattr(mk.population, "worldpop_age_sex", bad_pop)
    snap = asyncio.run(mk.build_snapshot(lat=LAT, lng=LNG, catchment={"mode": "radius", "radius_km": 2.0},
                                         category=resolve_offline("gym").as_dict(), manual_population=None, cache=None))
    assert snap["population"]["source"] == "estimate_buildings"
    assert snap["population"]["total"] == 1500 * 12
    assert any(e.get("fallback") == "building-based estimate" for e in snap["errors"])
