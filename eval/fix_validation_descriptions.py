"""One-off: replace 500-char truncated descriptions in the expert validation
set with the full-text descriptions.

Sources:
  - zenodo / figshare / dryad / osf: local `data/metadata/<source>/*.json`
  - datacite: DataCite API (https://api.datacite.org/dois/{doi})
  - nei: NIH RePORTER API (POST /v2/projects/search with project_num filter)
  - kaggle: Kaggle descriptions are short (no truncation) - skip

The scrapers cap descriptions at 2000 chars for datacite/nei; local scraped
metadata for zenodo/figshare/dryad/osf contains the full text as returned by
each source API. This script preserves whatever length the upstream source
gave us - the 500-char cap was a downstream results-JSON display limit that
should never have been applied to the expert review set.
"""

import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from envision.utils import clean_text

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "eval" / "results" / "expert_validation_356_records.json"
META_ROOT = ROOT / "data" / "metadata"

DATACITE_BASE = "https://api.datacite.org/dois"
NEI_BASE = "https://api.reporter.nih.gov/v2/projects/search"


def local_meta_path(source: str, source_id: str) -> Path | None:
    root = META_ROOT / source
    if not root.exists():
        return None
    safe = str(source_id).replace("/", "_")
    for name in (f"{safe}.json", f"{source_id}.json"):
        p = root / name
        if p.exists():
            return p
    return None


def extract_desc_from_local(source: str, raw: dict) -> str | None:
    if source == "zenodo":
        md = raw.get("metadata") or {}
        return md.get("description") or raw.get("description")
    if source == "figshare":
        return raw.get("description")
    if source == "dryad":
        return raw.get("description")
    if source == "osf":
        return raw.get("description") or (raw.get("attributes") or {}).get("description")
    return raw.get("description")


def fetch_datacite(doi: str) -> str | None:
    try:
        r = requests.get(f"{DATACITE_BASE}/{doi}", timeout=15,
                         headers={"Accept": "application/json"})
        if r.status_code != 200:
            return None
        attrs = r.json().get("data", {}).get("attributes", {})
        descs = attrs.get("descriptions", []) or []
        for d in descs:
            if d.get("descriptionType") == "Abstract":
                return d.get("description")
        if descs:
            return descs[0].get("description")
    except Exception as e:
        print(f"    datacite err {doi}: {e}", flush=True)
    return None


def fetch_nei(project_num: str) -> str | None:
    try:
        payload = {
            "criteria": {"project_nums": [project_num]},
            "offset": 0,
            "limit": 1,
        }
        r = requests.post(NEI_BASE, json=payload, timeout=20,
                          headers={"Accept": "application/json"})
        if r.status_code != 200:
            return None
        results = r.json().get("results", []) or []
        if not results:
            return None
        return results[0].get("abstract_text")
    except Exception as e:
        print(f"    nei err {project_num}: {e}", flush=True)
    return None


def fetch_zenodo(zenodo_id: str) -> str | None:
    try:
        r = requests.get(
            f"https://zenodo.org/api/records/{zenodo_id}", timeout=15,
            headers={"Accept": "application/json"},
        )
        if r.status_code != 200:
            return None
        md = r.json().get("metadata", {}) or {}
        return md.get("description")
    except Exception as e:
        print(f"    zenodo err {zenodo_id}: {e}", flush=True)
    return None


def fetch_figshare(article_id: str) -> str | None:
    try:
        r = requests.get(
            f"https://api.figshare.com/v2/articles/{article_id}", timeout=15,
        )
        if r.status_code != 200:
            return None
        return r.json().get("description")
    except Exception as e:
        print(f"    figshare err {article_id}: {e}", flush=True)
    return None


def fetch_dryad(doi_or_source_id: str) -> str | None:
    import urllib.parse

    doi = doi_or_source_id if doi_or_source_id.startswith("doi:") else f"doi:{doi_or_source_id}"
    try:
        encoded = urllib.parse.quote(doi, safe="")
        r = requests.get(
            f"https://datadryad.org/api/v2/datasets/{encoded}", timeout=15,
            headers={"Accept": "application/json"},
        )
        if r.status_code != 200:
            return None
        j = r.json()
        # Dryad's primary field is `abstract`; some records use `description`
        return j.get("abstract") or j.get("description")
    except Exception as e:
        print(f"    dryad err {doi_or_source_id}: {e}", flush=True)
    return None


