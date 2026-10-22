"""Population (WorldPop) and travel-time catchments (openrouteservice)."""
from __future__ import annotations

import asyncio
import json
import re
import time
from datetime import timedelta

import httpx

from ..config import get_settings
from .http import Cache, ProviderError, cache_key, client
from .registry import provenance


_JSON_START = re.compile(r'\{\s*"(status|error|taskid)"')


def _json_tail(text: str) -> dict:
    """WorldPop sometimes prefixes its JSON with PHP deprecation notices (HTML). Parse the JSON object at the end."""
    try:
        return json.loads(text)
    except ValueError:
        pass
    dec = json.JSONDecoder()
    for m in _JSON_START.finditer(text):
        try:
            obj, _ = dec.raw_decode(text, m.start())  # tolerate warnings before *and* after the JSON
            return obj
        except ValueError:
            continue
    raise ProviderError("worldpop", f"unparseable response ({len(text)} bytes): {text[:100]!r}")


def _round_ring(ring: list[list[float]]) -> list[list[float]]:
    return [[round(x, 5), round(y, 5)] for x, y in ring]


async def _worldpop_stats(dataset: str, polygon: list[list[list[float]]], cache: Cache | None, ttl_days: int = 60) -> tuple[dict, object, bool]:
    s = get_settings()
    fc = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": [_round_ring(r) for r in polygon]}}]}
    gj = json.dumps(fc, separators=(",", ":"))
    params = {"dataset": dataset, "year": s.worldpop_year, "geojson": gj, "runasync": "true"}
    key = cache_key(f"worldpop:{dataset}", {"year": s.worldpop_year, "g": gj})
    if cache and (hit := cache.get(key)):
        return hit[0], hit[1], True
    try:
        body = None
        for attempt in range(2):
            try:
                r = await client().get(f"{s.worldpop_url}/services/stats", params=params, timeout=httpx.Timeout(40.0, connect=15.0))
                r.raise_for_status()
                body = _json_tail(r.text)
                break
            except httpx.TimeoutException:
                if attempt == 1:
                    raise
                await asyncio.sleep(2)
        deadline = time.monotonic() + 75
        while time.monotonic() < deadline:  # asynchronous task: poll until finished
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
            body = _json_tail(r.text)
        if body.get("status") != "finished":
            raise ProviderError("worldpop", f"{dataset} task did not finish in time")
        data = body["data"]
    except (httpx.HTTPError, KeyError, ValueError, TypeError) as e:
        raise ProviderError("worldpop", f"{dataset} query failed: {type(e).__name__} {e}".strip()) from e
    if cache:
        cache.put(key, f"worldpop:{dataset}", data, timedelta(days=ttl_days))
    from datetime import datetime, timezone
    return data, datetime.now(timezone.utc), False


async def worldpop_total(polygon: list[list[list[float]]], cache: Cache | None = None) -> tuple[float, dict]:
    """Total modelled population inside a GeoJSON polygon (WorldPop, fixed reference year)."""
    s = get_settings()
    data, fetched, cached = await _worldpop_stats("wpgppop", polygon, cache)
    try:
        total = float(data["total_population"])
    except (KeyError, TypeError, ValueError) as e:
        raise ProviderError("worldpop", f"unexpected population payload: {str(data)[:120]}") from e
    return total, provenance("worldpop", retrieved_at=fetched, cached=cached, source_updated_at=f"{s.worldpop_year} reference year",
                             detail="Total population inside the catchment")


def parse_age_sex(data: dict) -> dict:
    """WorldPop wpgpas -> 17 five-year bands (0-4 … 80+) with male/female counts."""
    rows = data.get("agesexpyramid") or []
    bands = []
    for r in sorted(rows, key=lambda x: int(x.get("class", 0))):
        bands.append({"age": str(r.get("age")), "male": float(r.get("male") or 0), "female": float(r.get("female") or 0)})
    if len(bands) != 17:
        raise ProviderError("worldpop", f"age-sex pyramid has {len(bands)} bands, expected 17")
    return {"bands": bands}


async def worldpop_age_sex(polygon: list[list[list[float]]], cache: Cache | None = None) -> tuple[dict, dict]:
    s = get_settings()
    data, fetched, cached = await _worldpop_stats("wpgpas", polygon, cache)
    return parse_age_sex(data), provenance("worldpop", retrieved_at=fetched, cached=cached, source_updated_at=f"{s.worldpop_year} reference year",
                                           detail="Age and sex structure inside the catchment (17 five-year bands)")


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
