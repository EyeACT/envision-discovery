"""Test setup.

``import envision`` re-exports the classifier from envision-classifier,
which pulls in torch and a HuggingFace model. The scraper tests do not
need it, so a stub is installed when the real package is not available.
"""

import sys
import types

try:  # pragma: no cover - depends on the environment
    import envision_classifier  # noqa: F401
except ImportError:  # pragma: no cover
    stub = types.ModuleType("envision_classifier")

    class EyeImagingClassifier:  # minimal stand-in
        def __init__(self, *a, **k):
            raise RuntimeError("envision_classifier is not installed")

    stub.EyeImagingClassifier = EyeImagingClassifier
    stub.LABELS = ["EYE_IMAGING", "NEGATIVE"]
    sys.modules["envision_classifier"] = stub
