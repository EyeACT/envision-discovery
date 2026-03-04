"""
ENVISION: Eye Imaging Dataset Classifier

A 4-class SetFit classifier for detecting eye imaging datasets:
  - EYE_IMAGING: Actual eye imaging datasets (fundus, OCT, OCTA, etc.)
  - EYE_SOFTWARE: Code, models, tools for eye imaging
  - EDGE_CASE: Eye research papers, reviews, borderline items
  - NEGATIVE: Unrelated domains
"""

__version__ = "0.3.0"
__author__ = "James O'Neill"

from .classifier import EyeImagingClassifier

# Backward-compatible training data exports
from .classifier import (
    POSITIVE_EXAMPLES,
    SOFTWARE_EXAMPLES,
    EDGE_CASES,
    NEGATIVE_EXAMPLES,
    LABELS,
    MODEL_NAME,
)

__all__ = [
    "EyeImagingClassifier",
    "POSITIVE_EXAMPLES",
    "SOFTWARE_EXAMPLES",
    "EDGE_CASES",
    "NEGATIVE_EXAMPLES",
    "LABELS",
    "MODEL_NAME",
]
