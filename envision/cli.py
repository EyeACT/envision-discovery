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
                       choices=['zenodo', 'figshare', 'dryad', 'osf', 'datacite', 'all'],
                       help='Data source to scrape and classify (default: zenodo)')
    parser.add_argument('--addf-output', help='Directory for ADDF schema export')
    parser.add_argument('--max-per-query', type=int, default=100,
                       help='Max results per search query (default: 100)')
    parser.add_argument('--no-zip-inspect', action='store_true',
                       help='Skip ZIP content inspection (faster)')

    args = parser.parse_args()

    if args.source == 'zenodo' and not args.addf_output:
        # Backward-compatible Zenodo-only path
        from .pipeline import run_zenodo_pipeline
        run_zenodo_pipeline(
            classify_only=args.classify_only,
            metadata_dir=args.metadata_dir,
            results_dir=args.results_dir,
        )
    else:
        _run_multi_source(args)


def _run_multi_source(args):
    """Run multi-source pipeline with scraping + classification + optional ADDF."""
    from .pipeline import run_pipeline
    from .metadata import DatasetMetadata

    sources = (
        ['zenodo', 'figshare', 'dryad', 'osf', 'datacite']
        if args.source == 'all'
        else [args.source]
    )

    for source in sources:
        print(f"\n{'#'*70}")
        print(f"# Source: {source.upper()}")
        print(f"{'#'*70}")

        metadata_records = None

        if source == 'zenodo':
            # Use legacy JSON-based path if metadata-dir provided
            if args.metadata_dir:
                run_pipeline(
                    source='zenodo',
                    classify_only=args.classify_only,
                    metadata_dir=args.metadata_dir,
                    results_dir=args.results_dir,
                    addf_output_dir=args.addf_output,
                )
                continue
            else:
                # Scrape fresh
                from .scraper import ZenodoScraper, run_scrape
                from pathlib import Path

                data_dir = Path(args.results_dir).parent / 'data' if args.results_dir else Path.cwd() / 'data'
                records = run_scrape(
                    output_dir=data_dir,
                    inspect_zips=not args.no_zip_inspect,
                    max_per_query=args.max_per_query,
                )
                scraper = ZenodoScraper(data_dir, resume=False)
                metadata_records = scraper.to_metadata_batch(records)

        elif source == 'figshare':
            from .scrapers.figshare import FigshareScraper
            scraper = FigshareScraper()
            metadata_records = scraper.scrape(max_per_query=args.max_per_query,
                                              inspect_zips=not args.no_zip_inspect)

        elif source == 'dryad':
            from .scrapers.dryad import DryadScraper
            scraper = DryadScraper()
            metadata_records = scraper.scrape(max_per_query=args.max_per_query)

        elif source == 'osf':
            from .scrapers.osf import OSFScraper
            scraper = OSFScraper()
            metadata_records = scraper.scrape(max_per_query=min(args.max_per_query, 50))

        elif source == 'datacite':
            from .scrapers.datacite import DataCiteScraper
            scraper = DataCiteScraper()
            metadata_records = scraper.scrape(max_per_query=args.max_per_query)

        if metadata_records:
            run_pipeline(
                metadata_records=metadata_records,
                source=source,
                classify_only=args.classify_only,
                results_dir=args.results_dir,
                addf_output_dir=args.addf_output,
            )
