#!/usr/bin/env python3
"""
ENVISION Discovery: CLI

Two-step pipeline: scrape → classify. Each step reads/writes disk.
No in-memory handoff. Every source is treated identically.

    python3 -m envision                          # scrape + classify all
    python3 -m envision --scrape-only            # scrape all, save to data/metadata/
    python3 -m envision --skip-scrape            # classify from data/metadata/
    python3 -m envision --source dryad           # single source
"""

import argparse
import json
import re
from html import unescape
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

ALL_SOURCES = ['zenodo', 'figshare', 'dryad', 'osf', 'datacite', 'kaggle', 'nei']


# ── Disk I/O for scraped data ───────────────────────────────────────

def _load_scraped(source, data_dir):
    """Load records from data/metadata/{source}/.

    Handles both DatasetMetadata JSON (all scrapers) and raw Zenodo API
    JSON (legacy format from the Zenodo scraper).
    """
    from .metadata import DatasetMetadata

    metadata_dir = data_dir / "metadata" / source
    if not metadata_dir.exists() or not any(metadata_dir.glob("*.json")):
        return None

    # Try loading as DatasetMetadata first (unified format)
    try:
        first = next(metadata_dir.glob("*.json"))
        with open(first) as f:
            sample = json.load(f)
        if "source" in sample and "source_id" in sample:
            records = DatasetMetadata.load_dir(metadata_dir)
            print(f"  Loaded {len(records):,} records ← {metadata_dir}/", flush=True)
            return records
    except Exception:
        pass

    # Fallback: raw Zenodo API JSON
    if source == "zenodo":
        records = _zenodo_json_to_metadata(metadata_dir)
        if records:
            print(f"  Loaded {len(records):,} records ← {metadata_dir}/ (raw Zenodo format)", flush=True)
            return records

    return None


# ── Zenodo adapter ──────────────────────────────────────────────────

def _zenodo_json_to_metadata(metadata_dir: Path):
    """Convert Zenodo per-record JSON files to DatasetMetadata objects.

    The Zenodo scraper saves one JSON per record to data/metadata/zenodo/.
    This converts them to the same DatasetMetadata format all other
    scrapers produce natively.
    """
    from .metadata import DatasetMetadata

    records = []
    for jf in sorted(metadata_dir.glob("*.json")):
        try:
            with open(jf) as f:
                raw = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue

        meta = raw.get("metadata", raw)
        zenodo_id = str(raw.get("id", jf.stem))

        title = meta.get("title", "")
        desc = meta.get("description", "")
        if desc:
            desc = unescape(re.sub("<[^<]+?>", " ", desc)).strip()

        keywords = meta.get("keywords", [])
        if isinstance(keywords, str):
            keywords = [k.strip() for k in keywords.split(",")]

        files = raw.get("files", [])
        file_names = [f.get("key", "") for f in files]
        file_types = set()
        total_size = 0

        for f_info in files:
            fname = f_info.get("key", "").lower()
            size = f_info.get("size", 0)
            total_size += size
            ext = "." + fname.rsplit(".", 1)[-1] if "." in fname else ""
            file_types.add(ext)

        analysis = raw.get("_file_analysis", {})

        creators = []
        for c in meta.get("creators", []):
            creators.append({
                "creatorName": c.get("name", ""),
                "nameType": "Personal",
            })

        records.append(DatasetMetadata(
            source="zenodo",
            source_id=zenodo_id,
            doi=meta.get("doi", raw.get("doi", "")),
            url=f"https://zenodo.org/records/{zenodo_id}",
            title=title,
            description=desc,
            keywords=keywords,
            file_names=file_names,
            file_types=file_types,
            file_count=len(files),
            total_size_bytes=total_size,
            img_count=analysis.get("imaging_file_count", 0),
            archive_count=analysis.get("archive_count", 0),
            genomics_count=analysis.get("genomics_count", 0),
            zip_contents=list(analysis.get("zip_contents", {}).keys()),
            access_type=meta.get("access_right"),
            license=meta.get("license", {}).get("id") if isinstance(meta.get("license"), dict) else None,
            creators=creators,
            publication_year=meta.get("publication_date", "")[:4] if meta.get("publication_date") else None,
            external_links=[l.get("url", "") for l in raw.get("_weblinks", [])],
        ))

    return records


# ── Per-source scraper dispatch ─────────────────────────────────────

