"""
ENVISION Discovery: Eye Imaging Dataset Discovery Pipeline

Uses envision-classifier to find eye imaging datasets across repositories.
"""

__version__ = "0.1.0"
__author__ = "James O'Neill"

# Re-export classifier from envision-classifier package
from envision_classifier import EyeImagingClassifier, LABELS

__all__ = [
    "EyeImagingClassifier",
    "LABELS",
]
