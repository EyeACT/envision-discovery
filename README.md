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
# Full pipeline: scrape all repos -> classify -> post to portal
./automation.sh

# Run steps independently
./automation.sh scrape      # Scrape only (saves to data/metadata/{source}/)
./automation.sh classify    # Classify existing data (loads from data/metadata/)
./automation.sh post        # Post results to portal only
```

### CLI

```bash
# Scrape and classify all 7 repositories
python -m envision

# Single repository
python -m envision --source dryad

# Scrape only (saves per-record JSON, no classification)
python -m envision --scrape-only

# Classify existing data (loads from data/metadata/, no scraping)
python -m envision --skip-scrape --results-dir ./results

# Classify + download files for records labelled EYE_IMAGING
python -m envision --source zenodo --skip-scrape --download

# Download across all sources at a tighter confidence gate
python -m envision --source all --download --download-threshold 0.95
```

Files are **only** downloaded after a record is classified as EYE_IMAGING with
confidence ≥ `--download-threshold` (default 0.80). They land in
`data/downloads/{source}/{source_id}/` alongside a per-record `manifest.json`.
See [docs/downloading.md](docs/downloading.md).

### Turning downloads into training-ready trees

That's a separate tool — [envision-eye-actionable](https://github.com/EyeACT/envision-eye-actionable).
It reads this repo's `data/downloads/{source}/{id}/` layout by default and
produces HuggingFace-loadable ADDF v0.1.0 trees at `data/actionable/{source}/{id}/`.

```bash
pip install envision-eye-actionable
envision-conform --source zenodo                  # conforms every downloaded record
envision-conform --source zenodo --source-id 4521044   # one record
```

### Scrapers

All 7 scrapers follow the same pattern:
- Save per-record JSON to `data/metadata/{source}/` as they scrape
- Resume automatically on restart (skip already-scraped records)
- Proactive rate limiting (delay before every API call) + unlimited exponential backoff retries
- Shared search terms across 47 ophthalmology-specific queries

| Source | API | Rate Limit | Archive Inspection | Notes |
|--------|-----|-----------|-------------------|-------|
| **Zenodo** | REST + Elasticsearch | 2s/req | ZIP, TAR | AND-required queries, date-range pagination |
| **Figshare** | REST (POST) | 1s (0.3s with token) | ZIP, TAR | Set `FIGSHARE_ACCESS_TOKEN` in `.env` |
| **DataCite** | REST | 1s/req | N/A (metadata only) | Indexes DOIs across repositories |
| **Kaggle** | REST | 1s/req | ZIP, TAR | Requires `KAGGLE_API_TOKEN` |
| **Dryad** | REST | 1.5s/req | ZIP, TAR | Small corpus |
| **NEI** | NIH RePORTER (POST) | 1.5s/req | N/A (grants) | Eye-specific by definition |
| **OSF** | REST v2 search | 2s/req | ZIP, TAR | Set `OSF_TOKEN` in `.env` for higher limits |

### Output

Each scraper saves per-record JSON to `data/metadata/{source}/{source_id}.json`.

Classification results go to `results/`:

| File | Description |
|------|-------------|
| `{source}_eye_imaging.json` | Records classified as EYE_IMAGING, sorted by confidence |
| `{source}_all_results.json` | All classified records with binary labels |

Each classified record:

```json
{
  "source": "zenodo",
  "source_id": "8254022",
  "doi": "10.5281/zenodo.8254022",
  "url": "https://zenodo.org/records/8254022",
  "label": "EYE_IMAGING",
  "confidence": 0.9998,
  "prob_eye_imaging": 0.9998,
  "prob_negative": 0.0002,
  "title": "Dataset for PT-OCT ANN Project",
  "description": "...",
  "keywords": ["PT-OCT", "ANN"],
  "access_type": "open",
  "license": "cc-by-4.0",
  "file_types": [".zip"],
  "file_names": ["Data.zip"],
  "file_count": 1,
  "img_count": 0,
  "medical_count": 0,
  "archive_count": 1,
  "genomics_count": 0,
  "size_mb": 302.1,
  "external_links": [],
  "related_dois": []
}
```

### Classification labels

| Label | Description |
|-------|-------------|
| **EYE_IMAGING** | Actual eye imaging datasets (fundus, OCT, OCTA, cornea, slit-lamp, anterior segment) |
| **NEGATIVE** | Everything else (non-eye data, software/code, eye-adjacent non-imaging, non-eye medical imaging) |

## Repository structure

```
envision-discovery/
├── envision/
│   ├── __init__.py         # Re-exports EyeImagingClassifier from envision-classifier
│   ├── __main__.py         # python -m envision entry point
│   ├── cli.py              # CLI (--source, --skip-scrape, --scrape-only, --download)
│   ├── scraper.py          # Zenodo scraper with ZIP inspection + AND queries
│   ├── pipeline.py         # Classification pipeline (downloads model from HuggingFace)
│   ├── downloader.py       # Post-classification file downloader (gated by EYE_IMAGING)
│   ├── addf_export.py      # ADDF metadata export (dataset_description + structure_description from the scrape)
│   ├── metadata.py         # DatasetMetadata dataclass (save/load/resume)
│   ├── utils.py            # Shared utilities (backoff, archive inspector, pagination)
│   └── scrapers/           # Per-source scrapers (all save to data/metadata/{source}/)
│       ├── datacite.py
│       ├── figshare.py
│       ├── kaggle.py
│       ├── dryad.py
│       ├── nei.py
│       └── osf.py
├── automation.sh           # Weekly cron — scrape/classify/post (run steps independently)
├── data/
│   └── metadata/           # Per-record JSON files per source (not committed)
│       ├── zenodo/
│       ├── figshare/
│       ├── datacite/
│       ├── kaggle/
│       ├── dryad/
│       ├── nei/
│       └── osf/
├── results/                # Classification output (not committed)
├── .env.example            # API tokens template (Figshare, OSF, Kaggle, Portal)
├── pyproject.toml
└── README.md
```

## Related repositories

- [envision-eye-actionable](https://github.com/EyeACT/envision-eye-actionable) — turns this repo's downloads into HuggingFace-loadable ADDF v0.1.0 trees
- [envision-classifier](https://github.com/EyeACT/envision-classifier) — The SetFit classifier package (`pip install envision-classifier`)
- [Model weights on HuggingFace](https://huggingface.co/fairdataihub/envision-eye-imaging-classifier)

## License

MIT License. Individual dataset licenses vary — check each dataset before use.
