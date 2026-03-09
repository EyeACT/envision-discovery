#!/usr/bin/env python3
"""
ENVISION: Multi-Source Classification Pipeline

Batch classification pipeline for dataset metadata records.
Supports Zenodo (legacy) and DatasetMetadata (multi-source) inputs.
Uses EyeImagingClassifier to classify scraped eye imaging datasets.
Exports results as JSON and optionally as ADDF schema files.
"""

import json
import re
from collections import Counter
from datetime import datetime
from html import unescape
from pathlib import Path

from envision_classifier import EyeImagingClassifier, LABELS

from .metadata import DatasetMetadata

# ============================================================
# File type constants for Zenodo record filtering
# ============================================================

# Standard image formats
IMG_EXTS = {'.jpg', '.jpeg', '.png', '.tif', '.tiff', '.bmp', '.gif'}

# Medical/scientific imaging formats (eye imaging specific)
MEDICAL_EXTS = {
    '.dcm', '.dicom',           # DICOM (standard medical)
    '.nii', '.nii.gz',          # NIfTI (neuroimaging, OCT volumes)
    '.mat',                      # MATLAB (common for OCT data)
    '.h5', '.hdf5',             # HDF5 (large imaging datasets) - NOT h5ad
    '.npy', '.npz',             # NumPy arrays
    # OCT-specific formats
    '.fds',                      # Topcon OCT
    '.e2e',                      # Heidelberg OCT
    '.vol',                      # Zeiss OCT volumes
    '.img',                      # Generic imaging
    '.oct',                      # Generic OCT
    '.fda',                      # Optovue OCT
}

# Archive formats (may contain imaging data)
ARCH_EXTS = {'.zip', '.tar', '.gz', '.tar.gz', '.rar', '.7z'}

# GWAS/Genomics file types to EXCLUDE (these are not eye imaging)
GENOMICS_EXTS = {
    '.fasta', '.fa', '.fna',    # DNA/RNA sequences
    '.fastq', '.fq',            # Sequencing reads
    '.fastq.gz', '.fq.gz',      # Compressed reads
    '.h5ad',                     # AnnData (single-cell RNA-seq)
    '.bam', '.sam', '.cram',    # Alignments
    '.vcf', '.bcf', '.vcf.gz',  # Variants
    '.bed', '.gtf', '.gff',     # Genomic annotations
    '.gff3', '.bigwig', '.bw',  # More genomics
    '.cel', '.idat',            # Microarray
    '.loom',                     # Single-cell
}

ALL_DATA_EXTS = IMG_EXTS | MEDICAL_EXTS | ARCH_EXTS

# External dataset link patterns
DATASET_LINK_PATTERNS = [
    'kaggle.com', 'huggingface.co', 'github.com',
    'drive.google.com', 'osf.io', 'datadryad.org', 'dryad.org',
    'figshare.com', 'dataverse', 'openneuro.org',
    'physionet.org', 'synapse.org', 'grand-challenge.org'
]


def extract_dataset_links(record):
    """Extract external dataset links from description and related identifiers."""
    links = []

    # Check description for links
    desc = record.get('metadata', {}).get('description', '')
    if desc:
        url_pattern = r'https?://[^\s<>"\']+|www\.[^\s<>"\']+'
        urls = re.findall(url_pattern, desc)
        for url in urls:
            for pattern in DATASET_LINK_PATTERNS:
                if pattern in url.lower():
                    links.append(url)
                    break

    # Check related_identifiers
    related = record.get('metadata', {}).get('related_identifiers', [])
    for rel in related:
        ident = rel.get('identifier', '')
        if any(p in ident.lower() for p in DATASET_LINK_PATTERNS):
            links.append(ident)

    # Check custom _dataset_links field from scraper
    custom_links = record.get('_dataset_links', [])
    if custom_links:
        for link in custom_links:
            if isinstance(link, str):
                links.append(link)
            elif isinstance(link, dict):
                url = link.get('url', link.get('identifier', ''))
                if url:
                    links.append(str(url))

    # Check _weblinks from scraper (data_platform type = GitHub, Kaggle, etc.)
    weblinks = record.get('_weblinks', [])
    for wl in weblinks:
        if isinstance(wl, dict) and wl.get('type') == 'data_platform':
            url = wl.get('url', '')
            if url:
                links.append(str(url))

    # Deduplicate
    unique_links = []
    seen = set()
    for link in links:
        link_str = str(link) if not isinstance(link, str) else link
        if link_str and link_str not in seen:
            seen.add(link_str)
            unique_links.append(link_str)

    return unique_links


