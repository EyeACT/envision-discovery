#!/usr/bin/env python3
"""
ENVISION Discovery: CLI Entry Points

Command-line interfaces for the dataset discovery pipeline.
Supports multi-source scraping, classification, and ADDF export.
"""

import argparse
import json
import re
from html import unescape

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
from pathlib import Path


def pipeline_cli():
    """Run the ENVISION discovery pipeline."""
    parser = argparse.ArgumentParser(
        prog='envision-pipeline',
        description='Run ENVISION dataset discovery pipeline',
    )
    parser.add_argument('--classify-only', action='store_true',
                       help='Load existing model instead of training')
    parser.add_argument('--metadata-dir', help='Directory with metadata JSON files')
    parser.add_argument('--results-dir', help='Output directory for results')
    parser.add_argument('--source', default='zenodo',
                       choices=['zenodo', 'figshare', 'dryad', 'osf', 'datacite', 'kaggle', 'nei', 'all'],
                       help='Data source to scrape and classify (default: zenodo)')
    parser.add_argument('--addf-output', help='Directory for ADDF schema export')
    parser.add_argument('--max-per-query', type=int, default=100,
                       help='Max results per search query (default: 100)')
    parser.add_argument('--no-zip-inspect', action='store_true',
                       help='Skip ZIP content inspection (faster)')
    parser.add_argument('--dedup', action='store_true',
                       help='Run cross-source duplicate detection after classification')
    parser.add_argument('--dedup-threshold', type=float, default=0.92,
                       help='Cosine similarity threshold for dedup (default: 0.92)')

    args = parser.parse_args()
    _run_multi_source(args)


def _zenodo_json_to_metadata(metadata_dir: Path):
    """Convert scraped Zenodo JSON files to DatasetMetadata objects.

    Bridges the Zenodo scraper (saves raw JSON) with the unified pipeline
    (expects DatasetMetadata). All other scrapers return DatasetMetadata
    directly; this adapter makes Zenodo consistent.
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
        img_count = archive_count = genomics_count = 0
        total_size = 0

        for f_info in files:
            fname = f_info.get("key", "").lower()
            size = f_info.get("size", 0)
            total_size += size
            ext = "." + fname.rsplit(".", 1)[-1] if "." in fname else ""
            file_types.add(ext)

        analysis = raw.get("_file_analysis", {})
        img_count = analysis.get("imaging_file_count", 0)
        archive_count = analysis.get("archive_count", 0)
        genomics_count = analysis.get("genomics_count", 0)

        creators = []
        for c in meta.get("creators", []):
            creators.append({
                "creatorName": c.get("name", ""),
                "nameType": "Personal",
            })

        doi = meta.get("doi", raw.get("doi", ""))

        records.append(DatasetMetadata(
            source="zenodo",
            source_id=zenodo_id,
            doi=doi,
            url=f"https://zenodo.org/records/{zenodo_id}",
            title=title,
            description=desc,
            keywords=keywords,
            file_names=file_names,
            file_types=file_types,
            file_count=len(files),
            total_size_bytes=total_size,
            img_count=img_count,
            archive_count=archive_count,
            genomics_count=genomics_count,
            zip_contents=list(analysis.get("zip_contents", {}).keys()),
            access_type=meta.get("access_right"),
            license=meta.get("license", {}).get("id") if isinstance(meta.get("license"), dict) else None,
            creators=creators,
            publication_year=meta.get("publication_date", "")[:4] if meta.get("publication_date") else None,
            external_links=[l.get("url", "") for l in raw.get("_weblinks", [])],
        ))

    return records


def _run_multi_source(args):
    """Run multi-source pipeline with scraping + classification + optional ADDF."""
    from .pipeline import run_pipeline

    sources = (
        ['zenodo', 'figshare', 'dryad', 'osf', 'datacite', 'kaggle', 'nei']
        if args.source == 'all'
        else [args.source]
    )

    for source in sources:
        print(f"\n{'#'*70}", flush=True)
        print(f"# Source: {source.upper()}", flush=True)
        print(f"{'#'*70}", flush=True)

        metadata_records = None

        if source == 'zenodo':
            from .scraper import run_scrape
            output_dir = Path(args.metadata_dir) if args.metadata_dir else Path.cwd() / "data"
            run_scrape(
                output_dir=output_dir,
                datasets_only=True,
                inspect_zips=not args.no_zip_inspect,
            )
            zenodo_dir = output_dir / "metadata" / "zenodo"
            metadata_records = _zenodo_json_to_metadata(zenodo_dir)

        elif source == 'figshare':
            from .scrapers.figshare import FigshareScraper
            scraper = FigshareScraper()
            metadata_records = scraper.scrape(max_per_query=args.max_per_query,
                                              inspect_zips=not args.no_zip_inspect)

        elif source == 'dryad':
            from .scrapers.dryad import DryadScraper
            scraper = DryadScraper()
            metadata_records = scraper.scrape(max_per_query=args.max_per_query,
                                              inspect_zips=not args.no_zip_inspect)

        elif source == 'osf':
            from .scrapers.osf import OSFScraper
            scraper = OSFScraper()
            metadata_records = scraper.scrape(max_per_query=min(args.max_per_query, 50))

        elif source == 'datacite':
            from .scrapers.datacite import DataCiteScraper
            scraper = DataCiteScraper()
            metadata_records = scraper.scrape(max_per_query=args.max_per_query)

        elif source == 'kaggle':
            from .scrapers.kaggle import KaggleScraper
            scraper = KaggleScraper()
            metadata_records = scraper.scrape(max_per_query=args.max_per_query,
                                              inspect_zips=not args.no_zip_inspect)

        elif source == 'nei':
            from .scrapers.nei import NEIScraper
            scraper = NEIScraper()
            metadata_records = scraper.scrape(max_per_query=args.max_per_query)

        if metadata_records:
            run_pipeline(
                metadata_records=metadata_records,
                source=source,
                classify_only=args.classify_only,
                results_dir=args.results_dir,
                addf_output_dir=args.addf_output,
            )

    # Cross-source deduplication
    if args.dedup and args.source == 'all':
        results_dir = args.results_dir or 'results'
        print(f"\n{'#'*70}", flush=True)
        print("# CROSS-SOURCE DEDUPLICATION", flush=True)
        print(f"{'#'*70}", flush=True)
        from .dedup import run_dedup
        duplicates = run_dedup(results_dir, threshold=args.dedup_threshold)
        print(f"  Found {len(duplicates)} potential duplicate pairs", flush=True)
