"""Live checks against real providers. Run with RUN_LIVE=1 (CI does this in a separate job)."""
import asyncio

import pytest

from app.categories.resolver import resolve_offline
from app.engine.geo import circle_polygon
from app.providers import osm, population
from app.services.market import build_snapshot

pytestmark = pytest.mark.live
LAT, LNG = 28.6315, 77.2167  # Connaught Place, New Delhi


def test_live_geocode():
    res, prov = asyncio.run(osm.geocode("Connaught Place, New Delhi"))
    assert res and abs(res[0]["lat"] - LAT) < 0.05


def test_live_overpass_gyms():
    cat = resolve_offline("gym")
    pois, prov = asyncio.run(osm.fetch_pois(LAT, LNG, 2000, cat.filters))
    assert isinstance(pois, list)
    print("gyms found:", len(pois), prov["source_updated_at"])


def test_live_worldpop():
    total, prov = asyncio.run(population.worldpop_total([circle_polygon(LAT, LNG, 1.0)]))
    assert total > 1000
    print("population 1km:", round(total))


def test_live_snapshot_end_to_end():
    snap = asyncio.run(build_snapshot(lat=LAT, lng=LNG, catchment={"mode": "radius", "radius_km": 1.5},
                                      category=resolve_offline("cafe").as_dict(), manual_population=None, cache=None))
    print("status", snap["status"], "zones", len(snap["zones"]), "competitors", len(snap["competitors"]), "errors", snap["errors"])
    assert snap["zones"]
