---
license: mit
language:
- en
library_name: setfit
tags:
- setfit
- sentence-transformers
- text-classification
- ophthalmology
- medical
- eye-imaging
- dataset-discovery
pipeline_tag: text-classification
datasets:
- custom
metrics:
- accuracy
base_model: Alibaba-NLP/gte-large-en-v1.5
model-index:
- name: envision-eye-imaging-classifier
  results: []
---

# ENVISION Eye Imaging Dataset Classifier

A SetFit few-shot classifier for detecting ophthalmic imaging datasets from repository metadata (titles, descriptions, keywords).

## Model Description

This model classifies scientific dataset metadata into four categories:

| Label | Description | Examples |
|-------|-------------|----------|
| **EYE_IMAGING** | Actual ophthalmic imaging datasets | Fundus photos, OCT scans, OCTA, corneal imaging |
| **EYE_SOFTWARE** | Code/tools for eye imaging (no data) | GitHub repos, model weights, toolboxes |
| **EDGE_CASE** | Eye research but not imaging datasets | Review papers, clinical trials, animal studies |
| **NEGATIVE** | Not eye-related | Other medical imaging, taxonomy papers, etc. |

## Intended Use

- **Primary Use**: Automated discovery of eye imaging datasets from scientific repositories (Zenodo, Figshare, etc.)
- **Input**: Dataset metadata text (title + description + keywords)
- **Output**: Classification label and confidence scores

## Training Data

| Class | Examples | Source |
|-------|----------|--------|
| EYE_IMAGING | 99 | Known benchmarks (DRIVE, IDRiD, REFUGE, OLIVES, etc.) |
| EYE_SOFTWARE | 30 | GitHub eye imaging repositories |
| EDGE_CASE | 90 | Eye research papers, reviews, adjacent imaging |
| NEGATIVE | 233 | False positive patterns (cardiovascular OCT, taxonomy papers, industrial imaging) |

**Total: 452 training examples**

## Model Architecture

- **Base Model**: [Alibaba-NLP/gte-large-en-v1.5](https://huggingface.co/Alibaba-NLP/gte-large-en-v1.5)
- **Framework**: SetFit (few-shot learning)
- **Embedding Dimension**: 1024
- **Max Sequence Length**: 8192 tokens
- **Training**: 2 epochs, batch size 16

## Usage

```python
from setfit import SetFitModel

# Load model
model = SetFitModel.from_pretrained("EyeACT/envision-eye-imaging-classifier")

# Classify dataset metadata
texts = [
    "Fundus photography dataset for diabetic retinopathy detection with 10,000 images",
    "Deep learning code for retinal vessel segmentation PyTorch implementation",
    "Climate change impact on coral reef ecosystems"
]

predictions = model.predict(texts)
probabilities = model.predict_proba(texts)

for text, pred, probs in zip(texts, predictions, probabilities):
    print(f"Text: {text[:50]}...")
    print(f"Prediction: {pred}")
    print(f"Probabilities: {probs}")
    print()
```

## Performance

Initial validation on Zenodo metadata (30,439 records):

| Metric | Value |
|--------|-------|
| Records with data files | 9,881 |
| EYE_IMAGING detected | ~380 |
| EYE_SOFTWARE detected | ~70 |
| EDGE_CASE | ~2,500 |
| NEGATIVE | ~6,900 |

**Note**: Results require manual validation. The model is optimized for high precision on the EYE_IMAGING class.

## Limitations

1. **Training Data**: Based on synthetic/curated examples, not manually labeled records
2. **Domain Specificity**: Optimized for ophthalmic imaging; may not generalize to other medical domains
3. **False Positives**: Some categories (e.g., papers with "FIGURES" in title) may still be misclassified
4. **Language**: English only

## Ethical Considerations

- This model is designed for dataset discovery, not clinical decision-making
- Results should be manually validated before use in research
- The model may reflect biases in the training data

## Citation

If you use this model, please cite:

```bibtex
@misc{envision2026,
  title={ENVISION: Eye Imaging Dataset Discovery},
  author={FAIR Data Innovations Hub and EyeACT Study Team},
  year={2026},
  publisher={Hugging Face},
  url={https://huggingface.co/EyeACT/envision-eye-imaging-classifier}
}
```

## About

### FAIR Data Innovations Hub

The [FAIR Data Innovations Hub](https://fairdataihub.org/) develops open-source tools and practices to make biomedical research data Findable, Accessible, Interoperable, and Reusable (FAIR). We are part of the California Medical Innovations Institute (CALMI2).

### EyeACT Study

The [Eye ACT study](https://eyeactstudy.org/) investigates the connection between eye health and brain function, pioneering research to uncover early indicators of Alzheimer's disease through ophthalmic imaging. The study is a collaboration between:

- **California Medical Innovations Institute (CALMI2)**
- **Kaiser Permanente Washington**
- **University of Washington**

### ENVISION Project

ENVISION (Eye Imaging Dataset Discovery) is a systematic effort to catalog and classify publicly available ophthalmic imaging datasets. This supports the broader goal of making eye imaging research data FAIR and accessible to the scientific community.

## Links

- **GitHub**: [EyeACT/envision-discovery](https://github.com/EyeACT/envision-discovery)
- **EyeACT Study**: [eyeactstudy.org](https://eyeactstudy.org/)
- **FAIR Data Innovations Hub**: [fairdataihub.org](https://fairdataihub.org/)
- **CALMI2**: [calmi2.org](https://calmi2.org/)

## License

MIT License


