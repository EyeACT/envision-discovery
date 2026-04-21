"""Programmatic hallucination-rate estimate for the 77 summarized records.

For each summary, we extract tokens from a fixed whitelist of modality /
anatomy / subject terms and check whether each extracted term also appears
in the original description (case-insensitive, word-boundary). Any term
present in the summary but absent from the original is flagged.

This is a coarse check; it cannot detect paraphrasing or synonym-level
hallucinations (e.g., "retina" in the summary when the original only said
"macula"). It catches the failure mode that most matters for our classifier:
a fabricated imaging modality. Pair with the 30-record expert audit for
a full picture.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

TARGET = Path("eval/results/expert_validation_356_records.json")
OUT = Path("eval/results/hallucination_check_results.json")

# Terms we care about (lowercase). Any of these claimed by the summary but
# absent in the original is flagged.
MODALITY_TERMS = {
    "oct", "octa", "oct-a", "fundus", "slit-lamp", "slit lamp", "slitlamp",
    "mri", "magnetic resonance", "ct scan", "ct-scan", "ultrasound", "us",
    "fluorescein", "angiography", "indocyanine", "icg",
    "confocal", "microscop", "histolog", "wavefront",
    "adaptive optics", "electroretinogra", "erg", "visual field",
    "perimetry", "topograph", "pachymetry", "biometry",
    "optical coherence", "spectral domain", "sd-oct", "swept source", "ss-oct",
    "color fundus", "red-free", "autofluorescence",
    "scanning laser ophthalmoscop", "slo",
    "anterior segment", "posterior segment",
}
ANATOMY_TERMS = {
    "retina", "corneal", "cornea", "optic nerve", "optic disc", "optic cup",
    "macul", "fovea", "choroid", "iris", "lens",
    "rpe", "retinal pigment epithelium", "nerve fibre", "nerve fiber",
    "vitreous", "sclera", "trabecular meshwork",
}
SUBJECT_TERMS = {
    "human", "patient", "subject", "murine", "mouse", "mice",
    "rat", "rabbit", "primate", "monkey", "zebrafish", "pig",
    "bovine", "canine", "cadaver", "postmortem", "in vivo", "in vitro",
    "ex vivo", "phantom",
}
DATA_FORMAT_TERMS = {
    "image", "dicom", "nifti", "nii", "tiff", "png", "jpg",
    "segmentation", "mask", "annotation", "label",
    "video", "volumetric", "b-scan", "a-scan", "en face",
}

ALL_TERMS = MODALITY_TERMS | ANATOMY_TERMS | SUBJECT_TERMS | DATA_FORMAT_TERMS


def extract_claimed(text: str, terms: set[str]) -> set[str]:
    low = text.lower()
    claimed = set()
    for t in terms:
        # Multi-word terms: substring; single-word: use word boundaries
        if " " in t or "-" in t:
            if t in low:
                claimed.add(t)
        else:
            if re.search(rf"\b{re.escape(t)}\b", low):
                claimed.add(t)
    return claimed


# Bi-directional synonym classes. If the summary claims any member of a
# class and the original contains any other member of the same class, the
# claim counts as supported. Covers abbreviation-expansion pairs that
# otherwise trip the literal substring check.
SYNONYMS: list[set[str]] = [
    {"mri", "magnetic resonance", "magnetic resonance imaging"},
    {"oct", "optical coherence tomography"},
    {"octa", "oct-a", "oct angiography", "optical coherence tomography angiography"},
    {"slit-lamp", "slit lamp", "slitlamp"},
    {"ct", "ct scan", "ct-scan", "computed tomography"},
    {"erg", "electroretinogram", "electroretinography"},
    # "optic nerve" vs "ONH" (optic nerve head) vs typo "optic never head"
    {"optic nerve", "optic nerve head", "onh", "optic never head"},
    {"nerve fiber", "nerve fibre", "rnfl", "retinal nerve fiber", "retinal nerve fibre"},
    {"icg", "indocyanine", "indocyanine green"},
    {"slo", "scanning laser ophthalmoscop"},
    {"rpe", "retinal pigment epithelium"},
    {"us", "ultrasound", "ultrasonic"},
    {"sdoct", "sd-oct", "spectral-domain oct", "spectral domain oct"},
    {"ssoct", "ss-oct", "swept-source oct", "swept source oct"},
]


def check_supported(term: str, original_low: str) -> bool:
    """Does `term` or a synonym appear in the original?"""
    candidates = {term}
    for synset in SYNONYMS:
        if term in synset:
            candidates |= synset
    for cand in candidates:
        if " " in cand or "-" in cand:
            if cand in original_low:
                return True
        else:
            if re.search(rf"\b{re.escape(cand)}", original_low):
                return True
    return False


def main() -> int:
    with TARGET.open() as f:
        records = json.load(f)
    summarized = [r for r in records if "description_summary_meta" in r]
    print(f"Checking {len(summarized)} summarized records")

    by_category = {
        "modality": (MODALITY_TERMS, []),
        "anatomy": (ANATOMY_TERMS, []),
        "subject": (SUBJECT_TERMS, []),
        "data_format": (DATA_FORMAT_TERMS, []),
    }

    per_record = []
    total_claims = 0
    total_unsupported = 0
    records_with_any_unsupported = 0

    for r in summarized:
        summary = r["description"]
        original = r["description_original"]
        original_low = original.lower()

        rec_entry = {
            "source": r["source"],
            "source_id": r["source_id"],
            "title": r["title"][:80],
            "unsupported_claims": {},
        }

        any_unsupported = False
        for cat, (terms, bucket) in by_category.items():
            claimed = extract_claimed(summary, terms)
            unsupported = [t for t in claimed if not check_supported(t, original_low)]
            total_claims += len(claimed)
            total_unsupported += len(unsupported)
            if unsupported:
                rec_entry["unsupported_claims"][cat] = sorted(unsupported)
                any_unsupported = True
                bucket.extend(unsupported)

        if any_unsupported:
            records_with_any_unsupported += 1
        per_record.append(rec_entry)

    n = len(summarized)
    report = {
        "n_summarized": n,
        "records_with_any_unsupported_claim": records_with_any_unsupported,
        "hallucination_rate_records": records_with_any_unsupported / n if n else 0,
        "total_whitelist_claims": total_claims,
        "total_unsupported_claims": total_unsupported,
        "hallucination_rate_claims": total_unsupported / total_claims if total_claims else 0,
        "per_record_findings": [
            r for r in per_record if r["unsupported_claims"]
        ],
    }

    print()
    print(f"Records with any unsupported whitelist term: "
          f"{records_with_any_unsupported}/{n} "
          f"({report['hallucination_rate_records']:.1%})")
    print(f"Unsupported claims: {total_unsupported}/{total_claims} "
          f"({report['hallucination_rate_claims']:.1%})")

    if report["per_record_findings"]:
        print("\nRecords flagged (manually triage — many will be synonyms, not hallucinations):")
        for rec in report["per_record_findings"]:
            print(f"  {rec['source']}/{rec['source_id']}: {rec['unsupported_claims']}")

    OUT.write_text(json.dumps(report, indent=2))
    print(f"\nWrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