def has_data_files_or_links(record):
    """Check if record has data files OR external dataset links.
    Excludes records that ONLY have genomics files (GWAS, RNA-seq, etc.)
    """
    files = record.get('files', [])
    has_imaging_files = False
    has_only_genomics = True

    for f in files:
        name = f.get('key', '').lower()

        is_genomics = any(name.endswith(ext) for ext in GENOMICS_EXTS)
        is_imaging = any(name.endswith(ext) for ext in ALL_DATA_EXTS)

        if is_imaging and not is_genomics:
            has_imaging_files = True
            has_only_genomics = False
        elif is_imaging and is_genomics:
            pass
        elif not is_genomics and is_imaging:
            has_only_genomics = False

    if has_imaging_files:
        return True

    if extract_dataset_links(record):
        return True

    return False


def get_record_text(record):
    """Extract text for classification from a Zenodo record."""
    title = record.get('metadata', {}).get('title', record.get('title', ''))
    desc = EyeImagingClassifier.strip_html(
        record.get('metadata', {}).get('description', '')
    )
    keywords = record.get('metadata', {}).get('keywords', [])
    if isinstance(keywords, list):
        keywords = ' '.join(keywords)
    return f"{title} {desc} {keywords}"


def get_file_details(record):
    """Extract detailed file information from a Zenodo record."""
    files = record.get('files', [])

    file_names = []
    file_types = set()
    total_size = 0
    img_count = 0
    medical_count = 0
    archive_count = 0
    genomics_count = 0

    for f in files:
        name = f.get('key', '')
        size = f.get('size', 0)
        name_lower = name.lower()

        file_names.append(name)
        total_size += size

        # Check for genomics files first
        is_genomics = False
        for ext in sorted(GENOMICS_EXTS, key=len, reverse=True):
            if name_lower.endswith(ext):
                file_types.add(ext)
                genomics_count += 1
                is_genomics = True
                break

        if is_genomics:
            continue

        # Extract extension for imaging files
        for ext in sorted(ALL_DATA_EXTS, key=len, reverse=True):
            if name_lower.endswith(ext):
                file_types.add(ext)
                if ext in IMG_EXTS:
                    img_count += 1
                elif ext in MEDICAL_EXTS:
                    medical_count += 1
                elif ext in ARCH_EXTS:
                    archive_count += 1
                break

    return {
        'file_names': file_names[:20],
        'file_types': sorted(file_types),
        'file_count': len(files),
        'img_count': img_count,
        'medical_count': medical_count,
        'archive_count': archive_count,
        'genomics_count': genomics_count,
        'total_size': total_size,
    }


def get_metadata_details(record):
    """Extract rich metadata from a Zenodo record."""
    meta = record.get('metadata', {})

    keywords = meta.get('keywords', [])
    if isinstance(keywords, str):
        keywords = [keywords]

    desc = EyeImagingClassifier.strip_html(meta.get('description', ''))[:500]

    related_dois = []
    for rel in meta.get('related_identifiers', []):
        if rel.get('scheme') == 'doi':
            related_dois.append(rel.get('identifier', ''))

    return {
        'description': desc,
        'keywords': keywords[:10],
        'access_right': meta.get('access_right', 'unknown'),
        'license': meta.get('license', {}).get('id', 'unknown'),
        'resource_type': meta.get('resource_type', {}).get('type', 'unknown'),
        'doi': meta.get('doi', ''),
        'related_dois': related_dois[:5],
    }


# ============================================================
# Multi-source pipeline (new)
# ============================================================

