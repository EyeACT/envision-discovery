# ENVISION: Eye Imaging Dataset Discovery

A systematic collection and classification of ophthalmic imaging datasets using few-shot learning. This is an ongoing project with classification results pending manual validation.

## Project Status

**Work in Progress** — The classifier has been trained on a limited set of examples and requires further refinement to capture edge cases that may contain eye imaging data.

## Current Results

| Metric | Value |
|--------|-------|
| Total Zenodo records scraped | 30,439 |
| Records with data files/links (open access) | 9,881 |
| Open access eye imaging candidates | 579 |
| Restricted access eye imaging candidates | 285 |
| **Total eye imaging candidates** | **864** |
| Total estimated data volume (open access) | ~1.14 TB |

### White Paper Validation

We validated our results against datasets cited in the Envision Portal white paper:

| Dataset | DOI | Status |
|---------|-----|--------|
| Fundus photography (DR) | zenodo.org/records/4891308 | ✅ Found (96.1% confidence) |
| OCTA (Diabetic Retinopathy) | zenodo.org/records/10400092 | ✅ Found (96.8% confidence, restricted) |

The OCTA dataset was initially missed because it has **restricted access** — the API's such as Zenodo API don't expose file information for such datasets. This discovery led us to run a separate classification pass on 1,289 restricted/embargoed records, identifying 285 additional eye imaging datasets.

### Why 579 Candidates?

These 579 records were classified as likely eye imaging datasets based on:
- High semantic similarity to known ophthalmic imaging terminology (fundus, OCT, retinal, macular, etc.)
- Presence of data files (images, archives) or links to dataset repositories
- Low similarity to known false positive categories (cardiovascular OCT, industrial imaging, etc.)

However, this count represents **preliminary candidates**, not confirmed datasets. The classifier may:
- **Miss edge cases**: Datasets with unconventional descriptions or niche terminology
- **Include false positives**: Records that match keywords but contain non-ophthalmic data
- **Undercount**: Many edge case records (3,521) may contain relevant eye imaging data

### Confidence Distribution

| Confidence Level | Count | Notes |
|-----------------|-------|-------|
| High (≥0.95) | 63 | Likely accurate, still require verification |
| Medium (0.80-0.95) | 173 | Probable eye imaging, manual review recommended |
| Lower (<0.80) | 343 | Uncertain, higher false positive risk |

## Next Steps

1. **Manual Validation**: Review a stratified sample of candidates to measure precision
2. **Edge Case Analysis**: Examine the 3,521 "edge case" records for missed eye imaging datasets
3. **Classifier Refinement**: Incorporate validated labels to improve few-shot training
4. **Expanded Negative Training**: Add additional false positive patterns as discovered

## Search Keywords

The scraper queried Zenodo using combinations of the following terms:

### Ophthalmic Anatomy
```
eye, ophthalmic, ocular, retina, retinal, macula, macular, fovea, foveal,
optic disc, optic nerve head, choroid, choroidal, cornea, corneal,
anterior segment, posterior segment, vitreous, lens, iris, sclera,
conjunctiva, fundus
```

### Imaging Modalities
```
OCT, optical coherence tomography, fundus photography, fundus imaging,
OCTA, OCT angiography, fluorescein angiography, FA, ICG angiography,
slit lamp, corneal topography, confocal microscopy, meibography,
adaptive optics, scanning laser ophthalmoscopy, SLO
```

### Eye Diseases
```
diabetic retinopathy, glaucoma, macular degeneration, AMD, DME,
diabetic macular edema, geographic atrophy, drusen, CNV,
choroidal neovascularization, retinal detachment, macular hole,
epiretinal membrane, keratoconus, cataract, retinitis pigmentosa
```

### Equipment Brands
```
Zeiss, Heidelberg, Spectralis, Cirrus, Topcon, Maestro, Triton,
Optos, Nidek, Canon, Huvitz, Tomey
```

### Benchmark Dataset Names
```
DRIVE, STARE, CHASE_DB1, HRF, MESSIDOR, IDRiD, APTOS, REFUGE,
RIM-ONE, ORIGA, ACRIMA, AIROGS, EyePACS, RFMiD, OLIVES
```

### Wildcard Search Patterns
Generated combinations of anatomy terms with data suffixes:
- `{anatomy} imag*` (e.g., "retina imag*", "fundus imag*")
- `{anatomy} dataset` (e.g., "macular dataset", "corneal dataset")
- `{anatomy} data` (e.g., "OCT data", "choroidal data")
- `{disease} imag*` (e.g., "diabetic retinopathy imag*")
- `{brand} OCT/fundus/retina*/ophthalmol*` (e.g., "Zeiss OCT", "Heidelberg fundus")

