"""A/B test: does summarization preserve the information the classifier
needs? Run the deployed classifier on the 77 long records in the
expert-validation set with (a) the full original description and (b) the
LLM summary. Compare predictions, confidences, and per-class F1 against
the predicted_label already stored in the JSON (which was produced on
the pre-summarization text).

This tests the information-loss hypothesis of the summarization step
independent of any retraining effect: same classifier, same weights,
different inputs.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "eval" / "results" / "expert_validation_356_records.json"
OUT = ROOT / "eval" / "results" / "ab_summarization_results.json"

sys.path.insert(0, str(ROOT / "envision-classifier"))
from envision_classifier.classifier import EyeImagingClassifier


def classifier_input(title: str, description: str, keywords) -> str:
    parts = [title or "", description or ""]
    if keywords:
        if isinstance(keywords, list):
            parts.append(" ".join(keywords))
        else:
            parts.append(str(keywords))
    return " ".join(p for p in parts if p).strip()


def main() -> int:
    with TARGET.open() as f:
        records = json.load(f)

    # Only the records that got summarized
    targets = [r for r in records if "description_summary_meta" in r]
    print(f"A/B testing {len(targets)} summarized records", flush=True)

    if not targets:
        print("No summarized records found; nothing to test.")
        return 0

    print("Loading deployed classifier...", flush=True)
    clf = EyeImagingClassifier()

    print("Classifying with ORIGINAL text...", flush=True)
    original_texts = [
        classifier_input(r["title"], r["description_original"], r.get("keywords"))
        for r in targets
    ]
    original_results = clf.classify_batch(original_texts, verbose=True)

    print("Classifying with SUMMARY text...", flush=True)
    summary_texts = [
        classifier_input(r["title"], r["description"], r.get("keywords"))
        for r in targets
    ]
    summary_results = clf.classify_batch(summary_texts, verbose=True)

    # Agreement metrics
    agree = 0
    flips = []  # records where label changed
    conf_deltas = []

    per_record = []
    for r, a, b in zip(targets, original_results, summary_results):
        same_label = a["label"] == b["label"]
        agree += int(same_label)
        conf_deltas.append(b["confidence"] - a["confidence"])
        entry = {
            "source": r["source"],
            "source_id": r["source_id"],
            "stored_predicted_label": r.get("predicted_label"),
            "stored_confidence": r.get("confidence"),
            "original_label": a["label"],
            "original_confidence": a["confidence"],
            "summary_label": b["label"],
            "summary_confidence": b["confidence"],
            "agree": same_label,
            "input_mpnet_tokens": r["description_summary_meta"]["input_mpnet_tokens"],
            "summary_mpnet_tokens": r["description_summary_meta"]["summary_mpnet_tokens"],
        }
        per_record.append(entry)
        if not same_label:
            flips.append(entry)

    n = len(targets)
    agreement_rate = agree / n if n else 0.0
    mean_conf_delta = float(np.mean(conf_deltas)) if conf_deltas else 0.0
    median_conf_delta = float(np.median(conf_deltas)) if conf_deltas else 0.0

    # Per-class confusion (original label -> summary label)
    labels = ["NEGATIVE", "EYE_IMAGING"]
    cm = {a: {b: 0 for b in labels} for a in labels}
    for rec in per_record:
        cm[rec["original_label"]][rec["summary_label"]] += 1

    summary_out = {
        "n_summarized": n,
        "agreement_rate": agreement_rate,
        "flips": len(flips),
        "mean_confidence_delta": mean_conf_delta,  # summary - original
        "median_confidence_delta": median_conf_delta,
        "confusion_matrix_original_to_summary": cm,
        "flipped_records": flips,
        "per_record": per_record,
    }

    print()
    print("=" * 60)
    print(f"n_summarized:         {n}")
    print(f"agreement_rate:       {agreement_rate:.3f}  ({agree}/{n})")
    print(f"label flips:          {len(flips)}")
    print(f"mean conf delta:      {mean_conf_delta:+.4f}  (summary - original)")
    print(f"median conf delta:    {median_conf_delta:+.4f}")
    print()
    print("Confusion (original label → summary label):")
    print(f"                 →NEG    →EYE")
    for a in labels:
        row = cm[a]
        print(f"  {a:13s}  {row['NEGATIVE']:>5}   {row['EYE_IMAGING']:>5}")
    print()
    if flips:
        print("Flipped records:")
        for f in flips:
            print(
                f"  {f['source']}/{f['source_id']}: "
                f"{f['original_label']}({f['original_confidence']:.3f}) "
                f"→ {f['summary_label']}({f['summary_confidence']:.3f})"
            )

    OUT.write_text(json.dumps(summary_out, indent=2))
    print(f"\nWrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
