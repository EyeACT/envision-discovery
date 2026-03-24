# ENVISION Classifier Integration Handoff

**To**: Dorian, Sanjay  
**From**: James O'Neill  
**Date**: February 4, 2026  
**Subject**: Database Integration for Eye Imaging Dataset Discovery

---

## Overview

This document provides technical specifications for integrating the ENVISION classifier results into the Envision Portal database.

---

## 1. Data Sources

### GitHub Repository
```
https://github.com/EyeACT/envision-discovery
```

### Result Files

All sources use the same unified JSON schema. Files are named `{source}_eye_imaging.json`, `{source}_negative.json`, `{source}_all_results.json`. The classifier uses a binary schema: EYE_IMAGING (actual eye imaging data) vs. NEGATIVE (everything else).

| Source | EYE_IMAGING | All Records |
|--------|-------------|-------------|
| `results/zenodo_*.json` | 60 | 515 |
| `results/figshare_*.json` | TBD | TBD |
| `results/dryad_*.json` | TBD | TBD |
| `results/kaggle_*.json` | TBD | TBD |
| `results/nei_*.json` | TBD | TBD |
| `results/datacite_*.json` | TBD | TBD |

### HuggingFace Model
```
https://huggingface.co/fairdataihub/envision-eye-imaging-classifier
```

---

## 2. JSON Schema

### Unified Record Structure (all sources)

