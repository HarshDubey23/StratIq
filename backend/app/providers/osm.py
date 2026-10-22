"""OpenStreetMap providers: Nominatim (search) and Overpass (POIs, buildings)."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx

from ..config import get_settings
from .http import Cache, ProviderError, cache_key, client, nominatim_throttle
from .registry import provenance

log = logging.getLogger("strataiq.osm")

PERSONAL_META = {"user", "uid", "changeset"}


# ---------------- Nominatim ----------------
def parse_nominatim(items: list[dict]) -> list[dict]:
    out = []
    for it in items:
        try:
            bbox = [float(x) for x in it.get("boundingbox", [])] or None
            out.append({
                "name": it.get("name") or it.get("display_name", "").split(",")[0],
                "display_name": it.get("display_name", ""),
                "lat": float(it["lat"]), "lng": float(it["lon"]),
                "type": it.get("type"), "class": it.get("class") or it.get("category"),
                "bbox": bbox,  # [south, north, west, east]
                "osm_ref": f"{it.get('osm_type')}/{it.get('osm_id')}" if it.get("osm_type") else None,
                "importance": it.get("importance"),
            })
        except (KeyError, ValueError, TypeError):
            continue
    return out


async def geocode(q: str, limit: int = 6, cache: Cache | None = None, country_codes: str | None = None) -> tuple[list[dict], dict]:
    s = get_settings()
    params = {"q": q, "format": "jsonv2", "limit": limit, "addressdetails": 0}
    if country_codes:
        params["countrycodes"] = country_codes
    key = cache_key("nominatim", params)
    if cache and (hit := cache.get(key)):
        payload, fetched = hit
        return payload["results"], provenance("osm_nominatim", retrieved_at=fetched, cached=True)
    await nominatim_throttle()
    try:
        r = await client().get(f"{s.nominatim_url}/search", params=params)
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise ProviderError("nominatim", f"search failed: {e}") from e
    results = parse_nominatim(r.json())
    if cache:
        cache.put(key, "nominatim", {"results": results}, timedelta(days=14))
    return results, provenance("osm_nominatim")


async def reverse(lat: float, lng: float, cache: Cache | None = None) -> str:
    s = get_settings()
    params = {"lat": round(lat, 5), "lon": round(lng, 5), "format": "jsonv2", "zoom": 17}
    key = cache_key("nominatim_rev", params)
    if cache and (hit := cache.get(key)):
        return hit[0].get("display_name", "")
    await nominatim_throttle()
    try:
        r = await client().get(f"{s.nominatim_url}/reverse", params=params)
        r.raise_for_status()
        name = r.json().get("display_name", "")
    except (httpx.HTTPError, ValueError):
        return ""
    if cache:
        cache.put(key, "nominatim_rev", {"display_name": name}, timedelta(days=30))
    return name


# ---------------- Overpass ----------------
def build_poi_query(lat: float, lng: float, radius_m: int, filters: list[str], timeout: int = 40, limit: int = 400) -> str:
    parts = "".join(f"nwr{f}(around:{radius_m},{lat:.6f},{lng:.6f});" for f in filters)
    return f"[out:json][timeout:{timeout}];({parts});out center meta qt {limit};"


def build_buildings_query(lat: float, lng: float, radius_m: int, timeout: int = 60) -> str:
    return f'[out:json][timeout:{timeout}][maxsize:200000000];way["building"](around:{radius_m},{lat:.6f},{lng:.6f});out center qt;'


def parse_pois(data: dict) -> list[dict]:
    """Normalise Overpass elements to point records and drop contributor personal metadata."""
    seen, out = set(), []
    for el in data.get("elements", []):
        if el.get("type") == "node":
            lat, lng = el.get("lat"), el.get("lon")
        else:
            c = el.get("center") or {}
            lat, lng = c.get("lat"), c.get("lon")
        if lat is None or lng is None:
            continue
        ref = f"{el['type']}/{el['id']}"
        if ref in seen:
            continue
        seen.add(ref)
        tags = {k: v for k, v in (el.get("tags") or {}).items() if k not in PERSONAL_META}
        out.append({
            "ref": ref, "lat": float(lat), "lng": float(lng), "tags": tags,
            "name": tags.get("name") or tags.get("brand") or tags.get("name:en") or "",
            "source_updated_at": el.get("timestamp"),
        })
    return out


def parse_building_centers(data: dict) -> list[tuple[float, float]]:
    pts = []
    for el in data.get("elements", []):
        c = el.get("center")
        if c:
            pts.append((float(c["lat"]), float(c["lon"])))
        elif "lat" in el:
            pts.append((float(el["lat"]), float(el["lon"])))
    return pts


async def overpass(query: str, cache: Cache | None = None, ttl: timedelta = timedelta(hours=12), tag: str = "overpass") -> tuple[dict, datetime, bool, str]:
    """Run an Overpass query against the configured endpoints in order. Returns (data, fetched_at, cached, endpoint)."""
    s = get_settings()
    key = cache_key(tag, {"q": query})
    if cache and (hit := cache.get(key)):
        return hit[0], hit[1], True, "cache"
    errors = []
    for url in s.overpass_urls:
        try:
            r = await client().post(url, data={"data": query}, timeout=httpx.Timeout(90.0, connect=10.0))
            if r.status_code in (429, 504, 503):
                errors.append(f"{url}: HTTP {r.status_code}")
                continue
            r.raise_for_status()
            data = r.json()
            remark = data.get("remark") or ""
            if "runtime error" in remark.lower():
                errors.append(f"{url}: {remark[:160]}")
                continue
            if cache:
                cache.put(key, tag, data, ttl)
            return data, datetime.now(timezone.utc), False, url
        except (httpx.HTTPError, ValueError) as e:
            errors.append(f"{url}: {e}")
    raise ProviderError("overpass", "; ".join(errors) or "no endpoint configured")


async def fetch_pois(lat, lng, radius_m, filters, cache=None) -> tuple[list[dict], dict]:
    if not filters:
        return [], provenance("osm_overpass", status="skipped", detail="No category filters.")
    data, fetched, cached, endpoint = await overpass(build_poi_query(lat, lng, radius_m, filters), cache)
    pois = parse_pois(data)
    osm_base = data.get("osm3s", {}).get("timestamp_osm_base")
    return pois, provenance("osm_overpass", retrieved_at=fetched, source_updated_at=osm_base, cached=cached,
                            detail=f"{len(pois)} features matched {len(filters)} tag filter(s) within {radius_m} m")


async def fetch_buildings(lat, lng, radius_m, cache=None) -> tuple[list[tuple[float, float]], dict]:
    data, fetched, cached, _ = await overpass(build_buildings_query(lat, lng, radius_m), cache, ttl=timedelta(days=3), tag="overpass_bld")
    pts = parse_building_centers(data)
    osm_base = data.get("osm3s", {}).get("timestamp_osm_base")
    return pts, provenance("osm_overpass", retrieved_at=fetched, source_updated_at=osm_base, cached=cached,
                           detail=f"{len(pts)} mapped buildings used to place population within the catchment")
