---
license: mit
tags:
- text-classification
- setfit
- sentence-embedding
- eye-imaging
- ophthalmology
- medical-imaging
- fair-data
- eyeact
---

# Envision Eye Imaging Classifier

SetFit few-shot classifier for identifying eye imaging datasets from scientific metadata.

**Developed by**: FAIR Data Innovations Hub in collaboration with the EyeACT Study

## Model Description

Uses `sentence-transformers/all-mpnet-base-v2` as backbone with 4-class classification:

- **EYE_IMAGING (3)**: Actual ophthalmic imaging datasets (fundus, OCT, OCTA, cornea)
- **EYE_SOFTWARE (2)**: Code, tools, models for eye imaging
- **EDGE_CASE (1)**: Eye research papers, reviews, non-imaging data
- **NEGATIVE (0)**: Not eye-related

## Results on Zenodo

Tested on 514 Zenodo datasets (filtered to `resource_type=dataset` only):

| Class | Count |
|-------|-------|
| EYE_IMAGING | 127 |
| EYE_SOFTWARE | 24 |
| EDGE_CASE | 32 |
| NEGATIVE | 331 |

### Confidence Distribution (EYE_IMAGING)

| Confidence | Count | % |
|------------|-------|---|
| High (>=0.95) | 49 | 38.6% |
| Medium (0.80-0.95) | 70 | 55.1% |
| Lower (<0.80) | 8 | 6.3% |

### Validation Metrics

| Metric | Held-out Test | Spot-check (33 records) |
|--------|--------------|------------------------|
| Accuracy | 0.937 | 0.879 (29/33) |
| Macro F1 | 0.902 | 0.828 |

Per-class spot-check F1: EYE_IMAGING=0.947, EDGE_CASE=0.889, NEGATIVE=0.903, EYE_SOFTWARE=0.571

### Data Pipeline

- Scraped with datasets-only filter
- ZIP contents inspected via HTTP Range requests (31,958 files catalogued)
- Genomics files excluded (.fasta, .h5ad, .vcf, etc.)

## Training

- **Base model**: sentence-transformers/all-mpnet-base-v2 (768-dimensional)
- **Examples**: 474 (77 EYE_IMAGING, 48 EYE_SOFTWARE, 79 EDGE_CASE, 270 NEGATIVE)
- **Epochs**: 2
- **Batch Size**: 16

## Usage

```python
from sentence_transformers import SentenceTransformer
import joblib

model = SentenceTransformer("fairdataihub/envision-eye-imaging-classifier", trust_remote_code=True)
head = joblib.load("model_head.pkl")

embeddings = model.encode(["Retinal OCT dataset for diabetic retinopathy"])
predictions = head.predict(embeddings)
```

## Citation

- EyeACT Envision project
- FAIR Data Innovations Hub (fairdataihub.org)
- sentence-transformers/all-mpnet-base-v2

## Contact

EyeACT team: [eyeactstudy.org](https://eyeactstudy.org)
