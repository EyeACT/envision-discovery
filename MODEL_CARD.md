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

SetFit binary classifier for identifying eye imaging datasets from scientific metadata.

**Developed by**: FAIR Data Innovations Hub in collaboration with the EyeACT Study

## Model Description

Uses `sentence-transformers/all-mpnet-base-v2` as backbone with binary classification:

- **EYE_IMAGING (1)**: Actual ophthalmic imaging datasets (fundus, OCT, OCTA, cornea)
- **NEGATIVE (0)**: Everything else (software, non-imaging eye data, unrelated)

## Results on Zenodo

Tested on 515 Zenodo datasets (filtered to `resource_type=dataset` only):

| Class | Count |
|-------|-------|
| EYE_IMAGING | 60 |
| NEGATIVE | 455 |

The binary classifier identifies records containing actual eye imaging data, filtering out software, non-imaging eye research, and unrelated domains.

### Validation Metrics

| Metric | Held-out Test | Spot-check (33 records) |
|--------|--------------|------------------------|
| Accuracy | 0.961 | 0.909 (30/33) |
| Macro F1 | 0.954 | — |
| EYE_IMAGING F1 | 0.936 (P=0.911, R=0.962) | 0.824 |

### Data Pipeline

- Scraped with datasets-only filter
- ZIP contents inspected via HTTP Range requests (31,958 files catalogued)
- Genomics files excluded (.fasta, .h5ad, .vcf, etc.)

## Training

- **Base model**: sentence-transformers/all-mpnet-base-v2 (768-dimensional)
- **Examples**: 891 (262 EYE_IMAGING, 629 NEGATIVE) from multi-repository sources (Zenodo, Figshare, Dryad, Kaggle, NEI)
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
