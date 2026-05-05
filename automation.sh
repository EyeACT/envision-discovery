#!/bin/bash

# ENVISION Discovery Pipeline
# ===========================
# Full pipeline:   ./automation.sh
# Scrape only:     ./automation.sh scrape
# Classify only:   ./automation.sh classify
# Post to portal:  ./automation.sh post
#
# Cron: 0 0 * * 0 /path/to/automation.sh

set -e

STEP="${1:-all}"
echo "=== ENVISION Pipeline (step: $STEP) ==="

# ── Setup ────────────────────────────────────────────────────────────
echo "Pulling latest code..."
git pull
chmod +x automation.sh

echo "Installing dependencies..."
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt --upgrade
pip install -e . --no-deps

# ── Scrape ───────────────────────────────────────────────────────────
if [ "$STEP" = "all" ] || [ "$STEP" = "scrape" ]; then
    # echo ""
    # echo "=== Cleaning old data ==="
    # rm -rf ./data/metadata/zenodo
    # rm -rf ./data/metadata/figshare
    # rm -rf ./data/metadata/datacite
    # rm -rf ./data/metadata/kaggle
    # rm -rf ./data/metadata/dryad
    # rm -rf ./data/metadata/nei
    # rm -rf ./data/metadata/osf
    # rm -rf ./results/addf

    echo ""
    echo "=== Scraping all repositories ==="
    python3 -m envision --scrape-only
fi

# ── Classify ─────────────────────────────────────────────────────────
if [ "$STEP" = "all" ] || [ "$STEP" = "classify" ]; then
    echo ""
    echo "=== Classifying all repositories ==="
    python3 -m envision --skip-scrape --results-dir ./results
fi

# ── Post to portal ───────────────────────────────────────────────────
if [ "$STEP" = "all" ] || [ "$STEP" = "post" ]; then
    echo ""
    echo "=== Posting to portal ==="
    python3 add_dataset_records.py
fi

echo ""
echo "=== Done (step: $STEP) ==="
