"""De-truncate descriptions in the production results JSONs.

envision/pipeline.py used to cap descriptions at 500 chars when writing
results/*_eye_imaging.json and results/*_all_results.json. Everything
downstream — the portal UI, the expert validation set, paper figures —
displayed or worked from those truncated strings. The cap is now lifted
to 10 KB in pipeline.py, but existing files still carry the old damage.

This script walks every record in the target files and re-fetches the
full description from the source API when the current description matches
one of the known truncation patterns (see ``is_truncated``). The rules
and API fetchers mirror eval/fix_validation_descriptions.py exactly — this
is the production-scale version of the 356-record fix.

Usage:
    python eval/detruncate_results.py              # default: all files
    python eval/detruncate_results.py --files results/zenodo_eye_imaging.json
    python eval/detruncate_results.py --dry-run    # report counts only
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fix_validation_descriptions import (  # type: ignore
    fetch_datacite,
    fetch_dryad,
    fetch_figshare,
    fetch_nei,
    fetch_zenodo,
    is_truncated,
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from envision.utils import clean_text  # type: ignore

ROOT = Path(__file__).resolve().parent.parent


def pick_fetcher(src: str):
    return {
        "datacite": lambda r: fetch_datacite(r.get("doi") or r.get("source_id")),
        "nei":      lambda r: fetch_nei(str(r.get("source_id"))),
        "zenodo":   lambda r: fetch_zenodo(str(r.get("source_id") or r.get("zenodo_id"))),
        "figshare": lambda r: fetch_figshare(str(r.get("source_id"))),
        "dryad":    lambda r: fetch_dryad(str(r.get("source_id") or r.get("doi"))),
    }.get(src)


# Per-source politeness delay (seconds between API calls)
SOURCE_DELAY = {
    "datacite": 1.0,
    "nei":      1.5,
    "zenodo":   0.5,
    "figshare": 0.5,
    "dryad":    0.5,
}

# In-memory cache keyed by (source, source_id). eye_imaging.json records are
# subsets of all_results.json; running both files in one invocation lets us
# cache the ~1,400 overlapping records between them.
_FETCH_CACHE: dict[tuple[str, str], str | None] = {}


def cached_fetch(src: str, r: dict, fetcher) -> str | None:
    key = (src, str(r.get("source_id") or r.get("zenodo_id") or r.get("doi") or ""))
    if key in _FETCH_CACHE:
        return _FETCH_CACHE[key]
    result = fetcher(r)
    # Only cache successful fetches. Caching None would poison subsequent
    # lookups of the same record (e.g. from _all_results.json -> _eye_imaging.json)
    # when the first attempt had a transient failure.
    if result:
        _FETCH_CACHE[key] = result
    return result


def process_file(path: Path, dry_run: bool = False) -> dict:
    records = json.loads(path.read_text())
    targets = [(i, r) for i, r in enumerate(records)
               if is_truncated(r.get("description"))]
    report = {"file": str(path), "n": len(records), "n_truncated": len(targets),
              "updated": 0, "missed": 0, "unchanged": 0}

    if dry_run or not targets:
        return report

    for k, (i, r) in enumerate(targets, 1):
        src = r.get("source")
        fetcher = pick_fetcher(src)
        if fetcher is None:
            report["missed"] += 1
            continue
        key = (src, str(r.get("source_id") or ""))
        was_cached = key in _FETCH_CACHE
        try:
            raw = cached_fetch(src, r, fetcher)
        except Exception as e:
            print(f"    [{k}/{len(targets)}] {src}/{r.get('source_id')} fetch err: {e}",
                  flush=True)
            report["missed"] += 1
            continue
        if not raw:
            report["missed"] += 1
            continue
        cleaned = clean_text(raw) or ""
        current = r.get("description") or ""
        if len(cleaned) > len(current) and not is_truncated(cleaned):
            r["description"] = cleaned
            report["updated"] += 1
        else:
            report["unchanged"] += 1
        # Politeness delay: skip when the response came from cache
        if not was_cached:
            time.sleep(SOURCE_DELAY.get(src, 1.0))

        # Incremental save every 50 records: survives crashes
        if k % 50 == 0:
            path.write_text(json.dumps(records, indent=2, ensure_ascii=False))
            print(f"    [{k}/{len(targets)}] {path.name}: incremental save "
                  f"(updated={report['updated']}, missed={report['missed']})",
                  flush=True)

    # Final write
    path.write_text(json.dumps(records, indent=2, ensure_ascii=False))
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--files", nargs="*", default=None,
                    help="Specific files to process. Default: all "
                         "results/*_eye_imaging.json and *_all_results.json")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.files:
        files = [Path(p) for p in args.files]
    else:
        files = sorted(
            list((ROOT / "results").glob("*_eye_imaging.json"))
            + list((ROOT / "results").glob("*_all_results.json"))
        )

    grand = {"updated": 0, "missed": 0, "unchanged": 0, "truncated": 0}
    for p in files:
        if not p.exists():
            print(f"SKIP (missing): {p}", flush=True)
            continue
        print(f"\n== {p} ==", flush=True)
        rep = process_file(p, dry_run=args.dry_run)
        print(f"   n={rep['n']} truncated={rep['n_truncated']} "
              f"updated={rep['updated']} missed={rep['missed']} "
              f"unchanged={rep['unchanged']}", flush=True)
        grand["updated"] += rep["updated"]
        grand["missed"] += rep["missed"]
        grand["unchanged"] += rep["unchanged"]
        grand["truncated"] += rep["n_truncated"]

    print()
    print(f"GRAND TOTAL  truncated={grand['truncated']}  "
          f"updated={grand['updated']}  missed={grand['missed']}  "
          f"unchanged={grand['unchanged']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
