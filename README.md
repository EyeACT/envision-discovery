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

## Current Results

| Metric | Value |
|--------|-------|
| Total Zenodo datasets scraped | 515 |
| Datasets with data files | 514 |
| **Eye imaging datasets** | **120** |
| Eye software/code | 66 |
| Edge cases | 3 |
| Negative (unrelated) | 325 |

### Confidence Distribution (EYE_IMAGING)

| Confidence Level | Count | Notes |
|-----------------|-------|-------|
| High (≥0.95) | 117 | Strong candidates (97.5%) |
| Medium (0.80-0.95) | 2 | Likely eye imaging |
| Lower (<0.80) | 1 | Manual review recommended |

### File Types in Eye Imaging Datasets

| File Type | Count |
|-----------|-------|
| .zip | 80 |
| .rar | 10 |
| .mat | 10 |
| .tif | 7 |
| .jpg | 4 |
| .tar.gz | 4 |
| .png | 3 |
| .h5 | 3 |

> **Note**: All records are `resource_type=dataset` (filtered during scraping). ZIP contents inspected via HTTP Range requests.

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
| EYE_IMAGING | 99 | Known benchmark datasets + curated positives |
| EYE_SOFTWARE | 30 | GitHub repos, model weights, toolboxes |
| EDGE_CASE | 90 | Papers, reviews, animal studies, adjacent imaging |
| NEGATIVE | 233 | Non-eye data + extensive false positive patterns |

**Total: 452 training examples**

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
├── results/
│   ├── zenodo_eye_imaging.json    # 524 eye imaging datasets
│   ├── zenodo_software.json       # 1,150 software/code repos
│   └── zenodo_all_results.json    # All 9,448 classified records
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

### Supported File Types

| Category | Extensions |
|----------|------------|
| Standard Images | `.jpg`, `.jpeg`, `.png`, `.tif`, `.tiff`, `.bmp`, `.gif` |
| Medical/Scientific | `.dcm`, `.dicom`, `.nii`, `.nii.gz`, `.mat`, `.h5`, `.hdf5`, `.npy`, `.npz` |
| OCT-Specific | `.fds` (Topcon), `.e2e` (Heidelberg), `.vol` (Zeiss), `.oct`, `.fda` (Optovue), `.img` |
| Archives | `.zip`, `.tar`, `.gz`, `.tar.gz`, `.rar`, `.7z` |

### External Dataset Links

Records with links to these platforms are also included:
- Kaggle, HuggingFace, GitHub
- Google Drive, OSF, Dryad, Figshare
- OpenNeuro, PhysioNet, Synapse
- Grand Challenge

## Output Format

Each record in `zenodo_eye_imaging.json` includes:

```json
{
  "zenodo_id": "12166457",
  "doi": "10.5281/zenodo.12166457",
  "url": "https://zenodo.org/records/12166457",
  
  "label": "EYE_IMAGING",
  "confidence": 0.9998847,
  "prob_eye_imaging": 0.9998847,
  
  "title": "Corneal OCT elastography dataset",
  "description": "Raw OCT data from corneal cross-linking study...",
  "keywords": ["cornea", "OCT", "elastography"],
  "access_right": "open",
  "license": "cc-by-4.0",
  "resource_type": "dataset",
  
  "file_types": [".mat"],
  "file_names": ["CXL_1.mat", "CXL_2.mat", ...],
  "file_count": 33,
  "img_count": 0,
  "medical_count": 33,
  "archive_count": 0,
  "size_mb": 34378.5,
  
  "dataset_links": [],
  "related_dois": ["10.1038/s41598-024-67278-1"]
}
```

## Limitations

1. Results require manual validation
2. Single platform (Zenodo only; Figshare planned)
3. Restricted access datasets identified separately
4. May miss datasets with unusual terminology

## Scraper

The scraper (`scraper_v2.py`) collects eye imaging datasets from Zenodo with intelligent filtering:

### Features

1. **ZIP Content Inspection** - Uses HTTP Range requests to read the last 64KB of ZIP files, extracting the file manifest without downloading the full archive. Works on multi-GB files!

2. **Dataset Links Detection** - Extracts links from `related_identifiers` and descriptions pointing to:
   - GitHub, GitLab, Bitbucket
   - Kaggle, HuggingFace, Google Drive
   - OSF, Dryad, Figshare, Dataverse
   - Cloud storage (S3, GCS, Azure)

3. **Weblinks Extraction** - Parses descriptions for URLs to potential data files

4. **Genomics Exclusion** - Automatically skips records with only genomics files:
   - Sequences: `.fasta`, `.fastq`, `.fa`
   - Single-cell: `.h5ad`, `.loom`, `.mtx`
   - Alignments: `.bam`, `.sam`, `.cram`
   - Variants: `.vcf`, `.bcf`

5. **Datasets-Only Filter** - Searches only `resource_type=dataset`, skipping publications/figures

### Usage

```bash
# Full scrape
python -m envision.scraper_v2 --output ./data

# Quick test (skip ZIP inspection)
python -m envision.scraper_v2 --output ./data --no-zip-inspect --max-per-query 50

# Include all resource types (not just datasets)
python -m envision.scraper_v2 --output ./data --all-types
```

## Contributing

Contributions welcome:
1. Review records in `results/zenodo_eye_imaging.json`
2. Visit Zenodo URLs to verify dataset contents
3. Report false positives or missed datasets

## License

MIT License. Individual dataset licenses vary — check each dataset before use.
