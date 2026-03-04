#!/usr/bin/env python3
"""
ENVISION Discovery: CLI Entry Points

Command-line interfaces for the dataset discovery pipeline.
Classification commands are provided by envision-classifier (envision-classifier classify/train).
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

    args = parser.parse_args()

    from .pipeline import run_zenodo_pipeline
    run_zenodo_pipeline(
        classify_only=args.classify_only,
        metadata_dir=args.metadata_dir,
        results_dir=args.results_dir,
    )