def _scrape_source(source, args):
    """Run one scraper. Returns list[DatasetMetadata]."""
    mpq = args.max_per_query
    zips = not args.no_zip_inspect

    if source == 'zenodo':
        from .scraper import run_scrape
        output_dir = Path.cwd() / "data"
        run_scrape(output_dir=output_dir, datasets_only=True, inspect_zips=zips)
        return _zenodo_json_to_metadata(output_dir / "metadata" / "zenodo")

    scrapers = {
        'figshare': ('.scrapers.figshare', 'FigshareScraper', dict(max_per_query=mpq, inspect_zips=zips)),
        'dryad':    ('.scrapers.dryad',    'DryadScraper',    dict(max_per_query=mpq, inspect_zips=zips)),
        'osf':      ('.scrapers.osf',      'OSFScraper',      dict(max_per_query=min(mpq, 50))),
        'datacite': ('.scrapers.datacite', 'DataCiteScraper', dict(max_per_query=mpq)),
        'kaggle':   ('.scrapers.kaggle',   'KaggleScraper',   dict(max_per_query=mpq, inspect_zips=zips)),
        'nei':      ('.scrapers.nei',      'NEIScraper',      dict(max_per_query=mpq)),
    }

    if source not in scrapers:
        print(f"  Unknown source: {source}", flush=True)
        return None

    module_path, class_name, kwargs = scrapers[source]
    import importlib
    mod = importlib.import_module(module_path, package='envision')
    scraper_cls = getattr(mod, class_name)
    return scraper_cls().scrape(**kwargs)


# ── Main pipeline ───────────────────────────────────────────────────

def pipeline_cli():
    """Entry point for python3 -m envision."""
    parser = argparse.ArgumentParser(
        prog='envision',
        description='ENVISION: Eye imaging dataset discovery pipeline',
    )
    parser.add_argument('--source', default='all',
                       choices=ALL_SOURCES + ['all'],
                       help='Source to process (default: all)')
    parser.add_argument('--scrape-only', action='store_true',
                       help='Scrape and save to disk, skip classification')
    parser.add_argument('--skip-scrape', action='store_true',
                       help='Classify from previously scraped data on disk')
    parser.add_argument('--results-dir',
                       help='Output directory for classification results')
    parser.add_argument('--addf-output',
                       help='Directory for ADDF schema export')
    parser.add_argument('--max-per-query', type=int, default=100,
                       help='Max results per search query (default: 100)')
    parser.add_argument('--no-zip-inspect', action='store_true',
                       help='Skip ZIP content inspection (faster)')
    parser.add_argument('--dedup', action='store_true',
                       help='Run cross-source duplicate detection')
    parser.add_argument('--dedup-threshold', type=float, default=0.92,
                       help='Cosine similarity threshold for dedup (default: 0.92)')

    args = parser.parse_args()
    _run_pipeline(args)


def _run_pipeline(args):
    """Scrape → disk → classify. Every source follows the same path."""
    import sys
    import traceback

    sources = ALL_SOURCES if args.source == 'all' else [args.source]
    data_dir = Path.cwd() / "data"

    for source in sources:
        print(f"\n{'#'*70}", flush=True)
        print(f"# {source.upper()}", flush=True)
        print(f"{'#'*70}", flush=True)

        try:
            records = None

            # ── Step 1: Scrape (each scraper saves per-record JSON to data/metadata/{source}/)
            if not args.skip_scrape:
                records = _scrape_source(source, args)
                if not records:
                    print(f"  Scraper returned 0 records for {source}", flush=True)

            if args.scrape_only:
                continue

            # ── Step 2: Load from disk → classify
            if records is None:
                records = _load_scraped(source, data_dir)

            if records is None:
                print(f"  No data for {source}. Run without --skip-scrape first.", flush=True)
                continue

            from .pipeline import run_pipeline
            run_pipeline(
                metadata_records=records,
                source=source,
                results_dir=args.results_dir,
                addf_output_dir=args.addf_output,
            )

        except Exception as e:
            print(f"\n  ERROR [{source}]: {e}", flush=True)
            traceback.print_exc()
            sys.stdout.flush()
            sys.stderr.flush()
            continue

    # Cross-source dedup
    if args.dedup and args.source == 'all' and not args.scrape_only:
        results_dir = args.results_dir or 'results'
        print(f"\n{'#'*70}", flush=True)
        print("# CROSS-SOURCE DEDUPLICATION", flush=True)
        print(f"{'#'*70}", flush=True)
        try:
            from .dedup import run_dedup
            duplicates = run_dedup(results_dir, threshold=args.dedup_threshold)
            print(f"  Found {len(duplicates)} duplicate pairs", flush=True)
        except Exception as e:
            print(f"  Dedup failed: {e}", flush=True)
