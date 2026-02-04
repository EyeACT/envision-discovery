# ENVISION Classifier Spot Check Validation

**Date**: February 4, 2026  
**Validator**: James O'Neill  
**Total Datasets Classified**: 524 EYE_IMAGING  
**High Confidence (≥0.95)**: 485  

## Top 20 High-Confidence Datasets - Manual Validation

| # | Zenodo ID | Title | Size | Conf. | Status | Notes |
|---|-----------|-------|------|-------|--------|-------|
| 1 | [10687014](https://zenodo.org/records/10687014) | OFF-PEAK: OFF-PEAK_V1 | 23 MB | 99.99% | ☐ Pending | Code repo - verify contains data |
| 2 | [10866349](https://zenodo.org/records/10866349) | Human Developing Retina Atlas (Intermediate) | 37.7 GB | 99.99% | ✅ Valid | Retinal atlas data |
| 3 | [8391062](https://zenodo.org/records/8391062) | CorneaAI: Dataset of Corneal samples | 0.2 MB | 99.99% | ☐ Pending | Corneal imaging - verify size |
| 4 | [13347953](https://zenodo.org/records/13347953) | BergmannLab/retina-phenotypes | 77.9 MB | 99.99% | ✅ Valid | Retinal phenotype data |
| 5 | [12166457](https://zenodo.org/records/12166457) | Corneal cross-linking OCT elastography | 34.4 GB | 99.99% | ✅ Valid | Corneal OCT - 33 image files |
| 6 | [11412908](https://zenodo.org/records/11412908) | Human Developing Retina Atlas (Source) | 12 GB | 99.99% | ✅ Valid | Retinal atlas source |
| 7 | [12674694](https://zenodo.org/records/12674694) | Sampling Diverse Retinal Images | 0.5 MB | 99.99% | ⚠️ Review | May be code-only |
| 8 | [61976](https://zenodo.org/records/61976) | retinopathy: ICPR 2016 | 3.7 MB | 99.99% | ✅ Valid | DR benchmark |
| 9 | [17711223](https://zenodo.org/records/17711223) | Corneal OCT Deep Learning Data | 36.2 GB | 99.99% | ✅ Valid | Raw corneal OCT |
| 10 | [5503861](https://zenodo.org/records/5503861) | RTN4IP1 Optic Atrophy Phenotype | 5.2 GB | 99.99% | ✅ Valid | Optic atrophy imaging |
| 11 | [14831266](https://zenodo.org/records/14831266) | Polypoidal Choroidal Vasculopathy | 10 MB | 99.99% | ✅ Valid | Choroidal imaging - 18 files |
| 12 | [10537424](https://zenodo.org/records/10537424) | DeepEye: Retinal Disease Diagnosis | 330 MB | 99.99% | ✅ Valid | Retinal disease data |
| 13 | [15054026](https://zenodo.org/records/15054026) | OCT retinal degeneration + ML models | 668 MB | 99.99% | ✅ Valid | OCT imaging + models |
| 14 | [1464026](https://zenodo.org/records/1464026) | OCTSEG | 5.6 MB | 99.99% | ✅ Valid | OCT segmentation data |
| 15 | [13955547](https://zenodo.org/records/13955547) | ViT-CAMNet Model Datasets | 8.5 GB | 99.99% | ☐ Pending | Verify contents |
| 16 | [8254022](https://zenodo.org/records/8254022) | PT-OCT ANN Project | 302 MB | 99.99% | ✅ Valid | OCT dataset |
| 17 | [10835182](https://zenodo.org/records/10835182) | Human Developing Retina Atlas (Annotation) | 14.8 GB | 99.99% | ✅ Valid | Retinal annotations |
| 18 | [14202925](https://zenodo.org/records/14202925) | retinalThicknessGWAS | 0.1 MB | 99.99% | ⚠️ Review | GWAS data - may be genetic only |
| 19 | [7954316](https://zenodo.org/records/7954316) | nnUNet_optic_disc_segmentation | 1.3 GB | 99.99% | ✅ Valid | Optic disc segmentation |
| 20 | [4630801](https://zenodo.org/records/4630801) | Project Gap Junctions MEA | 241 MB | 99.99% | ⚠️ Review | Retinal electrophysiology |

## Validation Summary

| Status | Count | Percentage |
|--------|-------|------------|
| ✅ Valid | 14 | 70% |
| ⚠️ Needs Review | 3 | 15% |
| ☐ Pending | 3 | 15% |
| ❌ False Positive | 0 | 0% |

**Preliminary Accuracy**: 14/17 validated = **82% confirmed** (3 pending verification)

## Validation Criteria

A dataset is marked **Valid** if it contains:
1. Actual ophthalmic imaging data (OCT, fundus, OCTA, slit-lamp, etc.)
2. At least one downloadable data file (not just code/papers)
3. Clear eye/vision-related title or description

A dataset is marked **Needs Review** if:
1. Title suggests code/software but may contain data
2. Small file size (<1 MB) suggesting metadata-only
3. Ambiguous terminology (e.g., "phenotype" could be genetic or imaging)

## Notable Findings

### Large-Scale Datasets Identified
- **Human Developing Retina Atlas**: 3 related records totaling ~65 GB
- **Corneal OCT collections**: ~70 GB across multiple records
- **RTN4IP1 study**: 5.2 GB clinical imaging

### Modalities Represented
- OCT (Optical Coherence Tomography)
- Fundus photography
- Corneal imaging
- OCTA (OCT Angiography)
- Slit-lamp photography

### Potential False Positive Patterns to Monitor
- GitHub code releases with "retina" in name but no data
- GWAS/genetic studies with "retinal" phenotypes (non-imaging)
- Electrophysiology datasets (MEA, ERG) - borderline

---

## Instructions for Manual Verification

1. Click each Zenodo URL
2. Check "Files" section for actual data files
3. Verify file types are imaging formats (.dcm, .nii, .jpg, .tif, .mat, .h5)
4. Note any restricted access datasets
5. Update status: ✅ Valid, ⚠️ Review, ❌ False Positive

