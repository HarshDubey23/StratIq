"""Population synthesis and microsimulation package."""
from .ipf import ipf_solve, IPFResult
from .synthesis import (
    AGE_BANDS,
    AGE_MIDPOINTS,
    SyntheticPerson,
    SyntheticPopulation,
    build_synthetic_population,
)
from .validation import ValidationReport, validate_population

__all__ = [
    "ipf_solve",
    "IPFResult",
    "AGE_BANDS",
    "AGE_MIDPOINTS",
    "SyntheticPerson",
    "SyntheticPopulation",
    "build_synthetic_population",
    "ValidationReport",
    "validate_population",
]
