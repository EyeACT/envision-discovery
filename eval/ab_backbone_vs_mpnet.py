"""2x2 experiment: {MPNet deployed, ModernBERT-large} x {original, summary}.

Answers two questions:
  1. Does summarization help even on a labeled test set where we can
     compute F1? (Spot-check set: 92 labeled Zenodo records, 11 of which
     exceed 512 MPNet tokens.)
  2. On the subset of records where summarization actually triggers
     (the 77 long records in the expert-validation set), how do the four
     arms agree with each other?

Outputs: eval/results/ab_backbone_results.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import joblib
import numpy as np
from sklearn.metrics import f1_score, precision_recall_fscore_support

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "envision-classifier"))
sys.path.insert(0, str(ROOT / "envision-classifier" / "preprocess_scripts"))
sys.path.insert(0, str(ROOT / "eval"))

from envision_classifier.classifier import EyeImagingClassifier  # type: ignore
from summarize_descriptions import (  # type: ignore
    CLASSIFIER_TOKEN_BUDGET,
    joined_classifier_text,
    mpnet_token_count,
)
from model_eval import SPOT_CHECK, load_zenodo_records, get_record_text  # type: ignore

BINARY_LABELS = ["NEGATIVE", "EYE_IMAGING"]

MODERNBERT_DIR = ROOT / "eval" / "results" / "full-data_cosine-warmup_modernbert-embed-large"


def load_modernbert():
    from sentence_transformers import SentenceTransformer

    st = SentenceTransformer(str(MODERNBERT_DIR), trust_remote_code=True)
    head = joblib.load(MODERNBERT_DIR / "model_head.pkl")
    return st, head


def classify_modernbert(st, head, texts: list[str]) -> list[dict]:
    emb = st.encode(texts, convert_to_numpy=True, show_progress_bar=False)
    preds = head.predict(emb)
    probas = head.predict_proba(emb)
    out = []
    for p, pr in zip(preds, probas):
        idx = int(p)
        out.append({
            "label": BINARY_LABELS[idx],
            "confidence": float(max(pr)),
            "probabilities": {BINARY_LABELS[0]: float(pr[0]), BINARY_LABELS[1]: float(pr[1])},
        })
    return out


def build_pair(record: dict, spot_summaries: dict) -> tuple[str, str, int, bool]:
    """Return (original_text, summary_text, joined_mpnet_tokens, is_long)."""
    title = record.get("title", "")
    desc = record.get("description", "") or record.get("metadata", {}).get("description", "") or ""
    kw = record.get("keywords", "")
    original = joined_classifier_text(title, desc, kw)
    n_tok = mpnet_token_count(original)
    is_long = n_tok > CLASSIFIER_TOKEN_BUDGET

    zid = str(record.get("zenodo_id") or record.get("id"))
    if is_long and zid in spot_summaries:
        summary_desc = spot_summaries[zid]["summary"]
        summary_text = joined_classifier_text(title, summary_desc, kw)
    else:
        summary_text = original

    return original, summary_text, n_tok, is_long


def score(labels_true: list[str], labels_pred: list[str]) -> dict:
    y_true = [1 if l == "EYE_IMAGING" else 0 for l in labels_true]
    y_pred = [1 if l == "EYE_IMAGING" else 0 for l in labels_pred]
    acc = sum(int(a == b) for a, b in zip(y_true, y_pred)) / len(y_true)
    p, r, f, _ = precision_recall_fscore_support(
        y_true, y_pred, average=None, labels=[0, 1], zero_division=0
    )
    macro = f1_score(y_true, y_pred, average="macro", zero_division=0)
    return {
        "accuracy": round(acc, 4),
        "macro_f1": round(macro, 4),
        "per_class": {
            "NEGATIVE":    {"precision": round(p[0], 4), "recall": round(r[0], 4), "f1": round(f[0], 4)},
            "EYE_IMAGING": {"precision": round(p[1], 4), "recall": round(r[1], 4), "f1": round(f[1], 4)},
        },
    }


def main() -> int:
    # ---- Load summaries from the spot check that were produced by the Llama run ----
    spot_summaries_path = ROOT / "eval" / "results" / "spot_check_summaries.json"
    with spot_summaries_path.open() as f:
        spot_summaries = json.load(f)

    # ---- Load spot-check records with ground truth ----
    meta_dir = ROOT / "data" / "metadata" / "zenodo_full"
    if not meta_dir.exists():
        meta_dir = ROOT / "data" / "metadata" / "zenodo"
    z_records = load_zenodo_records(meta_dir)
    by_zid = {str(r.get("zenodo_id") or r.get("id")): r for r in z_records}

    spot_items = []  # (zid, gt, original_text, summary_text, is_long)
    for zid, gt in SPOT_CHECK:
        r = by_zid.get(zid)
        if r is None:
            continue
        orig, summ, n_tok, is_long = build_pair(r, spot_summaries)
        spot_items.append({
            "zenodo_id": zid,
            "ground_truth": gt,
            "original_text": orig,
            "summary_text": summ,
            "joined_mpnet_tokens": n_tok,
            "is_long": is_long,
        })
    print(f"Spot-check items (with GT): {len(spot_items)}; long: "
          f"{sum(1 for s in spot_items if s['is_long'])}")

    # ---- Load 77 long validation records ----
    val_path = ROOT / "eval" / "results" / "expert_validation_356_records.json"
    with val_path.open() as f:
        val_recs = json.load(f)
    long_val = [r for r in val_recs if "description_summary_meta" in r]
    long_items = []
    for r in long_val:
        title = r.get("title", "")
        orig_desc = r.get("description_original", "") or ""
        summ_desc = r.get("description", "") or ""
        kw = r.get("keywords", "")
        orig_text = joined_classifier_text(title, orig_desc, kw)
        summ_text = joined_classifier_text(title, summ_desc, kw)
        long_items.append({
            "source": r.get("source"),
            "source_id": r.get("source_id"),
            "original_text": orig_text,
            "summary_text": summ_text,
        })
    print(f"Long validation items: {len(long_items)}")

    # ---- Load classifiers ----
    print("Loading MPNet (deployed)...", flush=True)
    mpnet = EyeImagingClassifier()
    print("Loading ModernBERT-large (full-data cosine-warmup variant)...", flush=True)
    mb_st, mb_head = load_modernbert()

    # ---- Classify spot-check on 4 arms ----
    print("\nClassifying spot-check (4 arms)...")
    spot_orig = [s["original_text"] for s in spot_items]
    spot_summ = [s["summary_text"] for s in spot_items]

    mp_orig = mpnet.classify_batch(spot_orig, verbose=False)
    mp_summ = mpnet.classify_batch(spot_summ, verbose=False)
    mb_orig = classify_modernbert(mb_st, mb_head, spot_orig)
    mb_summ = classify_modernbert(mb_st, mb_head, spot_summ)

    gt = [s["ground_truth"] for s in spot_items]
    spot_metrics = {
        "mpnet_original":      score(gt, [r["label"] for r in mp_orig]),
        "mpnet_summary":       score(gt, [r["label"] for r in mp_summ]),
        "modernbert_original": score(gt, [r["label"] for r in mb_orig]),
        "modernbert_summary":  score(gt, [r["label"] for r in mb_summ]),
    }

    # Long-only subset (where summarization actually triggers)
    long_idx = [i for i, s in enumerate(spot_items) if s["is_long"]]
    if long_idx:
        gt_long = [gt[i] for i in long_idx]
        spot_metrics_long = {
            "mpnet_original":      score(gt_long, [mp_orig[i]["label"] for i in long_idx]),
            "mpnet_summary":       score(gt_long, [mp_summ[i]["label"] for i in long_idx]),
            "modernbert_original": score(gt_long, [mb_orig[i]["label"] for i in long_idx]),
            "modernbert_summary":  score(gt_long, [mb_summ[i]["label"] for i in long_idx]),
        }
    else:
        spot_metrics_long = None

    # ---- Classify 77 long validation records on 4 arms ----
    print("\nClassifying long validation records (4 arms)...")
    val_orig = [v["original_text"] for v in long_items]
    val_summ = [v["summary_text"] for v in long_items]
    mp_orig_v = mpnet.classify_batch(val_orig, verbose=False)
    mp_summ_v = mpnet.classify_batch(val_summ, verbose=False)
    mb_orig_v = classify_modernbert(mb_st, mb_head, val_orig)
    mb_summ_v = classify_modernbert(mb_st, mb_head, val_summ)

    # Pairwise agreement on long validation (no GT)
    def agreement(a, b):
        return sum(1 for x, y in zip(a, b) if x["label"] == y["label"]) / len(a)

    val_agreement = {
        "mpnet_orig_vs_mpnet_summ":       round(agreement(mp_orig_v, mp_summ_v), 4),
        "mbert_orig_vs_mbert_summ":       round(agreement(mb_orig_v, mb_summ_v), 4),
        "mpnet_orig_vs_mbert_orig":       round(agreement(mp_orig_v, mb_orig_v), 4),
        "mpnet_summ_vs_mbert_orig":       round(agreement(mp_summ_v, mb_orig_v), 4),
        "mpnet_summ_vs_mbert_summ":       round(agreement(mp_summ_v, mb_summ_v), 4),
    }

    # Mean confidence per arm on long validation
    def mean_conf(arm):
        return round(float(np.mean([r["confidence"] for r in arm])), 4)

    val_confidence = {
        "mpnet_original":      mean_conf(mp_orig_v),
        "mpnet_summary":       mean_conf(mp_summ_v),
        "modernbert_original": mean_conf(mb_orig_v),
        "modernbert_summary":  mean_conf(mb_summ_v),
    }

    out = {
        "spot_check": {
            "n": len(spot_items),
            "n_long": len(long_idx),
            "all_records_metrics": spot_metrics,
            "long_records_only_metrics": spot_metrics_long,
        },
        "long_validation": {
            "n": len(long_items),
            "pairwise_agreement": val_agreement,
            "mean_confidence": val_confidence,
        },
    }

    out_path = ROOT / "eval" / "results" / "ab_backbone_results.json"
    out_path.write_text(json.dumps(out, indent=2))
    print(f"\nWrote {out_path}")

    # Pretty print
    print("\n" + "=" * 70)
    print(f"SPOT-CHECK (n={len(spot_items)}, labeled) — macro F1 on ALL records:")
    for arm, m in spot_metrics.items():
        print(f"  {arm:22s} acc={m['accuracy']:.3f}  macro_f1={m['macro_f1']:.3f}  "
              f"EI_f1={m['per_class']['EYE_IMAGING']['f1']:.3f}")
    if spot_metrics_long:
        print(f"\nSPOT-CHECK LONG SUBSET (n={len(long_idx)}, >512 tokens):")
        for arm, m in spot_metrics_long.items():
            print(f"  {arm:22s} acc={m['accuracy']:.3f}  macro_f1={m['macro_f1']:.3f}  "
                  f"EI_f1={m['per_class']['EYE_IMAGING']['f1']:.3f}")
    print(f"\nLONG VALIDATION (n={len(long_items)}, unlabeled) — pairwise agreement:")
    for pair, a in val_agreement.items():
        print(f"  {pair:38s} {a:.4f}")
    print(f"\nLONG VALIDATION — mean confidence:")
    for arm, c in val_confidence.items():
        print(f"  {arm:22s} {c:.4f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
