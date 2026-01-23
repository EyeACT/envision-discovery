# ENVISION: Eye Imaging Dataset Discovery

A systematic collection and classification of ophthalmic imaging datasets using few-shot learning.

## Installation

```bash
# Clone and install
git clone https://github.com/EyeACT/envision-discovery.git
cd envision-discovery
pip install -e .

# Or install directly from GitHub
pip install git+https://github.com/EyeACT/envision-discovery.git
```

## Usage

```bash
# Run classifier (trains model and classifies Zenodo metadata)
python -m envision.classifier

# Run scraper to collect new metadata
python -m envision.scraper
```

## Current Results (January 2026)

| Metric | Value |
|--------|-------|
| Total Zenodo records scraped | 30,439 |
| Records with data files | 9,881 |
| **Eye imaging datasets** | **380** |
| Eye imaging software/tools | 70 |
| Edge cases (research papers, etc.) | ~2,500 |
| Negative (unrelated) | ~6,900 |

### Classification Improvements

The v2 classifier addresses key issues from v1:

1. **4-class system**: Separates `EYE_SOFTWARE` (code/models) from `EYE_IMAGING` (actual datasets)
2. **~620 training examples**: Up from ~210, including 200+ curated false positive patterns
3. **Better model**: `Alibaba-NLP/gte-large-en-v1.5` (8K context) vs `thenlper/gte-large` (512 tokens)
4. **False positive filtering**: Extensive negative examples for taxonomy papers, cardiovascular OCT, industrial imaging, etc.

### White Paper Validation

Datasets cited in the Envision Portal white paper:

| Dataset | DOI | Status |
|---------|-----|--------|
| Fundus photography (DR) | zenodo.org/records/4891308 | ✅ Found |
| OCTA (Diabetic Retinopathy) | zenodo.org/records/10400092 | ✅ Found |

## Classification Approach

### SetFit Few-Shot Learning

We use SetFit, a few-shot learning framework optimized for limited labeled data:

- **Base Model**: `Alibaba-NLP/gte-large-en-v1.5` (1024-dim, 8K context)
- **Training**: 2 epochs, batch size 16
- **Classes**:
  - `EYE_IMAGING` — Actual ophthalmic imaging datasets (fundus, OCT, OCTA, cornea, etc.)
  - `EYE_SOFTWARE` — Code, tools, models for eye imaging (no actual data)
  - `EDGE_CASE` — Eye research (papers, reviews, non-imaging data)
  - `NEGATIVE` — Not eye-related

### Training Data

| Class | Examples | Description |
|-------|----------|-------------|
| EYE_IMAGING | 137 | Known benchmark datasets + curated positives |
| EYE_SOFTWARE | 29 | GitHub repos, model weights, toolboxes |
| EDGE_CASE | 100 | Papers, reviews, animal studies, adjacent imaging |
| NEGATIVE | 255 | Non-eye data + extensive false positive patterns |

### Known False Positive Patterns (in NEGATIVE training)

- **Cardiovascular OCT**: Intravascular OCT (IVOCT), coronary artery imaging
- **Taxonomy papers**: Biology papers with "FIGURES 1-10 in..." titles
- **Industrial OCT/CT**: Material inspection, pharmaceutical, art conservation
- **Non-ophthalmic medical**: Brain MRI, cardiac CT, mammography, dermoscopy
- **Microscopy**: Cryo-EM, confocal, STORM (non-retinal)
- **Acousto-optics**: Photonics, optical sensors, fiber optics
- **Robotics**: Hand-eye calibration, machine vision

## Search Keywords

The scraper queries Zenodo using 249 unique search terms across:

- **Ophthalmic Anatomy**: retina, macula, fundus, cornea, optic disc, choroid
- **Imaging Modalities**: OCT, OCTA, fundus photography, fluorescein angiography
- **Eye Diseases**: diabetic retinopathy, glaucoma, AMD, DME, keratoconus
- **Equipment Brands**: Zeiss, Heidelberg, Topcon, Optos
- **Benchmark Datasets**: DRIVE, STARE, IDRiD, REFUGE, OLIVES, AIROGS

## Repository Structure

```
envision-discovery/
├── envision/                  # Python package
│   ├── __init__.py
│   ├── classifier.py          # 4-class SetFit classifier
│   └── scraper.py             # Zenodo metadata scraper
├── data/
│   └── zenodo_metadata_sample.json
├── results/
│   ├── zenodo_eye_imaging.json
│   └── zenodo_software.json
├── pyproject.toml             # pip install configuration
├── requirements.txt
└── README.md
```

## Requirements

```
python>=3.9
torch>=2.0.0
setfit>=1.0.0
sentence-transformers>=2.2.0
datasets>=2.0.0
transformers>=4.30.0
```

## Data Filtering

Records are only classified if they contain:
1. **Data files**: `.dcm`, `.nii`, `.jpg`, `.png`, `.tif`, `.mat`, `.h5`, `.npy`, `.zip`, `.tar`, `.gz`
2. **Dataset links**: Kaggle, GitHub, Google Drive, HuggingFace, OSF, Dryad

## Limitations

1. Results require manual validation
2. Single platform (Zenodo only; Figshare planned)
3. Restricted access datasets identified separately
4. May miss datasets with unusual terminology

## Contributing

Contributions welcome:
1. Review records in `results/zenodo_eye_imaging.json`
2. Visit Zenodo URLs to verify dataset contents
3. Report false positives or missed datasets

## License

MIT License. Individual dataset licenses vary — check each dataset before use.