def run_pipeline(
    metadata_records: list[DatasetMetadata] | None = None,
    source: str = "zenodo",
    classify_only: bool = True,
    metadata_dir: str | Path | None = None,
    results_dir: str | Path | None = None,
    addf_output_dir: str | Path | None = None,
    model_dir: str | Path | None = None,
):
    """Run the generalized classification pipeline.

    Supports both DatasetMetadata objects (from any source) and
    legacy Zenodo JSON files (backward compatible).

    Args:
        metadata_records: Pre-built DatasetMetadata list. If None, loads
            from metadata_dir (Zenodo JSON files for backward compat).
        source: Source name for output file naming.
        classify_only: If True, load existing model instead of training.
        metadata_dir: Directory containing Zenodo metadata JSON files
            (used only when metadata_records is None).
        results_dir: Directory to save results JSON files.
        addf_output_dir: If set, export ADDF schema files here.
        model_dir: Path to the trained model directory.
    """
    BASE_DIR = Path(__file__).resolve().parent.parent

    if results_dir is None:
        results_dir = BASE_DIR / "results"
    else:
        results_dir = Path(results_dir)

    if model_dir is None:
        model_dir = BASE_DIR / "models" / "setfit_v7"
    else:
        model_dir = Path(model_dir)

    print("=" * 70)
    print(f"ENVISION: Eye Imaging Dataset Classifier ({source})")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("=" * 70)

    # Load model
    if (model_dir / "model.safetensors").exists():
        print(f"\nLoading model from {model_dir}")
        classifier = EyeImagingClassifier(model_path=model_dir)
    elif classify_only:
        print("\nDownloading model from HuggingFace...")
        classifier = EyeImagingClassifier()
    else:
        print("\nTraining new model...")
        classifier = EyeImagingClassifier.train(output_dir=model_dir)

    print(f"Device: {classifier._device}")

    # If DatasetMetadata provided, use the new path
    if metadata_records is not None:
        return _run_metadata_pipeline(
            classifier, metadata_records, source, results_dir, addf_output_dir
        )

    # Legacy Zenodo path
    return _run_zenodo_legacy_pipeline(
        classifier, metadata_dir, results_dir, addf_output_dir, BASE_DIR
    )


def _run_metadata_pipeline(
    classifier: EyeImagingClassifier,
    metadata_records: list[DatasetMetadata],
    source: str,
    results_dir: Path,
    addf_output_dir: str | Path | None,
):
    """Classify DatasetMetadata records from any source."""
    print(f"\n{'='*70}")
    print(f"Classifying {len(metadata_records)} {source} records")
    print("=" * 70)

    # Classify in batches
    BATCH_SIZE = 16
    texts = [m.to_classifier_text() for m in metadata_records]
    all_classifications = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        all_classifications.extend(classifier.classify_batch(batch, batch_size=BATCH_SIZE))
        if (i + BATCH_SIZE) % 500 == 0:
            print(f"  Processed {min(i + BATCH_SIZE, len(texts)):,} / {len(texts):,}")

    # Build results
    all_results = []
    addf_records = []  # for ADDF export

    for meta, cls_result in zip(metadata_records, all_classifications):
        probs = cls_result["probabilities"]
        result = {
            "source": meta.source,
            "source_id": meta.source_id,
            "doi": meta.doi,
            "url": meta.url,
            "label": cls_result["label"],
            "confidence": cls_result["confidence"],
            "prob_eye_imaging": probs["EYE_IMAGING"],
            "prob_software": probs["EYE_SOFTWARE"],
            "prob_edge": probs["EDGE_CASE"],
            "prob_negative": probs["NEGATIVE"],
            "title": meta.title[:200],
            "description": meta.description[:500],
            "keywords": meta.keywords[:10],
            "access_type": meta.access_type,
            "license": meta.license,
            "file_types": sorted(meta.file_types),
            "file_names": meta.file_names[:20],
            "file_count": meta.file_count,
            "img_count": meta.img_count,
            "medical_count": meta.medical_count,
            "archive_count": meta.archive_count,
            "genomics_count": meta.genomics_count,
            "size_mb": meta.size_mb,
            "external_links": meta.external_links[:10],
        }
        all_results.append(result)

        if cls_result["label"] in ("EYE_IMAGING", "EYE_SOFTWARE"):
            addf_records.append((meta, cls_result))

    # Analyze
    _print_analysis(all_results)

    # Save results
    results_dir.mkdir(exist_ok=True, parents=True)

    eye_imaging = [r for r in all_results if r["label"] == "EYE_IMAGING"]
    software = [r for r in all_results if r["label"] == "EYE_SOFTWARE"]

    eye_imaging.sort(key=lambda x: (-x["prob_eye_imaging"], -x["size_mb"]))
    software.sort(key=lambda x: (-x["confidence"], -x["size_mb"]))

    with open(results_dir / f"{source}_eye_imaging.json", "w") as f:
        json.dump(eye_imaging, f, indent=2)

    with open(results_dir / f"{source}_software.json", "w") as f:
        json.dump(software, f, indent=2)

    with open(results_dir / f"{source}_all_results.json", "w") as f:
        json.dump(all_results, f, indent=2)

    print(f"\n  Results: {results_dir}")
    print(f"    - {source}_eye_imaging.json ({len(eye_imaging):,} records)")
    print(f"    - {source}_software.json ({len(software):,} records)")
    print(f"    - {source}_all_results.json ({len(all_results):,} records)")

    # ADDF export
    if addf_output_dir and addf_records:
        from .addf_export import ADDFExporter

        addf_output_dir = Path(addf_output_dir)
        paths = ADDFExporter.export_batch(addf_records, addf_output_dir)
        print(f"\n  ADDF export: {len(paths)} records to {addf_output_dir}")

    return all_results


