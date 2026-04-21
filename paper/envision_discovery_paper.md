**Envision Discovery: Automated Identification of Eye Imaging Datasets Across Scientific Repositories**

James O'Neill1, [Validator Names]2, Bhavesh Patel1

*¹ FAIR Data Innovations Hub, California Medical Innovations Institute (CalMI²), San Diego, CA, USA*

*² [Validator Affiliations]*

**Correspondence:** joneill@calmi2.org, bpatel@calmi2.org

# Abstract

Eye imaging datasets---including optical coherence tomography (OCT), fundus photography, and OCT angiography (OCTA)---are essential resources for developing artificial intelligence (AI) tools in ophthalmology. However, these datasets are scattered across generalist repositories with no centralized catalog, making discovery and reuse prohibitively difficult. Here we present Envision Discovery, a machine learning pipeline that automatically identifies eye imaging datasets from scientific data repositories. The system uses a SetFit few-shot binary classifier built on the sentence-transformers/all-mpnet-base-v2 embedding model (768-dimensional) trained on 891 curated examples from multiple data repositories to distinguish genuine eye imaging datasets from all other record types. Applied to 6,833 metadata records harvested from six repositories (Zenodo, Figshare, DataCite, Kaggle, Dryad, and NEI), the pipeline identified 1,933 unique candidate eye imaging datasets from 4,674 deduplicated records. On a held-out test set, the classifier achieved an accuracy of 0.961 and an EYE_IMAGING F1 score of 0.936. Expert validation by [N] ophthalmology specialists across 356 stratified records sampled proportionally from all six repositories confirmed a precision of [XX]% and recall of [XX]%. All identified datasets are registered on the Envision Portal (https://envisionportal.org), providing researchers with a single entry point for discovering publicly available ophthalmic imaging data. The classifier, pipeline code, and trained model are openly available at https://github.com/EyeACT/envision-discovery.

**Keywords:** *eye imaging, dataset discovery, machine learning, FAIR data, ophthalmology, OCT, fundus photography, SetFit, few-shot learning*

# 1. Introduction

Eye imaging modalities such as OCT, OCTA, fundus photography, and fluorescence lifetime imaging ophthalmoscopy (FLIO) provide detailed structural and functional views of ocular tissues and have become indispensable for ophthalmic research and clinical innovation. These datasets have been particularly critical for developing AI-based diagnostic tools. RETFound, a self-supervised foundation model trained on 1.6 million unlabeled retinal images, demonstrated state-of-the-art performance across both ophthalmic and systemic disease detection tasks (Zhou et al., 2023). OphGLM combined fundus photography with natural language capabilities for diagnostic support (OphGLM, 2024), while Ophtha-LLaMA2 fine-tuned a large language model on multimodal ophthalmic data for efficient clinical deployment (Zhao et al., 2023). These advances depend critically on the availability and accessibility of large-scale imaging datasets.

However, sharing and discovering eye imaging data remains a significant challenge. Unlike neuroimaging, where community standards such as BIDS (Gorgolewski et al., 2016) and centralized platforms like OpenNeuro (Markiewicz et al., 2021) have transformed data sharing practices, ophthalmology lacks equivalent infrastructure. Eye imaging datasets are fragmented across generalist repositories---Zenodo, Figshare, Dryad, and institutional archives---that do not support ophthalmic-specific metadata or enforce standardized data formatting. This fragmentation makes datasets difficult to find and, when found, often difficult to reuse (Gim et al., 2025).

We experienced this challenge directly when searching for open-access OCT data related to age-related macular degeneration (AMD). Despite extensive multi-platform searches using diverse query strategies, finding relevant datasets was time-consuming and often required reading through published manuscripts on PubMed to locate associated data deposits (Gim et al., 2025). The absence of a centralized, searchable catalog means that researchers routinely duplicate collection efforts or remain unaware of existing data that could accelerate their work.

To address this gap, we developed Envision Discovery, an automated pipeline that harvests metadata from six scientific data repositories, classifies records using a few-shot machine learning model, and identifies those containing eye imaging data. The identified datasets are then registered on the Envision Portal (https://envisionportal.org), a platform developed as part of the Eye Aging, Cognition, and Imaging (EyeACT) study to share and discover FAIR (Findable, Accessible, Interoperable, Reusable) and AI-ready eye imaging datasets. In this paper, we describe the design and implementation of the Envision Discovery pipeline, present results from its application across six repositories, and report on expert validation of classifier predictions by ophthalmology domain specialists.

# 2. Methods

## 2.1 Overview

The Envision Discovery pipeline consists of four stages: (1) metadata harvesting from scientific repositories, (2) intelligent filtering and enrichment, (3) automated classification using a few-shot learning model, and (4) expert validation. Figure 1 provides an overview of the pipeline architecture.

*[Figure 1. Pipeline overview: metadata harvesting from six repositories → filtering & enrichment → binary classification → expert validation → Envision Portal registration.]*

## 2.2 Metadata Harvesting

We developed scrapers targeting six scientific data repositories:

- **Zenodo** (https://zenodo.org): A general-purpose open repository operated by CERN. Queried via REST API using 249 ophthalmology-specific search terms.
- **Figshare** (https://figshare.com): A multi-disciplinary open repository. Queried via REST API with targeted ophthalmic search terms.
- **DataCite** (https://datacite.org): A DOI registration agency providing metadata for datasets across 2,500+ repositories. Queried via the DataCite Commons API.
- **Kaggle** (https://kaggle.com): A data science and machine learning platform. Queried via the Kaggle API with bearer token authentication.
- **Dryad** (https://datadryad.org): A curated digital repository for research data. Queried via REST API.
- **NEI** (National Eye Institute): Grant-funded research data indexed through the NEI data portal.

Search terms span seven categories: imaging modalities (OCT, OCTA, fundus photography, fluorescein angiography, etc.), anatomical structures (retina, macula, optic nerve, cornea, etc.), diseases (diabetic retinopathy, glaucoma, AMD, etc.), equipment vendors (Heidelberg Spectralis, Zeiss Cirrus, Topcon, etc.), benchmark datasets (DRIVE, STARE, IDRiD, REFUGE, etc.), clinical measurements (RNFL thickness, visual acuity, FAZ area, etc.), and cornea/anterior segment terms.

## 2.3 Filtering and Metadata Enrichment

Retrieved records undergo several enrichment steps:

**File-type filtering.** Records are retained if they contain recognized data files (.dcm, .nii, .nii.gz, .mat, .h5, .hdf5, .npy, .npz, .jpg, .jpeg, .png, .tif, .tiff, .bmp) or archives (.zip, .tar.gz, .rar, .7z). Records containing only genomics files (.fasta, .h5ad, .vcf, .bam, .fastq) are excluded.

**ZIP content inspection.** For archived records on Zenodo, we implemented a non-destructive inspection technique using HTTP Range requests. By downloading only the ZIP central directory (the last ~64 KB of the archive), we extract the complete file manifest without downloading the full archive. This catalogued 31,958 files across all inspected archives at minimal bandwidth cost.

**Cross-source deduplication.** Records appearing in multiple repositories (e.g., a dataset indexed by both DataCite and Figshare) are deduplicated by DOI to avoid double-counting.

**Metadata normalization.** For each record, we extract and normalize: title, description (HTML stripped), keywords, file types, file counts, total size, and source repository.

## 2.4 Classification Model

### 2.4.1 Architecture

We use SetFit (Tunstall et al., 2022), a few-shot text classification framework that combines contrastive learning on sentence embeddings with a lightweight classification head. SetFit achieves strong performance with limited labeled data, which is critical given the specialized nature of ophthalmic dataset descriptions.

The backbone model is sentence-transformers/all-mpnet-base-v2, a general-purpose sentence embedding model producing 768-dimensional representations. It uses 12 transformer layers with 12 attention heads. The classification head is a logistic regression model trained on the contrastively learned embeddings.

### 2.4.2 Classification Schema

We adopted a binary classification schema (Table 1) after evaluating both four-class and binary approaches. The binary schema consolidates eye-related software, edge cases (eye genetics, electrophysiology, metabolomics), and unrelated records into a single NEGATIVE class, simplifying the decision boundary and improving precision on the primary task of identifying actual imaging datasets.

| Class | Label | Description |
|-------|-------|-------------|
| 1 | EYE_IMAGING | Contains actual ophthalmic imaging data (OCT scans, fundus photographs, OCTA images, corneal imaging, slit-lamp photographs, anterior segment imaging) |
| 0 | NEGATIVE | Everything else: non-eye data, software/code, eye-adjacent non-imaging (genetics, electrophysiology, metabolomics, drug delivery), non-eye medical imaging, reviews |

**Table 1.** *Binary classification schema for the Envision Discovery classifier.*

### 2.4.3 Training Data

The training set consists of 891 manually curated and verified examples sourced from multiple repositories to avoid domain-specific overfitting (Table 2).

| Class | Count | Sources |
|-------|-------|---------|
| EYE_IMAGING | 262 | Hand-curated examples (77) + verified records from Zenodo (20), Figshare (45), Dryad (30), Kaggle (45), and NEI (45) |
| NEGATIVE | 629 | Real dataset records from discovery pipelines (502) + eye-related software examples (48) + eye-adjacent non-imaging examples (79) |

**Table 2.** *Distribution of training examples. Positive examples are sourced from five repositories to ensure the model generalizes across metadata styles. Negative examples include targeted hard negatives: non-eye medical imaging (brain MRI, chest X-ray, microscopy), non-eye OCT (industrial, dermatological, cardiovascular), and eye-adjacent non-imaging data (GWAS, electrophysiology, metabolomics).*

Training examples use full metadata text (title + description + keywords), averaging 344 characters for positives and 466 characters for negatives. The model was trained for 2 epochs with a batch size of 16.

### 2.4.4 Input Representation

For each record, the classifier receives a concatenation of the title, description (with HTML tags removed), and keywords as a single text input. This combined representation provides sufficient context for the embedding model to capture both domain specificity (ophthalmology vs. other fields) and data-type specificity (imaging data vs. software vs. publications).

### 2.4.5 Description Summarization for Over-Length Records

MPNet's 512-token context window cannot accommodate all records in our corpus. In the 356-record stratified expert-validation sample, 77 records (21.6%) exceed this budget once title, description, and keywords are concatenated; across the full 4,674-record corpus, approximately the same proportion is over-budget. Handling these records requires a principled choice, because length-blind truncation throws away the segments most likely to contain the discriminative signals (imaging modality, anatomical focus, study subjects) — these are typically introduced in the methods or study-design paragraphs that follow a lengthy clinical or scientific background.

We considered three strategies and adopted the third.

**Strategy 1: Long-context backbone.** We benchmarked six embedding backbones against MPNet on a held-out 92-record spot-check set drawn from the Zenodo corpus (Table 3), including two long-context models from the ModernBERT family (Warner et al., 2024; 8,192-token context) and three additional 512-token models for comparison. Long-context backbones did not improve accuracy: ModernBERT-large scored 83/92, ModernBERT-base 79/92, and Snowflake-arctic-embed-l-v2.0 77/92 — all below MPNet's 84–85/92. In addition, ModernBERT-large requires approximately 3.6× the parameter count (395M vs 110M) and correspondingly more inference VRAM. Adopting a long-context backbone would have traded measurable task accuracy for a nominal context-window advantage while increasing deployment cost. We therefore retained MPNet.

| Backbone | Context | Params | Spot-check (n=92) |
|---|---|---|---|
| mixedbread-ai/mxbai-embed-large-v1 | 512 | 335M | 86 |
| MPNet + cosine warmup | 512 | 110M | 85 |
| MPNet (baseline, deployed) | 512 | 110M | 84 |
| lightonai/modernbert-embed-large | 8192 | 395M | 83 |
| intfloat/e5-large-v2 | 512 | 335M | 82 |
| nomic-ai/modernbert-embed-base | 8192 | 149M | 79 |
| Snowflake/snowflake-arctic-embed-l-v2.0 | 8192 | 567M | 77 |

**Table 3.** *Backbone comparison on a 92-record held-out spot-check set. Long-context models (ModernBERT-base, ModernBERT-large, Snowflake-arctic-embed-l-v2.0, all 8,192-token context) all scored below MPNet's 512-token deployment, motivating a preprocessing-based rather than architecture-based solution to record length.*

**Strategy 2: Truncation.** Hard-truncating over-length descriptions at 512 tokens systematically discards the methods- and data-describing paragraphs we rely on for classification. In an earlier deployment of our pipeline, a pre-tokenization character slice inadvertently reduced all inputs to approximately 100 tokens (≈512 characters in English, below the tokenizer's 512-token budget); we diagnosed and corrected this artifact, which on long records is the strategy-2 failure mode in its extreme form.

**Strategy 3: Task-scoped LLM summarization (adopted).** For any record whose combined title+description+keywords exceeds 512 MPNet tokens, the description is replaced with a 2–4 sentence abstractive summary produced by Llama-3.1-8B-Poster-Extraction (FAIR Data Innovations Hub), an instruction-tuned variant of Llama-3.1-8B we host via HuggingFace. The model is loaded with bitsandbytes 4-bit NF4 quantization (Dettmers et al., 2023) and bf16 compute, resident in approximately 6 GB of GPU memory. The summarization prompt is scoped to the classification task: it instructs the model to preserve imaging modalities (OCT, OCTA, fundus, slit-lamp, MRI, etc.), anatomical structures (retina, cornea, optic nerve, etc.), data formats (images, tables, code, segmentation masks), and study subjects (human, animal, phantom), while dropping author biographies, funding boilerplate, and bibliography fragments. The original description is retained verbatim in a sibling field (`description_original`) for auditing; a per-record metadata block records the model identifier, prompt version, quantization configuration, a SHA-256 of the input, and the MPNet token counts before and after.

**Reproducibility.** The pipeline uses greedy decoding (`do_sample=False`), so output is a deterministic function of input, model weights, prompt, and CUDA kernel selection. Before any production generation, a fixed warmup string is summarized three times back-to-back and the SHA-256 of each output is compared; generation proceeds only if all three hashes are identical. This self-check is required because driver or kernel-selection drift can silently introduce non-determinism on a nominally greedy pipeline. A disk cache keyed on SHA-256 of (input text, model identifier, prompt version, quantization configuration) guarantees that any cached summary was produced with exactly the configuration in the key, and that no input is re-summarized across runs. The cache is committed to the repository alongside the classification corpus.

**Train/test consistency.** The same summarization gate is applied to the training corpus prior to classifier fitting. Empirically, no training example in any of the four class lists (EYE_IMAGING, EYE_SOFTWARE, OTHER_EYE_DATA, NEGATIVE; 891 total) exceeds the 512-token budget — the training corpus was curated as short, high-signal examples with a maximum of 236 MPNet tokens and a mean of 70 tokens. The gate therefore triggers only on the tail of longer real-world records encountered at inference; no retrain is required to accommodate the preprocessing step. This is a feature of the curated training set: because training examples are already short, the deployed model has never been exposed to input-distribution shift from the summarization operation.

**Validity results.** We ran three validity checks. The hallucination and expert-audit checks support the information-preservation claim at the surface-semantic level; the classifier A/B check, together with the labeled evaluation in Section 3.4, surfaces a genuine limitation of the current summarization prompt on hard-negative inputs.

1. *Whitelist-based hallucination check.* Each summary was scanned for mentions of 84 imaging-modality, anatomy, study-subject, and data-format terms from a fixed whitelist, and each claimed term was checked against the original description with synonym-class equivalences for common abbreviation-expansion pairs (MRI ↔ magnetic resonance imaging, OCT ↔ optical coherence tomography, ONH ↔ optic nerve head, etc.). Across 77 summaries and 215 total whitelist claims, **0 unsupported claims** were detected (0% record-level, 0% claim-level hallucination rate). This is a coarse check that cannot detect synonym-level drift or omissions of disambiguating context; the classifier A/B check below captures one concrete failure of the latter kind.

2. *Classifier A/B on preserved task signal.* The deployed classifier was applied to all 77 records twice — once with the original full-length description and once with the summary — using the same title and keywords in both arms. Label agreement between the two arms was **90.9% (70/77)**; mean confidence change was +0.019. Case-level inspection of the seven flips reveals a two-sided mix: at least two EYE_IMAGING → NEGATIVE flips are corrections (a brain-MRI-for-Parkinson's-disease dataset and an NEI center-core-grant record; see Section 3.5), while at least three flips in the labeled spot-check set (Section 3.4) are regressions on non-ocular OCT records, where summarization preserved the modality term "OCT" but compressed away the non-ocular application context. The 90.9% agreement rate therefore *bounds* both the correction rate and the regression rate; the expert validation protocol (Section 2.5) will provide the signed contribution. We release all four sets of per-record predictions at `eval/results/ab_summarization_results.json` and `eval/results/ab_backbone_results.json` for case-level inspection.

3. *Expert audit.* A stratified random sample of 30 summaries (proportionally drawn across sources: 14 NEI, 11 Figshare, 4 DataCite, 1 Zenodo; seed = 42) was prepared as a CSV at `eval/results/summary_fidelity_audit_n30.csv` for review by an ophthalmology-literate annotator. Each row shows the original description and summary side-by-side and requests a fidelity score on a three-point scale (1 = faithful, 0 = minor paraphrase, −1 = hallucination or critical information dropped), plus free-text notes.

## 2.5 Expert Validation Protocol

To rigorously evaluate classifier performance across repositories, we designed a multi-validator expert review protocol using stratified sampling from all six data sources.

### 2.5.1 Sample Size Determination

Using Cochran's formula with finite population correction:

n₀ = (Z² × p × (1-p)) / e² = (1.96² × 0.5 × 0.5) / 0.05² = 384

n = n₀ / (1 + (n₀ - 1) / N) = 384 / (1 + 383/4,674) = 356

where Z = 1.96 (95% confidence), p = 0.5 (maximum variability), e = 0.05 (5% margin of error), and N = 4,674 (total unique records). This yields a required sample of 356 records.

### 2.5.2 Stratified Sampling

Records are sampled proportionally by repository and predicted class, with confidence-stratified selection within each stratum (Table 3).

| Source | Unique Records | Sample Size | Predicted EYE_IMAGING | Predicted NEGATIVE |
|--------|---------------|-------------|----------------------|-------------------|
| Zenodo | 502 | 38 | 5 | 33 |
| DataCite | 1,061 | 81 | 32 | 49 |
| Figshare | 1,620 | 123 | 66 | 57 |
| Kaggle | 667 | 51 | 21 | 30 |
| Dryad | 37 | 3 | 0 | 3 |
| NEI | 787 | 60 | 23 | 37 |
| **Total** | **4,674** | **356** | **147** | **209** |

**Table 3.** *Stratified validation sample. Records are further stratified by model confidence within each repository to ensure experts review both high-confidence and borderline predictions.*

### 2.5.3 Validation Interface

Each validator is presented with dataset records including the title, source repository, description, keywords, and file types. For each record, validators assign a score from 0 to 5 indicating their confidence that the dataset contains eye imaging data (5 = certain eye imaging, 0 = certain not eye imaging). Scores ≥ 3 map to EYE_IMAGING and scores ≤ 2 map to NEGATIVE for computing binary metrics. Model predictions and confidence scores are withheld to prevent anchoring bias.

### 2.5.4 Validation Batches

Records are distributed in batches of 100. Three independent reviewers annotate all 356 records with full overlap, enabling pairwise and multi-rater agreement analysis.

### 2.5.5 Evaluation Metrics

Classifier performance is evaluated using per-class precision, recall, and F1 score; macro F1; a 2×2 confusion matrix with 95% bootstrap confidence intervals; inter-rater agreement (Cohen's kappa pairwise, Fleiss' kappa multi-rater, target κ ≥ 0.70); per-repository performance to assess cross-repository generalizability; and a confidence calibration curve.

# 3. Results

## 3.1 Metadata Harvesting

The pipeline harvested metadata from six repositories, retrieving a total of 6,833 records. After cross-source deduplication by DOI, 4,674 unique records remained (Table 4).

| Source | Records Retrieved | Unique After Dedup |
|--------|------------------|-------------------|
| Zenodo | 514 | 502 |
| DataCite | 1,836 | 1,061 |
| Figshare | 2,000 | 1,620 |
| Kaggle | 732 | 667 |
| Dryad | 89 | 37 |
| NEI | 1,662 | 787 |
| **Total** | **6,833** | **4,674** |

**Table 4.** *Records harvested from each repository. DataCite shows the largest deduplication reduction because it indexes DOIs from other repositories (particularly Figshare and Dryad).*

## 3.2 Classification Results

Of the 4,674 unique records, the classifier identified 1,933 as EYE_IMAGING and 2,741 as NEGATIVE (Table 5).

| Source | EYE_IMAGING | NEGATIVE | Total |
|--------|-------------|----------|-------|
| Zenodo | 60 | 455 | 515 |
| DataCite | 752 | 1,084 | 1,836 |
| Figshare | 1,049 | 951 | 2,000 |
| Kaggle | 248 | 484 | 732 |
| Dryad | 32 | 57 | 89 |
| NEI | 686 | 976 | 1,662 |

**Table 5.** *Classification distribution across repositories (before deduplication). After deduplication, 1,933 unique EYE_IMAGING records remain.*

## 3.3 Held-Out Test Set Evaluation

The classifier was evaluated on a stratified 20% held-out test set (Table 6).

| Metric | Value |
|--------|-------|
| Accuracy | 0.961 |
| Macro F1 | 0.954 |
| EYE_IMAGING Precision | 0.911 |
| EYE_IMAGING Recall | 0.962 |
| EYE_IMAGING F1 | 0.936 |
| NEGATIVE F1 | 0.972 |

**Table 6.** *Held-out test set performance.*

## 3.4 Spot-Check Validation

An expanded spot-check set of 92 manually verified Zenodo records (15 EYE_IMAGING, 77 NEGATIVE) was used to benchmark the deployed classifier under realistic input conditions. Of these 92 records, 61 were available in the local metadata mirror at evaluation time (15 EYE_IMAGING, 46 NEGATIVE); the remaining 31 records (all NEGATIVE) were retired from the source repository between scrape and evaluation. Seventeen of the 61 records (27.9%) exceeded MPNet's 512-token budget in their joined (title + description + keywords) representation, making them the natural test of how each handling strategy performs on long inputs.

We evaluated four configurations on these 61 labeled records — a 2×2 design over backbone (MPNet vs. ModernBERT-large, the best-scoring long-context alternative from the backbone comparison in Section 2.4.5) and input representation (original description vs. LLM summary). The "original" arms pass the full text to the tokenizer, which truncates at the backbone's native context length (384 tokens for the deployed MPNet SentenceTransformer, 8,192 for ModernBERT-large). The "summary" arms replace the description of long records with the Llama-generated summary described in Section 2.4.5 before tokenization; short records pass through unchanged. Results are reported in Table 7.

| Configuration | Accuracy | Macro F1 | EYE_IMAGING F1 | NEGATIVE F1 |
|---|---|---|---|---|
| **MPNet, original text** (deployed) | **0.836** | **0.803** | **0.722** | **0.885** |
| MPNet, summarized long records | 0.787 | 0.755 | 0.667 | 0.843 |
| ModernBERT-large, original text | 0.705 | 0.673 | 0.571 | 0.775 |
| ModernBERT-large, summarized long records | 0.689 | 0.665 | 0.578 | 0.753 |

**Table 7.** *Spot-check performance (n=61 labeled records) across backbone × input-representation. MPNet with tokenizer-truncated original text achieves the highest macro F1; the LLM summarization step slightly reduces accuracy on this set, and the long-context ModernBERT backbone underperforms MPNet despite having no context-window constraint.*

Restricting to the 17 records that exceeded 512 MPNet tokens (the subset where preprocessing decisions actually matter, Table 8) sharpens the finding.

| Configuration | Accuracy | Macro F1 | EYE_IMAGING F1 |
|---|---|---|---|
| **MPNet, original text** (deployed) | **0.941** | **0.933** | **0.909** |
| MPNet, summarized | 0.765 | 0.757 | 0.714 |
| ModernBERT-large, original text | 0.882 | 0.837 | 0.750 |
| ModernBERT-large, summarized | 0.824 | 0.798 | 0.727 |

**Table 8.** *Long-records subset of the spot-check (n=17, >512 MPNet tokens). Tokenizer-truncated MPNet remains the strongest configuration; neither backbone swap nor LLM summarization improves on it in this evaluation.*

On this labeled set, the LLM summarization step — which we developed explicitly to handle over-length inputs — does not deliver measurable improvement and in fact costs approximately three correct predictions out of 17 long records (a ~17-percentage-point drop in accuracy on the long subset). Case-level inspection identifies a consistent failure mode: all three regressions are *non-ocular optical coherence tomography (OCT)* records — a well-known hard-negative class in this domain, including "endoscopic OCT for epidural anesthesia," "wavenumber-dependent dynamic light scattering OCT," and "sub-diffusion flow velocimetry with OCT." The summarization prompt (Section 2.4.5) was scoped to preserve imaging modality but not application context; when the summarizer faithfully retains "OCT" while compressing the surrounding 1,000–2,000-token description into 100–200 tokens, the non-ocular disambiguating context (e.g., "epidural anesthesia") is lost. The MPNet tokenizer-truncated "original" arm, which sees the first ~1,500 characters of the description, retains that context and classifies correctly.

This is a meaningful finding for deployment: the char-level truncation bug we diagnosed and corrected on 2026-04-20 — which had reduced effective input to ~100 tokens — was the critical performance regression. Once that bug is fixed, MPNet's native tokenizer truncation (to ~384 tokens) appears sufficient for this task, and additional abstractive preprocessing trades interpretability against a small accuracy loss on hard-negative long inputs. We release both the summarization pipeline and the empirical tradeoff data; downstream users can choose which pre-classifier text representation to deploy.

## 3.5 Summarization Behavior on Unlabeled Production-Scale Inputs

On the 77 long records in the expert-validation sample (no consensus ground-truth labels; drawn proportionally from NEI, Figshare, DataCite, Dryad, and Zenodo), we ran the same four configurations and report inter-configuration agreement rather than accuracy.

| Comparison | Label agreement |
|---|---|
| MPNet original vs. MPNet summary | 0.909 (70/77) |
| ModernBERT original vs. ModernBERT summary | 0.805 (62/77) |
| MPNet original vs. ModernBERT original | 0.766 (59/77) |
| MPNet summary vs. ModernBERT original | 0.779 (60/77) |
| MPNet summary vs. ModernBERT summary | 0.792 (61/77) |

**Table 9.** *Pairwise label agreement on 77 long expert-validation records. The two MPNet arms agree 90.9% of the time; cross-backbone agreement is substantially lower (~77-80%), suggesting MPNet and ModernBERT-large have meaningfully different decision boundaries on long, real-world inputs.*

Manual case-level inspection of the seven MPNet original → summary flips in this sample found a mix of corrections and regressions: at least two flips toward NEGATIVE were corrections (a brain-MRI-for-Parkinson's dataset misclassified as EYE_IMAGING on the original text but correctly flipped to NEGATIVE after summarization; an NEI center-core-grant describing research infrastructure rather than a dataset), consistent with the hypothesis that summarization can improve predictions when the original text contains distracting background material. However, the labeled-test-set failure mode from Section 3.4 (non-ocular OCT) establishes that the same mechanism can also discard disambiguating context. Without labels for the 77-record sample we cannot decompose the 9% disagreement rate into corrections vs. regressions; the ongoing expert-validation protocol (Section 2.5) will provide that ground truth.

## 3.6 Expert Validation Results

*[This section will be populated following completion of expert validation across the 356 stratified records.]*

[N] ophthalmology specialists validated 356 records sampled proportionally from all six repositories. Overall results:

- **EYE_IMAGING Precision:** [XX]%
- **EYE_IMAGING Recall:** [XX]%
- **EYE_IMAGING F1:** [X.XXX]
- **Inter-rater agreement (Fleiss' kappa):** [X.XX]
- **Per-repository F1 variation:** [range]

*[Table 7. Expert validation confusion matrix with 95% bootstrap confidence intervals.]*

*[Table 8. Per-repository classifier performance based on expert validation.]*

*[Figure 2. Classifier confidence vs. expert agreement rate (calibration curve).]*

# 4. Discussion

## 4.1 Automated Dataset Discovery as Infrastructure

Envision Discovery demonstrates the feasibility of using few-shot machine learning to automate the identification of domain-specific datasets from generalist repositories at scale. The 891-example training set---small by typical machine learning standards---proved sufficient to learn discriminative features for ophthalmic imaging datasets when combined with the strong pre-trained representations of all-mpnet-base-v2 and the contrastive learning framework of SetFit. This few-shot approach is particularly advantageous for specialized scientific domains where large labeled datasets are impractical to construct.

The binary classification schema was adopted after extensive comparison with a four-class approach that separately identified eye-related software, eye-adjacent non-imaging data, and unrelated records. While the four-class model provided finer-grained categorization, it achieved lower precision on the primary task of identifying actual imaging datasets due to confusion between the intermediate classes. The binary approach, which consolidates all non-imaging records into a single NEGATIVE class, produced higher precision with comparable recall.

## 4.2 Multi-Source Training to Address Domain Shift

A key methodological finding was the importance of source-balanced training data. Early classifier versions trained predominantly on records from a single repository exhibited domain shift when applied to other sources: metadata description styles, lengths, and vocabulary vary substantially across repositories (e.g., DataCite descriptions average 466 characters while Kaggle averages 56 characters). By including verified training examples from all five non-Zenodo repositories, we reduced source-specific overfitting and improved cross-repository generalizability.

## 4.3 Challenges and False Positive Patterns

Several categories of records posed classification challenges:

- **Non-ophthalmic OCT.** Cardiovascular, dermatological, and industrial OCT share imaging terminology but are unrelated to ophthalmology. The training set includes explicit negative examples for these domains.
- **Retinal neuroscience.** Studies involving retinal ganglion cell electrophysiology, spike train recordings, and calcium imaging use similar vocabulary to ophthalmic imaging but contain physiological measurements rather than clinical images.
- **Eye-adjacent research.** GWAS studies referencing retinal phenotypes, metabolomics of retinal tissue, and drug delivery studies targeting the retina are clinically relevant but do not contain imaging data.
- **Short metadata.** Some repositories (particularly Kaggle) have very brief descriptions that provide limited signal for classification.

## 4.4 Comparison with Manual Discovery

The contrast between automated and manual dataset discovery is stark. Gim et al. (2025) documented the extensive effort required to manually locate AMD-related OCT datasets across multiple platforms. Envision Discovery screened 6,833 records across six repositories and identified 1,933 unique eye imaging datasets---a task that would take weeks or months of manual effort and would inevitably miss datasets described with non-standard terminology.

## 4.5 Limitations

1. **Language bias.** Search terms and training examples are in English. Datasets described in other languages may be missed.
2. **Metadata-only classification.** The classifier operates on metadata (titles, descriptions, keywords) without examining actual data files. Records with uninformative metadata may be misclassified.
3. **Restricted-access records.** Content behind access controls cannot be independently verified without requesting access.
4. **Evolving repositories.** New deposits, updated metadata, and removed records require periodic re-scraping to maintain currency.
5. **Repository coverage.** While six repositories represent substantial coverage, institutional repositories, preprint servers with associated data, and national data archives are not yet included.

## 4.6 Future Directions

Immediate next steps include:

- **Active learning:** Using expert validation results to iteratively refine the training set and retrain the classifier
- **Dataset quality scoring:** Developing automated metrics for metadata completeness, documentation quality, and AI-readiness
- **Continuous monitoring:** Implementing automated weekly re-scraping with incremental classification updates via the automation pipeline
- **Additional repositories:** Expanding to institutional repositories and national data archives
- **Multilingual support:** Expanding search terms and training examples to support non-English datasets

# 5. Conclusion

We present Envision Discovery, an automated pipeline for identifying eye imaging datasets across six scientific repositories. By combining targeted metadata harvesting, intelligent filtering with non-destructive archive inspection, and few-shot binary classification using SetFit, the system identified 1,933 unique eye imaging datasets from 4,674 deduplicated records with an EYE_IMAGING F1 of 0.936 on held-out evaluation and [XX]% expert-validated precision across 356 stratified records. The discovered datasets, spanning OCT, OCTA, fundus photography, and other ophthalmic modalities, are catalogued on the Envision Portal, providing the research community with a centralized resource for finding publicly available eye imaging data. As the pipeline incorporates feedback from expert validation and expands to additional repositories, Envision Discovery will serve as a continuously expanding, community-validated catalog to accelerate AI development and clinical research in ophthalmology.

# Data and Code Availability

The pipeline code and trained model are available at https://github.com/EyeACT/envision-discovery. The model is published on HuggingFace at https://huggingface.co/fairdataihub/envision-eye-imaging-classifier. The Envision Portal is accessible at https://envisionportal.org. All classified results are available in the repository under results/.

# Acknowledgments

This work was supported by [NIH grant number]. The Envision Portal is developed as part of the Eye Aging, Cognition, and Imaging (EyeACT) study (https://eyeactstudy.org). We thank [validator names] for their expert validation of classifier predictions. [Additional acknowledgments.]

# References

Gim, N., et al. (2025). Publicly available imaging datasets for age-related macular degeneration: Evaluation according to the Findable, Accessible, Interoperable, Reusable (FAIR) principles. Experimental Eye Research, 255, 110342.

Gorgolewski, K. J., et al. (2016). The brain imaging data structure, a format for organizing and describing outputs of neuroimaging experiments. Scientific Data, 3, 160044.

Markiewicz, C. J., et al. (2021). The OpenNeuro resource for sharing of neuroscience data. eLife, 10, e71774.

OphGLM. (2024). OphGLM: An ophthalmology large language-and-vision assistant. Artificial Intelligence in Medicine, 157, 103001.

Tunstall, L., et al. (2022). Efficient few-shot learning without prompts. arXiv:2209.11055.

Zhao, H., et al. (2023). Ophtha-LLaMA2: A Large Language Model for Ophthalmology. arXiv preprint.

Zhou, Y., et al. (2023). A foundation model for generalizable disease detection from retinal images. Nature, 622, 156--163.
