"""Unit tests and parameter recovery validation for McFadden Conditional Logit Discrete Choice Engine.

Tests:
1. Synthetic choice data generation and parameter recovery within confidence intervals.
2. Analytical gradient and Fisher Information-based standard error consistency.
3. Holdout cross-validation: out-of-sample log-likelihood, McFadden pseudo-R², Brier score, and accuracy.
4. Expected Calibration Error (ECE) and reliability curve computation.
5. Invariant checking, dimension mismatches, and boundary edge cases.
"""
from __future__ import annotations

import numpy as np
import pytest
from scipy.special import logsumexp

from app.engine.choice.conditional_logit import (
    ChoiceDataset,
    ChoiceEstimationResult,
    ConditionalLogitEstimator,
)
from app.engine.choice.validation import calculate_calibration_curve, evaluate_holdout


def generate_synthetic_choice_data(
    n_samples: int,
    true_beta: np.ndarray,
    feature_names: list[str],
    n_alternatives: int = 4,
    seed: int = 42,
) -> ChoiceDataset:
    """Generates synthetic multinomial choices from a true McFadden random utility model:
        U_{nj} = X_{nj} * beta + epsilon_{nj},  epsilon_{nj} ~ Gumbel(0, 1)
    """
    rng = np.random.default_rng(seed)
    K = len(true_beta)
    X_list: list[np.ndarray] = []
    y_list: list[int] = []

    for _ in range(n_samples):
        # Varying choice set size between 3 and n_alternatives
        J = rng.integers(3, n_alternatives + 1)
        # Generate varied realistic features: e.g. normalized price, quality, distance
        x_n = np.zeros((J, K))
        for k in range(K):
            if k == 0:
                x_n[:, k] = rng.normal(0.0, 1.0, size=J)   # price / feature 0
            elif k == 1:
                x_n[:, k] = rng.uniform(0.1, 0.9, size=J)   # quality / feature 1
            else:
                x_n[:, k] = rng.exponential(1.5, size=J)    # distance / other feature


        v = x_n @ true_beta
        p = np.exp(v - logsumexp(v))
        # Draw choice according to probabilities
        choice = rng.choice(J, p=p)

        X_list.append(x_n)
        y_list.append(choice)

    return ChoiceDataset(X=X_list, y=np.array(y_list, dtype=int), feature_names=feature_names)


def test_choice_dataset_validation():
    """Verify input validation on ChoiceDataset."""
    features = ["price", "quality", "dist"]
    # Empty dataset
    with pytest.raises(ValueError, match="cannot be empty"):
        ChoiceDataset(X=[], y=np.array([]), feature_names=features)

    # Length mismatch
    with pytest.raises(ValueError, match="Mismatch"):
        ChoiceDataset(X=[np.ones((3, 3))], y=np.array([0, 1]), feature_names=features)

    # Dimension mismatch in X
    with pytest.raises(ValueError, match="expected"):
        ChoiceDataset(X=[np.ones((3, 2))], y=np.array([0]), feature_names=features)

    # Choice index out of bounds
    with pytest.raises(ValueError, match="out of bounds"):
        ChoiceDataset(X=[np.ones((3, 3))], y=np.array([5]), feature_names=features)

    # Duplicate feature names
    with pytest.raises(ValueError, match="Duplicate feature names"):
        ChoiceDataset(X=[np.ones((3, 2))], y=np.array([0]), feature_names=["f1", "f1"])

    # Choice set size < 2
    with pytest.raises(ValueError, match="choice set size 1 < 2"):
        ChoiceDataset(X=[np.ones((1, 3))], y=np.array([0]), feature_names=features)


