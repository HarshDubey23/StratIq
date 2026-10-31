"""Real-data income layer: who in this catchment can afford what.

Every synthetic person gets a monthly per-capita consumption (MPCE, Rs) drawn from official and observed data:

1. Official rupee anchor - HCES 2023-24 (MoSPI): all-India rural and urban fractile tables (Table 3.1) and P10..P90
   deciles for 18 states x rural/urban (Tables 3.4R/U). Each curve is fitted with a Singh-Maddala distribution
   (Singh & Maddala 1976; McDonald 1984), F(x) = 1 - (1 + (x/b)^a)^(-q), by least squares on log quantiles and class means.
2. Local wealth ranking - Meta Relative Wealth Index (Chi et al. 2022, PNAS) on ~2.4 km tiles. The data pipeline
   (scripts/build_wealth_grid.py) gives each tile its WorldPop population, its state (geoBoundaries ADM1) and an
   urban/rural class (one national density threshold that makes 35% of people urban, UN WUP 2018), and ranks tiles by
   RWI *within their state x sector*, population-weighted: p_t = "richer than p_t of this state's rural/urban people".
3. Rank matching (Hruschka, Gerkey & Hadley 2015; Chi et al. 2022 SM): a person in tile t gets a rank
       z = a * Phi^-1(p_t) + sqrt(1 - a^2) * e,   e ~ N(0,1),   u = Phi(z)
   and MPCE = Q_{state,sector}(u), the official curve of the same geography the rank was taken in. Because p_t is
   uniform over that state x sector's population, z is standard normal there, so the official distribution is
   reproduced exactly; a^2 is the share of wealth variance between tiles (assumption, varied in Monte Carlo).
   States outside HCES Table 3.4 use the all-India sector curve.

Fallbacks, recorded in provenance: no tile -> the state x sector HCES curve (state from reverse geocoding) -> the
all-India sector curve. Nothing is invented: every step names its source and status.
"""
from __future__ import annotations

import json
import math
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares
from scipy.special import ndtr, ndtri

DATA = Path(__file__).resolve().parents[2] / "data"
GRID_FILE = DATA / "wealth_grid_ind.npz"
BETWEEN_TILE_LOADING = (0.6, 0.4, 0.8)  # a (value, low, high): assumption, see module docstring
# National consumption classes used for segments and for the "income mix" display.
CLASS_EDGES = (0.0, 0.4, 0.8, 1.0)  # bottom 40 % / middle 40 % / top 20 % of India by MPCE
CLASS_KEYS = ("budget", "mainstream", "premium")


@lru_cache(maxsize=1)
def hces() -> dict:
    return json.loads((DATA / "hces_2023_24.json").read_text())


# ---------------------------------------------------------------- Singh-Maddala
def sm_cdf(x, b, a, q):
    x = np.maximum(np.asarray(x, float), 1e-9)
    return 1.0 - (1.0 + (x / b) ** a) ** (-q)


def sm_ppf(u, b, a, q):
    u = np.clip(np.asarray(u, float), 1e-9, 1 - 1e-9)
    return b * ((1.0 - u) ** (-1.0 / q) - 1.0) ** (1.0 / a)


def _class_means(b, a, q, edges):
    out = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        uu = np.linspace(lo, hi, 802)[1:-1]
        out.append(sm_ppf(uu, b, a, q).mean())
    return np.array(out)


@dataclass(frozen=True)
class Curve:
    key: str
    b: float
    a: float
    q: float
    fit_error: float  # worst relative fit error against the published points
    source: str

    def ppf(self, u):
        return sm_ppf(u, self.b, self.a, self.q)

    def cdf(self, x):
        return sm_cdf(x, self.b, self.a, self.q)

    @property
    def median(self) -> float:
        return float(self.ppf(0.5))


def _fit(quantiles: list[tuple[float, float]], means: list[float] | None, edges: list[float] | None, key: str, source: str) -> Curve:
    qp = np.array([p for p, _ in quantiles])
    qv = np.array([v for _, v in quantiles], float)
    m = np.array(means, float) if means else None

    def resid(theta):
        b, a, q = np.exp(theta)
        r = [np.log(sm_ppf(qp, b, a, q)) - np.log(qv)]
        if m is not None:
            r.append(np.log(_class_means(b, a, q, edges)) - np.log(m))
        return np.concatenate(r)

    sol = least_squares(resid, [math.log(float(np.median(qv))), math.log(3.5), 0.0], method="lm")
    b, a, q = np.exp(sol.x)
    err = float(np.max(np.abs(np.expm1(resid(sol.x)))))
    return Curve(key, float(b), float(a), float(q), err, source)


