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
rm -rf results/*

# Activate virtual environment and reinstall dependencies
echo "Step 0c: Activating virtual environment and installing dependencies..."
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Scrape data from repositories
echo "Step 1: Scraping data..."
python3 -m envision.scraper --output ./data

# Classify datasets
echo "Step 2: Classifying datasets..."
python3 -m envision --classify-only

# Add dataset records
echo "Step 3: Adding dataset records..."
python3 add_dataset_records.py

echo "Pipeline completed successfully!"
