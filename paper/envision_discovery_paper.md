# Envision Discovery: Automated Identification of Eye Imaging Datasets Across Scientific Repositories

**James O'Neill¹, [Validator Names]², Bhavesh Patel¹**

¹ FAIR Data Innovations Hub, California Medical Innovations Institute (CalMI²), San Diego, CA, USA
² [Validator Affiliations]

**Correspondence:** joneill@calmi2.org, bpatel@calmi2.org

---

## Abstract

Eye imaging datasets—including optical coherence tomography (OCT), fundus photography, and OCT angiography (OCTA)—are essential resources for developing artificial intelligence (AI) tools in ophthalmology. However, these datasets are scattered across generalist repositories with no centralized catalog, making discovery and reuse prohibitively difficult. Here we present Envision Discovery, a machine learning pipeline that automatically identifies eye imaging datasets from scientific data repositories. The system uses a SetFit few-shot classifier built on a sentence embedding model (mpnet-base, 768-dimensional) trained on 474 curated examples to distinguish four classes: genuine eye imaging datasets, eye-related software, other eye datas, and unrelated records. Applied to 30,439 metadata records harvested from Zenodo, the pipeline identified 127 candidate eye imaging datasets from 515 records containing data files, with high confidence across positive predictions. Expert validation by [N] ophthalmology specialists across [N] independent batches confirmed a precision of [XX]% for high-confidence predictions. All identified datasets are registered on the Envision Portal (https://envisionportal.org), providing researchers with a single entry point for discovering publicly available ophthalmic imaging data. The classifier, pipeline code, and trained model are openly available at https://github.com/EyeACT/envision-discovery.

**Keywords:** eye imaging, dataset discovery, machine learning, FAIR data, ophthalmology, OCT, fundus photography, SetFit, few-shot learning

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

Records are classified into four mutually exclusive categories:

| Class | Label | Description |
|-------|-------|-------------|
| 3 | **EYE_IMAGING** | Contains actual ophthalmic imaging data (e.g., OCT scans, fundus photographs, OCTA images, corneal imaging, slit-lamp photographs) |
| 2 | **EYE_SOFTWARE** | Code, tools, or pre-trained models related to eye imaging analysis, but no actual image data |
| 1 | **OTHER_EYE_DATA** | Related to eye or vision research but not imaging datasets (e.g., genetics/GWAS, electrophysiology, eye tracking, animal models) |
| 0 | **NEGATIVE** | Unrelated to eye or vision research |

This four-class schema was designed to address specific false-positive patterns observed during development. For example, cardiovascular OCT (intravascular OCT of coronary arteries), industrial OCT (semiconductor inspection), and dental OCT are classified as NEGATIVE despite sharing terminology with ophthalmic OCT. Software repositories containing eye imaging analysis tools but no image data are common on Zenodo and are captured by the EYE_SOFTWARE class. GWAS studies referencing retinal phenotypes and electrophysiology studies (ERG, VEP) are captured as OTHER_EYE_DATA.

#### 2.4.3 Training Data

The training set consists of 474 manually curated examples:

| Class | Count | Proportion | Representative Examples |
|-------|-------|------------|------------------------|
| EYE_IMAGING | 77 | 16.2% | IDRiD, REFUGE, RFMiD, OLIVES, Rotterdam EyePACS, retinal vessel segmentation datasets |
| EYE_SOFTWARE | 48 | 10.1% | GitHub repositories, segmentation model weights, Python/MATLAB packages, ImageJ plugins |
| OTHER_EYE_DATA | 79 | 16.7% | DR detection review papers, glaucoma ML literature, GWAS meta-analyses, zebrafish/Drosophila eye development, eye tracking, eye metabolomics |
| NEGATIVE | 270 | 57.0% | Climate data, COVID genomics, face recognition (LFW), cardiac imaging, brain MRI, MNIST, robotics, taxonomy papers |

Training examples were curated to cover known confounding patterns, with particular attention to negative examples that share superficial similarity with eye imaging (e.g., intravascular OCT, hand-eye calibration in robotics, taxonomy papers with figure references). The model was trained for 2 epochs with a batch size of 16.

#### 2.4.4 Input Representation

For each record, the classifier receives a concatenation of the title, description (with HTML tags removed), and keywords as a single text input. This combined representation provides sufficient context for the embedding model to capture both the domain specificity (ophthalmology vs. other fields) and the data-type specificity (imaging data vs. software vs. publications).

### 2.5 Expert Validation Protocol

To rigorously evaluate classifier performance, we designed a multi-validator expert review protocol. Ophthalmology domain specialists independently review classifier predictions through a dedicated web interface.

#### 2.5.1 Validation Interface

Each validator is presented with dataset records including:
- Dataset title
- Brief description/abstract
- File types contained in the record
- Link to the original Zenodo record

For each record, validators assign one of the four classification labels (Eye Imaging, Eye Software, Other Eye Data, Not Related) and a confidence score from 0 to 5 indicating their certainty in the assessment.

#### 2.5.2 Validation Batches

Records are distributed to validators in batches of 50. Each batch is designed to include a mix of high-confidence and lower-confidence classifier predictions to evaluate performance across the confidence spectrum. [Multiple validators review overlapping subsets to enable inter-rater agreement analysis.] Each batch is estimated to require 1–3 hours of reviewer time.

#### 2.5.3 Evaluation Metrics

Classifier performance is evaluated using:
- **Precision** (positive predictive value): proportion of EYE_IMAGING predictions that are confirmed by experts
- **Recall** (sensitivity): proportion of true eye imaging datasets correctly identified by the classifier [assessed via a held-out sample of manually curated records]
- **Inter-rater agreement**: Cohen's kappa or Fleiss' kappa for overlapping validation batches
- **Confidence calibration**: correlation between classifier confidence scores and expert agreement rates

---

## 3. Results

### 3.1 Metadata Harvesting

The scraper retrieved metadata for 30,439 records from Zenodo matching at least one of the 249 search terms. After file-type filtering, 514 records (1.7%) contained recognized data files or archives and were retained for classification. The low retention rate reflects the predominance of publications, software, and non-data records in Zenodo search results, even when filtering for `resource_type=dataset`.

### 3.2 Classification Results

Of the 515 filtered records, the classifier produced the following distribution:

| Class | Count | Proportion |
|-------|-------|------------|
| NEGATIVE | 332 | 64.5% |
| EYE_IMAGING | 127 | 24.7% |
| OTHER_EYE_DATA | 32 | 6.2% |
| EYE_SOFTWARE | 24 | 4.7% |

The 127 EYE_IMAGING predictions showed high confidence across the board, with the classifier demonstrating well-separated class boundaries. The mpnet-base backbone also produced a more balanced distribution across the non-negative classes compared to previous iterations, correctly distinguishing more other eye datas and separating software from imaging datasets.

The identified eye imaging datasets span a total volume of approximately 489.4 GB, with individual datasets ranging from a few megabytes (segmentation benchmarks) to 37.7 GB (Human Developing Retina Atlas). Represented modalities include OCT, OCTA, fundus photography, corneal imaging, and slit-lamp photography.

### 3.3 Preliminary Spot-Check Validation

A spot-check validation of 33 randomly sampled records across all classes was conducted (Table 1). Of 33 records evaluated, 29 (87.9%) were correctly classified, yielding a spot-check macro F1 of 0.828. Per-class spot-check F1 scores were: EYE_IMAGING 0.947, OTHER_EYE_DATA 0.889, NEGATIVE 0.903, and EYE_SOFTWARE 0.571 (lowest due to small sample size).

[**Table 1.** Spot-check validation of the top 20 high-confidence EYE_IMAGING predictions. Includes Zenodo ID, title, dataset size, confidence score, and validation status.]

Notable discoveries include:
- **Human Developing Retina Atlas**: 3 related records totaling over 65 GB of multi-modal retinal imaging data
- **Corneal OCT collections**: Over 70 GB across multiple studies using Spectralis, Zeiss, and Topcon instruments
- **Clinical imaging studies**: RTN4IP1 optic atrophy (5.2 GB), polypoidal choroidal vasculopathy/choroidal neovascularization imaging
- **Segmentation benchmarks**: nnUNet optic disc segmentation, OCTSEG, retinal vessel datasets

### 3.4 Expert Validation Results

In addition to the spot-check, a held-out test set evaluation yielded accuracy of 0.937 and macro F1 of 0.902. Per-class spot-check F1 scores provide insight into per-category performance:

| Class | Spot-Check F1 | Test Set F1 |
|-------|--------------|-------------|
| EYE_IMAGING | 0.947 | ~0.95 |
| OTHER_EYE_DATA | 0.889 | ~0.90 |
| NEGATIVE | 0.903 | ~0.95 |
| EYE_SOFTWARE | 0.571 | ~0.80 |

[N] ophthalmology specialists validated [N] records across [N] batches of 50. Overall results:

- **Precision for EYE_IMAGING (high confidence, >=0.95):** [XX]%
- **Precision for EYE_IMAGING (all confidence levels):** [XX]%
- **Inter-rater agreement (Cohen's kappa):** [X.XX]
- **False positive rate:** [XX]%
- **Common misclassification patterns:** [to be determined]

[**Table 2.** Expert validation confusion matrix across all validated records.]

[**Figure 2.** Classifier confidence vs. expert agreement rate, demonstrating calibration of confidence scores.]

---

## 4. Discussion

### 4.1 Automated Dataset Discovery as Infrastructure

Envision Discovery demonstrates the feasibility of using few-shot machine learning to automate the identification of domain-specific datasets from generalist repositories. The 474-example training set—small by typical machine learning standards—proved sufficient to learn discriminative features for ophthalmic imaging datasets when combined with the strong pre-trained representations of mpnet-base and the contrastive learning framework of SetFit. This few-shot approach is particularly advantageous for specialized scientific domains where large labeled datasets are impractical to construct.

The four-class schema proved essential for practical deployment. A binary (eye imaging vs. not) classifier would conflate software tools, other eye datas, and truly unrelated records into a single negative class, reducing interpretability and making it difficult to identify improvement targets. The EYE_SOFTWARE class, in particular, captures a distinct category (4.7% of filtered records) that is relevant to the eye imaging community but should not be presented as imaging data.

### 4.2 Confidence-Based Triaging

The extreme confidence distribution—97.5% of positive predictions above 0.95—suggests the classifier effectively separates clear positives from ambiguous cases. This enables a confidence-based triaging strategy for the Envision Portal: high-confidence predictions can be surfaced immediately with minimal review overhead, while lower-confidence predictions are prioritized for expert validation. Such a strategy can scale dataset discovery to much larger repository collections without proportionally increasing validation burden.

### 4.3 Challenges and False Positive Patterns

Several categories of records posed classification challenges:

- **Non-ophthalmic OCT:** Cardiovascular, dermatological, and industrial OCT share imaging terminology but are unrelated to ophthalmology. The training set includes explicit negative examples for these domains.
- **Code-with-data hybrids:** Some software repositories include small sample datasets alongside code. These fall in a gray area between EYE_SOFTWARE and EYE_IMAGING.
- **Genetics with retinal phenotypes:** GWAS and genetic studies that reference retinal measurements (e.g., RNFL thickness as a phenotype) are clinically adjacent but do not contain imaging data.
- **Multi-domain repositories:** Some Zenodo records aggregate heterogeneous content where eye imaging is a minor component.

### 4.4 Comparison with Manual Discovery

The contrast between automated and manual dataset discovery is stark. Gim et al. (2025) documented the extensive effort required to manually locate AMD-related OCT datasets: multi-platform searches, diverse query strategies, manuscript reading on PubMed, and still only a small number of datasets meeting eligibility criteria. Envision Discovery screened 30,439 records and identified 127 eye imaging datasets in approximately 30 minutes of compute time—a task that would take weeks or months of manual effort and would inevitably miss datasets described with non-standard terminology.

### 4.5 Limitations

Several limitations should be acknowledged:

1. **Repository coverage.** While multi-repository support (Zenodo, Figshare, Dryad, OSF, DataCite) is now implemented, coverage of institutional repositories and non-English platforms remains limited.
2. **Language bias.** Search terms and training examples are in English. Datasets described in other languages may be missed.
3. **Metadata-only classification.** The classifier operates on metadata (titles, descriptions, keywords) without examining actual data files. Records with uninformative metadata may be misclassified.
4. **Restricted-access records.** Content behind access controls cannot be independently verified without requesting access.
5. **Evolving repositories.** New deposits, updated metadata, and removed records require periodic re-scraping to maintain currency.
6. **Training set size.** While 474 examples proved sufficient for the current task, performance on rare or novel dataset types may be limited.

### 4.6 Future Directions

Immediate next steps include:
- **Multi-repository expansion:** Adapting the scraper for Figshare, Dryad, OSF, and DataCite Commons
- **Active learning:** Using expert validation results to iteratively refine the training set and retrain the classifier
- **Dataset quality scoring:** Developing automated metrics for metadata completeness, documentation quality, and AI-readiness
- **Continuous monitoring:** Implementing automated monthly re-scraping with incremental classification updates
- **Multilingual support:** Expanding search terms and training examples to support non-English datasets

---

## 5. Conclusion

We present Envision Discovery, an automated pipeline for identifying eye imaging datasets across scientific repositories. By combining targeted metadata harvesting, intelligent filtering with non-destructive archive inspection, and few-shot classification using SetFit, the system identified 127 eye imaging datasets from over 30,000 Zenodo records with high confidence (87.9% spot-check accuracy, 0.937 held-out test accuracy) and [XX]% expert-validated precision. The discovered datasets, spanning OCT, OCTA, fundus photography, and other ophthalmic modalities, are now catalogued on the Envision Portal, providing the research community with a centralized resource for finding publicly available eye imaging data. As the pipeline extends to additional repositories and incorporates feedback from expert validation, Envision Discovery will serve as a continuously expanding, community-validated catalog to accelerate AI development and clinical research in ophthalmology.

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
