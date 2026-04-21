"""Generate a 30-record audit CSV for an ophthalmologist-literate reviewer
to score summary factual fidelity. Stratified sample across sources and
confidence tiers so the reviewer sees a representative mix.

Columns:
  - id (sequential)
  - source, source_id, url (for clicking through to the source)
  - title
  - original_description (ground truth)
  - summary (LLM output under review)
  - predicted_label, confidence (classifier's judgement on the pre-summary text)
  - fidelity_score  (reviewer fills in: 1=good, 0=acceptable, -1=hallucination/wrong)
  - notes           (reviewer fills in)
"""

from __future__ import annotations

import csv
import json
import random
from pathlib import Path

TARGET = Path("eval/results/expert_validation_356_records.json")
OUT_CSV = Path("eval/results/summary_fidelity_audit_n30.csv")

N = 30
SEED = 42


def main() -> int:
    with TARGET.open() as f:
        records = json.load(f)
    pool = [r for r in records if "description_summary_meta" in r]
    print(f"Pool: {len(pool)} summarized records")

    # Stratify by source for balanced sampling
    by_source: dict[str, list[dict]] = {}
    for r in pool:
        by_source.setdefault(r["source"], []).append(r)
    print("By source:", {k: len(v) for k, v in by_source.items()})

    random.seed(SEED)
    # Proportional allocation with at least 1 per source
    total = len(pool)
    alloc = {}
    remaining = N
    for src, items in sorted(by_source.items(), key=lambda kv: -len(kv[1])):
        take = max(1, round(N * len(items) / total))
        take = min(take, len(items), remaining)
        alloc[src] = take
        remaining -= take
    # Distribute any leftover to the largest strata
    if remaining > 0:
        for src, _ in sorted(by_source.items(), key=lambda kv: -len(kv[1])):
            if remaining == 0:
                break
            if alloc[src] < len(by_source[src]):
                alloc[src] += 1
                remaining -= 1

    print("Allocation:", alloc, "total", sum(alloc.values()))

    sample = []
    for src, k in alloc.items():
        sample.extend(random.sample(by_source[src], k))
    random.shuffle(sample)

    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "id", "source", "source_id", "url", "title",
            "original_description", "summary",
            "predicted_label", "confidence",
            "fidelity_score_{1=faithful,0=minor_paraphrase,-1=hallucination_or_drop}",
            "notes",
        ])
        for i, r in enumerate(sample, 1):
            writer.writerow([
                i,
                r["source"], r["source_id"], r.get("url", ""),
                r["title"],
                r["description_original"],
                r["description"],
                r.get("predicted_label", ""),
                f"{r.get('confidence', 0):.4f}",
                "",  # reviewer fills in
                "",  # reviewer fills in
            ])
    print(f"Wrote {OUT_CSV} ({len(sample)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
