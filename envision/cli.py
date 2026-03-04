#!/usr/bin/env python3
"""
ENVISION: CLI Entry Points

Command-line interfaces for the eye imaging classifier.
"""

import argparse
import json
import sys


def classify_cli():
    """Classify metadata as eye imaging datasets.

    Usage:
        envision-classify input.json
        envision-classify --text "Retinal OCT dataset for diabetic retinopathy"
        echo '{"title": "Fundus images"}' | envision-classify
    """
    parser = argparse.ArgumentParser(
        prog='envision-classify',
        description='Classify metadata as eye imaging datasets',
    )
    parser.add_argument('input', nargs='?', help='JSON file with metadata to classify')
    parser.add_argument('--text', '-t', help='Classify a text string directly')
    parser.add_argument('--model', '-m', help='Path to trained model directory')
    parser.add_argument('--device', '-d', help='Device (cuda/cpu)')

    args = parser.parse_args()

    from .classifier import EyeImagingClassifier

    classifier = EyeImagingClassifier(model_path=args.model, device=args.device)

    if args.text:
        result = classifier.classify(args.text)
        print(json.dumps(result, indent=2))
    elif args.input:
        with open(args.input) as f:
            data = json.load(f)
        if isinstance(data, list):
            results = classifier.classify_batch(data)
        else:
            results = classifier.classify(data)
        print(json.dumps(results, indent=2))
    elif not sys.stdin.isatty():
        data = json.load(sys.stdin)
        if isinstance(data, list):
            results = classifier.classify_batch(data)
        else:
            results = classifier.classify(data)
        print(json.dumps(results, indent=2))
    else:
        parser.print_help()
        sys.exit(1)


def pipeline_cli():
    """Run the ENVISION Zenodo classification pipeline."""
    parser = argparse.ArgumentParser(
        prog='envision-pipeline',
        description='Run ENVISION Zenodo classification pipeline',
    )
    parser.add_argument('--classify-only', action='store_true',
                       help='Load existing model instead of training')
    parser.add_argument('--metadata-dir', help='Directory with Zenodo metadata JSON files')
    parser.add_argument('--results-dir', help='Output directory for results')

    args = parser.parse_args()

    from .pipeline import run_zenodo_pipeline
    run_zenodo_pipeline(
        classify_only=args.classify_only,
        metadata_dir=args.metadata_dir,
        results_dir=args.results_dir,
    )


def train_cli():
    """Train a new ENVISION classifier model."""
    parser = argparse.ArgumentParser(
        prog='envision-train',
        description='Train ENVISION eye imaging classifier',
    )
    parser.add_argument('--output', '-o', help='Output directory for trained model')
    parser.add_argument('--device', '-d', help='Device (cuda/cpu)')

    args = parser.parse_args()

    from .classifier import EyeImagingClassifier
    classifier = EyeImagingClassifier.train(output_dir=args.output, device=args.device)
    print(f"\nModel ready. Label set: {classifier.LABELS}")
