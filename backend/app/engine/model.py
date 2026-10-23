"""StrataIQ customer-choice and demand model (numpy, vectorised).

See ``docs/MODEL.md`` for the full specification. Summary, per demand zone z,
synthetic segment s and alternative j (j=0 is the user's business):

    N_zs   = W_z * participation * share_s               in-market people / month
    F_sj   = 1 - Phi( (ln p_j - ln(m_s * p_ref)) / sigma )  affordability
    V_zsj  = bq*(q_j - 0.5) - bp*k_s*ln(p_j / p_ref) - (lambda / t_s) * d_zj + ln(a_j)
    A_zsj  = F_sj * exp(V_zsj) * 1[d_zj <= max_km * t_s]
    P_zsj  = A_zsj / (exp(U0) + sum_k A_zsk)                 multinomial logit with outside option
    D_j    = sum_zs N_zs * P_zsj * frequency                 units / month
    Q_0    = min(D_0, K)                                     capacity-constrained

Everything is computed for a batch of parameter draws at once so the same
code path serves the deterministic run (1 draw) and Monte Carlo.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.special import ndtr

from ..categories.archetypes import Archetype
from .geo import distance_matrix_km

MODEL_VERSION = "siq-choice-1.2"

UNCERTAIN_PARAMS = (
    "participation", "frequency", "beta_price", "beta_quality", "distance_decay",
    "awareness_base", "competitor_quality", "competitor_price_ratio", "wtp_sigma",
    "outside_utility",
)


@dataclass
class Zone:
    lat: float
    lng: float
    population: float
    activity: float = 0.0  # count of activity points mapped to the zone


@dataclass
class Competitor:
    id: str
    name: str
    lat: float
    lng: float
    price: float | None = None  # known price (observed or user-entered)
    quality: float | None = None  # 0-1, user-entered if known
    source: str = "osm"


@dataclass
class BusinessInputs:
    lat: float
    lng: float
    price: float
    quality: float = 0.55
    marketing_spend: float = 0.0
    reference_price: float | None = None  # typical local price, if known
    variable_cost_per_unit: float | None = None
    capacity: dict = field(default_factory=dict)
    rent: float = 0.0
    payroll: float = 0.0
    utilities: float = 0.0
    other_fixed: float = 0.0
    startup_cost: float = 0.0


@dataclass
class ResolvedParams:
    """Parameter values (point estimate) plus their [low, high] ranges."""

    values: dict[str, float]
    ranges: dict[str, tuple[float, float]]
    status: dict[str, str]

    @classmethod
    def from_archetype(cls, arch: Archetype, overrides: dict | None = None) -> "ResolvedParams":
        values, ranges, status = {}, {}, {}
        for k, p in arch.params.items():
            values[k], ranges[k], status[k] = p.value, (p.low, p.high), "assumption"
        values.setdefault("activity_equivalent", 120.0)
        ranges.setdefault("activity_equivalent", (60.0, 200.0))
        status.setdefault("activity_equivalent", "assumption")
        for k, v in (overrides or {}).items():
            if k not in values or v is None:
                continue
            v = float(v)
            values[k] = v
            lo, hi = sorted((v * 0.85, v * 1.15))
            ranges[k] = (lo, hi) if k != "frequency" or v != 1.0 else (v, v)
            status[k] = "user"
        return cls(values, ranges, status)

    def draws(self, n: int, rng: np.random.Generator | None) -> dict[str, np.ndarray]:
        """Point estimate when ``rng`` is None, else triangular draws in [low, high] around the value."""
        out: dict[str, np.ndarray] = {}
        for k, v in self.values.items():
            lo, hi = self.ranges.get(k, (v, v))
            if rng is None or k not in UNCERTAIN_PARAMS or hi <= lo:
                out[k] = np.full(n, v, dtype=float)
            else:
                mode = min(max(v, lo), hi)
                out[k] = rng.triangular(lo, mode, hi, size=n)
        return out


@dataclass
class MarketArrays:
    dist_km: np.ndarray  # [Z, J] estimated road km
    weight: np.ndarray  # [Z] resident-equivalents
    prices: np.ndarray  # [J] point prices (competitor unknown -> NaN)
    price_known: np.ndarray  # [J] bool
    quality: np.ndarray  # [J] (unknown -> NaN)
    quality_known: np.ndarray  # [J] bool
    ref_price: float
    ref_price_status: str


def build_arrays(arch: Archetype, zones: list[Zone], comps: list[Competitor], biz: BusinessInputs,
                 params: ResolvedParams, travel_km: np.ndarray | None = None) -> MarketArrays:
    if not zones:
        raise ValueError("No demand zones: population data is required to simulate demand.")
    if biz.price <= 0:
        raise ValueError("Price must be positive.")
    lats = [biz.lat] + [c.lat for c in comps]
    lngs = [biz.lng] + [c.lng for c in comps]
    if travel_km is None:
        d = distance_matrix_km([z.lat for z in zones], [z.lng for z in zones], lats, lngs)
        d = d * params.values["circuity"]
    else:
        d = np.asarray(travel_km, float)
    # Zone centroids are ~150-250 m from any point inside them; floor avoids zero-distance artifacts.
    d = np.maximum(d, 0.15)
    pop = np.array([max(0.0, z.population) for z in zones], float)
    act = np.array([max(0.0, z.activity) for z in zones], float)
    if arch.demand_base == "residents_and_activity":
        weight = pop + act * params.values["activity_equivalent"]
    else:
        weight = pop
    known_prices = [c.price for c in comps if c.price and c.price > 0]
    if biz.reference_price and biz.reference_price > 0:
        ref, ref_status = float(biz.reference_price), "user"
    elif known_prices:
        ref, ref_status = float(np.median(known_prices)), "derived_from_competitor_prices"
    else:
        ref, ref_status = float(biz.price), "assumption_equals_own_price"
    prices = np.array([biz.price] + [c.price if c.price and c.price > 0 else np.nan for c in comps], float)
    quality = np.array([biz.quality] + [c.quality if c.quality is not None else np.nan for c in comps], float)
    return MarketArrays(
        dist_km=d, weight=weight, prices=prices, price_known=~np.isnan(prices),
        quality=quality, quality_known=~np.isnan(quality), ref_price=ref, ref_price_status=ref_status,
    )


def awareness(spend: float, base: np.ndarray, half_sat: np.ndarray) -> np.ndarray:
    """Share of in-market people who know the new business exists (saturating in spend)."""
    spend = max(0.0, float(spend))
    return base + (1 - base) * (1 - np.exp(-np.log(2) * spend / np.maximum(half_sat, 1.0)))


def run_choice(arch: Archetype, m: MarketArrays, biz: BusinessInputs, p: dict[str, np.ndarray],
               keep_detail: bool = False) -> dict:
    """Evaluate the choice model for D parameter draws. Returns arrays with leading draw axis."""
    D = len(p["participation"])
    Z, J = m.dist_km.shape
    seg_share = np.array([s.share for s in arch.segments])  # [S]
    seg_wtp = np.array([s.wtp_multiplier for s in arch.segments])
    seg_ps = np.array([s.price_sensitivity for s in arch.segments])
    seg_dt = np.array([s.distance_tolerance for s in arch.segments])

    # Prices per draw: unknown competitor prices = ref * competitor_price_ratio draw.
    prices = np.broadcast_to(m.prices, (D, J)).copy()
    unk = ~m.price_known
    prices[:, unk] = (m.ref_price * p["competitor_price_ratio"])[:, None]
    quality = np.broadcast_to(m.quality, (D, J)).copy()
    quality[:, ~m.quality_known] = p["competitor_quality"][:, None]

    aw = np.ones((D, J))
    aw[:, 0] = awareness(biz.marketing_spend, p["awareness_base"], p["marketing_half_saturation"])

    # Affordability F[D,S,J]
    sigma = p["wtp_sigma"][:, None, None]
    median_wtp = (m.ref_price * seg_wtp)[None, :, None]
    afford = 1.0 - ndtr((np.log(prices[:, None, :]) - np.log(median_wtp)) / sigma)

    # Utility V[D,Z,S,J]
    v_q = p["beta_quality"][:, None] * (quality - 0.5)  # [D,J]
    v_p = -(p["beta_price"][:, None, None] * seg_ps[None, :, None]) * np.log(prices[:, None, :] / m.ref_price)  # [D,S,J]
    decay = p["distance_decay"][:, None, None, None] / seg_dt[None, None, :, None]  # [D,1,S,1]
    v_d = -decay * m.dist_km[None, :, None, :]  # [D,Z,S,J]
    V = v_q[:, None, None, :] + v_p[:, None, :, :] + v_d + np.log(aw)[:, None, None, :]
    reach = m.dist_km[None, :, None, :] <= (p["max_km"][:, None, None, None] * seg_dt[None, None, :, None])
    A = afford[:, None, :, :] * np.exp(V) * reach
    denom = np.exp(p["outside_utility"])[:, None, None] + A.sum(axis=3)  # [D,Z,S]
    P = A / denom[..., None]  # [D,Z,S,J]

    N = m.weight[None, :, None] * p["participation"][:, None, None] * seg_share[None, None, :]  # [D,Z,S]
    units_by_alt = (N[..., None] * P).sum(axis=(1, 2)) * p["frequency"][:, None]  # [D,J]
    in_market = N.sum(axis=(1, 2)) * p["frequency"]  # [D]

    out = {
        "units_by_alt": units_by_alt,
        "in_market_units": in_market,
        "prices": prices,
        "afford_user_by_segment": afford[:, :, 0],  # [D,S]
        "awareness_user": aw[:, 0],
    }
    if keep_detail:
        out["P"] = P
        out["N"] = N
        out["reach_user"] = reach[..., 0]
    return out
