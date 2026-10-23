"""Foursquare Places API (optional, needs FSQ_API_KEY).

Adds businesses that OpenStreetMap volunteers haven't mapped yet — common for small Indian shops.
Results are merged with OpenStreetMap: a Foursquare place with the same name near an OSM place is
treated as the same business. Every record keeps its source so provenance stays visible.
"""
from __future__ import annotations

import asyncio
import logging
import math
import re

import httpx

from ..config import get_settings
from .http import client

log = logging.getLogger("strataiq.fsq")
URL = "https://places-api.foursquare.com/places/search"
VERSION = "2025-06-17"


def enabled() -> bool:
    return bool(get_settings().fsq_api_key)


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def _dist_m(a_lat: float, a_lng: float, b_lat: float, b_lng: float) -> float:
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = p2 - p1, math.radians(b_lng - a_lng)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6_371_000 * 2 * math.asin(min(1.0, math.sqrt(h)))


LEGACY_URL = "https://api.foursquare.com/v3/places/search"
STATUS: dict = {"last_http": None, "last_error": None, "api": None}


def _parse_next(r: httpx.Response) -> str | None:
    m = re.search(r"<([^>]+)>;\s*rel=\"?next\"?", r.headers.get("link") or "")
    return m.group(1) if m else None


async def _search(lat: float, lng: float, radius_m: int, query: str, pages: int = 3) -> list[dict]:
    """New Places API first (service key, Bearer); legacy v3 (key in Authorization) if the key is an older one."""
    key = get_settings().fsq_api_key
    params = {"ll": f"{lat:.6f},{lng:.6f}", "radius": min(int(radius_m), 100_000), "query": query, "limit": 50}
    apis = [("places", URL, {"Authorization": f"Bearer {key}", "X-Places-Api-Version": VERSION, "Accept": "application/json"}),
            ("v3", LEGACY_URL, {"Authorization": key, "Accept": "application/json"})]
    if STATUS["api"] == "v3":
        apis.reverse()
    for name, base, headers in apis:
        out: list[dict] = []
        url: str | None = base
        ok = False
        for _ in range(pages):
            if not url:
                break
            try:
                r = await client().get(url, params=params if url == base else None, headers=headers,
                                       timeout=httpx.Timeout(15.0, connect=6.0))
            except httpx.HTTPError as e:
                STATUS["last_error"] = f"{name}: {type(e).__name__}"
                break
            STATUS["last_http"] = f"{name} {r.status_code}"
            if r.status_code != 200:
                STATUS["last_error"] = f"{name} HTTP {r.status_code}: {r.text[:160]}"
                log.warning("foursquare %s", STATUS["last_error"])
                break
            ok = True
            STATUS["api"] = name
            out += r.json().get("results") or []
            url = _parse_next(r)
        if ok:
            return out
        if STATUS["last_http"] not in (f"{name} 401", f"{name} 403", f"{name} 410"):
            return out  # not an auth problem: don't hammer the other API
    return []


async def fsq_pois(lat: float, lng: float, radius_m: int, terms: list[str]) -> list[dict]:
    """Search Foursquare with a few everyday words for the category; returns POI dicts shaped like the OSM ones."""
    if not enabled():
        return []
    queries = list(dict.fromkeys(t.strip().lower() for t in terms if t and len(t.strip()) >= 3))[:3]
    results = await asyncio.gather(*(_search(lat, lng, radius_m, q) for q in queries))
    seen: dict[str, dict] = {}
    for batch in results:
        for p in batch:
            pid = p.get("fsq_place_id") or p.get("fsq_id")
            plat, plng = p.get("latitude"), p.get("longitude")
            if plat is None and isinstance(p.get("geocodes"), dict):
                main = p["geocodes"].get("main") or {}
                plat, plng = main.get("latitude"), main.get("longitude")
            if not pid or plat is None or plng is None:
                continue
            if _dist_m(lat, lng, float(plat), float(plng)) > radius_m:
                continue
            cats = [c.get("name") for c in (p.get("categories") or []) if c.get("name")]
            loc = p.get("location") or {}
            tags = {"name": p.get("name") or "", "fsq:categories": "; ".join(cats)[:200]}
            if loc.get("formatted_address"):
                tags["addr:full"] = str(loc["formatted_address"])[:200]
            seen[pid] = {"ref": f"fsq/{pid}"[:80], "lat": float(plat), "lng": float(plng), "tags": tags, "name": p.get("name") or "",
                         "source_updated_at": None, "src": "foursquare"}
    return list(seen.values())


def merge_with_osm(osm: list[dict], fsq: list[dict]) -> tuple[list[dict], int]:
    """Add Foursquare places that OSM doesn't already have (same normalised name within 80 m = same business)."""
    added = 0
    out = list(osm)
    for f in fsq:
        nf = _norm(f["name"])
        dup = False
        for o in out:
            no = _norm(o.get("name") or "")
            if _dist_m(f["lat"], f["lng"], o["lat"], o["lng"]) < 80 and nf and no and (nf == no or nf in no or no in nf):
                dup = True
                break
        if not dup:
            out.append(f)
            added += 1
    return out, added
