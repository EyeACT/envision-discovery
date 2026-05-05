#!/usr/bin/env python3
"""
ENVISION: Classification Pipeline

Takes DatasetMetadata records, classifies them with EyeImagingClassifier,
and writes results to disk. This module has one job: classify.
It does not scrape, does not load from disk, does not decide sources.
"""

import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from envision_classifier import EyeImagingClassifier

from .metadata import DatasetMetadata


def run_pipeline(
    metadata_records: list[DatasetMetadata],
    source: str,
    results_dir: str | Path | None = None,
    addf_output_dir: str | Path | None = None,
    **kwargs,
):
    """Classify records and save results.

    Args:
        metadata_records: Records to classify.
        source: Source name for output filenames.
        results_dir: Output directory. Defaults to ./results.
        addf_output_dir: Optional ADDF export directory.
    """
    BASE_DIR = Path(__file__).resolve().parent.parent
    results_dir = Path(results_dir) if results_dir else BASE_DIR / "results"

    print(f"\n{'='*70}", flush=True)
    print(f"Classifying {len(metadata_records):,} {source} records", flush=True)
    print(f"Timestamp: {datetime.now().isoformat()}", flush=True)
    print("=" * 70, flush=True)

    # ── Load classifier ──────────────────────────────────────────────
    classifier = _load_classifier()
    print(f"Device: {classifier._device}", flush=True)

    # ── Sanitize text fields (strip HTML, fix mojibake, normalize unicode) ──
    # TODO: please fix
    # for m in metadata_records:
    #     m.sanitize()

    # ── Classify ─────────────────────────────────────────────────────
    texts = [m.to_classifier_text() for m in metadata_records]
    print(f"  Classifying {len(texts):,} texts...", flush=True)
    sys.stdout.flush()

    classifications = classifier.classify_batch(texts, batch_size=16)

    # ── Build + save results ─────────────────────────────────────────
    all_results, addf_records = _build_results(metadata_records, classifications)
    _save_results(all_results, source, results_dir)
    _print_summary(all_results)

    if addf_output_dir and addf_records:
        from .addf_export import ADDFExporter

        addf_output_dir = Path(addf_output_dir)
        paths = ADDFExporter.export_batch(addf_records, addf_output_dir)
        print(f"  ADDF export: {len(paths)} records → {addf_output_dir}", flush=True)

    return all_results


def _load_classifier():
    """Load the classifier from HuggingFace (cached locally after first download)."""
    return EyeImagingClassifier()


def _build_results(metadata_records, classifications):
    """Pair metadata with classification results."""
    all_results = []
    addf_records = []

    for meta, cls in zip(metadata_records, classifications):
        probs = cls["probabilities"]
        result = {
            "source": meta.source,
            "source_id": meta.source_id,
            "doi": meta.doi,
            "url": meta.url,
            "label": cls["label"],
            "confidence": cls["confidence"],
            "prob_eye_imaging": probs.get("EYE_IMAGING", 0),
            "prob_negative": probs.get("NEGATIVE", 0),
            "title": meta.title[:200],
            # No aggressive truncation on description: downstream consumers
            # (portal UI, expert validation, paper figures) need the full
            # text. Classifier input truncation happens separately in the
            # classifier's tokenizer (MAX_TOKENS=512 tokens, not chars).
            # The 10 KB safety cap prevents pathological inputs from
            # bloating the results JSON.
            "description": meta.description[:10_000],
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
            "zip_file_types": {},
            "external_links": meta.external_links[:10],
            "related_dois": [],
        }
        all_results.append(result)
        if cls["label"] == "EYE_IMAGING":
            addf_records.append((meta, cls))

    return all_results, addf_records


def _save_results(all_results, source, results_dir):
    """Write classification results to disk."""
    results_dir.mkdir(exist_ok=True, parents=True)

    eye_imaging = sorted(
        [r for r in all_results if r["label"] == "EYE_IMAGING"],
        key=lambda x: (-x["prob_eye_imaging"], -x.get("size_mb", 0)),
    )

    with open(results_dir / f"{source}_eye_imaging.json", "w") as f:
        json.dump(eye_imaging, f, indent=2)
    with open(results_dir / f"{source}_all_results.json", "w") as f:
        json.dump(all_results, f, indent=2)

    print(f"  Results → {results_dir}/", flush=True)
    print(f"    {source}_eye_imaging.json  ({len(eye_imaging):,} records)", flush=True)
    print(f"    {source}_all_results.json  ({len(all_results):,} records)", flush=True)


def _print_summary(all_results):
    """Print classification summary."""
    eye = [r for r in all_results if r["label"] == "EYE_IMAGING"]
    neg = [r for r in all_results if r["label"] == "NEGATIVE"]

    print(f"\n  EYE_IMAGING: {len(eye):,}  |  NEGATIVE: {len(neg):,}", flush=True)

    if eye:
        high = sum(1 for r in eye if r["confidence"] >= 0.95)
        med = sum(1 for r in eye if 0.80 <= r["confidence"] < 0.95)
        low = sum(1 for r in eye if r["confidence"] < 0.80)
        print(
            f"  Confidence: {high} high (>=0.95), {med} medium, {low} low", flush=True
        )

        types = Counter()
        for r in eye:
            for ft in r.get("file_types", []):
                types[ft] += 1
        if types:
            top = ", ".join(f"{ft}({n})" for ft, n in types.most_common(5))
            print(f"  Top file types: {top}", flush=True)
