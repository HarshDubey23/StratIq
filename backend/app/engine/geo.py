"""Small, dependency-free geometry helpers (numpy only)."""
from __future__ import annotations

import math

import numpy as np

EARTH_R_KM = 6371.0088


def haversine_km(lat1, lng1, lat2, lng2):
    """Great-circle distance in km. Accepts scalars or broadcastable arrays."""
    lat1, lng1, lat2, lng2 = map(np.radians, (lat1, lng1, lat2, lng2))
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlng / 2) ** 2
    return 2 * EARTH_R_KM * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def distance_matrix_km(zone_lat, zone_lng, pt_lat, pt_lng) -> np.ndarray:
    zl = np.asarray(zone_lat, float)[:, None]
    zg = np.asarray(zone_lng, float)[:, None]
    pl = np.asarray(pt_lat, float)[None, :]
    pg = np.asarray(pt_lng, float)[None, :]
    return haversine_km(zl, zg, pl, pg)


def travel_time_matrix_minutes(
    dist_km: np.ndarray,
    speed_kmh: float = 20.0,
    congestion_factor: float = 1.0,
) -> np.ndarray:
    """Computes travel-time matrix T_{zj} (minutes) from distance matrix D_{zj} (km).
    
    Formula:
        T_{zj} = (D_{zj} / speed_kmh) * 60.0 * congestion_factor
    Floored at 1.0 minute to account for local access, egress, and parking.
    """
    speed = max(1.0, float(speed_kmh))
    time_min = (np.asarray(dist_km, float) / speed) * 60.0 * float(congestion_factor)
    return np.maximum(time_min, 1.0)


def compute_spatial_matrices(
    zone_lats: list[float] | np.ndarray,
    zone_lngs: list[float] | np.ndarray,
    dest_lats: list[float] | np.ndarray,
    dest_lngs: list[float] | np.ndarray,
    *,
    circuity: float = 1.3,
    speed_kmh: float = 20.0,
    travel_km: np.ndarray | None = None,
    travel_time_min: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray, dict]:
    """Computes or accepts pre-computed distance matrix D_{zj} (km) and travel-time matrix T_{zj} (minutes).
    
    Falls back to Haversine * circuity factor when explicit routing distance is not provided.
    Falls back to (distance / speed_kmh) * 60 when explicit routing travel time is not provided.
    
    Returns:
        (dist_km, travel_time_min, metadata)
    """
    Z = len(zone_lats)
    J = len(dest_lats)
    if travel_km is not None:
        travel_km_arr = np.asarray(travel_km, float)
        if travel_km_arr.shape != (Z, J):
            raise ValueError(f"travel_km shape {travel_km_arr.shape} does not match expected ({Z}, {J})")
        dist = np.maximum(travel_km_arr, 0.15)
        dist_source = "precomputed_network"
    else:
        raw_dist = distance_matrix_km(zone_lats, zone_lngs, dest_lats, dest_lngs)
        dist = np.maximum(raw_dist * float(circuity), 0.15)
        dist_source = "haversine_circuity_fallback"

    if travel_time_min is not None:
        tt_arr = np.asarray(travel_time_min, float)
        if tt_arr.shape != (Z, J):
            raise ValueError(f"travel_time_min shape {tt_arr.shape} does not match expected ({Z}, {J})")
        tt = np.maximum(tt_arr, 1.0)
        time_source = "precomputed_network"
    else:
        tt = travel_time_matrix_minutes(dist, speed_kmh=speed_kmh)
        time_source = "circuity_speed_fallback"

    metadata = {
        "dist_source": dist_source,
        "travel_time_source": time_source,
        "circuity_factor": float(circuity),
        "assumed_speed_kmh": float(speed_kmh),
        "min_dist_km": float(np.min(dist)) if dist.size else 0.0,
        "max_dist_km": float(np.max(dist)) if dist.size else 0.0,
        "min_travel_time_min": float(np.min(tt)) if tt.size else 0.0,
        "max_travel_time_min": float(np.max(tt)) if tt.size else 0.0,
    }
    return dist, tt, metadata



def km_to_deg_lat(km: float) -> float:
    return km / 110.574


def km_to_deg_lng(km: float, lat: float) -> float:
    return km / (111.320 * max(0.05, math.cos(math.radians(lat))))


def hex_grid(center_lat: float, center_lng: float, radius_km: float, spacing_km: float) -> list[tuple[float, float]]:
    """Pointy-top hexagonal lattice of cell centres within ``radius_km``."""
    pts: list[tuple[float, float]] = []
    dy = spacing_km * math.sqrt(3) / 2
    rows = int(radius_km / dy) + 1
    cols = int(radius_km / spacing_km) + 1
    for r in range(-rows, rows + 1):
        y = r * dy
        offset = spacing_km / 2 if r % 2 else 0.0
        for c in range(-cols - 1, cols + 2):
            x = c * spacing_km + offset
            if x * x + y * y <= radius_km * radius_km:
                pts.append((center_lat + km_to_deg_lat(y), center_lng + km_to_deg_lng(x, center_lat)))
    return pts


def circle_polygon(lat: float, lng: float, radius_km: float, n: int = 48) -> list[list[float]]:
    """Closed ring of [lng, lat] coordinates (GeoJSON order)."""
    ring = []
    for i in range(n):
        t = 2 * math.pi * i / n
        ring.append([lng + km_to_deg_lng(radius_km * math.cos(t), lat), lat + km_to_deg_lat(radius_km * math.sin(t))])
    ring.append(ring[0])
    return ring


def point_in_ring(lng: float, lat: float, ring: list[list[float]]) -> bool:
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > lat) != (yj > lat) and lng < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def points_in_polygon(points: list[tuple[float, float]], polygon: list[list[list[float]]]) -> list[bool]:
    """``points`` as (lat, lng); ``polygon`` as GeoJSON Polygon coordinates (outer ring + holes)."""
    out = []
    for lat, lng in points:
        if not polygon or not point_in_ring(lng, lat, polygon[0]):
            out.append(False)
            continue
        out.append(not any(point_in_ring(lng, lat, h) for h in polygon[1:]))
    return out
