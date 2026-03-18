#!/usr/bin/env python3
"""
ENVISION Discovery: CLI Entry Points

Command-line interfaces for the dataset discovery pipeline.
Supports multi-source scraping, classification, and ADDF export.
"""

import argparse


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
            # Zenodo uses legacy JSON-based path (pre-scraped metadata)
            run_pipeline(
                source='zenodo',
                classify_only=args.classify_only,
                metadata_dir=args.metadata_dir,
                results_dir=args.results_dir,
                addf_output_dir=args.addf_output,
            )
            continue

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
        from pathlib import Path
        results_dir = args.results_dir or 'results'
        print(f"\n{'#'*70}", flush=True)
        print("# CROSS-SOURCE DEDUPLICATION", flush=True)
        print(f"{'#'*70}", flush=True)
        from .dedup import run_dedup
        duplicates = run_dedup(results_dir, threshold=args.dedup_threshold)
        print(f"  Found {len(duplicates)} potential duplicate pairs", flush=True)
