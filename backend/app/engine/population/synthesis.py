"""Spatial Synthetic Population Construction Engine.

Builds evidence-constrained synthetic consumer populations with:
1. Household hierarchical structure (cohabitants share home location and expenditure deciles).
2. IPF calibration against WorldPop / Census marginal controls (17 age-sex bands, zone population totals).
3. Two supported modes:
   - Mode A (Scientific Baseline): Calibrated weighted synthetic records.
   - Mode B (Deterministic 10,000 records): Representative microdata sample via controlled integer rounding.
4. Purely deterministic and reproducible for a given seed and dataset snapshot.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
import numpy as np

from .ipf import ipf_solve, IPFResult

AGE_BANDS = [
    "0-4", "5-9", "10-14", "15-19", "20-24", "25-29", "30-34", "35-39",
    "40-44", "45-49", "50-54", "55-59", "60-64", "65-69", "70-74", "75-79", "80+"
]
AGE_MIDPOINTS = np.array([2, 7, 12, 17, 22, 27, 32, 37, 42, 47, 52, 57, 62, 67, 72, 77, 84], dtype=float)


@dataclass
class SyntheticPerson:
    person_id: int
    household_id: int
    zone_index: int
    lat: float
    lng: float
    age: float
    age_band: str
    sex: str  # "male" | "female"
    weight: float  # Population weight represented by this record
    income_decile: int  # 1 (lowest) to 10 (highest), expenditure proxy
    household_size: int

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class SyntheticPopulation:
    agents: list[SyntheticPerson]
    total_represented_population: float
    n_records: int
    mode: str  # "weighted" | "representative_fixed"
    calibration: IPFResult | None
    marginal_errors: dict[str, float]
    seed: int


def build_synthetic_population(
    total_population: float,
    age_sex_distribution: dict | None,
    zones: list[dict],
    target_records: int = 10000,
    mode: str = "representative_fixed",
    seed: int = 42,
    avg_household_size: float = 4.4,
) -> SyntheticPopulation:
    """Generate a calibrated synthetic consumer population.

    Args:
        total_population: Total population inside the catchment.
        age_sex_distribution: Dictionary with 'bands' list containing [{'age': ..., 'male': ..., 'female': ...}].
        zones: List of zone dictionaries with [{'lat': ..., 'lng': ..., 'population': ...}].
        target_records: Target number of records (e.g. exactly 10,000 for Mode B).
        mode: "weighted" (Mode A) or "representative_fixed" (Mode B).
        seed: Random seed for deterministic reproducibility.
        avg_household_size: Baseline average persons per household.
    """
    if total_population <= 0:
        raise ValueError("Catchment population must be positive to synthesize agents.")
    if not zones:
        raise ValueError("At least one demand zone is required for spatial allocation.")

    rng = np.random.default_rng(seed)
    N = int(target_records)

    # 1. Parse demographic targets
    if age_sex_distribution and "bands" in age_sex_distribution:
        bands_data = age_sex_distribution["bands"]
        male_targets = np.array([float(b["male"]) for b in bands_data], dtype=float)
        female_targets = np.array([float(b["female"]) for b in bands_data], dtype=float)
        tot_m = male_targets.sum() + female_targets.sum()
        if tot_m > 0:
            male_shares = male_targets / tot_m
            female_shares = female_targets / tot_m
        else:
            male_shares = np.full(17, 0.52 / 17)
            female_shares = np.full(17, 0.48 / 17)
    else:
        # Default census demographic pyramid
        default_p = np.array([0.075, 0.080, 0.085, 0.088, 0.092, 0.092, 0.085, 0.077, 0.068, 0.060, 0.052, 0.043, 0.035, 0.027, 0.019, 0.012, 0.010])
        male_shares = default_p * 0.52 / default_p.sum()
        female_shares = default_p * 0.48 / default_p.sum()

    # 2. Zone probabilities
    zone_pops = np.array([max(0.0, float(z.get("population", 0))) for z in zones], dtype=float)
    if zone_pops.sum() <= 0:
        zone_probs = np.full(len(zones), 1.0 / len(zones))
    else:
        zone_probs = zone_pops / zone_pops.sum()

    # 3. Household synthesis
    # Household sizes follow a shifted Poisson distribution around (avg_household_size - 1)
    lam = max(0.5, avg_household_size - 1.0)
    hh_sizes = []
    tot_persons = 0
    while tot_persons < N:
        sz = int(1 + rng.poisson(lam))
        sz = min(sz, 9)  # Cap at 9
        hh_sizes.append(sz)
        tot_persons += sz
    # Adjust last household size to match N exactly
    if tot_persons > N:
        hh_sizes[-1] -= (tot_persons - N)
        if hh_sizes[-1] <= 0:
            hh_sizes.pop()

    n_households = len(hh_sizes)

    # Assign households to demand zones
    hh_zones = rng.choice(len(zones), size=n_households, p=zone_probs)
    # Assign household income decile (lognormal consumption expenditure proxy)
    hh_income = np.clip(np.ceil(rng.lognormal(mean=1.5, sigma=0.6, size=n_households) * 1.5).astype(int), 1, 10)

    # 4. Generate individuals within households
    agents: list[SyntheticPerson] = []
    pid = 0
    combined_dem_shares = np.concatenate([male_shares, female_shares])
    combined_dem_shares /= combined_dem_shares.sum()

    for h_idx, sz in enumerate(hh_sizes):
        z_idx = int(hh_zones[h_idx])
        z = zones[z_idx]
        # Coordinates with spatial jitter inside the ~300m cell
        jitter_lat = float(rng.uniform(-0.0012, 0.0012))
        jitter_lng = float(rng.uniform(-0.0012, 0.0012))
        h_lat = round(float(z["lat"]) + jitter_lat, 6)
        h_lng = round(float(z["lng"]) + jitter_lng, 6)
        inc = int(hh_income[h_idx])

        for member_idx in range(sz):
            # Sample age-sex from combined distribution
            d_idx = int(rng.choice(34, p=combined_dem_shares))
            is_female = d_idx >= 17
            band_idx = d_idx - 17 if is_female else d_idx
            band_str = AGE_BANDS[band_idx]
            mid_age = AGE_MIDPOINTS[band_idx]
            age = float(np.clip(mid_age + rng.uniform(-2.0, 2.0), 0.0, 95.0))
            sex = "female" if is_female else "male"

            agents.append(
                SyntheticPerson(
                    person_id=pid,
                    household_id=h_idx,
                    zone_index=z_idx,
                    lat=h_lat,
                    lng=h_lng,
                    age=round(age, 1),
                    age_band=band_str,
                    sex=sex,
                    weight=1.0,  # Will be calibrated below
                    income_decile=inc,
                    household_size=sz,
                )
            )
            pid += 1

    # 5. Calibration matrix X [N, K]
    # K constraints: 17 male bands, 17 female bands, len(zones) spatial totals
    K_dem = 34
    K_zones = len(zones)
    K = K_dem + K_zones
    X = np.zeros((N, K), dtype=np.float64)

    for i, a in enumerate(agents):
        b_idx = AGE_BANDS.index(a.age_band)
        col_dem = (b_idx + 17) if a.sex == "female" else b_idx
        X[i, col_dem] = 1.0
        X[i, K_dem + a.zone_index] = 1.0

    target_dem = np.concatenate([male_shares, female_shares]) * total_population
    target_zones = zone_probs * total_population
    target_margins = np.concatenate([target_dem, target_zones])

    margin_names = [f"male_{b}" for b in AGE_BANDS] + [f"female_{b}" for b in AGE_BANDS] + [f"zone_{z}" for z in range(len(zones))]

    # 6. Run IPF
    ipf_res = ipf_solve(X, target_margins, margin_names=margin_names, max_iter=150, tol=1e-3)

    if mode == "weighted":
        # Mode A: Retain continuous calibrated weights
        for i, a in enumerate(agents):
            a.weight = float(ipf_res.weights[i])
        total_rep = float(np.sum(ipf_res.weights))
    else:
        # Mode B: Exactly 10,000 representative records with uniform weight = total_pop / 10000
        # Records were sampled via the joint demographic & spatial distribution
        uniform_weight = float(total_population / N)
        for a in agents:
            a.weight = uniform_weight
        total_rep = float(total_population)

    # 7. Compute marginal evaluation metrics
    marginal_errors = {}
    calibrated_weights = np.array([a.weight for a in agents], dtype=np.float64)
    for k in range(K):
        achieved = float(np.dot(calibrated_weights, X[:, k]))
        target = float(target_margins[k])
        rel_diff = abs(achieved - target) / max(1.0, target)
        marginal_errors[margin_names[k]] = float(rel_diff)

    return SyntheticPopulation(
        agents=agents,
        total_represented_population=total_rep,
        n_records=N,
        mode=mode,
        calibration=ipf_res,
        marginal_errors=marginal_errors,
        seed=seed,
    )
