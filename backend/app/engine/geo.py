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
