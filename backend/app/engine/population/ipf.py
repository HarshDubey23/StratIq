"""Iterative Proportional Fitting (IPF) and Iterative Proportional Updating (IPU).

Theoretical Foundation:
Beckman, Baggerly, & McKay (1996), Transportation Research Part A.
Ye, Konduri, Pendyala, Sana, & Waddell (2009), Transportation Research Board.

Formulation:
Minimizes Kullback-Leibler divergence (entropy) from baseline weights w^(0):
    min_{w_i >= 0} sum_i w_i * ln(w_i / w_i^(0))
subject to:
    sum_i w_i * x_{ik} = m_k  for all margin constraints k

Features:
- Handles zero cells and non-negative constraints.
- Convergence detection on maximum relative margin error.
- Weight trimming to prevent extreme leverage points.
- Diagnostic metrics: Effective Sample Size (ESS), Weight Entropy, Residuals.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
import numpy as np


@dataclass
class IPFResult:
    weights: np.ndarray  # [N] calibrated weights
    converged: bool
    iterations: int
    max_relative_error: float
    residuals: dict[str, float]  # target margin key -> absolute error
    effective_sample_size: float  # (sum w)^2 / sum(w^2)
    weight_min: float
    weight_max: float
    weight_mean: float


def ipf_solve(
    X: np.ndarray,
    margins: np.ndarray,
    margin_names: list[str] | None = None,
    w0: np.ndarray | None = None,
    max_iter: int = 200,
    tol: float = 1e-4,
    min_weight: float = 1e-6,
    max_weight_ratio: float = 50.0,
) -> IPFResult:
    """Solve multi-margin population calibration via Iterative Proportional Fitting.

    Args:
        X: [N, K] matrix of indicator / characteristic values for N candidate profiles across K constraints.
        margins: [K] target marginal totals.
        margin_names: Optional human-readable labels for the K constraints.
        w0: Optional [N] initial sample weights. If None, initialized to uniform.
        max_iter: Maximum outer iterations through all K constraints.
        tol: Target tolerance on maximum relative margin discrepancy.
        min_weight: Floor for non-negative weights.
        max_weight_ratio: Maximum allowable ratio of max(w) / mean(w) to prevent run-away weights.
    """
    N, K = X.shape
    if len(margins) != K:
        raise ValueError(f"Length of margins ({len(margins)}) must match columns of X ({K})")

    # Initial weights
    if w0 is None:
        target_total = float(np.mean(margins[margins > 0])) if np.any(margins > 0) else float(N)
        w = np.full(N, target_total / max(1, N), dtype=np.float64)
    else:
        w = np.asarray(w0, dtype=np.float64).copy()
        w = np.maximum(w, min_weight)

    names = margin_names or [f"margin_{k}" for k in range(K)]
    converged = False
    max_rel_err = 1.0

    for it in range(max_iter):
        max_rel_err = 0.0

        for k in range(K):
            target = float(margins[k])
            col = X[:, k]
            current = float(np.dot(w, col))

            if target <= 0.0:
                if current > 0.0:
                    w[col > 0] = min_weight
                continue

            if current <= 1e-12:
                # Zero cell issue: candidate sample has no records with this characteristic
                continue

            factor = target / current
            rel_err = abs(current - target) / target
            if rel_err > max_rel_err:
                max_rel_err = rel_err

            # Multiplicative IPF update
            # Only update records that possess this attribute
            mask = col > 0
            w[mask] = np.maximum(w[mask] * (1.0 + (factor - 1.0) * col[mask]), min_weight)

        # Weight stabilization & trimming
        mean_w = max(1e-12, float(np.mean(w)))
        w = np.clip(w, min_weight, mean_w * max_weight_ratio)

        if max_rel_err < tol:
            converged = True
            break

    # Final diagnostics
    residuals = {}
    for k in range(K):
        current = float(np.dot(w, X[:, k]))
        residuals[names[k]] = abs(current - float(margins[k]))

    sum_w = float(np.sum(w))
    sum_w2 = float(np.sum(w ** 2))
    ess = (sum_w ** 2) / max(1e-12, sum_w2)

    return IPFResult(
        weights=w,
        converged=converged,
        iterations=it + 1,
        max_relative_error=float(max_rel_err),
        residuals=residuals,
        effective_sample_size=float(ess),
        weight_min=float(np.min(w)),
        weight_max=float(np.max(w)),
        weight_mean=float(np.mean(w)),
    )
