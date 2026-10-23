"""Market Reality Engine: turn live sources into a reproducible market snapshot."""
from __future__ import annotations

import asyncio
import logging
import math
from datetime import datetime, timezone

import numpy as np

from ..categories.archetypes import get_archetype
from ..config import get_settings
from ..categories.taxonomy import ACTIVITY_KINDS, CONTEXT_FILTERS, classify_poi
from ..engine.geo import circle_polygon, haversine_km, hex_grid, km_to_deg_lat, km_to_deg_lng, points_in_polygon
from ..providers import osm, population
from ..providers.http import Cache, ProviderError
from ..providers.registry import provenance

log = logging.getLogger("strataiq.market")

MAX_RADIUS_KM = 6.0


def polygon_radius_km(lat: float, lng: float, polygon: list[list[list[float]]]) -> float:
    ring = np.array(polygon[0])
    return float(haversine_km(lat, lng, ring[:, 1], ring[:, 0]).max())


def zone_spacing(radius_km: float) -> float:
    return float(min(0.6, max(0.25, radius_km / 9)))


def assign_counts(zone_pts: list[tuple[float, float]], pts: list[tuple[float, float]], spacing_km: float) -> np.ndarray:
    """Count points nearest to each zone centre (points farther than one spacing are ignored)."""
    counts = np.zeros(len(zone_pts))
    if not pts or not zone_pts:
        return counts
    zl = np.array([z[0] for z in zone_pts], dtype=np.float64)
    zg = np.array([z[1] for z in zone_pts], dtype=np.float64)
    arr = np.array(pts, dtype=np.float64)
    for start in range(0, len(arr), 4000):
        chunk = arr[start:start + 4000]
        d = haversine_km(chunk[:, 0][:, None], chunk[:, 1][:, None], zl[None, :], zg[None, :])
        nearest = d.argmin(axis=1)
        ok = d[np.arange(len(chunk)), nearest] <= spacing_km
        np.add.at(counts, nearest[ok], 1)
    return counts


def assemble_zones(lat: float, lng: float, polygon: list[list[list[float]]], radius_km: float,
                   total_population: float | None, buildings: list[tuple[float, float]] | None,
                   activity: list[tuple[float, float]] | None) -> tuple[list[dict], dict]:
    spacing = zone_spacing(radius_km)
    cand = hex_grid(lat, lng, radius_km, spacing)
    inside = points_in_polygon(cand, polygon)
    zpts = [p for p, ok in zip(cand, inside) if ok] or [(lat, lng)]
    b_counts = assign_counts(zpts, buildings or [], spacing)
    a_counts = assign_counts(zpts, activity or [], spacing)
    if total_population is None:
        pop = np.zeros(len(zpts))
        method = "unavailable"
    elif b_counts.sum() >= max(20, 0.2 * len(zpts)):
        pop = total_population * b_counts / b_counts.sum()
        method = "dasymetric_buildings"
    else:
        pop = np.full(len(zpts), total_population / len(zpts))
        method = "uniform"
    zones = [{"lat": round(p[0], 6), "lng": round(p[1], 6), "population": round(float(pop[i]), 2),
              "buildings": int(b_counts[i]), "activity": int(a_counts[i])} for i, p in enumerate(zpts)]
    meta = {"method": method, "spacing_km": round(spacing, 3), "zones": len(zones), "total": total_population,
            "buildings_used": int(b_counts.sum())}
    return zones, meta