def test_parameter_recovery_and_confidence_intervals():
    """Verify MLE converges and recovers true utility coefficients within 99% confidence intervals.
    
    Using N=3500 observations, parameter recovery guarantees:
        | beta_hat_k - beta_true_k | < 2.58 * SE_k
    """
    feature_names = ["price_log_ratio", "quality_score", "travel_distance"]
    true_beta = np.array([-1.25, 1.80, -0.65])

    dataset = generate_synthetic_choice_data(
        n_samples=3500,
        true_beta=true_beta,
        feature_names=feature_names,
        n_alternatives=4,
        seed=101,
    )

    estimator = ConditionalLogitEstimator()
    result = estimator.fit(dataset)

    assert result.converged, "Optimizer failed to converge"
    assert result.n_observations == 3500
    assert result.log_likelihood > result.null_log_likelihood, "Fitted model must outperform null model"
    assert 0.0 < result.mcfadden_r2 < 1.0, f"Invalid McFadden R²: {result.mcfadden_r2}"
    assert result.aic == pytest.approx(2 * 3 - 2 * result.log_likelihood, rel=1e-5)
    assert result.bic == pytest.approx(3 * np.log(3500) - 2 * result.log_likelihood, rel=1e-5)

    # Parameter recovery assertion
    for i, f in enumerate(feature_names):
        b_est = result.params[f]
        b_true = true_beta[i]
        se = result.standard_errors[f]

        assert not np.isnan(se), f"Standard error for {f} is NaN"
        assert se > 0.0, f"Standard error for {f} must be positive"

        # 99% confidence interval test: z = 2.58
        margin = 2.58 * se
        diff = abs(b_est - b_true)
        assert diff <= margin, (
            f"Parameter {f} failed recovery: true={b_true:.3f}, estimated={b_est:.3f}, "
            f"diff={diff:.3f} exceeded 99% CI margin={margin:.3f} (SE={se:.3f})"
        )

    # Check summary string generation
    summary_text = result.summary()
    assert "McFadden Conditional Logit Estimation Results" in summary_text
    for f in feature_names:
        assert f in summary_text


def test_fisher_information_and_standard_errors():
    """Verify observed Fisher Information matrix is symmetric positive semi-definite."""
    feature_names = ["cost", "rating"]
    true_beta = np.array([-0.8, 1.5])
    dataset = generate_synthetic_choice_data(1000, true_beta, feature_names, n_alternatives=3, seed=202)

    estimator = ConditionalLogitEstimator()
    res = estimator.fit(dataset)

    cov = res.covariance_matrix
    assert cov.shape == (2, 2)
    # Symmetry check
    assert cov[0, 1] == pytest.approx(cov[1, 0], abs=1e-6)
    # Diagonal variances positive
    assert cov[0, 0] > 0.0
    assert cov[1, 1] > 0.0
    # Standard errors match square root of diagonal
    assert res.standard_errors["cost"] == pytest.approx(np.sqrt(cov[0, 0]), rel=1e-5)
    assert res.standard_errors["rating"] == pytest.approx(np.sqrt(cov[1, 1]), rel=1e-5)


def test_holdout_cross_validation():
    """Verify out-of-sample evaluation: log-loss, Brier score, and accuracy."""
    feature_names = ["price", "quality", "dist"]
    true_beta = np.array([-1.5, 2.0, -0.9])

    train_data = generate_synthetic_choice_data(2500, true_beta, feature_names, seed=303)
    test_data = generate_synthetic_choice_data(800, true_beta, feature_names, seed=404)

    estimator = ConditionalLogitEstimator()
    estimator.fit(train_data)

    eval_results = evaluate_holdout(estimator, test_data, n_bins=10)

    assert eval_results["n_test_observations"] == 800
    assert eval_results["test_log_likelihood"] < 0.0
    assert eval_results["test_mcfadden_r2"] > 0.10, "Model should achieve substantial pseudo-R2 on holdout"
    assert eval_results["log_loss"] > 0.0
    assert 0.0 < eval_results["brier_score"] < 1.0, f"Invalid Brier score: {eval_results['brier_score']}"
    # Random guess top-1 accuracy for 3-4 alternatives is ~0.25 to 0.33; trained model should be > 0.45
    assert eval_results["top1_accuracy"] > 0.45, f"Top-1 accuracy too low: {eval_results['top1_accuracy']}"


