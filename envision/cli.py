#!/usr/bin/env python3
"""
ENVISION Discovery: CLI

Two-step pipeline: scrape → classify. Each step reads/writes disk.
No in-memory handoff. Every source is treated identically.

    python3 -m envision                          # scrape + classify all
    python3 -m envision --scrape-only            # scrape all, save to data/scraped/
    python3 -m envision --skip-scrape            # classify from data/scraped/
    python3 -m envision --source dryad           # single source
"""

import argparse
import json
import re
from dataclasses import asdict
from html import unescape
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

ALL_SOURCES = ['zenodo', 'figshare', 'dryad', 'osf', 'datacite', 'kaggle', 'nei']


# ── Disk I/O for scraped data ───────────────────────────────────────

def _save_scraped(records, source, data_dir):
    """Serialize DatasetMetadata list to data/scraped/{source}.json."""
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / f"{source}.json"
    serialized = []
    for r in records:
        d = asdict(r)
        d['file_types'] = sorted(d['file_types'])  # set → list for JSON
        serialized.append(d)
    with open(path, 'w') as f:
        json.dump(serialized, f)
    print(f"  Saved {len(records):,} records → {path}", flush=True)


def _load_scraped(source, data_dir):
    """Load DatasetMetadata list from data/scraped/{source}.json."""
    from .metadata import DatasetMetadata

    path = data_dir / f"{source}.json"
    if not path.exists():
        # Backward compat: check old naming convention
        old_path = data_dir / f"{source}_scraped.json"
        if old_path.exists():
            path = old_path
        else:
            return None

    with open(path) as f:
        raw = json.load(f)
    records = []
    for d in raw:
        d['file_types'] = set(d.get('file_types', []))
        records.append(DatasetMetadata(**d))
    print(f"  Loaded {len(records):,} records ← {path}", flush=True)
    return records


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
    scraped_dir = Path.cwd() / "data" / "scraped"

    for source in sources:
        print(f"\n{'#'*70}", flush=True)
        print(f"# {source.upper()}", flush=True)
        print(f"{'#'*70}", flush=True)

        try:
            records = None

            # ── Step 1: Scrape → save to disk ────────────────────────
            if not args.skip_scrape:
                records = _scrape_source(source, args)
                if records:
                    _save_scraped(records, source, scraped_dir)
                else:
                    print(f"  Scraper returned 0 records for {source}", flush=True)

            if args.scrape_only:
                continue

            # ── Step 2: Load from disk → classify ────────────────────
            if records is None:
                records = _load_scraped(source, scraped_dir)

            # Zenodo fallback: per-record JSON files from old scraper
            if records is None and source == 'zenodo':
                zenodo_dir = Path.cwd() / "data" / "metadata" / "zenodo"
                if zenodo_dir.exists() and any(zenodo_dir.glob("*.json")):
                    print(f"  No scraped cache, falling back to {zenodo_dir}", flush=True)
                    records = _zenodo_json_to_metadata(zenodo_dir)
                    if records:
                        _save_scraped(records, source, scraped_dir)

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