@lru_cache(maxsize=64)
def curve(sector: str, state: str | None = None) -> Curve:
    """HCES curve for a sector ('rural' | 'urban'), optionally a state (Table 3.4 names)."""
    h = hces()
    if state and state in h["state_deciles"][sector]:
        d = h["state_deciles"][sector][state]
        return _fit([(p / 10, v) for p, v in zip(range(1, 10), d)], None, None, f"{state}/{sector}",
                    f"HCES 2023-24 {h['state_deciles']['source'].split('(')[0].strip()} - {state}, {sector}")
    nf = h["national_fractiles"]
    s = nf[sector]
    edges = nf["edges"]
    qs = [(edges[i + 1], v) for i, v in enumerate(s["upper"]) if v]
    return _fit(qs, s["mean"], edges, f"India/{sector}", f"HCES 2023-24 Table 3.1 - all-India, {sector}")


class NationalCurve:
    """Rural/urban mixture of the all-India HCES curves: the distribution an RWI national rank refers to."""

    def __init__(self, rural_share: float | None = None):
        self.w = float(rural_share if rural_share is not None else hces()["rural_population_share"]["value"])
        self.r, self.u = curve("rural"), curve("urban")
        grid = np.exp(np.linspace(np.log(300), np.log(400_000), 4000))
        cdf = self.w * self.r.cdf(grid) + (1 - self.w) * self.u.cdf(grid)
        self._grid, self._cdf = grid, cdf

    def ppf(self, u):
        return np.exp(np.interp(np.clip(u, 1e-6, 1 - 1e-6), self._cdf, np.log(self._grid)))

    def cdf(self, x):
        return np.interp(np.log(np.maximum(x, 1.0)), np.log(self._grid), self._cdf)

    def p_urban(self, x):
        """Bayes: P(urban | MPCE = x) from the two official densities."""
        x = np.maximum(np.asarray(x, float), 1.0)
        dens = lambda c: c.a * c.q / c.b * (x / c.b) ** (c.a - 1) * (1 + (x / c.b) ** c.a) ** (-c.q - 1)  # noqa: E731
        fr, fu = self.w * dens(self.r), (1 - self.w) * dens(self.u)
        return fu / np.maximum(fr + fu, 1e-300)


# ---------------------------------------------------------------- wealth grid (Meta RWI x WorldPop)
@lru_cache(maxsize=1)
def _grid():
    if not GRID_FILE.exists():
        return None
    g = np.load(GRID_FILE)
    zoom = int(g["zoom"])
    tx, ty = g["tx"].astype(np.int64), g["ty"].astype(np.int64)
    key = tx * (1 << zoom) + ty
    order = np.argsort(key)
    meta_path = DATA / "wealth_grid_ind_meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    out = {"zoom": zoom, "key": key[order], "pct": g["pct"][order].astype(float), "rwi": g["rwi"][order].astype(float),
           "err": g["err"][order].astype(float), "pop": g["pop"][order].astype(float), "meta": meta}
    if "pct_ss" in g.files:  # tiles tagged with state and urban/rural, ranked within state x sector
        out.update(state=g["state"][order], urban=g["urban"][order], pct_ss=g["pct_ss"][order].astype(float))
    return out


def _tile_xy(lat, lng, zoom):
    n = 1 << zoom
    lat = np.clip(np.asarray(lat, float), -85.0511, 85.0511)
    x = np.floor((np.asarray(lng, float) + 180.0) / 360.0 * n).astype(np.int64)
    y = np.floor((1 - np.arcsinh(np.tan(np.radians(lat))) / np.pi) / 2 * n).astype(np.int64)
    return x, y


