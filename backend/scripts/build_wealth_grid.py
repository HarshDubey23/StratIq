"""Build backend/app/data/wealth_grid_ind.npz from two public datasets (run by .github/workflows/data.yml).

1. Meta Data for Good, Relative Wealth Index (Chi et al. 2022, PNAS), ~2.4 km Bing tiles, via the HDX CKAN API.
   Licence: CC BY-NC 4.0 - attribution "Relative Wealth Index, Meta Data for Good / Chi et al. (2022)".
2. WorldPop Global 1 km population (2020, UN-adjusted, CC BY 4.0) for India - used to population-weight tiles and to
   drop tiles outside India (the HDX file for India also covers Pakistan-administered areas).

Output per tile: Bing tile x/y (zoom 14 or whatever the quadkeys carry), RWI, its standard error, WorldPop population and
the tile's population-weighted national percentile of RWI (0..1). The percentile is what the engine uses:
"this tile is richer than X % of India's population".

Usage: python scripts/build_wealth_grid.py OUT.npz OUT_META.json
"""
from __future__ import annotations

import csv
import io
import json
import math
import sys
import urllib.request
from datetime import datetime, timezone

import numpy as np

HDX_PKG = "https://data.humdata.org/api/3/action/package_show?id=relative-wealth-index"
WORLDPOP_IND = "https://data.worldpop.org/GIS/Population/Global_2000_2020_1km_UNadj/2020/IND/ind_ppp_2020_1km_Aggregated_UNadj.tif"
UA = {"User-Agent": "StrataIQ-data-pipeline (github.com/HarshDubey23/stratiq)"}


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=600) as r:
        return r.read()


def quadkey_to_xyz(qk: str) -> tuple[int, int, int]:
    x = y = 0
    for i, c in enumerate(qk):
        mask = 1 << (len(qk) - i - 1)
        d = int(c)
        if d & 1:
            x |= mask
        if d & 2:
            y |= mask
    return x, y, len(qk)


def tile_bounds(x: np.ndarray, y: np.ndarray, z: int) -> tuple[np.ndarray, ...]:
    n = 2.0 ** z
    lon0 = x / n * 360.0 - 180.0
    lon1 = (x + 1) / n * 360.0 - 180.0
    lat0 = np.degrees(np.arctan(np.sinh(np.pi * (1 - 2 * (y + 1) / n))))
    lat1 = np.degrees(np.arctan(np.sinh(np.pi * (1 - 2 * y / n))))
    return lon0, lat0, lon1, lat1


def main(out_npz: str, out_meta: str) -> None:
    pkg = json.loads(fetch(HDX_PKG))["result"]
    res = [r for r in pkg["resources"] if "ind_pak" in (r.get("name", "") + r.get("url", "")).lower()]  # India ships as ind_pak_*.csv
    if not res:
        raise SystemExit("No India RWI resource found on HDX: " + ", ".join(r.get("name", "") for r in pkg["resources"])[:2000])
    rwi_res = res[0]
    text = fetch(rwi_res["url"]).decode("utf-8")
    rows = [{k.strip().lower().lstrip("\ufeff"): v for k, v in r.items()} for r in csv.DictReader(io.StringIO(text))]
    print("columns:", list(rows[0]), "rows:", len(rows), "resource:", rwi_res.get("name"))
    xs, ys, rwi, err = [], [], [], []
    zoom = None
    for r in rows:
        if r.get("quadkey"):
            x, y, z = quadkey_to_xyz(r["quadkey"].strip())
        else:  # some country files carry only the tile centroid: Bing tiles are zoom 14 (~2.4 km)
            z = 14
            la, lo = float(r.get("latitude") or r["lat"]), float(r.get("longitude") or r.get("lon") or r["lng"])
            n = 2 ** z
            x = int((lo + 180.0) / 360.0 * n)
            y = int((1 - math.asinh(math.tan(math.radians(la))) / math.pi) / 2 * n)
        zoom = zoom or z
        if z != zoom:
            continue
        xs.append(x), ys.append(y), rwi.append(float(r["rwi"])), err.append(float(r.get("error") or "nan"))
    xs, ys = np.array(xs, np.int64), np.array(ys, np.int64)
    rwi, err = np.array(rwi), np.array(err)

    # WorldPop 1 km raster -> population per tile via a summed-area table (exact pixel sums over the tile's window)
    import rasterio  # installed only in the data workflow

    with rasterio.MemoryFile(fetch(WORLDPOP_IND)) as mf, mf.open() as ds:
        a = ds.read(1).astype(np.float64)
        a[(a < 0) | ~np.isfinite(a)] = 0.0
        if ds.nodata is not None:
            a[a == ds.nodata] = 0.0
        tr = ds.transform
    # every populated pixel is assigned to the zoom-z tile containing its centre (an exact partition, no double counting)
    rr, cc = np.nonzero(a > 0)
    plon = tr.c + (cc + 0.5) * tr.a
    plat = tr.f + (rr + 0.5) * tr.e
    n = 2 ** zoom
    px = np.floor((plon + 180.0) / 360.0 * n).astype(np.int64)
    py = np.floor((1 - np.arcsinh(np.tan(np.radians(plat))) / np.pi) / 2 * n).astype(np.int64)
    pkey = px * n + py
    ukey, inv = np.unique(pkey, return_inverse=True)
    tile_pop = np.bincount(inv, weights=a[rr, cc])
    tkey = xs * n + ys
    i = np.clip(np.searchsorted(ukey, tkey), 0, len(ukey) - 1)
    pop = np.where(ukey[i] == tkey, tile_pop[i], 0.0)
    print("raster population", round(float(a.sum())), "covered by RWI tiles", round(float(pop.sum())))

    if not len(xs):
        raise SystemExit("no tiles parsed")
    keep = pop > 0  # outside India's WorldPop raster (incl. Pakistan) -> no population -> dropped
    xs, ys, rwi, err, pop = xs[keep], ys[keep], rwi[keep], err[keep], pop[keep]
    order = np.argsort(rwi, kind="stable")
    cum = np.cumsum(pop[order])
    pct = np.empty_like(rwi)
    pct[order] = (cum - pop[order] / 2) / cum[-1]  # mid-rank population-weighted percentile

    np.savez_compressed(out_npz, zoom=np.int64(zoom), tx=xs.astype(np.uint32), ty=ys.astype(np.uint32),
                        rwi=rwi.astype(np.float32), err=err.astype(np.float32), pop=pop.astype(np.float32), pct=pct.astype(np.float32))
    meta = {
        "built_at": datetime.now(timezone.utc).isoformat(),
        "rwi": {"dataset": pkg.get("title"), "resource": rwi_res.get("name"), "url": rwi_res.get("url"),
                "source_updated": rwi_res.get("last_modified") or pkg.get("metadata_modified"), "licence": pkg.get("license_title"),
                "citation": "Chi, Fang, Chatterjee & Blumenstock (2022) Microestimates of wealth for all low- and middle-income countries. PNAS 119(3)."},
        "population": {"dataset": "WorldPop Global 1km UN-adjusted 2020, India", "url": WORLDPOP_IND, "licence": "CC BY 4.0"},
        "zoom": zoom, "tiles_in": len(rows), "tiles_kept": int(keep.sum()), "population_total": float(pop.sum()),
        "tile_km_at_equator": round(40075.016 / 2 ** zoom, 3),
    }
    with open(out_meta, "w") as f:
        json.dump(meta, f, indent=2)
    print(json.dumps(meta, indent=2))
    if not math.isclose(pct.max(), 1.0, abs_tol=0.01):
        raise SystemExit("percentile sanity check failed")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
