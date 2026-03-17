# ENVISION Discovery

Eye imaging dataset discovery pipeline. Discovers eye imaging datasets across scientific data repositories (Zenodo, Figshare, Dryad, OSF, DataCite), inspects ZIP contents via HTTP Range requests, and classifies records using [envision-classifier](https://github.com/EyeACT/envision-classifier).

Part of the [EyeACT](https://github.com/EyeACT) project by the [FAIR Data Innovations Hub](https://fairdataihub.org).

## Installation

```bash
git clone https://github.com/EyeACT/envision-discovery.git
cd envision-discovery
pip install -e .
```

**Requirements**: Python >= 3.10, [envision-classifier](https://github.com/EyeACT/envision-classifier) (installed automatically)

## Usage

### 1. Scrape datasets from Zenodo

```bash
python -m envision.scraper --output ./data

# Faster: skip ZIP inspection
python -m envision.scraper --output ./data --no-zip-inspect

# Include all resource types (not just datasets)
python -m envision.scraper --output ./data --all-types
```

The scraper:
- Searches Zenodo using 47 ophthalmology-specific search terms across 7 categories (imaging modalities, diseases, anatomy, general ophthalmic, equipment/vendors, benchmark datasets, cornea/anterior segment — see [search terms](docs/SEARCH_TERMS.md))
- Filters for `resource_type=dataset` by default
- Inspects ZIP file contents via HTTP Range requests (downloads only ~64KB per ZIP)
- Detects external dataset links (GitHub, Kaggle, HuggingFace, etc.)
- Excludes genomics-only records (GWAS, RNA-seq, etc.)
- Resumes automatically — skips previously scraped records

Output:
```
data/
├── metadata/zenodo/        # Per-record JSON files (enriched with file analysis)
│   ├── 8254022.json
│   ├── 10537424.json
│   └── ...
└── scrape_summary.json     # Run statistics
```

### 2. Classify scraped records

```bash
# Classify using the trained model
python -m envision --classify-only

# Custom metadata and output paths
python -m envision --classify-only --metadata-dir ./data/metadata/zenodo --results-dir ./results

# Multi-source classification
python -m envision --classify-only --source figshare --results-dir ./results

# Export results in ADDF/DataCite schema (optional)
python -m envision --classify-only --results-dir ./results --addf-output ./results/datacite
```

Output files in `results/`:

| File | Description |
|------|-------------|
| `zenodo_eye_imaging.json` | Records classified as EYE_IMAGING, sorted by confidence |
| `zenodo_software.json` | Records classified as EYE_SOFTWARE |
| `zenodo_all_results.json` | All classified records |

### Output format

Each record in the results JSON:

```json
{
  "zenodo_id": "8254022",
  "doi": "10.5281/zenodo.8254022",
  "url": "https://zenodo.org/records/8254022",
  "label": "EYE_IMAGING",
  "confidence": 0.9998,
  "prob_eye_imaging": 0.9998,
  "prob_software": 0.0000,
  "prob_other_eye": 0.0000,
  "prob_negative": 0.0000,
  "title": "Dataset for PT-OCT ANN Project",
  "description": "...",
  "keywords": ["PT-OCT, ANN"],
  "access_right": "open",
  "license": "cc-by-4.0",
  "resource_type": "dataset",
  "file_types": [".zip"],
  "file_names": ["Data.zip"],
  "file_count": 1,
  "img_count": 0,
  "medical_count": 0,
  "archive_count": 1,
  "genomics_count": 0,
  "size_mb": 302.1,
  "dataset_links": [],
  "related_dois": []
}
```

### Classification labels

| Label | Description |
|-------|-------------|
| **EYE_IMAGING** | Actual eye imaging datasets (fundus, OCT, OCTA, cornea, etc.) |
| **EYE_SOFTWARE** | Code, tools, models for eye imaging (no actual image data) |
| **OTHER_EYE_DATA** | Eye research papers, reviews, non-imaging data |
| **NEGATIVE** | Not eye-related |

## Current Results (Zenodo)

From 515 Zenodo dataset records with data files (scraped from ~30,400 total records):

| Class | Count |
|-------|-------|
| EYE_IMAGING | 120 |
| EYE_SOFTWARE | 66 |
| OTHER_EYE_DATA | 3 |
| NEGATIVE | 325 |

Classification is metadata-only (titles, descriptions, keywords, and file types inspected inside archives via HTTP Range requests) — no dataset files are downloaded. Multi-source support (Figshare, Dryad, OSF, DataCite) is implemented and will expand coverage.

## Repository structure

```
envision-discovery/
├── envision/
│   ├── __init__.py         # Re-exports EyeImagingClassifier from envision-classifier
│   ├── __main__.py         # python -m envision entry point
│   ├── scraper.py          # Zenodo scraper with ZIP inspection
│   ├── pipeline.py         # Batch classification pipeline
│   └── cli.py              # CLI argument parsing
├── data/                   # Scraped metadata (not committed)
├── results/                # Classification output (not committed)
├── pyproject.toml
└── README.md
```

## Related repositories

- [envision-classifier](https://github.com/EyeACT/envision-classifier) — The SetFit classifier package (`pip install envision-classifier`)
- [Model weights on HuggingFace](https://huggingface.co/fairdataihub/envision-eye-imaging-classifier)

## License

MIT License. Individual dataset licenses vary — check each dataset before use.
