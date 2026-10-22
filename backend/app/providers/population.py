"""Population (WorldPop) and travel-time catchments (openrouteservice)."""
from __future__ import annotations

import asyncio
import json
from datetime import timedelta

import httpx

from ..config import get_settings
from .http import Cache, ProviderError, cache_key, client
from .registry import provenance


def _round_ring(ring: list[list[float]]) -> list[list[float]]:
    return [[round(x, 5), round(y, 5)] for x, y in ring]


async def worldpop_total(polygon: list[list[list[float]]], cache: Cache | None = None) -> tuple[float, dict]:
    """Total modelled population inside a GeoJSON polygon (WorldPop, fixed reference year)."""
    s = get_settings()
    fc = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": [_round_ring(r) for r in polygon]}}]}
    gj = json.dumps(fc, separators=(",", ":"))
    params = {"dataset": "wpgppop", "year": s.worldpop_year, "geojson": gj, "runasync": "true"}
    key = cache_key("worldpop", {"year": s.worldpop_year, "g": gj})
    if cache and (hit := cache.get(key)):
        return float(hit[0]["total"]), provenance("worldpop", retrieved_at=hit[1], cached=True, source_updated_at=f"{s.worldpop_year} reference year",
                                                  detail="Total population inside the catchment")
    try:
        r = await client().get(f"{s.worldpop_url}/services/stats", params=params, timeout=httpx.Timeout(30.0, connect=10.0))
        r.raise_for_status()
        body = r.json()
        for _ in range(30):  # asynchronous task: poll until finished (~60 s max)
            if body.get("error"):
                raise ProviderError("worldpop", str(body.get("error_message")))
            if body.get("status") == "finished" and body.get("data"):
                break
            tid = body.get("taskid")
            if not tid:
                raise ProviderError("worldpop", f"unexpected response: {str(body)[:200]}")
            await asyncio.sleep(2)
            r = await client().get(f"{s.worldpop_url}/tasks/{tid}", timeout=httpx.Timeout(20.0, connect=10.0))
            r.raise_for_status()
            body = r.json()
        if body.get("status") != "finished":
            raise ProviderError("worldpop", "population task did not finish in time")
        total = float(body["data"]["total_population"])
    except (httpx.HTTPError, KeyError, ValueError, TypeError) as e:
        raise ProviderError("worldpop", f"population query failed: {type(e).__name__} {e}".strip()) from e
    if cache:
        cache.put(key, "worldpop", {"total": total}, timedelta(days=60))
    return total, provenance("worldpop", source_updated_at=f"{s.worldpop_year} reference year", detail="Total population inside the catchment")


async def ors_isochrone(lat: float, lng: float, minutes: int, profile: str = "foot-walking", cache: Cache | None = None) -> tuple[list[list[list[float]]], dict]:
    s = get_settings()
    if not s.ors_api_key:
        raise ProviderError("openrouteservice", "ORS_API_KEY not configured")
    if profile not in {"foot-walking", "driving-car", "cycling-regular"}:
        raise ProviderError("openrouteservice", f"unsupported profile {profile}")
    body = {"locations": [[round(lng, 6), round(lat, 6)]], "range": [int(minutes) * 60], "range_type": "time"}
    key = cache_key("ors_iso", {"p": profile, **body})
    if cache and (hit := cache.get(key)):
        return hit[0]["polygon"], provenance("openrouteservice", retrieved_at=hit[1], cached=True, detail=f"{minutes} min {profile}")
    try:
        r = await client().post(f"{s.ors_url}/v2/isochrones/{profile}", json=body,
                                headers={"Authorization": s.ors_api_key, "Content-Type": "application/json"})
        r.raise_for_status()
        geom = r.json()["features"][0]["geometry"]
        poly = geom["coordinates"] if geom["type"] == "Polygon" else max(geom["coordinates"], key=lambda p: len(p[0]))
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
        raise ProviderError("openrouteservice", f"isochrone failed: {e}") from e
    if cache:
        cache.put(key, "ors_iso", {"polygon": poly}, timedelta(days=30))
    return poly, provenance("openrouteservice", detail=f"{minutes} min {profile} travel-time area")
