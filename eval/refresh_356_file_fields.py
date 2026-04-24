"""In-place refresh of scraper-derived file fields on the 356-record
expert validation set.

Motivation
----------
Recent patches to the scrapers (commits 4f951a0 and 2fc22d9) changed how
file metadata is extracted:

  * ``file_types`` now includes ALL extensions found on each record, not
    only the hand-picked EYE_IMAGING / ARCHIVE / GENOMICS sets. Dryad,
    Figshare, and Kaggle records previously had empty ``file_types`` for
    common extensions (.csv, .xlsx, .R, .pdf, etc.).
  * Archive inspection (ZIP / TAR / TAR.GZ) now records all filenames
    found inside the archives and feeds their extensions back into
    ``file_types``, not just imaging files.

The 356-record validation set was built before those fixes, so its
``file_types`` are overwhelmingly empty (e.g. 51/51 empty for Kaggle,
113/123 for Figshare). This script re-hits each record's source API and
rebuilds the full set of scraper-derived file fields, preserving the
rest of the record (description, expert_score, classifier outputs, etc.)
exactly as it is.

Fields written
--------------
For every record where the source API returns file information, we
add/overwrite:
  file_types, file_names, file_count, img_count, medical_count,
  archive_count, genomics_count, size_mb, zip_contents,
  zip_file_types (Counter of extensions inside archives).

Records whose source does not expose file listings (nei, osf) are left
untouched. Records whose API lookup 404s are also left untouched.

Usage
-----
    python eval/refresh_356_file_fields.py              # all sources
    python eval/refresh_356_file_fields.py --sources figshare kaggle
    python eval/refresh_356_file_fields.py --dry-run    # no writes
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "eval" / "results" / "expert_validation_356_records.json"

sys.path.insert(0, str(ROOT))
from envision.scrapers.figshare import FigshareScraper  # type: ignore
from envision.scrapers.kaggle import KaggleScraper  # type: ignore
from envision.scrapers.dryad import DryadScraper  # type: ignore
from envision.scrapers.datacite import DataCiteScraper  # type: ignore

# Sources that return file listings via their API
FILE_ENABLED = {"figshare", "kaggle", "dryad", "datacite", "zenodo"}


def _meta_to_file_fields(meta, inspect_zips: bool) -> dict:
    """Extract just the file-related fields from a DatasetMetadata."""
    zip_types = Counter()
    for name in meta.zip_contents or []:
        if "." in name:
            zip_types["." + name.rsplit(".", 1)[-1].lower()] += 1

    return {
        "file_types": sorted(meta.file_types),
        "file_names": meta.file_names[:20],
        "file_count": meta.file_count,
        "img_count": meta.img_count,
        "medical_count": meta.medical_count,
        "archive_count": meta.archive_count,
        "genomics_count": meta.genomics_count,
        "size_mb": meta.size_mb,
        "zip_contents": meta.zip_contents[:50],
        "zip_file_types": dict(zip_types),
    }


class _SilentSaveDir:
    """Dummy path that swallows .save() writes from scrapers.

    The scrapers' ``_xxx_to_metadata`` helpers call ``meta.save(metadata_dir)``
    when invoked via ``search()``, but we call them directly and don't want
    to touch data/metadata/. We also skip the seen_ids deduplication by
    bypassing ``search()`` entirely.
    """


def refresh_figshare(records: list[dict], inspect_zips: bool, dry_run: bool):
    """Refresh Figshare records via ``FigshareScraper._article_to_metadata``."""
    scraper = FigshareScraper(output_dir=ROOT / "data")
    updated = missed = 0
    targets = [r for r in records if r.get("source") == "figshare"]
    for i, r in enumerate(targets, 1):
        sid = str(r.get("source_id"))
        try:
            # Minimal stub: _article_to_metadata fetches detail internally
            meta = scraper._article_to_metadata(
                {"id": sid}, inspect_zips=inspect_zips
            )
        except Exception as e:
            print(f"  [{i}/{len(targets)}] figshare/{sid}: ERR {e}", flush=True)
            missed += 1
            continue
        if meta is None or meta.file_count == 0 and not meta.file_types:
            print(f"  [{i}/{len(targets)}] figshare/{sid}: no files", flush=True)
            missed += 1
            continue
        fields = _meta_to_file_fields(meta, inspect_zips)
        if dry_run:
            print(f"  [{i}/{len(targets)}] figshare/{sid}: "
                  f"types={fields['file_types']} count={fields['file_count']} "
                  f"size={fields['size_mb']}MB", flush=True)
        else:
            r.update(fields)
            updated += 1
            if i % 10 == 0:
                print(f"  [{i}/{len(targets)}] figshare: updated={updated} "
                      f"missed={missed}", flush=True)
    print(f"  figshare done: updated={updated} missed={missed}", flush=True)
    return updated, missed


def _kaggle_list_files_via_zip(
    scraper: KaggleScraper, owner: str, slug: str
) -> tuple[list[str], int] | None:
    """Kaggle's ``/datasets/view/`` endpoint returns an empty ``files`` list
    in the current API (verified 2026-04-24). The whole-dataset download
    endpoint redirects to a signed Google Cloud Storage URL that supports
    Range requests, so we stream-connect to resolve the redirect, then let
    RemoteZip pull just the ZIP central directory for the file listing.

    Returns (filenames, total_size_bytes) or None on failure. Handles
    Zip64 and CDs > 128 KB, so works on both small and multi-GB archives.
    """
    from remotezip import RemoteZip

    url = (
        f"https://www.kaggle.com/api/v1/datasets/download/{owner}/{slug}"
    )
    try:
        time.sleep(scraper.REQUEST_DELAY)
        r = scraper.session.get(
            url, stream=True, allow_redirects=True, timeout=30,
        )
        if r.status_code != 200:
            r.close()
            return None
        final_url = r.url
        size = int(r.headers.get("Content-Length") or 0)
        r.close()
        if size == 0:
            return None

        with RemoteZip(final_url, session=scraper.session) as zf:
            names = [
                info.filename for info in zf.infolist() if not info.is_dir()
            ]
        return names, size
    except Exception:
        return None


def refresh_kaggle(records: list[dict], inspect_zips: bool, dry_run: bool):
    """Refresh Kaggle records.

    Kaggle's API ``/datasets/view/`` returns empty ``files`` lists (verified
    2026-04-24), so ``KaggleScraper._dataset_to_metadata`` cannot populate
    file fields. This helper bypasses that by Range-reading the whole-dataset
    download ZIP's central directory and computing the file fields directly.
    """
    from envision.scraper import (  # type: ignore
        EYE_IMAGING_EXTS, ARCHIVE_EXTS, GENOMICS_EXTS,
    )

    scraper = KaggleScraper(output_dir=ROOT / "data")
    updated = missed = 0
    targets = [r for r in records if r.get("source") == "kaggle"]
    for i, r in enumerate(targets, 1):
        ref = str(r.get("source_id"))
        parts = ref.split("/", 1)
        if len(parts) != 2:
            missed += 1
            continue
        owner, slug = parts

        result = _kaggle_list_files_via_zip(scraper, owner, slug)
        if result is None:
            missed += 1
            continue
        names, total_size = result

        file_types: set[str] = set()
        img_count = medical_count = archive_count = genomics_count = 0
        for name in names:
            name_lower = name.lower()
            if "." in name_lower:
                file_types.add("." + name_lower.rsplit(".", 1)[-1])
            for ext in sorted(
                EYE_IMAGING_EXTS | ARCHIVE_EXTS | GENOMICS_EXTS,
                key=len, reverse=True,
            ):
                if name_lower.endswith(ext):
                    file_types.add(ext)
                    if ext in EYE_IMAGING_EXTS:
                        if ext in {".jpg", ".jpeg", ".png", ".tif",
                                   ".tiff", ".bmp", ".gif"}:
                            img_count += 1
                        else:
                            medical_count += 1
                    elif ext in ARCHIVE_EXTS:
                        archive_count += 1
                    elif ext in GENOMICS_EXTS:
                        genomics_count += 1
                    break

        fields = {
            "file_types": sorted(file_types),
            "file_names": names[:20],
            "file_count": len(names),
            "img_count": img_count,
            "medical_count": medical_count,
            "archive_count": archive_count,
            "genomics_count": genomics_count,
            "size_mb": round(total_size / (1024 * 1024), 1),
            "zip_contents": names[:50],
            "zip_file_types": {},
        }
        if dry_run:
            print(f"  [{i}/{len(targets)}] kaggle/{ref}: "
                  f"types={fields['file_types']} count={fields['file_count']} "
                  f"size={fields['size_mb']}MB", flush=True)
        else:
            r.update(fields)
            updated += 1
            if i % 10 == 0:
                print(f"  [{i}/{len(targets)}] kaggle: updated={updated} "
                      f"missed={missed}", flush=True)
    print(f"  kaggle done: updated={updated} missed={missed}", flush=True)
    return updated, missed


def refresh_dryad(records: list[dict], inspect_zips: bool, dry_run: bool):
    """Refresh Dryad records. Fetch the dataset JSON, then hand to
    ``DryadScraper._dataset_to_metadata``."""
    scraper = DryadScraper(output_dir=ROOT / "data")
    updated = missed = 0
    targets = [r for r in records if r.get("source") == "dryad"]
    for i, r in enumerate(targets, 1):
        ident = str(r.get("source_id"))
        # 356 records store dryad DOIs like "doi:10.5061/dryad.xxx" —
        # Dryad API wants the same format URL-encoded.
        encoded = ident.replace("/", "%2F")
        try:
            resp = scraper._request(
                "get", f"https://datadryad.org/api/v2/datasets/{encoded}",
                timeout=30,
            )
            if resp is None or resp.status_code == 404:
                print(f"  [{i}/{len(targets)}] dryad/{ident}: 404", flush=True)
                missed += 1
                continue
            ds = resp.json()
            meta = scraper._dataset_to_metadata(ds, inspect_zips=inspect_zips)
        except Exception as e:
            print(f"  [{i}/{len(targets)}] dryad/{ident}: ERR {e}", flush=True)
            missed += 1
            continue
        if meta is None:
            missed += 1
            continue
        fields = _meta_to_file_fields(meta, inspect_zips)
        if dry_run:
            print(f"  [{i}/{len(targets)}] dryad/{ident}: "
                  f"types={fields['file_types']} count={fields['file_count']}",
                  flush=True)
        else:
            r.update(fields)
            updated += 1
    print(f"  dryad done: updated={updated} missed={missed}", flush=True)
    return updated, missed


def refresh_datacite(records: list[dict], dry_run: bool):
    """Refresh DataCite records. DataCite returns file-type-like info via
    the ``formats`` attribute on each DOI record; no actual file listing."""
    scraper = DataCiteScraper(output_dir=ROOT / "data")
    updated = missed = 0
    targets = [r for r in records if r.get("source") == "datacite"]
    for i, r in enumerate(targets, 1):
        doi = str(r.get("source_id") or r.get("doi"))
        try:
            resp = scraper._request(
                "get", f"https://api.datacite.org/dois/{doi}",
                timeout=30,
            )
            if resp is None or resp.status_code == 404:
                missed += 1
                continue
            data = resp.json().get("data", {})
            if not data:
                missed += 1
                continue
            meta = scraper._item_to_metadata(data)
        except Exception as e:
            print(f"  [{i}/{len(targets)}] datacite/{doi}: ERR {e}", flush=True)
            missed += 1
            continue
        if meta is None:
            missed += 1
            continue
        fields = _meta_to_file_fields(meta, inspect_zips=False)
        if dry_run:
            if fields["file_types"]:
                print(f"  [{i}/{len(targets)}] datacite/{doi}: "
                      f"types={fields['file_types']}", flush=True)
        else:
            r.update(fields)
            updated += 1
    print(f"  datacite done: updated={updated} missed={missed}", flush=True)
    return updated, missed


def refresh_zenodo(records: list[dict], inspect_zips: bool, dry_run: bool):
    """Refresh Zenodo records via the Zenodo API.

    Zenodo is not patched for filetype extraction (it already reads the
    full file list from the API), but the 4 records with empty file_types
    may simply be software/no-file repos. Re-hit the API to confirm.
    """
    import requests
    from envision.scraper import (  # type: ignore
        EYE_IMAGING_EXTS, ARCHIVE_EXTS, GENOMICS_EXTS,
    )
    from envision.utils import ArchiveInspector  # type: ignore

    session = requests.Session()
    session.headers["Accept"] = "application/json"
    updated = missed = 0
    targets = [r for r in records if r.get("source") == "zenodo"]
    for i, r in enumerate(targets, 1):
        zid = str(r.get("source_id"))
        try:
            resp = session.get(
                f"https://zenodo.org/api/records/{zid}", timeout=30,
            )
            if resp.status_code != 200:
                missed += 1
                continue
            raw = resp.json()
        except Exception as e:
            print(f"  [{i}/{len(targets)}] zenodo/{zid}: ERR {e}", flush=True)
            missed += 1
            continue

        files = raw.get("files", [])
        file_names = [f.get("key", "") for f in files]
        file_types: set[str] = set()
        total_size = 0
        img_count = medical_count = archive_count = genomics_count = 0
        zip_contents: list[str] = []

        for f in files:
            name_lower = f.get("key", "").lower()
            total_size += f.get("size", 0)
            if "." in name_lower:
                file_types.add("." + name_lower.rsplit(".", 1)[-1])
            for ext in sorted(
                EYE_IMAGING_EXTS | ARCHIVE_EXTS | GENOMICS_EXTS,
                key=len, reverse=True,
            ):
                if name_lower.endswith(ext):
                    file_types.add(ext)
                    if ext in EYE_IMAGING_EXTS:
                        if ext in {".jpg", ".jpeg", ".png", ".tif",
                                   ".tiff", ".bmp", ".gif"}:
                            img_count += 1
                        else:
                            medical_count += 1
                    elif ext in ARCHIVE_EXTS:
                        archive_count += 1
                    elif ext in GENOMICS_EXTS:
                        genomics_count += 1
                    break
            if inspect_zips and any(
                name_lower.endswith(ext)
                for ext in (".zip", ".tar", ".tar.gz", ".tgz")
            ):
                url = f.get("links", {}).get("self", "")
                if url:
                    try:
                        contents = ArchiveInspector.inspect_archive(
                            url, f.get("key", ""), session,
                        )
                        if contents:
                            zip_contents.extend(contents[:50])
                            for zf in contents:
                                if "." in zf:
                                    file_types.add(
                                        "." + zf.rsplit(".", 1)[-1].lower()
                                    )
                            summary = ArchiveInspector.summarize_contents(
                                contents
                            )
                            img_count += summary.get("imaging_file_count", 0)
                    except Exception:
                        pass

        zip_types = Counter()
        for name in zip_contents:
            if "." in name:
                zip_types["." + name.rsplit(".", 1)[-1].lower()] += 1

        fields = {
            "file_types": sorted(file_types),
            "file_names": file_names[:20],
            "file_count": len(files),
            "img_count": img_count,
            "medical_count": medical_count,
            "archive_count": archive_count,
            "genomics_count": genomics_count,
            "size_mb": round(total_size / (1024 * 1024), 1),
            "zip_contents": zip_contents[:50],
            "zip_file_types": dict(zip_types),
        }
        if dry_run:
            print(f"  [{i}/{len(targets)}] zenodo/{zid}: "
                  f"types={fields['file_types']} count={fields['file_count']}",
                  flush=True)
        else:
            r.update(fields)
            updated += 1
        time.sleep(0.3)
    print(f"  zenodo done: updated={updated} missed={missed}", flush=True)
    return updated, missed


SOURCE_FUNCS = {
    "figshare": refresh_figshare,
    "kaggle":   refresh_kaggle,
    "dryad":    refresh_dryad,
    "datacite": lambda r, z, d: refresh_datacite(r, d),  # no zip inspect
    "zenodo":   refresh_zenodo,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--sources", nargs="*",
        default=sorted(FILE_ENABLED),
        help="Sources to refresh (default: all file-enabled sources)",
    )
    ap.add_argument("--no-zip-inspect", action="store_true",
                    help="Skip ZIP content inspection (faster)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Show what would change, don't write")
    ap.add_argument("--target", default=str(TARGET),
                    help="Override target JSON path")
    args = ap.parse_args()

    target = Path(args.target)
    with target.open() as f:
        records = json.load(f)
    print(f"Loaded {len(records)} records from {target}", flush=True)
    inspect_zips = not args.no_zip_inspect

    grand_upd = grand_miss = 0
    for src in args.sources:
        fn = SOURCE_FUNCS.get(src)
        if fn is None:
            print(f"SKIP: no refresher for source={src}", flush=True)
            continue
        n_for_src = sum(1 for r in records if r.get("source") == src)
        if n_for_src == 0:
            print(f"SKIP: no {src} records in target", flush=True)
            continue
        print(f"\n== {src.upper()} ({n_for_src} records) ==", flush=True)
        u, m = fn(records, inspect_zips, args.dry_run)
        grand_upd += u
        grand_miss += m
        # Incremental save after each source
        if not args.dry_run:
            target.write_text(json.dumps(records, indent=2, ensure_ascii=False))
            print(f"  saved checkpoint to {target.name}", flush=True)

    print()
    print(f"GRAND TOTAL: updated={grand_upd} missed={grand_miss}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
