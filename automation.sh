#!/bin/bash

# Weekly cron job - run with: 0 0 * * 0 /path/to/automation.sh
# (Runs every Sunday at midnight)

set -e

echo "Starting automated envision discovery pipeline..."

# Reset git and pull latest changes
echo "Step 0a: Resetting local changes and pulling latest code..."
git reset --hard
git pull

chmod +x automation.sh

# Delete the output files and folders
echo "Step 0b: Cleaning up old data..."
rm -rf ./data/metadata/zenodo/*
rm -rf ./data/metadata/figshare/*
rm -rf results/*.json
rm -rf results/addf/*

# Activate virtual environment and reinstall dependencies
echo "Step 0c: Activating virtual environment and installing dependencies..."
python3 -m venv .venv 
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Scrape and classify all repositories
# Uses the unified CLI which runs all 6 scrapers + classification
echo "Step 1: Scraping and classifying all repositories..."
python3 -m envision --source all

# Generate dataset records and post to portal
echo "Step 3: Adding dataset records to portal..."
python3 add_dataset_records.py

echo "Pipeline completed successfully!"
