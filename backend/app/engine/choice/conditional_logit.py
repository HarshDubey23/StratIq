"""McFadden Conditional Logit Estimation via Maximum Likelihood (MLE).

Theoretical foundation:
- McFadden, D. (1974). Conditional logit analysis of qualitative choice behavior.
- Train, K. E. (2009). Discrete Choice Methods with Simulation. Cambridge University Press.

Utility for consumer n choosing alternative j:
    V_nj = x_nj^T * beta
Probability:
    P_nj = exp(V_nj) / sum_{k in C_n} exp(V_nk)
Log-Likelihood:
    LL(beta) = sum_n sum_{j in C_n} y_nj * ln P_nj
Gradient:
    grad(LL) = sum_n (x_{n, y_n} - sum_{k} P_{nk} * x_{nk})
Hessian:
    H(LL) = - sum_n sum_k P_{nk} (x_{nk} - bar{x}_n)(x_{nk} - bar{x}_n)^T
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np
from scipy.optimize import minimize
from scipy.special import logsumexp
from scipy.stats import norm


@dataclass
class ChoiceDataset:
    """Represents choice observations across decision makers.
    
    Attributes:
        X: List of length N, where each element is a 2D ndarray of shape [J_n, K]
           representing attribute vectors for all alternatives in choice set C_n.
        y: 1D ndarray of length N of chosen alternative indices (0 <= y_n < J_n).
        feature_names: List of K feature names.
    """
    X: list[np.ndarray]
    y: np.ndarray
    feature_names: list[str]

    def __post_init__(self):
        if len(self.X) != len(self.y):
            raise ValueError(f"Mismatch between choices ({len(self.y)}) and choice sets ({len(self.X)})")
        if len(self.X) == 0:
            raise ValueError("ChoiceDataset cannot be empty")
        if len(self.feature_names) != len(set(self.feature_names)):
            raise ValueError("Duplicate feature names found in ChoiceDataset")
        K = len(self.feature_names)
        for i, x_i in enumerate(self.X):
            if x_i.ndim != 2 or x_i.shape[1] != K:
                raise ValueError(f"Observation {i} has shape {x_i.shape}, expected (*, {K})")
            if x_i.shape[0] < 2:
                raise ValueError(f"Observation {i} has choice set size {x_i.shape[0]} < 2; discrete choice requires at least 2 alternatives")
            if not (0 <= self.y[i] < x_i.shape[0]):
                raise ValueError(f"Choice {self.y[i]} out of bounds for choice set of size {x_i.shape[0]}")


@dataclass
class ChoiceEstimationResult:
    """Results from Maximum Likelihood Estimation of Conditional Logit."""
    params: dict[str, float]
    standard_errors: dict[str, float]
    z_stats: dict[str, float]
    p_values: dict[str, float]
    log_likelihood: float
    null_log_likelihood: float
    mcfadden_r2: float
    adj_mcfadden_r2: float
    aic: float
    bic: float
    n_observations: int
    converged: bool
    iterations: int
    covariance_matrix: np.ndarray
    feature_names: list[str]
    is_singular: bool = False

    def summary(self) -> str:
        lines = [
            "McFadden Conditional Logit Estimation Results",
            "=" * 60,
            f"Observations: {self.n_observations:<10} Log-Likelihood: {self.log_likelihood:.4f}",
            f"Null LL:      {self.null_log_likelihood:<10} McFadden R²:    {self.mcfadden_r2:.4f}",
            f"AIC:          {self.aic:<10.2f} Adj McFadden R²: {self.adj_mcfadden_r2:.4f}",
            f"BIC:          {self.bic:<10.2f} Converged:      {str(self.converged)}",
        ]
        if self.is_singular:
            lines.append("WARNING: Fisher Information matrix is near-singular (collinear features detected). Standard errors cannot be reliably identified.")
        lines.extend([
            "-" * 60,
            f"{'Feature':<20} {'Coef':>10} {'Std Err':>10} {'z':>8} {'P>|z|':>8}",
            "-" * 60,
        ])
        for f in self.feature_names:
            c = self.params[f]
            se = self.standard_errors[f]
            z = self.z_stats[f]
            p = self.p_values[f]
            se_str = f"{se:.4f}" if not np.isnan(se) else "NaN"
            z_str = f"{z:.3f}" if not np.isnan(z) else "NaN"
            p_str = f"{p:.4f}" if not np.isnan(p) else "NaN"
            lines.append(f"{f:<20} {c:>10.4f} {se_str:>10} {z_str:>8} {p_str:>8}")
        lines.append("=" * 60)
        return "\n".join(lines)


class ConditionalLogitEstimator:
    """Estimates McFadden Conditional Logit using analytical gradient and Hessian."""

    def __init__(self):
        self.result_: ChoiceEstimationResult | None = None
        self.coef_: np.ndarray | None = None
        self.feature_names_: list[str] = []

    def _neg_log_likelihood_and_grad(self, beta: np.ndarray, dataset: ChoiceDataset) -> tuple[float, np.ndarray]:
        nll = 0.0
        grad = np.zeros_like(beta)

        for x_n, y_n in zip(dataset.X, dataset.y):
            # Systematic utility: [J_n]
            v = x_n @ beta
            # Log-sum-exp for numerical stability
            log_denom = logsumexp(v)
            p = np.exp(v - log_denom)

            # Accumulate negative log-likelihood
            nll -= (v[y_n] - log_denom)

            # Gradient: - (x_{n, y} - sum_k p_k * x_{nk})
            expected_x = p @ x_n
            grad -= (x_n[y_n] - expected_x)

        return nll, grad

    def _compute_hessian(self, beta: np.ndarray, dataset: ChoiceDataset) -> np.ndarray:
        """Computes the observed negative Hessian (Fisher Information matrix)."""
        K = len(beta)
        fisher_info = np.zeros((K, K))

        for x_n in dataset.X:
            v = x_n @ beta
            p = np.exp(v - logsumexp(v))
            expected_x = p @ x_n
            # dev[j] = x_n[j] - expected_x
            dev = x_n - expected_x
            # Weighted covariance: sum_j p_j * dev_j * dev_j^T
            # dev^T @ diag(p) @ dev
            weighted_cov = (dev.T * p) @ dev
            fisher_info += weighted_cov

        return fisher_info

    def fit(
        self,
        dataset: ChoiceDataset,
        initial_beta: np.ndarray | None = None,
        bounds: list[tuple[float | None, float | None]] | None = None,
    ) -> ChoiceEstimationResult:
        """Fits the model via Maximum Likelihood Estimation."""
        K = len(dataset.feature_names)
        N = len(dataset.y)
        self.feature_names_ = list(dataset.feature_names)

        if initial_beta is None:
            initial_beta = np.zeros(K)
        else:
            initial_beta = np.asarray(initial_beta, dtype=float)

        # Objective and gradient
        def objective(b):
            return self._neg_log_likelihood_and_grad(b, dataset)

        opt = minimize(
            objective,
            initial_beta,
            jac=True,
            method="L-BFGS-B",
            bounds=bounds,
            options={"maxiter": 500, "ftol": 1e-9, "gtol": 1e-6},
        )

        beta_hat = opt.x
        self.coef_ = beta_hat
        ll = -float(opt.fun)

        # Compute null log likelihood (equal probabilities for each alternative in choice set)
        null_ll = sum(-np.log(len(x_n)) for x_n in dataset.X)

        # McFadden Pseudo R2
        mcfadden_r2 = 1.0 - (ll / null_ll) if null_ll != 0 else 0.0
        adj_mcfadden_r2 = 1.0 - ((ll - K) / null_ll) if null_ll != 0 else 0.0

        # AIC and BIC
        aic = 2.0 * K - 2.0 * ll
        bic = K * np.log(N) - 2.0 * ll

        # Fisher Information & Standard Errors
        fisher_info = self._compute_hessian(beta_hat, dataset)
        is_singular = False
        try:
            eigvals = np.linalg.eigvalsh(fisher_info)
            max_eig = float(np.max(eigvals)) if len(eigvals) > 0 else 0.0
            min_eig = float(np.min(eigvals)) if len(eigvals) > 0 else 0.0
            if max_eig <= 0.0 or (min_eig / max_eig) < 1e-10:
                is_singular = True
                cov = np.full((K, K), np.nan)
                se_arr = np.full(K, np.nan)
            else:
                cov = np.linalg.inv(fisher_info)
                se_arr = np.sqrt(np.maximum(0.0, np.diag(cov)))
        except np.linalg.LinAlgError:
            is_singular = True
            cov = np.full((K, K), np.nan)
            se_arr = np.full(K, np.nan)

        params = {}
        standard_errors = {}
        z_stats = {}
        p_values = {}

        for i, f_name in enumerate(self.feature_names_):
            b_val = float(beta_hat[i])
            se_val = float(se_arr[i])
            params[f_name] = b_val
            standard_errors[f_name] = se_val
            if not np.isnan(se_val) and se_val > 1e-12:
                z = b_val / se_val
                p = 2.0 * (1.0 - norm.cdf(abs(z)))
                z_stats[f_name] = float(z)
                p_values[f_name] = float(p)
            else:
                z_stats[f_name] = np.nan
                p_values[f_name] = np.nan

        self.result_ = ChoiceEstimationResult(
            params=params,
            standard_errors=standard_errors,
            z_stats=z_stats,
            p_values=p_values,
            log_likelihood=ll,
            null_log_likelihood=null_ll,
            mcfadden_r2=mcfadden_r2,
            adj_mcfadden_r2=adj_mcfadden_r2,
            aic=aic,
            bic=bic,
            n_observations=N,
            converged=bool(opt.success),
            iterations=int(opt.nit),
            covariance_matrix=cov,
            feature_names=self.feature_names_,
            is_singular=is_singular,
        )
        return self.result_

    def predict_proba(self, x_n: np.ndarray) -> np.ndarray:
        """Predicts choice probabilities for alternatives in a single choice set."""
        if self.coef_ is None:
            raise RuntimeError("Model must be fitted before predict_proba")
        x_n = np.asarray(x_n, dtype=float)
        if x_n.ndim != 2:
            raise ValueError(f"x_n must be a 2D array of shape (J, K), got ndim={x_n.ndim}")
        if x_n.shape[1] != len(self.coef_):
            raise ValueError(f"x_n feature dimension {x_n.shape[1]} does not match model ({len(self.coef_)})")
        if x_n.shape[0] == 0:
            return np.array([], dtype=float)
        v = x_n @ self.coef_
        return np.exp(v - logsumexp(v))
