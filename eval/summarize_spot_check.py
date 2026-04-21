"""Summarize the over-length records in the 92-record SPOT_CHECK labeled set.

Reuses the summarization cache at eval/results/summary_cache so anything
already seen in the expert-validation run is free. Writes output to
eval/results/spot_check_summaries.json keyed by zenodo_id.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "envision-classifier" / "preprocess_scripts"))
sys.path.insert(0, str(ROOT / "eval"))

from llama_loader import JSON_MODEL_ID, load_llama  # type: ignore
from summarize_descriptions import (  # type: ignore
    CLASSIFIER_TOKEN_BUDGET,
    SummaryCache,
    joined_classifier_text,
    mpnet_token_count,
    summarize_one,
    warmup_and_self_check,
)

from model_eval import SPOT_CHECK, load_zenodo_records, get_record_text  # type: ignore


def main() -> int:
    meta_dir = ROOT / "data" / "metadata" / "zenodo_full"
    if not meta_dir.exists():
        meta_dir = ROOT / "data" / "metadata" / "zenodo"
    print(f"Using metadata dir: {meta_dir}")
    zs = load_zenodo_records(meta_dir)
    by_id = {str(r.get("zenodo_id") or r.get("id")): r for r in zs}

    cache_dir = ROOT / "eval" / "results" / "summary_cache"
    cache = SummaryCache(cache_dir)

    long_ids = []
    for zid, gt in SPOT_CHECK:
        r = by_id.get(zid)
        if r is None:
            continue
        text = get_record_text(r)
        n = mpnet_token_count(text)
        if n > CLASSIFIER_TOKEN_BUDGET:
            long_ids.append((zid, gt, r, text, n))

    print(f"Long records in SPOT_CHECK (>{CLASSIFIER_TOKEN_BUDGET} tokens): {len(long_ids)}")
    if not long_ids:
        return 0

    # Only load the LLM if at least one summary is not cached
    model, tokenizer = None, None

    results = {}
    for zid, gt, r, text, n_tok in long_ids:
        desc = r.get("description", "") or r.get("metadata", {}).get("description", "") or ""
        # We summarize the description; the classifier text re-joins with title+keywords
        if not desc:
            print(f"  {zid}: no description field — skipping")
            continue
        # Check cache first
        from summarize_descriptions import _cache_key  # type: ignore

        key = _cache_key(desc, JSON_MODEL_ID)
        cached = cache.get(key)
        if cached is None and model is None:
            print("Loading Llama (4-bit NF4)...")
            model, tokenizer = load_llama(JSON_MODEL_ID, quantization="4bit")
            if not warmup_and_self_check(model, tokenizer):
                print("Reproducibility check failed; aborting")
                return 2

        payload = summarize_one(desc, cache, model, tokenizer)
        results[zid] = {
            "ground_truth": gt,
            "original_desc": desc,
            "summary": payload["summary"],
            "input_mpnet_tokens": payload["input_mpnet_tokens"],
            "summary_mpnet_tokens": payload["summary_mpnet_tokens"],
            "joined_before": n_tok,
        }
        print(
            f"  {zid} ({gt}): {payload['input_mpnet_tokens']} -> "
            f"{payload['summary_mpnet_tokens']} tok  "
            f"{'[cache]' if payload.get('cache_hit') else ''}"
        )

    out = ROOT / "eval" / "results" / "spot_check_summaries.json"
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"Wrote {out} ({len(results)} summaries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
