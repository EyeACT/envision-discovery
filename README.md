# ENVISION Discovery

Eye imaging dataset discovery pipeline. Discovers eye imaging datasets across 7 scientific data repositories (Zenodo, Figshare, Dryad, OSF, DataCite, Kaggle, NEI), inspects ZIP/TAR contents via HTTP Range requests, and classifies records using [envision-classifier](https://github.com/EyeACT/envision-classifier).

Part of the [EyeACT](https://github.com/EyeACT) project by the [FAIR Data Innovations Hub](https://fairdataihub.org).

## Installation

```bash
git clone https://github.com/EyeACT/envision-discovery.git
cd envision-discovery
pip install -r requirements.txt
pip install -e .
```

**Requirements**: Python >= 3.10, [envision-classifier](https://github.com/EyeACT/envision-classifier) (installed automatically)

## Usage

### Automated pipeline

```bash
# Full pipeline: scrape all repos → classify → post to portal
./automation.sh

# Run steps independently
./automation.sh scrape      # Scrape only (skip classification)
./automation.sh classify    # Classify existing data (skip scraping)
./automation.sh post        # Post results to portal only
```

### CLI

```bash
# Scrape and classify all 7 repositories
python -m envision --source all

# Single repository
python -m envision --source dryad

# Scrape only (no classification)
python -m envision --source all --scrape-only

# Classify existing data (no scraping)
python -m envision --source all --skip-scrape

# Zenodo standalone scraper
python -m envision.scraper --output ./data
```

### Scrapers

All scrapers use shared search terms, exponential backoff, and archive inspection:

| Source | API | Archive Inspection | Notes |
|--------|-----|-------------------|-------|
| **Zenodo** | REST + Elasticsearch | ZIP, TAR | AND-required queries, date-range pagination |
| **DataCite** | REST | N/A (metadata only) | Indexes DOIs across repositories |
| **Figshare** | REST (POST) | ZIP, TAR | 3s inter-request delay |
| **Kaggle** | REST | ZIP, TAR | Requires API token |
| **Dryad** | REST | ZIP, TAR | Small corpus (~89 eye records) |
| **NEI** | NIH RePORTER (POST) | N/A (grants) | Eye-specific by definition |
| **OSF** | REST v2 search | ZIP, TAR | Optional token for higher rate limits |

Output files in `results/`:

| File | Description |
|------|-------------|
| `{source}_eye_imaging.json` | Records classified as EYE_IMAGING, sorted by confidence |
| `{source}_all_results.json` | All classified records with binary labels |

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
  "prob_negative": 0.0002,
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
| **EYE_IMAGING** | Actual eye imaging datasets (fundus, OCT, OCTA, cornea, slit-lamp, anterior segment) |
| **NEGATIVE** | Everything else (non-eye data, software/code, eye-adjacent non-imaging, non-eye medical imaging) |

## Current Results

From 4,674 unique records across six repositories (Zenodo, Figshare, DataCite, Kaggle, Dryad, NEI):

| Source | EYE_IMAGING | NEGATIVE | Total |
|--------|-------------|----------|-------|
| Zenodo | 60 | 455 | 515 |
| DataCite | 752 | 1,084 | 1,836 |
| Figshare | 1,049 | 951 | 2,000 |
| Kaggle | 248 | 484 | 732 |
| Dryad | 32 | 57 | 89 |
| NEI | 686 | 976 | 1,662 |
| **Unique (deduped)** | **1,933** | **2,741** | **4,674** |

Classification is metadata-only (titles, descriptions, keywords, and file types inspected inside archives via HTTP Range requests) — no dataset files are downloaded. Multi-source support (Figshare, Dryad, OSF, DataCite) is implemented and will expand coverage.

## Repository structure

```
envision-discovery/
├── envision/
│   ├── __init__.py         # Re-exports EyeImagingClassifier from envision-classifier
│   ├── __main__.py         # python -m envision entry point
│   ├── cli.py              # CLI argument parsing (--source, --skip-scrape, etc.)
│   ├── scraper.py          # Zenodo scraper with ZIP inspection + AND queries
│   ├── pipeline.py         # Batch classification pipeline
│   ├── metadata.py         # DatasetMetadata dataclass (shared across scrapers)
│   ├── utils.py            # Shared utilities (backoff, archive inspector, pagination)
│   └── scrapers/           # Per-source scrapers
│       ├── datacite.py
│       ├── figshare.py
│       ├── kaggle.py
│       ├── dryad.py
│       ├── nei.py
│       └── osf.py
├── automation.sh           # Weekly cron — scrape/classify/post (run steps independently)
├── data/                   # Scraped metadata (not committed)
├── results/                # Classification output (not committed)
├── .env.example            # API tokens template (OSF, Kaggle, Portal)
├── pyproject.toml
└── README.md
```

## Related repositories

- [envision-classifier](https://github.com/EyeACT/envision-classifier) — The SetFit classifier package (`pip install envision-classifier`)
- [Model weights on HuggingFace](https://huggingface.co/fairdataihub/envision-eye-imaging-classifier)

## License

MIT License. Individual dataset licenses vary — check each dataset before use.
