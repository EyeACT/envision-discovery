"""Re-fetch and re-summarize the 7 expert-validation records whose
``description_original`` was inadvertently preserved at 2000 chars
(the pre-fix scraper cap). For each, we pull the full source text from
the Figshare API, overwrite description_original, and re-run
summarization so the summary is derived from the full text.

Predicted labels/confidences are left untouched — they were produced on
the original long text before any preprocessing, and the deployment
record for those predictions pre-dates this fix.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "eval" / "results" / "expert_validation_356_records.json"

sys.path.insert(0, str(ROOT))
from envision.utils import clean_text  # type: ignore

sys.path.insert(0, str(ROOT / "envision-classifier" / "preprocess_scripts"))
from llama_loader import JSON_MODEL_ID, load_llama  # type: ignore
from summarize_descriptions import (  # type: ignore
    CLASSIFIER_TOKEN_BUDGET,
    SummaryCache,
    joined_classifier_text,
    mpnet_token_count,
    summarize_one,
    warmup_and_self_check,
)


def is_capped_at_2000(s: str | None) -> bool:
    if not s:
        return False
    n = len(s)
    if not (1985 <= n <= 2002):
        return False
    stripped = s.rstrip()
    return bool(stripped) and stripped[-1] not in ".!?"


def fetch_figshare(article_id: str) -> str | None:
    try:
        r = requests.get(
            f"https://api.figshare.com/v2/articles/{article_id}", timeout=15
        )
        if r.status_code == 200:
            return r.json().get("description")
    except Exception as e:
        print(f"    err {article_id}: {e}", flush=True)
    return None


def main() -> int:
    with TARGET.open() as f:
        records = json.load(f)

    targets = [
        r for r in records
        if r.get("source") == "figshare"
        and "description_summary_meta" in r
        and is_capped_at_2000(r.get("description_original"))
    ]
    print(f"Figshare records with capped description_original: {len(targets)}")
    if not targets:
        return 0

    # Step 1: fetch fresh originals (API calls only, no LLM yet)
    for r in targets:
        sid = str(r["source_id"])
        print(f"  fetch figshare/{sid} ...", end="", flush=True)
        raw = fetch_figshare(sid)
        if not raw:
            print(" FAIL")
            continue
        cleaned = clean_text(raw) or ""
        old_len = len(r["description_original"])
        if len(cleaned) <= old_len:
            print(f" no improvement ({len(cleaned)} vs {old_len})")
            continue
        r["description_original"] = cleaned
        # Mark for re-summarization: overwrite description with full text
        # and drop the stale summary metadata so the summarizer treats it
        # as a fresh record.
        r["description"] = cleaned
        r.pop("description_summary_meta", None)
        print(f" {old_len} -> {len(cleaned)} chars, flagged for resummary")
        time.sleep(0.5)

    # Save after the API step — in case the LLM load fails, we at least
    # have the detruncated originals persisted.
    TARGET.write_text(json.dumps(records, indent=2, ensure_ascii=False))
    print(f"Saved detruncated originals to {TARGET}")

    # Step 2: re-summarize the records we just flagged
    to_resummarize = [r for r in targets if "description_summary_meta" not in r]
    if not to_resummarize:
        print("No records need re-summarization.")
        return 0
    print(f"Re-summarizing {len(to_resummarize)} records...")

    cache = SummaryCache(ROOT / "eval" / "results" / "summary_cache")
    print("Loading Llama (4-bit NF4)...")
    model, tokenizer = load_llama(JSON_MODEL_ID, quantization="4bit")
    if not warmup_and_self_check(model, tokenizer):
        print("Reproducibility check failed — aborting re-summarization.")
        return 2

    for r in to_resummarize:
        title = r.get("title", "")
        orig = r["description_original"]
        kw = r.get("keywords")
        joined_before = mpnet_token_count(joined_classifier_text(title, orig, kw))
        print(f"  {r['source']}/{r['source_id']}: joined_before={joined_before} tok")

        payload = summarize_one(orig, cache, model, tokenizer)
        summary = payload["summary"]
        joined_after = mpnet_token_count(joined_classifier_text(title, summary, kw))

        r["description"] = summary
        r["description_summary_meta"] = {
            "model_id": payload["model_id"],
            "prompt_version": payload["prompt_version"],
            "quant_config": payload["quant_config"],
            "input_sha256": payload["input_sha256"],
            "input_mpnet_tokens": payload["input_mpnet_tokens"],
            "summary_mpnet_tokens": payload["summary_mpnet_tokens"],
            "joined_mpnet_tokens_before": joined_before,
            "joined_mpnet_tokens_after": joined_after,
        }
        print(
            f"    {payload['input_mpnet_tokens']} -> "
            f"{payload['summary_mpnet_tokens']} tok (joined {joined_before} -> {joined_after})"
        )

    TARGET.write_text(json.dumps(records, indent=2, ensure_ascii=False))
    print(f"Wrote {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