def tile_lookup(lats, lngs) -> dict | None:
    """Per point: national and state x sector RWI percentile, state name and sector of its wealth tile (None if no grid)."""
    g = _grid()
    if g is None:
        return None
    lats, lngs = np.atleast_1d(np.asarray(lats, float)), np.atleast_1d(np.asarray(lngs, float))
    x, y = _tile_xy(lats, lngs, g["zoom"])
    k = x * (1 << g["zoom"]) + y
    i = np.clip(np.searchsorted(g["key"], k), 0, len(g["key"]) - 1)
    hit = g["key"][i] == k
    out = {"hit": hit, "pct": np.where(hit, g["pct"][i], np.nan), "meta": g["meta"]}
    if "pct_ss" in g:
        names = g["meta"].get("states") or []
        out["pct_ss"] = np.where(hit, g["pct_ss"][i], np.nan)
        out["sector"] = np.where(hit & g["urban"][i], "urban", "rural")
        out["state"] = [normalise_state(names[s]) if h and s < len(names) else None for s, h in zip(g["state"][i], hit)]
    return out


def tile_percentiles(lats, lngs) -> tuple[np.ndarray, np.ndarray, dict | None]:
    """National population-weighted RWI percentile for each point (NaN where no tile). Returns (pct, rwi, grid meta)."""
    g = _grid()
    lats, lngs = np.atleast_1d(lats), np.atleast_1d(lngs)
    if g is None:
        return np.full(lats.shape, np.nan), np.full(lats.shape, np.nan), None
    x, y = _tile_xy(lats, lngs, g["zoom"])
    k = x * (1 << g["zoom"]) + y
    i = np.clip(np.searchsorted(g["key"], k), 0, len(g["key"]) - 1)
    hit = g["key"][i] == k
    return np.where(hit, g["pct"][i], np.nan), np.where(hit, g["rwi"][i], np.nan), g["meta"]


# ---------------------------------------------------------------- the income model for one catchment
@dataclass
class IncomeContext:
    method: str  # "rwi_state_rank" | "rwi_rank" | "state_curve" | "national_sector_curve"
    zone_pct: np.ndarray  # [Z] percentile of each zone's tile (within state x sector for rwi_state_rank, else national)
    state: str | None
    sector: str
    loading: float
    provenance: list[dict]
    curve_key: str
    fit_error: float
    zone_curve: list[Curve] | None = None  # [Z] official curve per zone (rwi_state_rank)

    def draw(self, rng: np.random.Generator, zi: np.ndarray, loading: float | None = None) -> tuple[np.ndarray, np.ndarray]:
        """MPCE (Rs/person/month) and national rank u for people living in zones ``zi``."""
        a = self.loading if loading is None else loading
        e = rng.standard_normal(zi.size)
        nat = national()
        if self.method == "rwi_state_rank":
            p = self.zone_pct[zi]
            p = np.where(np.isnan(p), 0.5, p)
            uu = ndtr(a * ndtri(np.clip(p, 1e-4, 1 - 1e-4)) + math.sqrt(1 - a * a) * e)
            x = np.empty(zi.size)
            for z in np.unique(zi):
                m = zi == z
                x[m] = self.zone_curve[z].ppf(uu[m])
            return x, nat.cdf(x)
        if self.method == "rwi_rank":
            p = self.zone_pct[zi]
            p = np.where(np.isnan(p), np.nanmean(self.zone_pct), p)
            z = a * ndtri(np.clip(p, 1e-4, 1 - 1e-4)) + math.sqrt(1 - a * a) * e
            u = ndtr(z)
            return nat.ppf(u), u
        c = curve(self.sector, self.state if self.method == "state_curve" else None)
        x = c.ppf(ndtr(e))
        return x, nat.cdf(x)

    def class_shares(self, u: np.ndarray, weights: np.ndarray | None = None) -> dict[str, float]:
        w = np.ones_like(u) if weights is None else weights
        out = {}
        for k, lo, hi in zip(CLASS_KEYS, CLASS_EDGES[:-1], CLASS_EDGES[1:]):
            out[k] = float(w[(u >= lo) & (u < hi + (1e-12 if hi == 1 else 0))].sum() / max(w.sum(), 1e-12))
        return out


@lru_cache(maxsize=4)
def national(rural_share: float | None = None) -> NationalCurve:
    return NationalCurve(rural_share)


STATE_ALIASES = {"orissa": "Odisha", "pondicherry": "Puducherry", "nct of delhi": "Delhi", "national capital territory of delhi": "Delhi",
                 "uttaranchal": "Uttarakhand", "chhatisgarh": "Chhattisgarh", "tamilnadu": "Tamil Nadu"}