def assess_coverage(competitors: list[dict], total_pop: float | None, n_buildings: int, area_km2: float) -> dict:
    """A coverage indicator computed from observable signals only (no invented percentages)."""
    signals = []
    now = datetime.now(timezone.utc)
    dates = []
    for c in competitors:
        ts = c.get("source_updated_at")
        if ts:
            try:
                dates.append(datetime.fromisoformat(ts.replace("Z", "+00:00")))
            except ValueError:
                pass
    named = sum(1 for c in competitors if c.get("name"))
    with_hours = sum(1 for c in competitors if (c.get("tags") or {}).get("opening_hours"))
    median_age_days = None
    if dates:
        ages = sorted((now - d).days for d in dates)
        median_age_days = ages[len(ages) // 2]
    b_per_1000 = (n_buildings / (total_pop / 1000)) if total_pop and total_pop > 0 else None
    level = "unknown"
    if b_per_1000 is not None:
        level = "good" if b_per_1000 >= 40 else "partial" if b_per_1000 >= 10 else "low"
        signals.append({"signal": "Mapped buildings per 1,000 residents", "value": round(b_per_1000, 1),
                        "why": "Areas where few buildings are mapped usually also have few mapped shops."})
    signals.append({"signal": "Competitors found", "value": len(competitors), "why": "Zero or very few results may mean missing data, not an empty market."})
    if competitors:
        signals.append({"signal": "Share with a name", "value": round(named / len(competitors), 2), "why": "Unnamed features are often incomplete records."})
        signals.append({"signal": "Share with opening hours", "value": round(with_hours / len(competitors), 2), "why": "Detail level of local mapping."})
    if median_age_days is not None:
        signals.append({"signal": "Median days since competitor records were last edited", "value": median_age_days, "why": "Old records may describe businesses that have changed or closed."})
    notes = {
        "good": "Map detail in this area looks reasonably complete, but small or informal businesses can still be missing.",
        "partial": "Map detail is partial here. Expect some competitors to be missing; verify on the ground.",
        "low": "Map detail is thin here. Many competitors are likely missing; field verification is essential.",
        "unknown": "Coverage could not be assessed because population data was unavailable.",
    }
    return {"level": level, "note": notes[level], "signals": signals, "method": "Heuristic from building mapping density, record completeness and edit recency. Not a measured recall rate."}


async def build_snapshot(*, lat: float, lng: float, catchment: dict, category: dict,
                         manual_population: float | None, cache: Cache | None) -> dict:
    arch = get_archetype(category["archetype"])
    sources, errors = [], []
    polygon, method = None, "radius"
    radius_km = float(catchment.get("radius_km") or arch.default_catchment_km)
    radius_km = max(0.3, min(radius_km, MAX_RADIUS_KM))
    if catchment.get("mode") == "isochrone":
        try:
            polygon, prov = await population.ors_isochrone(lat, lng, int(catchment.get("minutes") or 15),
                                                            catchment.get("profile") or "foot-walking", cache)
            sources.append(prov)
            method = "isochrone"
            radius_km = min(MAX_RADIUS_KM, polygon_radius_km(lat, lng, polygon))
        except ProviderError as e:
            errors.append({"source": "openrouteservice", "message": e.message, "fallback": "radius"})
    if polygon is None:
        polygon = [circle_polygon(lat, lng, radius_km)]
    radius_m = int(radius_km * 1000)
    # Competitors are searched in a slightly wider ring: people at the edge also see businesses just outside.
    comp_radius_m = int(min(MAX_RADIUS_KM, radius_km + 1.0) * 1000)

    async def comp_task():
        terms = [w for w in [category.get("query"), category.get("label")] if w]
        terms = [t.split("/")[0].strip() for t in terms]
        return await osm.fetch_competitors(lat, lng, comp_radius_m, category.get("filters") or [], cache, terms=terms,
                                           timeout_s=30 if get_settings().serverless else 40)

    async def bld_task():
        return await osm.fetch_buildings(lat, lng, radius_m, cache)

    async def ctx_task():
        # Context POIs feed the factor engine (schools, transit, offices…) and the visitor-demand proxy.
        return await osm.fetch_pois(lat, lng, radius_m, list(CONTEXT_FILTERS), cache, limit=6000, timeout_s=80)

    async def agesex_task():
        return await population.worldpop_age_sex(polygon, cache)

    async def pop_task():
        if manual_population:
            return float(manual_population), provenance("user", detail="Catchment population entered by the user")
        return await population.worldpop_total(polygon, cache)

    async def bounded(coro, seconds: float, what: str):
        try:
            return await asyncio.wait_for(coro, seconds)
        except asyncio.TimeoutError as e:
            raise ProviderError(what, f"no response within {int(seconds)} s") from e

    # Layers run concurrently; each races the Overpass mirrors. Competitors also fall back to Photon/Nominatim.
    k = 0.55 if get_settings().serverless else 1.0  # serverless requests must finish well inside the platform limit
    kp = 0.85 if get_settings().serverless else 1.0  # WorldPop is slow but it is the official population figure: give it longer
    results = await asyncio.gather(bounded(comp_task(), 95 * k, "overpass"), bounded(bld_task(), 110 * k, "overpass"),
                                   bounded(ctx_task(), 110 * k, "overpass"), bounded(pop_task(), 100 * kp, "worldpop"),
                                   bounded(agesex_task(), 100 * kp, "worldpop"), return_exceptions=True)
    names = ["competitors", "buildings", "context", "population", "age_sex"]
    vals = {}
    for nm, res in zip(names, results):
        if isinstance(res, Exception):
            msg = res.message if isinstance(res, ProviderError) else str(res)
            log.warning("snapshot %s failed: %s", nm, msg)
            errors.append({"source": nm, "message": msg[:400]})
            vals[nm] = None
        else:
            data, prov = res
            vals[nm] = data
            if prov:
                prov = dict(prov)
                also = prov.pop("also", None) or []
                prov["layer"] = nm
                sources.append(prov)
                sources.extend({**a, "layer": nm} for a in also)
    comps = vals["competitors"] or []
    context = []
    for c in vals["context"] or []:
        kind = classify_poi(c["tags"])
        if kind:
            context.append({"lat": c["lat"], "lng": c["lng"], "name": c["name"], "kind": kind})
    activity = [c for c in context if c["kind"] in ACTIVITY_KINDS] if arch.demand_base == "residents_and_activity" else []
    total_pop = vals["population"]
    pop_source = "user" if manual_population else ("worldpop" if total_pop is not None else None)
    if total_pop is None and vals["buildings"] and len(vals["buildings"]) >= 50:
        # Transparent fallback: mapped buildings x an explicit persons-per-building assumption.
        ppb = get_settings().persons_per_building
        total_pop = float(len(vals["buildings"]) * ppb)
        pop_source = "estimate_buildings"
        errors.append({"source": "population", "message": f"WorldPop unavailable; using a rough estimate of {ppb:g} persons per mapped building ({len(vals['buildings'])} buildings). Replace with a real figure if you have one.", "fallback": "building-based estimate"})
    zones, pop_meta = assemble_zones(lat, lng, polygon, radius_km, total_pop, vals["buildings"],
                                     [(a["lat"], a["lng"]) for a in activity])
    pop_meta["source"] = pop_source
    pop_meta["n_buildings"] = len(vals["buildings"] or [])
    if vals.get("age_sex"):
        pop_meta["age_sex"] = vals["age_sex"]
    bld = vals["buildings"] or []
    if bld:
        b = np.array(bld)
        d = haversine_km(lat, lng, b[:, 0], b[:, 1])
        pop_meta["buildings_1km"], pop_meta["buildings_2km"] = int((d <= 1).sum()), int((d <= 2).sum())
    area = math.pi * radius_km ** 2
    coverage = assess_coverage(comps, total_pop, len(vals["buildings"] or []), area)
    if total_pop is None:
        status = "failed" if vals["competitors"] is None else "partial"
    else:
        status = "complete" if not errors else "partial"
    return {
        "status": status,
        "catchment_geojson": {"type": "Polygon", "coordinates": polygon},
        "catchment_method": method,
        "radius_km": radius_km,
        "zones": zones,
        "population": pop_meta,
        "competitors": comps,
        "activity_points": context[:6000],
        "sources": sources,
        "coverage": coverage,
        "errors": errors,
        "bbox_deg": {"dlat": km_to_deg_lat(radius_km), "dlng": km_to_deg_lng(radius_km, lat)},
    }
