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

| File | Description | Records |
|------|-------------|---------|
| `results/zenodo_eye_imaging.json` | Eye imaging datasets | 524 |
| `results/zenodo_software.json` | Software/code repos | 1,150 |
| `results/zenodo_all_results.json` | All classified records | 9,448 |

### HuggingFace Model
```
https://huggingface.co/jimnoneill/envision-eye-imaging-classifier
```

---

## 2. JSON Schema

### Eye Imaging Record Structure

```json
{
  "zenodo_id": "10866349",
  "title": "Human Developing Retina Atlas (Intermediate Data Object)",
  "url": "https://zenodo.org/records/10866349",
  "prediction": 3,
  "label": "EYE_IMAGING",
  "prob_negative": 0.0000381,
  "prob_edge": 0.0000383,
  "prob_software": 0.0000385,
  "prob_eye_imaging": 0.9998850,
  "confidence": 0.9998850,
  "img_files": 0,
  "archives": 1,
  "size_mb": 37748.1
}
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `zenodo_id` | string | Unique Zenodo record identifier |
| `title` | string | Dataset title from metadata |
| `url` | string | Direct link to Zenodo record |
| `prediction` | int | Class index (0=NEG, 1=EDGE, 2=SW, 3=EYE) |
| `label` | string | Human-readable class name |
| `prob_negative` | float | Probability of NEGATIVE class |
| `prob_edge` | float | Probability of EDGE_CASE class |
| `prob_software` | float | Probability of EYE_SOFTWARE class |
| `prob_eye_imaging` | float | Probability of EYE_IMAGING class |
| `confidence` | float | Max probability (same as prob for predicted class) |
| `img_files` | int | Count of image files (.dcm, .nii, .jpg, etc.) |
| `archives` | int | Count of archive files (.zip, .tar, .gz) |
| `size_mb` | float | Total file size in megabytes |

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
    prob_software DECIMAL(10, 8),
    prob_edge DECIMAL(10, 8),
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
- `label` - Filter by class (EYE_IMAGING, EYE_SOFTWARE, etc.)
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

### Edge Cases to Monitor

- GWAS studies with "retinal" phenotypes (genetic, not imaging)
- Electrophysiology (MEA, ERG) - borderline relevant
- Code repos that also contain sample data

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
- [ ] Import 524 eye imaging records
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
             prob_eye_imaging, prob_software, prob_edge, prob_negative,
             img_file_count, archive_count, size_mb, source)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'zenodo')
            ON CONFLICT (zenodo_id) DO UPDATE SET
                confidence = EXCLUDED.confidence,
                updated_at = CURRENT_TIMESTAMP
        """, (
            r['zenodo_id'], r['title'], r['url'], r['label'],
            r['confidence'], r['prob_eye_imaging'], r['prob_software'],
            r['prob_edge'], r['prob_negative'],
            r['img_files'], r['archives'], r['size_mb']
        ))
    
    db_connection.commit()
    print(f"Imported {len(records)} records")

# Usage:
# import_results('results/zenodo_eye_imaging.json', conn)
```

