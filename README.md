# ENVISION: Eye Imaging Dataset Classifier

A 4-class eye imaging dataset classifier using SetFit few-shot learning. Given JSON metadata (title, description, keywords), ENVISION predicts whether a dataset contains eye imaging data and returns confidence scores.

## Quick Start

```bash
pip install git+https://github.com/EyeACT/envision-discovery.git
```

### Python API

```python
from envision import EyeImagingClassifier

clf = EyeImagingClassifier()

# Classify from text
result = clf.classify("Retinal OCT dataset for diabetic retinopathy screening")
# {'label': 'EYE_IMAGING', 'confidence': 0.999, 'probabilities': {...}}

# Classify from metadata dict
result = clf.classify({
    "title": "Fundus photography dataset",
    "description": "2000 retinal images with DR grading",
    "keywords": ["fundus", "diabetic retinopathy"]
})

# Batch classification
results = clf.classify_batch([
    "OCTA images of diabetic macular edema",
    "Cardiovascular IVOCT coronary artery dataset",
    {"title": "Corneal topography maps", "description": "Keratoconus screening data"}
])
```

### CLI

```bash
# Classify a text string
envision-classify --text "Retinal OCT dataset for diabetic retinopathy"

# Classify from JSON file
envision-classify metadata.json

# Classify from stdin
echo '{"title": "Fundus images"}' | envision-classify
```

## Input / Output Format

**Input**: A JSON object with any of these fields (or a plain text string):
```json
{
  "title": "Dataset title",
  "description": "Dataset description (HTML tags are stripped)",
  "keywords": ["keyword1", "keyword2"]
}
```

**Output**:
```json
{
  "label": "EYE_IMAGING",
  "confidence": 0.9998,
  "probabilities": {
    "EYE_IMAGING": 0.9998,
    "EYE_SOFTWARE": 0.0001,
    "EDGE_CASE": 0.0000,
    "NEGATIVE": 0.0001
  }
}
```

## Classification Classes

| Class | Label | Description |
|-------|-------|-------------|
| 3 | **EYE_IMAGING** | Actual eye imaging datasets (fundus, OCT, OCTA, cornea, etc.) |
| 2 | **EYE_SOFTWARE** | Code, tools, models for eye imaging (no actual image data) |
| 1 | **EDGE_CASE** | Eye research papers, reviews, non-imaging data |
| 0 | **NEGATIVE** | Not eye-related |

## Model Details

- **Framework**: [SetFit](https://github.com/huggingface/setfit) — few-shot learning
- **Backbone**: `Alibaba-NLP/gte-large-en-v1.5` (1024-dim, 8K context)
- **Training**: 2 epochs, batch size 16, 452 curated examples

| Class | Training Examples |
|-------|------------------|
| EYE_IMAGING | 99 |
| EYE_SOFTWARE | 30 |
| EDGE_CASE | 90 |
| NEGATIVE | 233 |

The negative set includes known false positive patterns: cardiovascular OCT (IVOCT), industrial OCT/CT, microscopy, taxonomy papers, acousto-optics, and robotics (hand-eye calibration).

## Validation on Zenodo

ENVISION was validated by classifying 515 scraped Zenodo dataset records:

| Metric | Value |
|--------|-------|
| Total datasets classified | 514 (with data files) |
| **Eye imaging datasets** | **120** |
| Eye software/code | 66 |
| Edge cases | 3 |
| Negative | 325 |

**Confidence**: 97.5% of EYE_IMAGING predictions at >= 0.95 confidence.

## Zenodo Pipeline

The full Zenodo scraping + classification pipeline is included for reproducibility:

```bash
# Run pipeline (train model + classify all Zenodo metadata)
envision-pipeline

# Classify only (skip training, use saved model)
envision-pipeline --classify-only

# Train a new model
envision-train --output ./my_model
```

The pipeline reads per-record JSON files from `data/metadata/zenodo/`, classifies them, and writes results to `results/`.

## Repository Structure

```
envision-discovery/
├── envision/                  # Python package
│   ├── __init__.py            # EyeImagingClassifier export
│   ├── classifier.py          # EyeImagingClassifier + training data
│   ├── pipeline.py            # Zenodo batch classification pipeline
│   ├── cli.py                 # CLI entry points
│   ├── scraper.py             # Zenodo metadata scraper
│   └── scraper_v2.py          # Zenodo scraper with ZIP inspection
├── models/                    # Trained SetFit models
├── results/                   # Classification output
├── data/                      # Scraped metadata
├── pyproject.toml
└── README.md
```

## Installation

```bash
# From GitHub
pip install git+https://github.com/EyeACT/envision-discovery.git

# Development
git clone https://github.com/EyeACT/envision-discovery.git
cd envision-discovery
pip install -e .
```

**Requirements**: Python >= 3.10, PyTorch >= 2.0, setfit >= 1.0

## License

MIT License. Individual dataset licenses vary — check each dataset before use.