def is_truncated(desc: str | None) -> bool:
    """Matches the truncation patterns the pipeline is known to produce:
      - hard cap at 500 (envision/pipeline.py, envision/dedup.py)
      - word-boundary cap near 500 (eval/verify_datacite_positives.py's
        ``[:500].rsplit(" ", 1)[0]`` leaves texts at 485-499 chars ending
        mid-sentence)
      - hard cap at 2000 (envision/scrapers/datacite.py,
        envision/scrapers/nei.py's ``description=... [:2000]``)

    Only actual sentence-end punctuation (``.!?``) counts as a clean
    terminator — closing quotes / parens can appear mid-sentence
    (e.g. "study of 98 patients (102 eyes)..."), so we do not treat
    ``)'"`` as terminators.
    """
    if not desc:
        return False
    n = len(desc)
    stripped = desc.rstrip()
    ends_cleanly = bool(stripped) and stripped[-1] in ".!?"
    if ends_cleanly:
        return False
    # Cap patterns: 500 exactly, 485-502 (word-boundary), 2000 exactly
    if 485 <= n <= 502:  # covers hard 500 + word-boundary variant
        return True
    if 1985 <= n <= 2002:  # covers hard 2000 + word-boundary variant
        return True
    if 985 <= n <= 1001:   # covers hard 1000 (sometimes used by scrapers)
        return True
    return False


def main():
    with TARGET.open() as f:
        records = json.load(f)

    total = len(records)
    n_trunc = sum(1 for r in records if is_truncated(r.get("description")))
    print(f"Loaded {total} records ({n_trunc} truncated)")

    updated = 0
    missed = 0
    unchanged = 0

    for idx, r in enumerate(records):
        # Never clobber a record that was intentionally summarized — its
        # `description` field is a Llama summary, not raw source text.
        if "description_summary_meta" in r:
            continue
        if not is_truncated(r.get("description")):
            continue
        src = r.get("source")
        sid = r.get("source_id")
        doi = r.get("doi")

        full = None

        # 1) try local metadata first
        p = local_meta_path(src, sid)
        if p:
            try:
                with p.open() as fh:
                    raw = json.load(fh)
                full = extract_desc_from_local(src, raw)
            except Exception as e:
                print(f"    local read err {p}: {e}", flush=True)

        # 2) fall back to API if local was missing or itself looks truncated
        if not full or is_truncated(full) or len(full) < 500:
            if src == "datacite" and doi:
                print(f"  [{idx+1}/{total}] datacite fetch {doi}", flush=True)
                full = fetch_datacite(doi)
                time.sleep(1.0)
            elif src == "nei" and sid:
                print(f"  [{idx+1}/{total}] nei fetch {sid}", flush=True)
                full = fetch_nei(str(sid))
            elif src == "zenodo" and sid:
                print(f"  [{idx+1}/{total}] zenodo fetch {sid}", flush=True)
                full = fetch_zenodo(str(sid))
                time.sleep(0.5)
            elif src == "figshare" and sid:
                print(f"  [{idx+1}/{total}] figshare fetch {sid}", flush=True)
                full = fetch_figshare(str(sid))
                time.sleep(0.5)
            elif src == "dryad" and sid:
                print(f"  [{idx+1}/{total}] dryad fetch {sid}", flush=True)
                full = fetch_dryad(str(sid))
                time.sleep(0.5)
                time.sleep(1.5)

        if not full:
            missed += 1
            continue

        cleaned = clean_text(full) or ""
        # only replace if the new text is strictly longer than current
        current = r.get("description") or ""
        if len(cleaned) > len(current):
            r["description"] = cleaned
            updated += 1
        else:
            unchanged += 1

    print(f"Updated: {updated}  Unchanged: {unchanged}  Missed: {missed}")

    with TARGET.open("w") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)
    print(f"Wrote {TARGET}")


if __name__ == "__main__":
    main()
