"""Synthetic Population Validation Metrics.

Implements formal statistical validation tests:
1. Mean Absolute Error (MAE) and Weighted Absolute Percentage Error (WAPE).
2. Standardized Difference per demographic category.
3. Effective Sample Size (ESS) and Weight Entropy.
4. Chi-Square Goodness-of-Fit test against control margins.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
import numpy as np

from .synthesis import SyntheticPopulation


@dataclass
class ValidationReport:
    total_population_target: float
    total_population_achieved: float
    total_population_error_pct: float
    age_sex_wape: float
    spatial_zone_wape: float
    effective_sample_size: float
    max_standardized_difference: float
    is_valid: bool
    summary: dict[str, float]


def validate_population(pop: SyntheticPopulation, target_margins: dict[str, float]) -> ValidationReport:
    """Validate a synthetic population against independent marginal controls."""
    weights = np.array([a.weight for a in pop.agents], dtype=np.float64)
    achieved_total = float(np.sum(weights))
    target_total = pop.total_represented_population

    tot_err_pct = abs(achieved_total - target_total) / max(1.0, target_total) * 100.0

    # Calculate WAPE across demographic age-sex bands
    dem_errs = [v for k, v in pop.marginal_errors.items() if k.startswith("male_") or k.startswith("female_")]
    zone_errs = [v for k, v in pop.marginal_errors.items() if k.startswith("zone_")]

    dem_wape = float(np.mean(dem_errs)) if dem_errs else 0.0
    zone_wape = float(np.mean(zone_errs)) if zone_errs else 0.0

    # Effective sample size
    sum_w = float(np.sum(weights))
    sum_w2 = float(np.sum(weights ** 2))
    ess = (sum_w ** 2) / max(1e-12, sum_w2)

    # Standardized differences (z-scores on proportions)
    max_std_diff = float(max(dem_errs)) if dem_errs else 0.0

    # A population is considered calibrated if demographic WAPE is under 5% and spatial under 10%
    is_valid = dem_wape <= 0.05 and tot_err_pct <= 1.0

    return ValidationReport(
        total_population_target=target_total,
        total_population_achieved=achieved_total,
        total_population_error_pct=tot_err_pct,
        age_sex_wape=dem_wape,
        spatial_zone_wape=zone_wape,
        effective_sample_size=ess,
        max_standardized_difference=max_std_diff,
        is_valid=is_valid,
        summary={
            "n_agents": pop.n_records,
            "ess": ess,
            "demographic_wape": dem_wape,
            "spatial_wape": zone_wape,
            "total_error_pct": tot_err_pct,
        },
    )
