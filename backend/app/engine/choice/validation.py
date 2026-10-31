"""Holdout Cross-Validation & Reliability Calibration for Discrete Choice Models.

Standards implemented:
- Out-of-sample Log-Likelihood and McFadden Pseudo-R2
- Multi-class Brier Score (mean squared error of predicted probabilities vs observed choice)
- Expected Calibration Error (ECE) and empirical calibration curves
- Top-1 Choice Accuracy
"""
from __future__ import annotations

import numpy as np
from .conditional_logit import ChoiceDataset, ConditionalLogitEstimator


def calculate_calibration_curve(
    predicted_probs: np.ndarray,
    actual_outcomes: np.ndarray,
    n_bins: int = 10,
) -> dict:
    """Calculates calibration reliability curve and Expected Calibration Error (ECE).
    
    Args:
        predicted_probs: 1D array of predicted probabilities across all alternative-occasion pairs.
        actual_outcomes: 1D binary array of observed choice outcomes (0 or 1).
        n_bins: Number of probability bins (default 10).
    
    Returns:
        dict containing bin edges, bin midpoints, mean predicted prob, observed frequency,
        sample count per bin, and overall ECE.
    """
    if n_bins <= 0:
        raise ValueError(f"n_bins must be a positive integer, got {n_bins}")
    
    p_arr = np.asarray(predicted_probs, dtype=float).ravel()
    y_arr = np.asarray(actual_outcomes, dtype=float).ravel()
    if len(p_arr) != len(y_arr):
        raise ValueError(f"Length mismatch: predicted_probs ({len(p_arr)}) vs actual_outcomes ({len(y_arr)})")

    bins = np.linspace(0.0, 1.0, n_bins + 1)
    bin_centers = (bins[:-1] + bins[1:]) / 2.0

    if len(p_arr) == 0:
        return {
            "bin_edges": bins.tolist(),
            "bin_centers": bin_centers.tolist(),
            "predicted_means": [0.0] * n_bins,
            "observed_frequencies": [0.0] * n_bins,
            "counts": [0] * n_bins,
            "ece": 0.0,
        }

    bin_indices = np.digitize(p_arr, bins) - 1
    # Clip in case prob == 1.0
    bin_indices = np.clip(bin_indices, 0, n_bins - 1)

    bin_pred = []
    bin_obs = []
    bin_counts = []
    total_samples = len(p_arr)
    ece = 0.0

    for i in range(n_bins):
        mask = bin_indices == i
        count = int(np.sum(mask))
        bin_counts.append(count)
        if count > 0:
            mean_pred = float(np.mean(p_arr[mask]))
            mean_obs = float(np.mean(y_arr[mask]))
            bin_pred.append(mean_pred)
            bin_obs.append(mean_obs)
            ece += (count / total_samples) * abs(mean_obs - mean_pred)
        else:
            bin_pred.append(float(bin_centers[i]))
            bin_obs.append(0.0)

    return {
        "bin_edges": bins.tolist(),
        "bin_centers": bin_centers.tolist(),
        "predicted_means": bin_pred,
        "observed_frequencies": bin_obs,
        "counts": bin_counts,
        "ece": float(ece),
    }


def evaluate_holdout(
    estimator: ConditionalLogitEstimator,
    test_dataset: ChoiceDataset,
    n_bins: int = 10,
) -> dict:
    """Evaluates an estimated choice model on out-of-sample holdout choice data.
    
    Returns:
        Dictionary with test_log_likelihood, test_null_log_likelihood,
        test_mcfadden_r2, log_loss, brier_score, top1_accuracy, and calibration curve.
    """
    N = len(test_dataset.y)
    test_ll = 0.0
    test_null_ll = 0.0
    correct_top1 = 0
    brier_sum = 0.0

    all_preds = []
    all_acts = []

    for x_n, y_n in zip(test_dataset.X, test_dataset.y):
        p_n = estimator.predict_proba(x_n)
        J_n = len(p_n)

        # Log likelihood
        p_chosen = max(1e-15, float(p_n[y_n]))
        test_ll += np.log(p_chosen)
        test_null_ll += -np.log(J_n)

        # Top-1 accuracy
        if np.argmax(p_n) == y_n:
            correct_top1 += 1

        # Brier score: sum_{j=1}^J (P_{nj} - y_{nj})^2
        y_vec = np.zeros(J_n)
        y_vec[y_n] = 1.0
        brier_sum += np.sum((p_n - y_vec) ** 2)

        # Accumulate for calibration
        all_preds.extend(p_n.tolist())
        all_acts.extend(y_vec.tolist())

    mcfadden_r2 = 1.0 - (test_ll / test_null_ll) if test_null_ll != 0 else 0.0
    log_loss = -test_ll / N
    brier_score = brier_sum / N
    accuracy = correct_top1 / N

    calib = calculate_calibration_curve(
        np.array(all_preds),
        np.array(all_acts),
        n_bins=n_bins,
    )

    return {
        "n_test_observations": N,
        "test_log_likelihood": float(test_ll),
        "test_null_log_likelihood": float(test_null_ll),
        "test_mcfadden_r2": float(mcfadden_r2),
        "log_loss": float(log_loss),
        "brier_score": float(brier_score),
        "top1_accuracy": float(accuracy),
        "calibration": calib,
    }
