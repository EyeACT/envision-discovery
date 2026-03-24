# Envision Discovery: Automated Identification of Eye Imaging Datasets Across Scientific Repositories

**James O'Neill¹, [Validator Names]², Bhavesh Patel¹**

¹ FAIR Data Innovations Hub, California Medical Innovations Institute (CalMI²), San Diego, CA, USA
² [Validator Affiliations]

**Correspondence:** joneill@calmi2.org, bpatel@calmi2.org

---

## Abstract

Eye imaging datasets—including optical coherence tomography (OCT), fundus photography, and OCT angiography (OCTA)—are essential resources for developing artificial intelligence (AI) tools in ophthalmology. However, these datasets are scattered across generalist repositories with no centralized catalog, making discovery and reuse prohibitively difficult. Here we present Envision Discovery, a machine learning pipeline that automatically identifies eye imaging datasets from scientific data repositories. The system uses a SetFit few-shot classifier built on a sentence embedding model (mpnet-base, 768-dimensional) trained on 891 curated examples to distinguish two classes: genuine eye imaging datasets (EYE_IMAGING) and everything else (NEGATIVE). Applied to 30,439 metadata records harvested from Zenodo, the pipeline identified 60 eye imaging datasets from 515 records containing data files. On a held-out test set, the classifier achieved accuracy of 0.961 and macro F1 of 0.954; a spot check of 33 randomly sampled records confirmed 30 correct (EYE_IMAGING F1 = 0.824). All identified datasets are registered on the Envision Portal (https://envisionportal.org), providing researchers with a single entry point for discovering publicly available ophthalmic imaging data. The classifier, pipeline code, and trained model are openly available at https://github.com/EyeACT/envision-discovery.

**Keywords:** eye imaging, dataset discovery, machine learning, FAIR data, ophthalmology, OCT, fundus photography, SetFit, few-shot learning, binary classification

---

## 1. Introduction

Eye imaging modalities such as OCT, OCTA, fundus photography, and fluorescence lifetime imaging ophthalmoscopy (FLIO) provide detailed structural and functional views of ocular tissues and have become indispensable for ophthalmic research and clinical innovation. These datasets have been particularly critical for developing AI-based diagnostic tools. RETFound, a self-supervised foundation model trained on 1.6 million unlabeled retinal images, demonstrated state-of-the-art performance across both ophthalmic and systemic disease detection tasks (Zhou et al., 2023). OphGLM combined fundus photography with natural language capabilities for diagnostic support (OphGLM, 2024), while Ophtha-LLaMA2 fine-tuned a large language model on multimodal ophthalmic data for efficient clinical deployment (Zhao et al., 2023). These advances depend critically on the availability and accessibility of large-scale imaging datasets.

However, sharing and discovering eye imaging data remains a significant challenge. Unlike neuroimaging, where community standards such as BIDS (Gorgolewski et al., 2016) and centralized platforms like OpenNeuro (Markiewicz et al., 2021) have transformed data sharing practices, ophthalmology lacks equivalent infrastructure. Eye imaging datasets are fragmented across generalist repositories—Zenodo, Figshare, Dryad, and institutional archives—that do not support ophthalmic-specific metadata or enforce standardized data formatting. This fragmentation makes datasets difficult to find and, when found, often difficult to reuse (Gim et al., 2025).

We experienced this challenge directly when searching for open-access OCT data related to age-related macular degeneration (AMD). Despite extensive multi-platform searches using diverse query strategies, finding relevant datasets was time-consuming and often required reading through published manuscripts on PubMed to locate associated data deposits (Gim et al., 2025). The absence of a centralized, searchable catalog means that researchers routinely duplicate collection efforts or remain unaware of existing data that could accelerate their work.

To address this gap, we developed Envision Discovery, an automated pipeline that harvests metadata from scientific data repositories, classifies records using a few-shot machine learning model, and identifies those containing eye imaging data. The identified datasets are then registered on the Envision Portal (https://envisionportal.org), a platform developed as part of the Eye Aging, Cognition, and Imaging (EyeACT) study to share and discover FAIR (Findable, Accessible, Interoperable, Reusable) and AI-ready eye imaging datasets. In this paper, we describe the design and implementation of the Envision Discovery pipeline, present results from its application to the Zenodo repository, and report on expert validation of classifier predictions by ophthalmology domain specialists.

---

## 2. Methods

### 2.1 Overview

The Envision Discovery pipeline consists of four stages: (1) metadata harvesting from scientific repositories, (2) intelligent filtering and enrichment, (3) automated classification using a few-shot learning model, and (4) expert validation. Figure 1 provides an overview of the pipeline architecture.

[**Figure 1.** Pipeline overview: metadata harvesting → filtering & enrichment → classification → expert validation → Envision Portal registration.]

### 2.2 Metadata Harvesting

We developed a scraper targeting the Zenodo repository (https://zenodo.org), a general-purpose open repository operated by CERN that hosts over 3 million research outputs. The scraper queries the Zenodo REST API using 249 unique search terms spanning:

- **Imaging modalities:** OCT, OCTA, SD-OCT, SS-OCT, AS-OCT, fundus photography, fluorescein angiography, indocyanine green angiography (ICGA), slit-lamp biomicroscopy, confocal microscopy, adaptive optics, photoacoustic imaging
- **Anatomical structures:** retina, macula, fovea, optic nerve/disc, choroid, cornea, lens, iris, anterior chamber
- **Retinal layers:** retinal nerve fiber layer (RNFL), ganglion cell layer (GCL), retinal pigment epithelium (RPE), ellipsoid zone
- **Diseases:** diabetic retinopathy, glaucoma, AMD, diabetic macular edema (DME), retinal detachment, retinitis pigmentosa, Stargardt disease, keratoconus, retinopathy of prematurity (ROP)
- **Equipment and vendors:** Heidelberg Spectralis, Zeiss Cirrus, Topcon Triton/DRI OCT, Optovue RTVue, Optos
- **Benchmark datasets:** DRIVE, STARE, CHASE_DB1, MESSIDOR, IDRiD, APTOS, REFUGE, EyePACS, AIROGS
- **Clinical measurements:** visual acuity, LogMAR, RNFL thickness, central macular thickness (CMT), cup-to-disc ratio, vessel density, foveal avascular zone (FAZ) area

Search results are filtered to include only records with `resource_type=dataset`, excluding publications, software, and miscellaneous uploads.

### 2.3 Filtering and Metadata Enrichment

Retrieved records undergo several enrichment steps:

**File-type filtering.** Records are retained if they contain recognized data files (`.dcm`, `.nii`, `.nii.gz`, `.mat`, `.h5`, `.hdf5`, `.npy`, `.npz`, `.jpg`, `.jpeg`, `.png`, `.tif`, `.tiff`, `.bmp`) or archives (`.zip`, `.tar.gz`, `.rar`, `.7z`). Records containing only genomics files (`.fasta`, `.h5ad`, `.vcf`, `.bam`, `.fastq`) are excluded to reduce false positives from genomics studies that reference ophthalmic phenotypes.

**ZIP content inspection.** For archived records, we implemented a non-destructive inspection technique using HTTP Range requests. By downloading only the ZIP central directory (the last ~64 KB of the archive), we extract the complete file manifest without downloading the full archive. This catalogued 31,958 files across all inspected archives and enabled accurate file-type profiling at minimal bandwidth cost.

**Link extraction.** External dataset links are extracted from Zenodo's `related_identifiers` metadata field and from description text, capturing references to platforms including GitHub, Kaggle, HuggingFace, Google Drive, OSF, Dryad, Figshare, and others. Links are categorized as data platform, archive download, direct file, or potential download.

**Metadata normalization.** For each record, we extract and normalize: title, description (HTML stripped), keywords, file types, file counts, total size, and counts of imaging, medical, archive, and genomics files.

### 2.4 Classification Model

#### 2.4.1 Architecture

We use SetFit (Tunstall et al., 2022), a few-shot text classification framework that combines contrastive learning on sentence embeddings with a lightweight classification head. SetFit is well-suited to our task because it achieves strong performance with limited labeled data—critical given the specialized nature of ophthalmic dataset descriptions.

The backbone model is `sentence-transformers/all-mpnet-base-v2`, a general-purpose sentence embedding model producing 768-dimensional representations. It uses 12 transformer layers with 12 attention heads, based on the MPNet architecture (Song et al., 2020). The classification head is a logistic regression model trained on the contrastively learned embeddings.

#### 2.4.2 Classification Schema

Records are classified into two mutually exclusive categories:

| Class | Label | Description |
|-------|-------|-------------|
| 1 | **EYE_IMAGING** | Contains actual ophthalmic imaging data (e.g., OCT scans, fundus photographs, OCTA images, corneal imaging, slit-lamp photographs) |
| 0 | **NEGATIVE** | Everything that is not actual eye imaging data, including software/code, other eye-related data (genetics, electrophysiology, eye tracking), and records unrelated to eye research |

This binary schema was chosen to optimize precision for the core task: identifying records that contain actual eye imaging data. Software repositories, GWAS studies referencing retinal phenotypes, electrophysiology studies (ERG, VEP), and non-ophthalmic uses of shared terminology (cardiovascular OCT, industrial OCT, dental OCT) are all classified as NEGATIVE. This approach reduces false positives compared to a multi-class schema, where boundary ambiguities between intermediate classes could propagate errors into the positive class.

#### 2.4.3 Training Data

The training set consists of 891 manually curated examples drawn from multiple repository sources:

| Class | Count | Proportion | Representative Examples |
|-------|-------|------------|------------------------|
| EYE_IMAGING | 262 | 29.4% | IDRiD, REFUGE, RFMiD, OLIVES, Rotterdam EyePACS, retinal vessel segmentation datasets, clinical OCT/OCTA collections |
| NEGATIVE | 629 | 70.6% | Software/code repositories, eye tracking studies, GWAS meta-analyses, climate data, COVID genomics, face recognition (LFW), cardiac imaging, brain MRI, MNIST, robotics, taxonomy papers |

Training examples were curated to cover known confounding patterns, with particular attention to negative examples that share superficial similarity with eye imaging (e.g., intravascular OCT, hand-eye calibration in robotics, taxonomy papers with figure references, eye-related software without actual imaging data, genetics studies referencing retinal phenotypes). The model was trained for 2 epochs with a batch size of 16.

#### 2.4.4 Input Representation

For each record, the classifier receives a concatenation of the title, description (with HTML tags removed), and keywords as a single text input. This combined representation provides sufficient context for the embedding model to capture both the domain specificity (ophthalmology vs. other fields) and the data-type specificity (imaging data vs. software vs. publications).

### 2.5 Expert Validation Protocol

To rigorously evaluate classifier performance across repositories, we designed a multi-validator expert review protocol using stratified sampling from all six data sources.

#### 2.5.1 Sample Size Determination

Using Cochran's formula with finite population correction:

n₀ = (Z² × p × (1-p)) / e² = (1.96² × 0.5 × 0.5) / 0.05² = 384

n = n₀ / (1 + (n₀ - 1) / N) = 384 / (1 + 383/4,674) = 356

where Z = 1.96 (95% confidence), p = 0.5 (maximum variability), e = 0.05 (5% margin of error), and N = 4,674 (total unique records across all repositories). This yields a required sample of **356 records**.

#### 2.5.2 Stratified Sampling

Records are sampled proportionally by repository and predicted class, with confidence-stratified selection within each stratum to ensure experts review both high-confidence and borderline predictions.

| Source | Unique Records | Sample Size | Predicted EYE_IMAGING | Predicted NEGATIVE |
|--------|---------------|-------------|----------------------|-------------------|
| Zenodo | 502 | 38 | 5 | 33 |
| DataCite | 1,061 | 81 | 32 | 49 |
| Figshare | 1,620 | 123 | 66 | 57 |
| Kaggle | 667 | 51 | 21 | 30 |
| Dryad | 37 | 3 | 0 | 3 |
| NEI | 787 | 60 | 23 | 37 |
| **Total** | **4,674** | **356** | **147** | **209** |

Within each repository stratum, records are further stratified by model confidence into thirds (high >0.95, medium 0.80–0.95, low <0.80).

#### 2.5.3 Validation Interface

Each validator is presented with dataset records including:
- Dataset title and source repository
- Brief description/abstract
- Keywords and file types detected
- Link to the original record

For each record, validators assign a score from 0 to 5:
- **5**: Certain eye imaging dataset
- **4**: Likely eye imaging, minor doubt
- **3**: Possible eye imaging, uncertain
- **2**: Unlikely eye imaging, significant doubt
- **1**: Likely not eye imaging
- **0**: Certain not eye imaging

Scores ≥ 3 are mapped to EYE_IMAGING and scores ≤ 2 to NEGATIVE for computing binary classifier metrics. Model predictions and confidence scores are withheld from validators to prevent anchoring bias.

#### 2.5.4 Validation Batches

Records are distributed to validators in batches of 100. Each batch includes records from multiple repositories and a mix of confidence levels. Three independent reviewers annotate all 356 records with full overlap, enabling pairwise and multi-rater agreement analysis. Each batch is estimated to require 1.5–5 hours of reviewer time.

#### 2.5.5 Evaluation Metrics

Classifier performance is evaluated using:
- **Precision** (positive predictive value): proportion of EYE_IMAGING predictions confirmed by experts
- **Recall** (sensitivity): proportion of true eye imaging datasets correctly identified
- **F1 Score**: harmonic mean of precision and recall, reported per class and as macro average
- **Confusion matrix**: 2×2 predicted vs. actual with 95% bootstrap confidence intervals
- **Inter-rater agreement**: Cohen's kappa (pairwise) and Fleiss' kappa (multi-rater), target κ ≥ 0.70
- **Per-repository performance**: F1 reported separately for each source to assess cross-repository generalizability
- **Confidence calibration**: accuracy vs. confidence bins (reliability diagram)

---

## 3. Results

### 3.1 Metadata Harvesting

The scraper retrieved metadata for 30,439 records from Zenodo matching at least one of the 249 search terms. After file-type filtering, 514 records (1.7%) contained recognized data files or archives and were retained for classification. The low retention rate reflects the predominance of publications, software, and non-data records in Zenodo search results, even when filtering for `resource_type=dataset`.

### 3.2 Classification Results

Of the 515 filtered records, the binary classifier produced the following distribution:

| Class | Count | Proportion |
|-------|-------|------------|
| EYE_IMAGING | 60 | 11.7% |
| NEGATIVE | 455 | 88.3% |

The binary classifier identified 60 EYE_IMAGING datasets, a substantial reduction from the 127 identified by the earlier 4-class model. This reduction reflects improved precision: records previously spread across EYE_SOFTWARE, OTHER_EYE_DATA, and borderline EYE_IMAGING categories are now correctly assigned to NEGATIVE, yielding fewer false positives among the positive predictions.

The identified eye imaging datasets span a range of modalities including OCT, OCTA, fundus photography, corneal imaging, and slit-lamp photography, with individual datasets ranging from a few megabytes (segmentation benchmarks) to 37.7 GB (Human Developing Retina Atlas).

### 3.3 Held-Out Test Set Evaluation

A held-out test set evaluation yielded the following performance:

| Metric | Value |
|--------|-------|
| Accuracy | 0.961 |
| Macro F1 | 0.954 |
| EYE_IMAGING F1 | 0.936 |

These results demonstrate strong discriminative performance for the binary classification task, with the model reliably separating genuine eye imaging datasets from all other record types.

### 3.4 Spot-Check Validation

A spot-check validation of 33 randomly sampled records across both classes was conducted. Of 33 records evaluated, 30 (90.9%) were correctly classified, with an EYE_IMAGING F1 of 0.824.

[**Table 1.** Spot-check validation results. Includes Zenodo ID, title, dataset size, confidence score, and validation status.]

Notable discoveries among the 60 identified eye imaging datasets include:
- **Human Developing Retina Atlas**: 3 related records totaling over 65 GB of multi-modal retinal imaging data
- **Corneal OCT collections**: Over 70 GB across multiple studies using Spectralis, Zeiss, and Topcon instruments
- **Clinical imaging studies**: RTN4IP1 optic atrophy (5.2 GB), polypoidal choroidal vasculopathy/choroidal neovascularization imaging
- **Segmentation benchmarks**: nnUNet optic disc segmentation, OCTSEG, retinal vessel datasets

---

## 4. Discussion

### 4.1 Automated Dataset Discovery as Infrastructure

Envision Discovery demonstrates the feasibility of using few-shot machine learning to automate the identification of domain-specific datasets from generalist repositories. The 891-example training set—small by typical machine learning standards—proved sufficient to learn discriminative features for ophthalmic imaging datasets when combined with the strong pre-trained representations of mpnet-base and the contrastive learning framework of SetFit. This few-shot approach is particularly advantageous for specialized scientific domains where large labeled datasets are impractical to construct.

The binary classification schema (EYE_IMAGING vs. NEGATIVE) proved well-suited for practical deployment. By collapsing software tools, other eye-related data, and truly unrelated records into a single NEGATIVE class, the classifier focuses exclusively on the core task—identifying records that contain actual eye imaging data. This design reduces false positives that arose in earlier multi-class iterations, where boundary ambiguities between intermediate classes (e.g., software repositories containing sample images, genetics studies referencing retinal phenotypes) could propagate errors into the positive class. The reduction from 127 to 60 identified datasets on the Zenodo corpus reflects this improved precision.

### 4.2 Confidence-Based Triaging

The classifier's confidence distribution suggests effective separation of clear positives from ambiguous cases. This enables a confidence-based triaging strategy for the Envision Portal: high-confidence predictions can be surfaced immediately with minimal review overhead, while lower-confidence predictions are prioritized for expert validation. Such a strategy can scale dataset discovery to much larger repository collections without proportionally increasing validation burden.

### 4.3 Challenges and False Positive Patterns

Several categories of records posed classification challenges:

- **Non-ophthalmic OCT:** Cardiovascular, dermatological, and industrial OCT share imaging terminology but are unrelated to ophthalmology. The training set includes explicit negative examples for these domains.
- **Code-with-data hybrids:** Some software repositories include small sample datasets alongside code. These are classified as NEGATIVE under the binary schema since they are primarily software, not imaging datasets.
- **Genetics with retinal phenotypes:** GWAS and genetic studies that reference retinal measurements (e.g., RNFL thickness as a phenotype) are clinically adjacent but do not contain imaging data and are classified as NEGATIVE.
- **Multi-domain repositories:** Some Zenodo records aggregate heterogeneous content where eye imaging is a minor component.

### 4.4 Comparison with Manual Discovery

The contrast between automated and manual dataset discovery is stark. Gim et al. (2025) documented the extensive effort required to manually locate AMD-related OCT datasets: multi-platform searches, diverse query strategies, manuscript reading on PubMed, and still only a small number of datasets meeting eligibility criteria. Envision Discovery screened 30,439 records and identified 60 eye imaging datasets in approximately 30 minutes of compute time—a task that would take weeks or months of manual effort and would inevitably miss datasets described with non-standard terminology.

### 4.5 Limitations

Several limitations should be acknowledged:

1. **Repository coverage.** While multi-repository support (Zenodo, Figshare, Dryad, OSF, DataCite) is now implemented, coverage of institutional repositories and non-English platforms remains limited.
2. **Language bias.** Search terms and training examples are in English. Datasets described in other languages may be missed.
3. **Metadata-only classification.** The classifier operates on metadata (titles, descriptions, keywords) without examining actual data files. Records with uninformative metadata may be misclassified.
4. **Restricted-access records.** Content behind access controls cannot be independently verified without requesting access.
5. **Evolving repositories.** New deposits, updated metadata, and removed records require periodic re-scraping to maintain currency.
6. **Training set size.** While 891 examples proved sufficient for the current task, performance on rare or novel dataset types may be limited.

### 4.6 Future Directions

Immediate next steps include:
- **Multi-repository expansion:** Adapting the scraper for Figshare, Dryad, OSF, and DataCite Commons
- **Active learning:** Using expert validation results to iteratively refine the training set and retrain the classifier
- **Dataset quality scoring:** Developing automated metrics for metadata completeness, documentation quality, and AI-readiness
- **Continuous monitoring:** Implementing automated monthly re-scraping with incremental classification updates
- **Multilingual support:** Expanding search terms and training examples to support non-English datasets

---

## 5. Conclusion

We present Envision Discovery, an automated pipeline for identifying eye imaging datasets across scientific repositories. By combining targeted metadata harvesting, intelligent filtering with non-destructive archive inspection, and few-shot binary classification using SetFit, the system identified 60 eye imaging datasets from over 30,000 Zenodo records with strong performance (held-out test accuracy 0.961, macro F1 0.954; spot-check 30/33 correct). The discovered datasets, spanning OCT, OCTA, fundus photography, and other ophthalmic modalities, are now catalogued on the Envision Portal, providing the research community with a centralized resource for finding publicly available eye imaging data. As the pipeline extends to additional repositories and incorporates feedback from expert validation, Envision Discovery will serve as a continuously expanding, community-validated catalog to accelerate AI development and clinical research in ophthalmology.

---

## Data and Code Availability

- **Pipeline code and trained model:** https://github.com/EyeACT/envision-discovery
- **HuggingFace model:** https://huggingface.co/fairdataihub/envision-eye-imaging-classifier
- **Envision Portal:** https://envisionportal.org
- **Classified results:** Available in the repository under `results/`

---

## Acknowledgments

This work was supported by [NIH grant number]. The Envision Portal is developed as part of the Eye Aging, Cognition, and Imaging (EyeACT) study (https://eyeactstudy.org). We thank [validator names] for their expert validation of classifier predictions. [Additional acknowledgments.]

---

## References

Gim, N., et al. (2025). Publicly available imaging datasets for age-related macular degeneration: Evaluation according to the Findable, Accessible, Interoperable, Reusable (FAIR) principles. *Experimental Eye Research*, 255, 110342.

Gorgolewski, K. J., et al. (2016). The brain imaging data structure, a format for organizing and describing outputs of neuroimaging experiments. *Scientific Data*, 3, 160044.

Markiewicz, C. J., et al. (2021). The OpenNeuro resource for sharing of neuroscience data. *eLife*, 10, e71774.

OphGLM. (2024). OphGLM: An ophthalmology large language-and-vision assistant. *Artificial Intelligence in Medicine*, 157, 103001.

Tunstall, L., et al. (2022). Efficient few-shot learning without prompts. arXiv:2209.11055.

Wang, Z., et al. (2022). Artificial Intelligence and Deep Learning in Ophthalmology. In *Artificial Intelligence in Medicine* (pp. 1519–1552).

Zhao, H., et al. (2023). Ophtha-LLaMA2: A Large Language Model for Ophthalmology. arXiv preprint.

Zhou, Y., et al. (2023). A foundation model for generalizable disease detection from retinal images. *Nature*, 622, 156–163.

Tan, Y. Y., et al. (2024). Prognostic potentials of AI in ophthalmology: systemic disease forecasting via retinal imaging. *Eye and Vision*, 11, 1–18.

(Patoni), S. I. P., et al. (2023). Artificial intelligence in ophthalmology. *Romanian Journal of Ophthalmology*, 67, 207.
