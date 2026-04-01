#!/bin/bash

# ENVISION Discovery Pipeline
# ===========================
# Run the full pipeline:     ./automation.sh
# Run only the scraper:      ./automation.sh scrape
# Run only the classifier:   ./automation.sh classify
# Run only the portal post:  ./automation.sh post
#
# Weekly cron job: 0 0 * * 0 /path/to/automation.sh

set -e

STEP="${1:-all}"

# ── Setup (always runs) ─────────────────────────────────────────────
echo "=== ENVISION Pipeline (step: $STEP) ==="

echo "Step 0a: Resetting local changes and pulling latest code..."
git reset --hard
git pull
chmod +x automation.sh

echo "Step 0b: Activating virtual environment and installing dependencies..."
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
# IMPORTANT: Reinstall local package so python3 -m envision uses latest code
pip install -e . --no-deps

# ── Scrape ───────────────────────────────────────────────────────────
if [ "$STEP" = "all" ] || [ "$STEP" = "scrape" ]; then
    echo ""
    echo "=== Step 1: Cleaning old data ==="
    rm -rf ./data/metadata/zenodo/*
    rm -rf ./data/metadata/figshare/*
    rm -rf results/*.json
    rm -rf results/addf/*

    echo ""
    echo "=== Step 2: Scraping all repositories ==="
    python3 -m envision --source all --scrape-only
fi

# ── Classify ─────────────────────────────────────────────────────────
if [ "$STEP" = "all" ] || [ "$STEP" = "classify" ]; then
    echo ""
    echo "=== Step 3: Classifying all repositories ==="
    python3 -m envision --source all --skip-scrape
fi

# ── Post to portal ───────────────────────────────────────────────────
if [ "$STEP" = "all" ] || [ "$STEP" = "post" ]; then
    echo ""
    echo "=== Step 4: Adding dataset records to portal ==="
    python3 add_dataset_records.py
fi

echo ""
echo "=== Pipeline completed (step: $STEP) ==="
