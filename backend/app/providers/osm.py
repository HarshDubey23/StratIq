"""OpenStreetMap providers: Nominatim (search) and Overpass (POIs, buildings)."""
from __future__ import annotations

import asyncio
import logging
import math
import re
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


def build_buildings_query(lat: float, lng: float, radius_m: int, timeout: int = 60, limit: int = 200000) -> str:
    # Skeleton output (ids + centres only) keeps the response small even in dense cities.
    return f'[out:json][timeout:{timeout}];way["building"](around:{radius_m},{lat:.6f},{lng:.6f});out skel center qt {limit};'


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


async def _overpass_one(url: str, query: str, timeout_s: float) -> dict:
    host = url.split("/")[2]
    try:
        r = await client().post(url, data={"data": query}, timeout=httpx.Timeout(timeout_s, connect=8.0))
    except httpx.HTTPError as e:
        raise ProviderError("overpass", f"{host}: {type(e).__name__}") from e
    if r.status_code != 200:
        raise ProviderError("overpass", f"{host}: HTTP {r.status_code}")
    try:
        data = r.json()
    except ValueError as e:
        raise ProviderError("overpass", f"{host}: invalid JSON") from e
    remark = data.get("remark") or ""
    if "runtime error" in remark.lower():
        raise ProviderError("overpass", f"{host}: {remark[:160]}")
    data["_endpoint"] = url
    return data


async def overpass(query: str, cache: Cache | None = None, ttl: timedelta = timedelta(hours=12), tag: str = "overpass",
                   timeout_s: float = 45.0, rounds: int = 2) -> tuple[dict, datetime, bool, str]:
    """Race the configured Overpass mirrors; the first valid answer wins and the others are cancelled.

    Public mirrors are frequently busy (HTTP 429/504) or slow. Racing them in parallel turns
    "one of four is up" into a fast answer instead of a 3-minute sequential timeout chain.
    Returns (data, fetched_at, cached, endpoint)."""
    s = get_settings()
    key = cache_key(tag, {"q": query})
    if cache and (hit := cache.get(key)):
        return hit[0], hit[1], True, "cache"
    errors: list[str] = []
    empty: tuple[dict, str] | None = None
    for rnd in range(rounds):
        tasks = [asyncio.create_task(_overpass_one(u, query, timeout_s)) for u in s.overpass_urls]
        try:
            for fut in asyncio.as_completed(tasks):
                try:
                    data = await fut
                except ProviderError as e:
                    errors.append(e.message)
                    continue
                url = data.pop("_endpoint", "")
                if not data.get("elements") and empty is None:
                    # An empty answer may be a stale or lagging mirror: keep waiting for the others.
                    empty = (data, url)
                    continue
                if cache:
                    cache.put(key, tag, data, ttl)
                return data, datetime.now(timezone.utc), False, url
        finally:
            for t in tasks:
                if not t.done():
                    t.cancel()
        if empty is not None:
            return empty[0], datetime.now(timezone.utc), False, empty[1]
        if rnd + 1 < rounds:
            await asyncio.sleep(3)
    raise ProviderError("overpass", "; ".join(errors[-8:]) or "no endpoint configured")


# ---------------- Fallback place sources (same OpenStreetMap data, different servers) ----------------
_FILTER_RE = re.compile(r'\["?([A-Za-z_:]+)"?\s*(=|~|!=)\s*"?([^"\]]*)"?(?:,i)?\]')


def filter_terms(filters: list[str]) -> tuple[list[str], list[str]]:
    """Turn Overpass tag selectors into (photon osm_tag values, free-text keywords)."""
    tags, words = [], []
    for f in filters:
        for k, op, v in _FILTER_RE.findall(f):
            if op == "!=":
                continue
            vals = [x for x in (y.strip("^$()") for y in re.split(r"[|]", v)) if x and x not in ("yes",) and re.fullmatch(r"[\w :-]+", x)]
            if k == "name":
                words += vals
            elif op == "=" and vals:
                tags.append(f"{k}:{vals[0]}")
            else:
                tags += [f"{k}:{x}" for x in vals[:4]]
    dedup = lambda xs: list(dict.fromkeys(xs))  # noqa: E731
    return dedup(tags)[:8], dedup(words)[:4]