def test_calibration_curve_and_ece():
    """Verify Expected Calibration Error (ECE) computation."""
    # Synthetic well-calibrated probabilities
    rng = np.random.default_rng(505)
    probs = rng.uniform(0.05, 0.95, size=2000)
    outcomes = (rng.random(size=2000) < probs).astype(float)

    calib = calculate_calibration_curve(probs, outcomes, n_bins=10)

    assert len(calib["bin_edges"]) == 11
    assert len(calib["bin_centers"]) == 10
    assert len(calib["predicted_means"]) == 10
    assert len(calib["observed_frequencies"]) == 10
    assert sum(calib["counts"]) == 2000

    # For true Bernoulli draws, ECE should be very low (< 0.05)
    assert 0.0 <= calib["ece"] < 0.05, f"ECE surprisingly high for true probabilities: {calib['ece']}"


def test_unfitted_predict_proba():
    """Verify calling predict_proba before fit raises RuntimeError."""
    estimator = ConditionalLogitEstimator()
    with pytest.raises(RuntimeError, match="must be fitted"):
        estimator.predict_proba(np.zeros((3, 2)))


def test_collinear_features_singularity_detection():
    """Verify that collinear features are flagged as singular, with NaN standard errors and warning."""
    rng = np.random.default_rng(707)
    x1 = rng.standard_normal((200, 3, 1))
    # Duplicate feature creates exact collinearity (rank 1 Fisher Information)
    x = np.concatenate([x1, x1], axis=2)
    y = rng.integers(0, 3, size=200)

    dataset = ChoiceDataset(X=[x[i] for i in range(200)], y=y, feature_names=["f1", "f2"])
    estimator = ConditionalLogitEstimator()
    res = estimator.fit(dataset)

    assert res.is_singular is True, "Model must flag collinear features as singular"
    assert np.isnan(res.standard_errors["f1"]), "Collinear standard error must be NaN"
    assert np.isnan(res.standard_errors["f2"]), "Collinear standard error must be NaN"
    assert "near-singular" in res.summary(), "Summary must warn about near-singular Fisher Information"


def test_predict_proba_dimension_validation():
    """Verify predict_proba enforces 2D array and matching feature dimensions."""
    true_beta = np.array([-1.0, 1.5])
    dataset = generate_synthetic_choice_data(100, true_beta, ["f1", "f2"], seed=808)
    estimator = ConditionalLogitEstimator()
    estimator.fit(dataset)

    # 1D input instead of 2D
    with pytest.raises(ValueError, match="must be a 2D array"):
        estimator.predict_proba(np.array([1.0, 2.0]))

    # Wrong feature count (3 instead of 2)
    with pytest.raises(ValueError, match="feature dimension 3 does not match model"):
        estimator.predict_proba(np.zeros((3, 3)))

    # Empty choice set returns empty array
    empty_probs = estimator.predict_proba(np.zeros((0, 2)))
    assert len(empty_probs) == 0


def test_calibration_curve_empty_and_mismatch():
    """Verify calibration curve handles empty arrays, length mismatches, and invalid n_bins."""
    # Length mismatch
    with pytest.raises(ValueError, match="Length mismatch"):
        calculate_calibration_curve(np.array([0.5, 0.2]), np.array([1]))

    # Invalid n_bins
    with pytest.raises(ValueError, match="n_bins must be a positive integer"):
        calculate_calibration_curve(np.array([0.5]), np.array([1]), n_bins=0)

    # Empty array returns valid empty structure with ECE 0.0
    empty_res = calculate_calibration_curve(np.array([]), np.array([]), n_bins=5)
    assert empty_res["ece"] == 0.0
    assert len(empty_res["bin_edges"]) == 6
    assert all(c == 0 for c in empty_res["counts"])
