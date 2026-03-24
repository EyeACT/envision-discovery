# ENVISION: Eye Imaging Dataset Discovery
## Classifier Results & Validation

**Presenter**: James O'Neill  
**Date**: Week of February 10, 2026  
**Audience**: Bhavesh (FAIR Data Innovations Hub)

---

## Slide 1: Problem Statement

**Challenge**: Eye imaging datasets are scattered across multiple repositories

- Researchers cannot easily find existing datasets for training AI models
- Manual curation is time-consuming and incomplete
- No systematic approach to discover ophthalmic imaging data

**Solution**: Automated classification of repository metadata using few-shot learning

---

## Slide 2: Methodology

### SetFit Few-Shot Classifier

| Component | Details |
|-----------|---------|
| Base Model | sentence-transformers/all-mpnet-base-v2 (768-dim embeddings) |
| Framework | SetFit (sentence-transformers + contrastive learning) |
| Training Data | 891 curated examples from multiple repositories |
| Classes | 2 (EYE_IMAGING vs. NEGATIVE) |

### Training Data Distribution

| Class | Examples | Description |
|-------|----------|-------------|
| EYE_IMAGING | 262 | Known benchmark datasets, clinical imaging collections |
| NEGATIVE | 629 | Software/code, other eye data (genetics, tracking), non-eye data, false positive patterns |

---

## Slide 3: Data Collection

### Zenodo Scraping

- **249 unique search terms** covering:
  - Anatomy: retina, macula, cornea, optic disc, choroid
  - Modalities: OCT, OCTA, fundus, fluorescein angiography
  - Diseases: diabetic retinopathy, glaucoma, AMD, DME
  - Equipment: Zeiss, Heidelberg, Topcon, Optos
  - Benchmarks: DRIVE, STARE, IDRiD, REFUGE, AIROGS

### Filtering Criteria

Records must contain:
1. Data files: `.dcm`, `.nii`, `.jpg`, `.png`, `.tif`, `.mat`, `.h5`, `.npy`
2. Or archives: `.zip`, `.tar`, `.gz`

---

## Slide 4: Results Summary

### Zenodo Classification (Binary: EYE_IMAGING vs. NEGATIVE)

| Metric | Value |
|--------|-------|
| Total Zenodo records scraped | 30,439 |
| Records with data files | 515 |
| **EYE_IMAGING** | **60** |
| **NEGATIVE** | **455** |

Previous 4-class model identified 127; binary model identifies 60 with improved precision (fewer false positives).

### Validation Performance

| Metric | Value |
|--------|-------|
| Held-out test accuracy | 0.961 |
| Held-out test macro F1 | 0.954 |
| Held-out EYE_IMAGING F1 | 0.936 |
| Spot check (33 records) | 30/33 correct |
| Spot check EYE_IMAGING F1 | 0.824 |

---

## Slide 5: Spot-Check Validation

### Manual Spot Check: 33 Randomly Sampled Records

- 30 of 33 records correctly classified (90.9%)
- EYE_IMAGING F1 = 0.824
- Errors were primarily borderline cases (e.g., software with sample data)

### Notable Discoveries Among 60 EYE_IMAGING Datasets

- **Human Developing Retina Atlas**: 65+ GB across 3 records
- **Corneal OCT collections**: 70+ GB across multiple studies
- **Clinical imaging studies**: RTN4IP1 optic atrophy, PCV imaging

---

## Slide 6: Top 10 Validated Datasets

| # | Dataset | Modality | Size |
|---|---------|----------|------|
| 1 | Human Developing Retina Atlas | Multi-modal | 37.7 GB |
| 2 | Corneal OCT Elastography | OCT | 34.4 GB |
| 3 | Corneal OCT Deep Learning | OCT | 36.2 GB |
| 4 | RTN4IP1 Optic Atrophy | Fundus/OCT | 5.2 GB |
| 5 | nnUNet Optic Disc Segmentation | Fundus | 1.3 GB |
| 6 | OCT Retinal Degeneration | OCT | 668 MB |
| 7 | DeepEye Retinal Disease | Fundus | 330 MB |
| 8 | PT-OCT ANN Project | OCT | 302 MB |
| 9 | Retina Phenotypes | Various | 77.9 MB |
| 10 | OCTSEG | OCT | 5.6 MB |

---

## Slide 7: Known Limitations

### False Positive Patterns (All Classified as NEGATIVE)

- Cardiovascular OCT (intravascular, coronary)
- Taxonomy papers ("FIGURES 1-10...")
- Industrial OCT/CT (materials, art conservation)
- Non-ophthalmic medical imaging
- Robotics ("hand-eye calibration")
- Eye-related software without actual imaging data
- Genetics/GWAS studies referencing retinal phenotypes

### Current Constraints

1. Single platform (Zenodo only; Figshare planned)
2. English-language bias in search terms
3. Cannot verify restricted-access contents
4. May miss datasets with unusual terminology

---

## Slide 8: Minimal Dataset Criteria

### Current Implementation

A record qualifies for classification if it has:
1. **At least one data file** (image or archive format)
2. **Metadata text** (title + description + keywords)

### Recommended Criteria for "Complete" Dataset

| Criterion | Rationale |
|-----------|-----------|
| ≥10 MB total size | Excludes metadata-only records |
| Description present | Enables accurate classification |
| ≥1 imaging file or archive | Contains actual data |
| Open access preferred | Enables reuse |

**Discussion point**: Should we filter by minimum size threshold?

---

## Slide 9: Next Steps

### Immediate (This Week)

- [ ] Complete manual validation of remaining 3 pending datasets
- [ ] Hand off integration specs to Dorian & Sanjay
- [ ] Finalize database schema for Envision Portal

### Short-term (Next 2 Weeks)

- [ ] Expand to Figshare scraping
- [ ] Add Dryad, OSF sources
- [ ] Implement confidence-based tiering in portal

### Medium-term

- [ ] Active learning: use validated results to improve classifier
- [ ] Add dataset quality scoring
- [ ] Automated monthly re-scraping

---

## Slide 10: Resources

| Resource | Link |
|----------|------|
| GitHub Repository | https://github.com/EyeACT/envision-discovery |
| HuggingFace Model | https://huggingface.co/fairdataihub/envision-eye-imaging-classifier |
| Results JSON | `results/zenodo_eye_imaging.json` |
| Validation Doc | `docs/SPOT_CHECK_VALIDATION.md` |

### Contact

- James O'Neill - Development & Validation
- Dorian & Sanjay - Database Integration
- Bhavesh - Project Lead

---

## Appendix: Confidence Score Interpretation

| Score Range | Interpretation | Recommended Action |
|-------------|----------------|-------------------|
| ≥0.95 | Strong candidate | Include automatically |
| 0.80-0.95 | Likely valid | Light review |
| 0.60-0.80 | Uncertain | Manual verification |
| <0.60 | Probably not eye imaging | Exclude unless flagged |