def _tag_word(t: str) -> str:
    return t.split(":", 1)[1].replace("_", " ")


async def photon_pois(lat: float, lng: float, radius_m: int, filters: list[str], limit: int = 50, terms: list[str] | None = None) -> list[dict]:
    """Komoot Photon (OSM-based geocoder) — finds POIs by OSM tag near a point. No key needed."""
    tags, words = filter_terms(filters)
    extra = [t for t in (terms or []) if t and len(t) >= 3]
    queries = [(_tag_word(t), t) for t in tags]
    # same tag, everyday words (Photon ranks by text, so "gym" finds fitness centres the tag word misses)
    queries += [(w, t) for t in tags[:2] for w in extra[:3] if w.lower() != _tag_word(t).lower()]
    queries += [(w, None) for w in words + extra[:2]]
    seen_q: list[tuple[str, str | None]] = []
    for q, tag in queries:
        if (q.lower(), tag) not in [(x.lower(), y) for x, y in seen_q] and len(seen_q) < 9:
            seen_q.append((q, tag))
    POI_KEYS = {"amenity", "shop", "leisure", "sport", "craft", "office", "healthcare", "tourism", "club"}

    async def one(q: str, tag: str | None) -> list[dict]:
        params: list[tuple[str, str]] = [("q", q), ("lat", f"{lat:.6f}"), ("lon", f"{lng:.6f}"), ("limit", str(limit)),
                                         ("location_bias_scale", "0.1"), ("zoom", "16")]
        if tag:
            params.append(("osm_tag", tag))
        try:
            r = await client().get("https://photon.komoot.io/api/", params=params, timeout=httpx.Timeout(15.0, connect=6.0))
            if r.status_code != 200:
                return []
            feats = r.json().get("features", [])
        except (httpx.HTTPError, ValueError):
            return []
        res = []
        for ft in feats:
            pr = ft.get("properties") or {}
            coords = (ft.get("geometry") or {}).get("coordinates") or []
            if len(coords) != 2 or not pr.get("osm_id"):
                continue
            if tag is None and pr.get("osm_key") not in POI_KEYS:
                continue  # free-text hit on a street or area name, not a business
            plng, plat = float(coords[0]), float(coords[1])
            if _dist_m(lat, lng, plat, plng) > radius_m:
                continue
            otype = {"N": "node", "W": "way", "R": "relation"}.get(pr.get("osm_type", ""), "node")
            ref = f"{otype}/{pr['osm_id']}"
            tags_out = {pr.get("osm_key", ""): pr.get("osm_value", "")} if pr.get("osm_key") else {}
            for k in ("street", "housenumber", "city", "postcode"):
                if pr.get(k):
                    tags_out[f"addr:{k}"] = str(pr[k])
            if pr.get("name"):
                tags_out["name"] = pr["name"]
            res.append({"ref": ref, "lat": plat, "lng": plng, "tags": tags_out, "name": pr.get("name") or "", "source_updated_at": None})
        return res

    out: dict[str, dict] = {}
    for batch in await asyncio.gather(*(one(q, t) for q, t in seen_q)):
        for p in batch:
            out.setdefault(p["ref"], p)
    return list(out.values())


