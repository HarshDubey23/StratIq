"""Road-network distance and travel time (OSRM table service).

Every demand zone is routed to the site and to the nearest competitors over the real OpenStreetMap road network, once on
foot and once by car. The matrices are stored in the market snapshot, so a run uses real network distance instead of
straight-line distance x circuity. Default servers are the FOSSGIS public OSRM instances (routing.openstreetmap.de);
point ROUTING_URLS at your own OSRM for heavy use.
"""
from __future__ import annotations

import asyncio
from datetime import timedelta

import httpx
import numpy as np

from ..config import get_settings
from .http import Cache, ProviderError, cache_key, client
from .registry import provenance

PROFILES = {"foot": "routed-foot", "car": "routed-car"}


def _chunks(n_src: int, n_dst: int, max_coords: int) -> list[tuple[int, int]]:
    step = max(1, max_coords - n_dst)
    return [(i, min(n_src, i + step)) for i in range(0, n_src, step)]


async def _table(base: str, src: list[tuple[float, float]], dst: list[tuple[float, float]], max_coords: int) -> tuple[np.ndarray, np.ndarray]:
    km = np.full((len(src), len(dst)), np.nan)
    mins = np.full((len(src), len(dst)), np.nan)
    dst_s = ";".join(f"{g:.5f},{a:.5f}" for a, g in dst)
    for a, b in _chunks(len(src), len(dst), max_coords):
        part = src[a:b]
        coords = ";".join(f"{g:.5f},{la:.5f}" for la, g in part) + ";" + dst_s
        params = {"sources": ";".join(map(str, range(len(part)))),
                  "destinations": ";".join(map(str, range(len(part), len(part) + len(dst)))),
                  "annotations": "distance,duration"}
        if a:
            await asyncio.sleep(1.0)
        r = await client().get(f"{base}/table/v1/driving/{coords}", params=params, timeout=httpx.Timeout(30.0, connect=10.0))
        r.raise_for_status()
        body = r.json()
        if body.get("code") != "Ok":
            raise ProviderError("routing", f"OSRM table: {body.get('code')} {body.get('message', '')}".strip())
        km[a:b] = np.array(body["distances"], dtype=float) / 1000.0  # null (unroutable) -> nan
        mins[a:b] = np.array(body["durations"], dtype=float) / 60.0
    return km, mins


async def route_matrix(zones: list[tuple[float, float]], dests: list[tuple[float, float]], cache: Cache | None = None) -> tuple[dict, dict]:
    """Zone x destination road distance (km) and time (min), on foot and by car. Unroutable pairs are None."""
    s = get_settings()
    key = cache_key("routing", {"z": [(round(a, 5), round(b, 5)) for a, b in zones], "d": [(round(a, 5), round(b, 5)) for a, b in dests]})
    if cache and (hit := cache.get(key)):
        return hit[0], provenance("osrm", retrieved_at=hit[1], cached=True, detail=f"{len(zones)} zones x {len(dests)} destinations")
    out: dict = {}
    try:
        for prof, path in PROFILES.items():
            km, mins = await _table(f"{s.routing_url.rstrip('/')}/{path}", zones, dests, s.routing_max_coords)
            out[prof] = {"km": np.where(np.isnan(km), None, np.round(km, 3)).tolist(),
                         "min": np.where(np.isnan(mins), None, np.round(mins, 2)).tolist()}
            await asyncio.sleep(1.0)  # public servers: about one request per second
    except (httpx.HTTPError, KeyError, ValueError, TypeError) as e:
        raise ProviderError("routing", f"OSRM table failed: {type(e).__name__} {e}".strip()) from e
    if cache:
        cache.put(key, "routing", out, timedelta(days=30))
    return out, provenance("osrm", detail=f"Road-network distance and time, {len(zones)} zones x {len(dests)} destinations, on foot and by car")


def point_key(lat: float, lng: float) -> str:
    """Destinations are matched by position (5 dp, ~1 m), so DB competitors find the routes stored in the snapshot."""
    return f"{lat:.5f},{lng:.5f}"


def matrix_for(routing: dict | None, dest_keys: list[str], points: list[tuple[str, float, float]], zones_ll: np.ndarray,
               circuity: float, speed_kmh: float, profile: str = "car") -> tuple[np.ndarray, np.ndarray | None, float]:
    """Assemble a zone x point km matrix from stored routes; points not routed fall back to haversine x circuity.

    Returns (km [Z,J], minutes [Z,J] or None when nothing was routed, share of cells from the road network)."""
    from ..engine.geo import haversine_km

    Z, J = len(zones_ll), len(points)
    hv = haversine_km(zones_ll[:, :1], zones_ll[:, 1:], np.array([[p[1] for p in points]]), np.array([[p[2] for p in points]])) * circuity
    km, mins = hv.copy(), np.full((Z, J), np.nan)
    if routing and routing.get(profile):
        col = {k: i for i, k in enumerate(dest_keys)}
        rk = np.array(routing[profile]["km"], dtype=float)
        rm = np.array(routing[profile]["min"], dtype=float)
        if rk.shape[0] == Z:
            for j, (pid, _, _) in enumerate(points):
                i = col.get(pid)
                if i is not None:
                    ok = np.isfinite(rk[:, i])
                    km[ok, j] = np.maximum(rk[ok, i], 0.05)
                    mins[ok, j] = np.maximum(rm[ok, i], 0.5)
    routed = np.isfinite(mins)
    share = float(routed.mean()) if mins.size else 0.0
    mins = np.where(routed, mins, km / max(speed_kmh, 1.0) * 60.0)  # unrouted cells: same fallback the model uses
    return km, (mins if share > 0 else None), share
