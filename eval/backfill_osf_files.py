"""Backfill the file-related fields on every cached OSF record.

OSFScraper used to skip per-record file fetching to stay under the 100 req/hr
unauthenticated rate limit. Now that the scraper has a budgeted recursive
file lister and we have an OSF_TOKEN (~400 req/hr), we can populate
file_types, file_count, img/medical/archive/genomics counts, and total size
by hitting the OSF Files API for each record.

This script reads ``data/metadata/osf/*.json`` and, for any record where
``file_count == 0``, runs ``OSFScraper._list_files_recursive`` and rewrites
the file-related fields in place. Records that already have ``file_count > 0``
are skipped so the script is safely resumable across rate-limit pauses or
crashes.

Expect ~10-15 hours wall time for ~2,400 records given OSF's hourly cap.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from envision.scrapers.osf import OSFScraper  # type: ignore


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None,
                    help="Stop after processing this many records (testing)")
    ap.add_argument("--max-calls", type=int, default=6,
                    help="Per-record API call budget (default 6)")
    ap.add_argument("--max-depth", type=int, default=2,
                    help="Folder recursion depth limit (default 2)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    osf_dir = ROOT / "data" / "metadata" / "osf"
    paths = sorted(osf_dir.glob("*.json"))
    print(f"Found {len(paths)} cached OSF records", flush=True)

    scraper = OSFScraper(output_dir=ROOT / "data")

    # Stats
    n_total = len(paths)
    n_skipped_already_done = 0
    n_updated = 0
    n_no_files = 0
    n_errors = 0
    start = time.time()

    for i, p in enumerate(paths, 1):
        if args.limit and (n_updated + n_no_files + n_errors) >= args.limit:
            print(f"\nReached --limit; stopping.", flush=True)
            break

        try:
            with p.open() as f:
                rec = json.load(f)
        except Exception as e:
            print(f"  [{i}/{n_total}] {p.name}: read err {e}", flush=True)
            n_errors += 1
            continue

        # Resume: skip records that already have file_count > 0
        if (rec.get("file_count") or 0) > 0:
            n_skipped_already_done += 1
            continue

        # The original scrape didn't store item_type; default to "nodes".
        # Registrations are rarer in our search results.
        node_id = rec.get("source_id")
        if not node_id:
            n_errors += 1
            continue

        try:
            file_entries = scraper._list_files_recursive(
                node_id,
                item_type="nodes",
                max_depth=args.max_depth,
                max_calls=args.max_calls,
            )
        except Exception as e:
            print(f"  [{i}/{n_total}] osf/{node_id}: list err {e}", flush=True)
            n_errors += 1
            continue

        if not file_entries:
            n_no_files += 1
            # Mark with a sentinel so we don't keep re-trying empty nodes.
            rec["file_count"] = 0
            rec["file_names"] = []
            rec["file_types"] = []
            # leave other fields at their existing 0 values
            if not args.dry_run:
                p.write_text(json.dumps(rec, indent=2, ensure_ascii=False))
            continue

        counts = scraper._files_to_counts(file_entries)
        names = [n for n, _ in file_entries]
        total_size = sum(s for _, s in file_entries)

        rec["file_names"] = names[:50]
        rec["file_types"] = sorted(counts["file_types"])
        rec["file_count"] = len(file_entries)
        rec["total_size_bytes"] = total_size
        rec["img_count"] = counts["img_count"]
        rec["medical_count"] = counts["medical_count"]
        rec["archive_count"] = counts["archive_count"]
        rec["genomics_count"] = counts["genomics_count"]

        if not args.dry_run:
            p.write_text(json.dumps(rec, indent=2, ensure_ascii=False))
        n_updated += 1

        if n_updated % 25 == 0:
            elapsed = time.time() - start
            done = n_updated + n_no_files + n_errors
            rate = done / elapsed if elapsed > 0 else 0
            remaining = (n_total - n_skipped_already_done - done) / rate \
                if rate > 0 else float("inf")
            print(
                f"  [{i}/{n_total}] osf/{node_id}: "
                f"{rec['file_count']} files, types={rec['file_types'][:6]}; "
                f"updated={n_updated} no_files={n_no_files} "
                f"errors={n_errors} skipped={n_skipped_already_done} | "
                f"~{remaining/60:.0f}min remaining",
                flush=True,
            )

    print()
    print(f"DONE  total={n_total}  updated={n_updated}  no_files={n_no_files} "
          f"errors={n_errors}  already_had_counts={n_skipped_already_done}",
          flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
