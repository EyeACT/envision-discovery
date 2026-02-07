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

Uses `Alibaba-NLP/gte-large-en-v1.5` as backbone with 4-class classification:

- **EYE_IMAGING (3)**: Actual ophthalmic imaging datasets (fundus, OCT, OCTA, cornea)
- **EYE_SOFTWARE (2)**: Code, tools, models for eye imaging
- **EDGE_CASE (1)**: Eye research papers, reviews, non-imaging data
- **NEGATIVE (0)**: Not eye-related

## Results on Zenodo

Tested on 515 Zenodo datasets (filtered to `resource_type=dataset` only):

| Class | Count |
|-------|-------|
| EYE_IMAGING | 120 |
| EYE_SOFTWARE | 66 |
| EDGE_CASE | 3 |
| NEGATIVE | 325 |

### Confidence Distribution (EYE_IMAGING)

| Confidence | Count | % |
|------------|-------|---|
| High (≥0.95) | 117 | 97.5% |
| Medium (0.80-0.95) | 2 | 1.7% |
| Lower (<0.80) | 1 | 0.8% |

### Data Pipeline

- Scraped with datasets-only filter
- ZIP contents inspected via HTTP Range requests (31,958 files catalogued)
- Genomics files excluded (.fasta, .h5ad, .vcf, etc.)

## Training

- **Examples**: 452 (99 positive, 30 software, 90 edge case, 233 negative)
- **Epochs**: 2
- **Batch Size**: 16

## Usage

```python
from sentence_transformers import SentenceTransformer
import joblib

model = SentenceTransformer("jimnoneill/envision-eye-imaging-classifier", trust_remote_code=True)
head = joblib.load("model_head.pkl")

embeddings = model.encode(["Retinal OCT dataset for diabetic retinopathy"])
predictions = head.predict(embeddings)
```

## Citation

- EyeACT Envision project
- FAIR Data Innovations Hub (fairdataihub.org)
- Alibaba-NLP/gte-large-en-v1.5

## Contact

EyeACT team: [eyeactstudy.org](https://eyeactstudy.org)

