"""Discrete Choice Modelling Engine for StratIq.

Implements McFadden's Random Utility Maximization (RUM) framework:
- Conditional Logit estimation via Maximum Likelihood (MLE)
- Analytical gradients and observed Fisher Information standard errors
- McFadden pseudo-R2, AIC, BIC, and out-of-sample holdout validation
- Brier score, Log Loss, and reliability calibration curves
"""
from .conditional_logit import ChoiceDataset, ChoiceEstimationResult, ConditionalLogitEstimator
from .validation import calculate_calibration_curve, evaluate_holdout

__all__ = [
    "ChoiceDataset",
    "ChoiceEstimationResult",
    "ConditionalLogitEstimator",
    "calculate_calibration_curve",
    "evaluate_holdout",
]