def _run_zenodo_legacy_pipeline(
    classifier: EyeImagingClassifier,
    metadata_dir: str | Path | None,
    results_dir: Path,
    addf_output_dir: str | Path | None,
    base_dir: Path,
):
    """Legacy Zenodo pipeline — backward compatible with original format."""
    if metadata_dir is None:
        metadata_dir = base_dir / "data" / "metadata" / "zenodo"
    else:
        metadata_dir = Path(metadata_dir)

    output_dir = base_dir / "models" / "setfit_v7"

    print(f"\n{'='*70}")
    print("Classifying Zenodo records")
    print("=" * 70)

    records = []
    json_files = list(metadata_dir.glob("*.json"))
    print(f"Found {len(json_files):,} metadata files")

    for json_file in sorted(json_files):
        try:
            with open(json_file) as f:
                record = json.load(f)
            record['_zenodo_id'] = str(record.get('id', json_file.stem))
            if has_data_files_or_links(record):
                records.append(record)
        except Exception:
            pass

    print(f"Loaded {len(records):,} records with data files or dataset links")

    # Classify in batches
    print("Classifying...")
    BATCH_SIZE = 16
    all_results = []

    for i in range(0, len(records), BATCH_SIZE):
        batch_records = records[i:i+BATCH_SIZE]
        batch_texts = [get_record_text(r) for r in batch_records]
        batch_classifications = classifier.classify_batch(batch_texts, batch_size=BATCH_SIZE)

        for j, r in enumerate(batch_records):
            cls_result = batch_classifications[j]
            probs = cls_result['probabilities']

            file_details = get_file_details(r)
            metadata_details = get_metadata_details(r)
            dataset_links = extract_dataset_links(r)

            result = {
                'zenodo_id': r['_zenodo_id'],
                'doi': metadata_details['doi'],
                'url': f"https://zenodo.org/records/{r['_zenodo_id']}",
                'label': cls_result['label'],
                'confidence': cls_result['confidence'],
                'prob_eye_imaging': probs['EYE_IMAGING'],
                'prob_software': probs['EYE_SOFTWARE'],
                'prob_edge': probs['EDGE_CASE'],
                'prob_negative': probs['NEGATIVE'],
                'title': r.get('metadata', {}).get('title', '')[:200],
                'description': metadata_details['description'],
                'keywords': metadata_details['keywords'],
                'access_right': metadata_details['access_right'],
                'license': metadata_details['license'],
                'resource_type': metadata_details['resource_type'],
                'file_types': file_details['file_types'],
                'file_names': file_details['file_names'],
                'file_count': file_details['file_count'],
                'img_count': file_details['img_count'],
                'medical_count': file_details['medical_count'],
                'archive_count': file_details['archive_count'],
                'genomics_count': file_details['genomics_count'],
                'size_mb': round(file_details['total_size'] / (1024*1024), 1),
                'dataset_links': dataset_links,
                'related_dois': metadata_details['related_dois'],
            }
            all_results.append(result)

        if (i + BATCH_SIZE) % 500 == 0:
            print(f"  Processed {min(i + BATCH_SIZE, len(records)):,} / {len(records):,}")

    # Analyze
    _print_analysis(all_results)

    # Save results (backward-compatible filenames)
    results_dir.mkdir(exist_ok=True, parents=True)

    eye_imaging = [r for r in all_results if r['label'] == 'EYE_IMAGING']
    software = [r for r in all_results if r['label'] == 'EYE_SOFTWARE']

    eye_imaging.sort(key=lambda x: (-x['prob_eye_imaging'], -x['size_mb']))
    software.sort(key=lambda x: (-x['confidence'], -x['size_mb']))

    with open(results_dir / 'zenodo_eye_imaging.json', 'w') as f:
        json.dump(eye_imaging, f, indent=2)

    with open(results_dir / 'zenodo_software.json', 'w') as f:
        json.dump(software, f, indent=2)

    with open(results_dir / 'zenodo_all_results.json', 'w') as f:
        json.dump(all_results, f, indent=2)

    print(f"\n{'='*70}")
    print("OUTPUT FILES")
    print("=" * 70)
    print(f"  Results: {results_dir}")
    print(f"    - zenodo_eye_imaging.json ({len(eye_imaging):,} records)")
    print(f"    - zenodo_software.json ({len(software):,} records)")
    print(f"    - zenodo_all_results.json ({len(all_results):,} records)")
    print(f"  Model: {output_dir}")
    print(f"\nTimestamp: {datetime.now().isoformat()}")

    # ADDF export (if requested)
    if addf_output_dir:
        from .addf_export import ADDFExporter
        from .scraper import _to_metadata

        addf_output_dir = Path(addf_output_dir)
        addf_records = []
        for r, record in zip(all_results, records):
            if r['label'] in ('EYE_IMAGING', 'EYE_SOFTWARE'):
                meta = _to_metadata(record)
                cls_result = {
                    'label': r['label'],
                    'confidence': r['confidence'],
                    'probabilities': {
                        'EYE_IMAGING': r['prob_eye_imaging'],
                        'EYE_SOFTWARE': r['prob_software'],
                        'EDGE_CASE': r['prob_edge'],
                        'NEGATIVE': r['prob_negative'],
                    },
                }
                addf_records.append((meta, cls_result))

        if addf_records:
            paths = ADDFExporter.export_batch(addf_records, addf_output_dir)
            print(f"\n  ADDF export: {len(paths)} records to {addf_output_dir}")

    return all_results