async def nominatim_pois(lat: float, lng: float, radius_m: int, filters: list[str], limit: int = 50) -> list[dict]:
    """Nominatim bounded search by category word inside the catchment box (last-resort fallback)."""
    s = get_settings()
    tags, words = filter_terms(filters)
    terms = list(dict.fromkeys([_tag_word(t) for t in tags] + words))[:3]
    dlat = radius_m / 111_320
    dlng = radius_m / (111_320 * max(0.2, math.cos(math.radians(lat))))
    viewbox = f"{lng - dlng:.6f},{lat + dlat:.6f},{lng + dlng:.6f},{lat - dlat:.6f}"
    out: dict[str, dict] = {}
    for term in terms:
        await nominatim_throttle()
        try:
            r = await client().get(f"{s.nominatim_url}/search", params={"q": term, "format": "jsonv2", "limit": limit, "viewbox": viewbox,
                                                                       "bounded": 1, "extratags": 1}, timeout=httpx.Timeout(15.0, connect=6.0))
            if r.status_code != 200:
                continue
            items = r.json()
        except (httpx.HTTPError, ValueError):
            continue
        for it in items:
            try:
                plat, plng = float(it["lat"]), float(it["lon"])
            except (KeyError, ValueError, TypeError):
                continue
            if _dist_m(lat, lng, plat, plng) > radius_m or not it.get("osm_type"):
                continue
            ref = f"{it['osm_type']}/{it['osm_id']}"
            tg = {k: v for k, v in (it.get("extratags") or {}).items() if k not in PERSONAL_META}
            if it.get("category") and it.get("type"):
                tg.setdefault(it["category"], it["type"])
            name = it.get("name") or ""
            if name:
                tg["name"] = name
            out[ref] = {"ref": ref, "lat": plat, "lng": plng, "tags": tg, "name": name, "source_updated_at": None}
    return list(out.values())


def _dist_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6_371_000 * 2 * math.asin(min(1.0, math.sqrt(a)))


async def fetch_pois(lat, lng, radius_m, filters, cache=None, limit: int = 400, fallback: bool = False,
                     timeout_s: float = 45.0, terms: list[str] | None = None) -> tuple[list[dict], dict]:
    """POIs matching tag filters. With ``fallback`` the same OpenStreetMap data is fetched from
    Photon / Nominatim when every Overpass mirror is down, so a busy mirror never empties the market."""
    if not filters:
        return [], provenance("osm_overpass", status="skipped", detail="No category filters.")
    q = build_poi_query(lat, lng, radius_m, filters, timeout=int(timeout_s) - 5, limit=limit)
    try:
        data, fetched, cached, endpoint = await overpass(q, cache, timeout_s=timeout_s, rounds=1 if fallback else 2)
    except ProviderError as e:
        if not fallback:
            raise
        log.warning("overpass failed (%s); trying Photon/Nominatim", e.message)
        fkey = cache_key("osm_fallback", {"q": q})
        if cache and (hit := cache.get(fkey)):
            pois = hit[0]["pois"]
            return pois, provenance("osm_photon", retrieved_at=hit[1], cached=True,
                                    detail=f"{len(pois)} features (Overpass busy; served from Photon/Nominatim index)")
        pois = await photon_pois(lat, lng, radius_m, filters, terms=terms)
        src = "osm_photon"
        if len(pois) < 3:
            more = await nominatim_pois(lat, lng, radius_m, filters)
            seen = {p["ref"] for p in pois}
            pois += [p for p in more if p["ref"] not in seen]
            if more:
                src = "osm_nominatim"
        if not pois:
            raise ProviderError("overpass", f"{e.message}; fallbacks returned nothing") from e
        if cache:
            cache.put(fkey, "osm_fallback", {"pois": pois}, timedelta(hours=12))
        return pois, provenance(src, detail=f"{len(pois)} features matched within {radius_m} m (Overpass mirrors busy: "
                                            f"same OpenStreetMap data via the {'Photon' if src == 'osm_photon' else 'Nominatim'} index; "
                                            "edit dates unavailable)")
    pois = parse_pois(data)
    osm_base = data.get("osm3s", {}).get("timestamp_osm_base")
    host = endpoint.split("/")[2] if "/" in endpoint else endpoint
    return pois, provenance("osm_overpass", retrieved_at=fetched, source_updated_at=osm_base, cached=cached,
                            detail=f"{len(pois)} features matched {len(filters)} tag filter(s) within {radius_m} m (via {host})")