def normalise_state(name: str | None) -> str | None:
    """Map geoBoundaries / Nominatim state names onto the HCES table names (case and spelling variants)."""
    if not name:
        return None
    n = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()  # geoBoundaries: "Bihār" -> "Bihar"
    n = " ".join(n.replace("&", "and").split())
    if n.lower() in STATE_ALIASES:
        return STATE_ALIASES[n.lower()]
    for known in hces()["state_deciles"]["rural"]:
        if known.lower() == n.lower():
            return known
    return n


def build_context(zone_lats, zone_lngs, *, state: str | None, sector: str | None) -> IncomeContext:
    state = normalise_state(state)
    sector = sector if sector in ("rural", "urban") else "urban"
    tl = tile_lookup(zone_lats, zone_lngs)
    pct = tl["pct"] if tl else np.full(np.atleast_1d(zone_lats).shape, np.nan)
    meta = tl["meta"] if tl else None
    h = hces()
    hces_prov = {"source": "hces_2023_24", "name": "MoSPI HCES 2023-24 (NSS Report 592)", "kind": "official_aggregate_estimate",
                 "url": h["url"], "license": "Government of India publication", "source_updated_at": "2023-24 survey, published Dec 2024",
                 "detail": "Rupee level of monthly per-person consumption (fractiles, state deciles, budget shares)"}
    provs = [hces_prov]
    a = BETWEEN_TILE_LOADING[0]
    if tl and "pct_ss" in tl and tl["hit"].mean() >= 0.5:
        hit = tl["hit"]
        # zones off any tile take the catchment's most common state/sector and the middle rank
        states = [s_ for s_ in tl["state"] if s_]
        st0 = max(set(states), key=states.count) if states else state
        secs = list(tl["sector"][hit])
        sec0 = max(set(secs), key=secs.count) if secs else sector
        zcurves, keys = [], set()
        for i in range(pct.size):
            st_i = tl["state"][i] or st0
            se_i = str(tl["sector"][i]) if hit[i] else sec0
            c = curve(se_i, st_i if st_i in h["state_deciles"][se_i] else None)
            zcurves.append(c)
            keys.add(c.key)
        rm = (meta or {}).get("rwi", {})
        um = (meta or {}).get("urban_rule", {})
        provs.append({"source": "meta_rwi", "name": "Meta Relative Wealth Index (2.4 km tiles) x WorldPop 2020", "kind": "derived",
                      "url": rm.get("url") or "https://data.humdata.org/dataset/relative-wealth-index", "license": "CC BY-NC 4.0 (HDX dataset page)",
                      "source_updated_at": rm.get("source_updated"),
                      "detail": f"{int(hit.sum())}/{pct.size} zones on a wealth tile; tiles ranked within their state x rural/urban by population. "
                                f"Urban = WorldPop density >= {um.get('density_threshold_per_km2', '?')}/km2 (35% of India urban, UN WUP)"})
        provs.append({"source": "geoboundaries", "name": "geoBoundaries India ADM1 (state boundaries)", "kind": "observed",
                      "url": "https://www.geoboundaries.org/", "license": "CC BY 4.0", "detail": "Which state each wealth tile is in"})
        zone_p = np.where(np.isnan(tl["pct_ss"]), 0.5, tl["pct_ss"])
        return IncomeContext("rwi_state_rank", zone_p, st0, sec0, a, provs, ", ".join(sorted(keys)),
                             max(c.fit_error for c in zcurves), zcurves)
    if np.isfinite(pct).mean() >= 0.5:
        rm = (meta or {}).get("rwi", {})
        provs.append({"source": "meta_rwi", "name": "Meta Relative Wealth Index (2.4 km tiles) x WorldPop 2020", "kind": "derived",
                      "url": rm.get("url") or "https://data.humdata.org/dataset/relative-wealth-index", "license": "CC BY-NC 4.0 (HDX dataset page)",
                      "source_updated_at": rm.get("source_updated"), "detail": f"{int(np.isfinite(pct).sum())}/{pct.size} zones on a wealth tile; "
                      "tile ranks are population-weighted national percentiles"})
        c = curve("urban")
        return IncomeContext("rwi_rank", pct, state, sector, a, provs, "India/rural+urban", max(c.fit_error, curve("rural").fit_error))
    method = "state_curve" if state and state in h["state_deciles"][sector] else "national_sector_curve"
    c = curve(sector, state if method == "state_curve" else None)
    return IncomeContext(method, pct, state, sector, a, provs, c.key, c.fit_error)