def _print_analysis(all_results: list[dict]):
    """Print classification analysis summary."""
    eye_imaging = [r for r in all_results if r['label'] == 'EYE_IMAGING']
    software = [r for r in all_results if r['label'] == 'EYE_SOFTWARE']
    edge_cases = [r for r in all_results if r['label'] == 'EDGE_CASE']
    negative = [r for r in all_results if r['label'] == 'NEGATIVE']

    print(f"\n{'='*70}")
    print("CLASSIFICATION RESULTS")
    print("=" * 70)
    print(f"  EYE_IMAGING:  {len(eye_imaging):,}")
    print(f"  EYE_SOFTWARE: {len(software):,}")
    print(f"  EDGE_CASE:    {len(edge_cases):,}")
    print(f"  NEGATIVE:     {len(negative):,}")

    # File type distribution
    print(f"\n{'='*70}")
    print("FILE TYPE DISTRIBUTION (EYE_IMAGING)")
    print("=" * 70)
    type_counts = Counter()
    for r in eye_imaging:
        for ft in r.get('file_types', []):
            type_counts[ft] += 1
    for ft, count in type_counts.most_common(15):
        print(f"  {ft}: {count:,}")

    # Confidence distribution
    print(f"\n{'='*70}")
    print("CONFIDENCE DISTRIBUTION (EYE_IMAGING)")
    print("=" * 70)
    high_conf = [r for r in eye_imaging if r['confidence'] >= 0.95]
    med_conf = [r for r in eye_imaging if 0.80 <= r['confidence'] < 0.95]
    low_conf = [r for r in eye_imaging if r['confidence'] < 0.80]
    print(f"  High (>=0.95):    {len(high_conf):,}")
    print(f"  Medium (0.80-0.95): {len(med_conf):,}")
    print(f"  Lower (<0.80):   {len(low_conf):,}")

    link_key = 'dataset_links' if 'dataset_links' in (all_results[0] if all_results else {}) else 'external_links'
    with_links = [r for r in eye_imaging if r.get(link_key)]
    print(f"\n  Records with external dataset links: {len(with_links):,}")


# ============================================================
# Backward-compatible entry point
# ============================================================

def run_zenodo_pipeline(classify_only=None, metadata_dir=None, results_dir=None):
    """Run the full Zenodo classification pipeline (backward compatible).

    Args:
        classify_only: If True, load existing model instead of training.
                      Defaults to checking --classify-only in sys.argv.
        metadata_dir: Directory containing Zenodo metadata JSON files.
        results_dir: Directory to save results.
    """
    import sys

    if classify_only is None:
        classify_only = '--classify-only' in sys.argv

    return run_pipeline(
        source="zenodo",
        classify_only=classify_only,
        metadata_dir=metadata_dir,
        results_dir=results_dir,
    )