async def fetch_buildings(lat, lng, radius_m, cache=None) -> tuple[list[tuple[float, float]], dict]:
    data, fetched, cached, _ = await overpass(build_buildings_query(lat, lng, radius_m, timeout=90), cache, ttl=timedelta(days=3),
                                              tag="overpass_bld", timeout_s=95, rounds=1)
    pts = parse_building_centers(data)
    osm_base = data.get("osm3s", {}).get("timestamp_osm_base")
    return pts, provenance("osm_overpass", retrieved_at=fetched, source_updated_at=osm_base, cached=cached,
                           detail=f"{len(pts)} mapped buildings used to place population within the catchment")


def _merge_pois(*groups: list[dict]) -> list[dict]:
    """Union of POI lists from several OpenStreetMap servers: same OSM id, or same name within ~40 m, is one place."""
    out: list[dict] = []
    seen_ref: set[str] = set()
    for g in groups:
        for p in g:
            if p["ref"] in seen_ref:
                continue
            nm = (p.get("name") or "").strip().lower()
            if nm and any((q.get("name") or "").strip().lower() == nm and _dist_m(p["lat"], p["lng"], q["lat"], q["lng"]) < 40 for q in out):
                continue
            seen_ref.add(p["ref"])
            out.append(p)
    return out


async def fetch_competitors(lat: float, lng: float, radius_m: int, filters: list[str], cache: Cache | None = None,
                            terms: list[str] | None = None, timeout_s: float = 38.0, limit: int = 600) -> tuple[list[dict], dict]:
    """Competitors from every OpenStreetMap server at once, merged for maximum coverage.

    Overpass (full tag query, raced across mirrors) and the Photon search index run in parallel; Nominatim fills in
    when both are thin. All three serve OpenStreetMap data, so the union is still one licensed, attributable source."""
    if not filters:
        return [], provenance("osm_overpass", status="skipped", detail="No category filters.")
    q = build_poi_query(lat, lng, radius_m, filters, timeout=int(timeout_s) - 5, limit=limit)
    key = cache_key("osm_merged_v2", {"q": q, "t": terms or []})
    if cache and (hit := cache.get(key)):
        pois = hit[0]["pois"]
        return pois, provenance("osm_overpass", retrieved_at=hit[1], cached=True, source_updated_at=hit[0].get("osm_base"),
                                detail=hit[0].get("detail") or f"{len(pois)} features")

    async def ov():
        try:
            data, fetched, _cached, ep = await overpass(q, None, timeout_s=timeout_s, rounds=1)
            return parse_pois(data), data.get("osm3s", {}).get("timestamp_osm_base"), ep.split("/")[2] if "/" in ep else ep
        except ProviderError as e:
            log.warning("overpass competitors failed: %s", e.message)
            return None, None, None

    async def ph():
        try:
            return await photon_pois(lat, lng, radius_m, filters, terms=terms)
        except Exception as e:  # noqa: BLE001 — a fallback index must never break the snapshot
            log.warning("photon failed: %s", e)
            return []

    (ov_pois, osm_base, host), ph_pois = await asyncio.gather(ov(), ph())
    merged = _merge_pois(ov_pois or [], ph_pois)
    used = (["Overpass" + (f" ({host})" if host else "")] if ov_pois is not None else []) + (["Photon"] if ph_pois else [])
    if len(merged) < 5:
        try:
            nm = await nominatim_pois(lat, lng, radius_m, filters)
        except Exception:  # noqa: BLE001
            nm = []
        if nm:
            merged = _merge_pois(merged, nm)
            used.append("Nominatim")
    if not merged and ov_pois is None:
        raise ProviderError("overpass", "Overpass mirrors busy and the search indexes returned nothing")
    detail = (f"{len(merged)} competitors within {radius_m} m, merged from OpenStreetMap servers: {', '.join(used) or 'none'}"
              f" (Overpass {len(ov_pois or [])}, Photon {len(ph_pois)})")
    if cache and merged:
        cache.put(key, "osm_merged", {"pois": merged, "osm_base": osm_base, "detail": detail}, timedelta(hours=12))
    return merged, provenance("osm_overpass", source_updated_at=osm_base, detail=detail)