```json
{
  "source": "zenodo",
  "source_id": "10866349",
  "doi": "10.5281/zenodo.10866349",
  "url": "https://zenodo.org/records/10866349",
  "label": "EYE_IMAGING",
  "confidence": 0.9998,
  "prob_eye_imaging": 0.9998,
  "prob_negative": 0.0002,
  "title": "Human Developing Retina Atlas",
  "description": "...",
  "keywords": ["retina", "OCT"],
  "access_type": "open",
  "license": "cc-by-4.0",
  "file_types": [".zip"],
  "file_names": ["Data.zip"],
  "file_count": 1,
  "img_count": 0,
  "medical_count": 0,
  "archive_count": 1,
  "genomics_count": 0,
  "size_mb": 37748.1,
  "zip_file_types": {".tif": 450},
  "external_links": [],
  "related_dois": []
}
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `source` | string | Platform: zenodo, figshare, dryad, kaggle, nei, datacite |
| `source_id` | string | Platform-specific unique identifier |
| `doi` | string | DOI if available, null otherwise |
| `url` | string | Direct link to record on source platform |
| `label` | string | Classification: EYE_IMAGING or NEGATIVE |
| `confidence` | float | Max class probability |
| `prob_eye_imaging` | float | Probability of EYE_IMAGING class |
| `prob_negative` | float | Probability of NEGATIVE class |
| `title` | string | Dataset title |
| `description` | string | Abstract/description (HTML stripped, max 500 chars) |
| `keywords` | list | Tags/keywords (max 10) |
| `access_type` | string | Access level: open, embargoed, restricted |
| `license` | string | License identifier |
| `file_types` | list | Top-level file extensions |
| `file_names` | list | Top-level file names (max 20) |
| `file_count` | int | Total file count |
| `img_count` | int | Standard image files (.jpg, .png, .tif, etc.) |
| `medical_count` | int | Medical imaging files (.dcm, .nii, .mat, etc.) |
| `archive_count` | int | Archive files (.zip, .tar, etc.) |
| `genomics_count` | int | Genomics files (excluded from eye imaging) |
| `size_mb` | float | Total size in megabytes |
| `zip_file_types` | object | File types found inside ZIP archives (ext → count) |
| `external_links` | list | URLs to external dataset platforms |
| `related_dois` | list | Related DOI identifiers |

---

## 3. Database Schema Recommendation

### Table: `discovered_datasets`

```sql
CREATE TABLE discovered_datasets (
    id SERIAL PRIMARY KEY,
    zenodo_id VARCHAR(20) UNIQUE NOT NULL,
    title TEXT NOT NULL,
    url VARCHAR(255) NOT NULL,
    label VARCHAR(50) NOT NULL,
    confidence DECIMAL(10, 8) NOT NULL,
    prob_eye_imaging DECIMAL(10, 8),
    prob_negative DECIMAL(10, 8),
    img_file_count INTEGER DEFAULT 0,
    archive_count INTEGER DEFAULT 0,
    size_mb DECIMAL(12, 2),
    source VARCHAR(50) DEFAULT 'zenodo',
    validation_status VARCHAR(20) DEFAULT 'pending',
    validated_by VARCHAR(100),
    validated_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for fast filtering
CREATE INDEX idx_label ON discovered_datasets(label);
CREATE INDEX idx_confidence ON discovered_datasets(confidence);
CREATE INDEX idx_validation ON discovered_datasets(validation_status);
```

### Validation Status Values

| Status | Description |
|--------|-------------|
| `pending` | Not yet manually reviewed |
| `validated` | Confirmed as eye imaging dataset |
| `rejected` | Confirmed false positive |
| `needs_review` | Flagged for further inspection |

---

## 4. Confidence Tiers

Use these thresholds for filtering and display:

| Tier | Confidence Range | Recommended Action |
|------|-----------------|-------------------|
| High | ≥ 0.95 | Auto-include, display prominently |
| Medium | 0.80 - 0.95 | Include with "likely" label |
| Low | 0.60 - 0.80 | Show in "unverified" section |
| Exclude | < 0.60 | Do not display unless validated |

### SQL Example: Get High-Confidence Eye Imaging

```sql
SELECT * FROM discovered_datasets
WHERE label = 'EYE_IMAGING'
  AND confidence >= 0.95
ORDER BY confidence DESC;
```

---

## 5. API Endpoints (Suggested)

### GET /api/datasets

Query parameters:
- `label` - Filter by class (EYE_IMAGING or NEGATIVE)
- `min_confidence` - Minimum confidence threshold
- `validation_status` - Filter by validation state
- `limit` / `offset` - Pagination

Example:
```
GET /api/datasets?label=EYE_IMAGING&min_confidence=0.95&limit=50
```

### GET /api/datasets/{zenodo_id}

Returns single dataset with full metadata.

### PATCH /api/datasets/{zenodo_id}/validate

Body:
```json
{
  "validation_status": "validated",
  "validated_by": "dorian@fairhub.io"
}
```

---

## 6. Running the Classifier

### Installation

```bash
git clone https://github.com/EyeACT/envision-discovery.git
cd envision-discovery
pip install -e .
```

### Execution

```bash
# Run full classification pipeline
python -m envision.classifier

# Output will be written to results/ directory
```

### Requirements

- Python 3.9+
- GPU recommended (8GB+ VRAM)
- ~30 minutes for full Zenodo classification

---

## 7. Update Schedule

### Recommended Cadence

| Task | Frequency |
|------|-----------|
| Re-scrape Zenodo | Monthly |
| Re-classify new records | After each scrape |
| Database sync | Daily (if incremental) |
| Model retraining | Quarterly (with new validation data) |

### Incremental Updates

To get only new records since last scrape:
1. Track `last_scraped_date` in database
2. Query Zenodo API with `created:>={last_date}`
3. Classify only new records
4. Append to database

---

## 8. Data Quality Notes

### High-Confidence Patterns (Valid)

- Titles containing: OCT, retina, fundus, cornea, optic disc
- Large file sizes (>100 MB typically contain actual data)
- Multiple image files in record

### False Positive Patterns (Filtered in Training)

- Cardiovascular OCT (IVOCT, coronary)
- Taxonomy papers with figure references
- Industrial OCT/CT applications
- "Hand-eye calibration" robotics datasets

### Borderline Cases to Monitor

- GWAS studies with "retinal" phenotypes (genetic, not imaging) -- classified as NEGATIVE
- Electrophysiology (MEA, ERG) -- classified as NEGATIVE
- Code repos that also contain sample data -- classified as NEGATIVE
- Multi-modal repositories where eye imaging is a minor component

---

## 9. Contact Information

| Role | Person | Responsibility |
|------|--------|----------------|
| Classifier Development | James O'Neill | Model training, validation |
| Database Integration | Dorian | Schema, ETL pipeline |
| API Development | Sanjay | Endpoints, frontend integration |
| Project Lead | Bhavesh | Requirements, priorities |

---

## 10. Quick Start Checklist

- [ ] Clone repository: `git clone https://github.com/EyeACT/envision-discovery.git`
- [ ] Review JSON schema in `results/zenodo_eye_imaging.json`
- [ ] Create database table with suggested schema
- [ ] Import 60 eye imaging records (from Zenodo; additional sources TBD)
- [ ] Set up confidence tier filtering
- [ ] Implement validation status tracking
- [ ] Schedule monthly re-classification job

---

## Appendix: Sample Data Import Script

```python
import json
import psycopg2

def import_results(json_path, db_connection):
    with open(json_path) as f:
        records = json.load(f)
    
    cursor = db_connection.cursor()
    
    for r in records:
        cursor.execute("""
            INSERT INTO discovered_datasets
            (zenodo_id, title, url, label, confidence,
             prob_eye_imaging, prob_negative,
             img_file_count, archive_count, size_mb, source)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'zenodo')
            ON CONFLICT (zenodo_id) DO UPDATE SET
                confidence = EXCLUDED.confidence,
                updated_at = CURRENT_TIMESTAMP
        """, (
            r['zenodo_id'], r['title'], r['url'], r['label'],
            r['confidence'], r['prob_eye_imaging'], r['prob_negative'],
            r['img_files'], r['archives'], r['size_mb']
        ))
    
    db_connection.commit()
    print(f"Imported {len(records)} records")

# Usage:
# import_results('results/zenodo_eye_imaging.json', conn)
```


