# Document Update Checklist: 4-Class to Binary Migration

## Already Updated (automated)
- [x] `README.md` - Classification labels and results tables
- [x] `MODEL_CARD.md` - Full rewrite for binary model
- [x] `paper/envision_discovery_paper.md` - Abstract, methods, results, discussion
- [x] `docs/INTEGRATION_HANDOFF.md` - Schema, API, database tables
- [x] `docs/PRESENTATION_BHAVESH.md` - Slides updated
- [x] `envision-classifier/envision_classifier/classifier.py` - Module docstring, class docstring, labels, train(), predict()
- [x] HuggingFace model + README pushed to `fairdataihub/envision-eye-imaging-classifier`

## Needs Manual Update (Office files)

### `envision_expert_validation_mock_up.pptx`
**Slide 1 - Classification Label Taxonomy:**
- Remove EYE_SOFTWARE and OTHER_EYE_DATA columns
- Change to 2 classes: EYE_IMAGING and NEGATIVE
- Update subtitle: "All classes experts will adjudicate: positive and negative"

**Slide 2 - Expert Evaluation Design:**
- PART 1: Change from 4 labels to 2 (EYE_IMAGING, NEGATIVE)
- Remove OTHER_EYE_DATA button

**Slide 3 - Validation Plan & Retraining Loop:**
- Replace 4-class sampling table with:
  | Class | Population | Sample | Method |
  | EYE_IMAGING | 60 | ALL 60 | Exhaustive |
  | NEGATIVE | 455 | 100 (stratified) | Low-confidence first |
- Update "4 classes" references to "2 classes"
- Update target: "Per-class F1 for both classes"

### `ENVISION_Validation_Summary (1).docx`
- Update label options from 4 to 2 (Eye Imaging, Not Related)
- Remove "Eye Software" and "Edge Case" labels
- Update "100 records per batch" if needed
- Update any references to 4-class counts

### Validation template Excel files
- `envision_validation_template.xlsx` - Update label columns
- `envision_validation_sheet_sanjay.xlsx` - Check if label options need updating

## Recommend Also Updating
- [ ] `envision/pipeline.py` - docstrings referencing 4 classes
- [ ] `envision/addf_export.py` - ADDF schema if it exports class labels
- [ ] `eval/model_eval.py` - SPOT_CHECK list (expand to 100 records)
- [ ] `eval/binary_hyperparameter_report.md` - Add note that this is historical comparison
- [ ] `create_overview_slides.py` - If it generates slides with class counts
- [ ] `paper/build_paper.py` - If it injects metrics into the paper
- [ ] Re-run classification pipeline on all repositories with new binary model to get updated counts
