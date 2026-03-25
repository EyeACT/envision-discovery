#!/usr/bin/env python3
"""Score a repository's records using LLM for ground truth classification."""

import json, os, sys, time, csv, re, argparse
from pathlib import Path
from html import unescape
from openai import OpenAI


PROMPT = """You are classifying dataset records for an eye imaging data catalog.

Classify as EYE_IMAGING if the dataset is ABOUT eye/ophthalmic imaging, even if:
- The description focuses on the method/algorithm rather than listing files
- It's a challenge/benchmark dataset (REFUGE, AIROGS, IDRiD, DRIVE, STARE, etc.)
- It mentions fundus, OCT, OCTA, retinal images, optic disc, macula in context of image analysis
- It's a segmentation/detection/grading dataset where the source data is eye images
- It includes model weights trained on eye imaging AND likely ships with training images

Classify as NEGATIVE if:
- It's about non-eye anatomy (brain, heart, lung, kidney, skin) even if it uses OCT
- It's purely code/software with no associated image data
- It's eye-related but NOT imaging: genetics (GWAS), electrophysiology (ERG, spike trains, MEA), metabolomics, drug delivery, surveys, eye tracking/gaze
- It's about non-eye organisms mentioning "retinal" in biochemistry context
- It's reviews, meta-analyses, or text documents

Key: If a researcher looking for eye imaging datasets to train AI would find this useful, classify as EYE_IMAGING.

Respond: LABEL | one-sentence reason"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, help="Repository name (datacite, figshare, kaggle, dryad, nei)")
    parser.add_argument("--delay", type=float, default=0.05)
    args = parser.parse_args()

    api_key = os.environ.get("LLM_API_KEY")
    api_base = os.environ.get("LLM_API_BASE")
    if not api_key or not api_base:
        print("ERROR: Set LLM_API_KEY and LLM_API_BASE environment variables")
        sys.exit(1)
    client = OpenAI(api_key=api_key, base_url=api_base)

    base_dir = Path(__file__).resolve().parent.parent
    src_file = base_dir / "results" / f"{args.source}_all_results.json"

    with open(src_file) as f:
        records = json.load(f)

    print(f"Scoring {len(records)} {args.source} records...")

    results = []
    for i, rec in enumerate(records):
        title = rec.get("title", "")
        desc = (rec.get("description", "") or "")[:2000]
        if desc:
            desc = unescape(re.sub("<[^<]+?>", " ", desc)).strip()
        kw = rec.get("keywords", "") or ""
        if isinstance(kw, list):
            kw = ", ".join(kw)

        try:
            resp = client.chat.completions.create(
                model=os.environ.get("LLM_MODEL", "default"),
                messages=[
                    {"role": "system", "content": PROMPT},
                    {"role": "user", "content": f"Title: {title}\nDescription: {desc}\nKeywords: {kw}"},
                ],
                max_tokens=150, temperature=0,
            )
            answer = resp.choices[0].message.content.strip()
            if "|" in answer:
                label, reason = answer.split("|", 1)
                label = label.strip()
                reason = reason.strip()
            else:
                label = "EYE_IMAGING" if answer.upper().startswith("EYE") else "NEGATIVE"
                reason = answer
        except Exception as e:
            label = "ERROR"
            reason = str(e)

        results.append({
            "source_id": rec.get("source_id", rec.get("doi", "")),
            "title": title,
            "llm_label": label,
            "llm_reason": reason,
        })

        if (i + 1) % 100 == 0:
            eye = sum(1 for r in results if r["llm_label"] == "EYE_IMAGING")
            print(f"  [{i+1}/{len(records)}] EYE_IMAGING={eye} NEGATIVE={len(results)-eye}")

        time.sleep(args.delay)

    from collections import Counter
    labels = Counter(r["llm_label"] for r in results)
    print(f"\nDone! {dict(labels)}")

    # Save TSV
    out_path = base_dir / "eval" / "results" / f"{args.source}_llm_ground_truth.tsv"
    with open(out_path, "w", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["source_id", "llm_label", "llm_reason", "title"])
        for r in results:
            w.writerow([r["source_id"], r["llm_label"], r["llm_reason"], r["title"]])

    # Save JSON
    json_path = base_dir / "eval" / "results" / f"{args.source}_llm_ground_truth.json"
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"Saved to {out_path}")


if __name__ == "__main__":
    main()
