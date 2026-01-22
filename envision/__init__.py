"""
ENVISION: Eye Imaging Dataset Discovery and Classification

A tool for discovering and classifying eye imaging datasets from Zenodo
using a 4-class SetFit classifier:
  - EYE_IMAGING: Actual eye imaging datasets (fundus, OCT, OCTA, etc.)
  - EYE_SOFTWARE: Code, models, tools for eye imaging
  - EDGE_CASE: Eye research papers, reviews, borderline items
  - NEGATIVE: Unrelated domains
"""

__version__ = "0.2.0"
__author__ = "James O'Neill"

from .classifier import (
    POSITIVE_EXAMPLES,
    SOFTWARE_EXAMPLES,
    EDGE_CASES,
    NEGATIVE_EXAMPLES,
)

__all__ = [
    "POSITIVE_EXAMPLES",
    "SOFTWARE_EXAMPLES", 
    "EDGE_CASES",
    "NEGATIVE_EXAMPLES",
]