### AI/ML Specific Terms
```
retinal deep learning, fundus neural network, OCT machine learning,
glaucoma detection dataset, diabetic retinopathy classification,
retinal vessel segmentation, optic disc segmentation, macular hole detection
```

**Total: 249 unique search terms**

## Classification Approach

### SetFit Few-Shot Learning

We used SetFit, a few-shot learning framework, due to limited labeled training data:

- **Base Model**: `thenlper/gte-large` (1024-dim sentence transformer)
- **Training**: 2 epochs, batch size 16
- **Classes**: 
  - `EYE_IMAGING` — Likely ophthalmic imaging datasets
  - `EDGE_CASE` — Eye-related but uncertain (papers, code, non-imaging research)
  - `NEGATIVE` — Not eye-related or known false positive patterns

### Training Data (Limited)

| Class | Examples | Description |
|-------|----------|-------------|
| POSITIVE | ~90 | Synthetic examples based on known eye imaging datasets |
| EDGE_CASE | ~55 | Eye research papers, code repositories, animal studies |
| NEGATIVE | ~65 | Non-eye data + known false positive patterns |

**Limitation**: Training examples were synthetically generated from domain knowledge, not manually labeled from actual Zenodo records. This introduces potential bias and may not capture the full variety of dataset descriptions.

### Known False Positive Patterns

The following categories were added to negative training to reduce misclassification:

- **Cardiovascular OCT**: Intravascular OCT (IVOCT), coronary artery imaging
- **Endoscopic imaging**: Colonoscopy, laparoscopy, bronchoscopy
- **Industrial OCT/CT**: Material inspection, pharmaceutical, art conservation
- **Dental OCT**: Tooth structure analysis
- **Dermatology OCT**: Skin imaging, dermoscopy
- **Pulmonary imaging**: Chest CT, lung nodule detection

Additional false positive patterns will be added as they are identified during manual review.

## Data Filtering

Records were only considered for classification if they contained:
1. **Data files** with extensions: `.dcm`, `.nii`, `.jpg`, `.png`, `.tif`, `.mat`, `.h5`, `.npy`, `.zip`, `.tar`, `.gz`
2. **Dataset links** to: Kaggle, GitHub, Google Drive, HuggingFace, OSF, Dryad, etc.

Records without data files or dataset references were excluded to focus on actual datasets rather than publications.

## Output Files

| File | Description |
|------|-------------|
| `results/zenodo_eye_imaging_v2.json` | 579 open access candidates (preliminary) |
| `results/zenodo_eye_imaging_v2.tsv` | Tab-separated for spreadsheet review |
| `results/zenodo_restricted_eye_imaging.json` | 285 restricted access candidates |
| `data/zenodo_metadata_sample.json` | Sample of 20 high-confidence records |

## Limitations

1. **Unvalidated Results**: Classification has not been manually verified
2. **Synthetic Training Data**: Model trained on generated examples, not labeled records
3. **Keyword Bias**: May miss datasets with unusual or domain-specific terminology
4. **Single Platform**: Currently only covers Zenodo; Figshare analysis in progress
5. **Edge Case Gap**: 3,521 records classified as "edge cases" may contain relevant data
6. **Restricted Access**: 285 restricted datasets identified separately (no file verification possible)

## Repository Structure

```
envision_zenodo/
├── README.md                    # This file
├── requirements.txt             # Python dependencies
├── data/
│   └── zenodo_metadata_sample.json
├── results/
│   ├── zenodo_eye_imaging_v2.json
│   └── zenodo_eye_imaging_v2.tsv
├── scripts/
│   ├── scraper.py              # Zenodo API scraper
│   └── classifier.py           # SetFit classifier
└── models/                      # For trained model weights (pending)
```

## Requirements

```
python>=3.10
setfit>=1.0.0
sentence-transformers>=2.2.0
torch>=2.0.0
requests>=2.28.0
```

## Contributing

Manual validation contributions are welcome. To help:
1. Review records in `results/zenodo_eye_imaging_v2.tsv`
2. Visit each Zenodo URL to verify dataset contents
3. Report false positives or missed datasets for classifier refinement

## License

This project collects metadata from publicly available Zenodo records. Individual dataset licenses vary — please check each dataset's license before use.
