#!/usr/bin/env python3
"""
Combined workflow for ENVISION:

1. Scrape Zenodo metadata using the enhanced scraper.
2. Classify records with the eye-imaging classifier (using an existing model if available).
3. Generate `data/datasetRecordsNew.json` in the format expected by the portal backend.

You can then point your Prisma/Node script at `data/datasetRecordsNew.json`
to load the records into your database.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json

from envision.scraper_v2 import run_scrape
from generate_dataset_records import generate_dataset_records


logger = logging.getLogger(__name__)


def run_zenodo_scraper(output_dir: Path) -> None:
    """
    Run the Zenodo scraper to collect and enrich metadata.

    This uses the same defaults as the CLI:
    - datasets_only=True (resource_type=dataset)
    - inspect_zips=True (HTTP Range inspection of ZIP contents)
    """
    logger.info("Starting Zenodo scrape into %s", output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    run_scrape(
        output_dir=output_dir,
        datasets_only=True,
        inspect_zips=True,
        max_per_query=500,
    )


def run_classifier_classify_only() -> None:
    """
    Run the classifier in 'classify-only' mode.

    This:
    - Reuses an existing trained model in `models/setfit_v6` if present.
    - Otherwise trains once, saves the model, and then classifies records.
    """
    logger.info("Running classifier in classify-only mode")
    cmd = [sys.executable, "-m", "envision.classifier", "--classify-only"]
    subprocess.run(cmd, check=True)


def run_dataset_record_generation() -> Path:
    """
    Generate `data/datasetRecordsNew.json` from:
    - Existing curated `data/datasetRecords.json`
    - Classified Zenodo eye-imaging results in `results/zenodo_eye_imaging.json`
    """
    logger.info("Generating datasetRecordsNew.json from classified results")
    generate_dataset_records()
    output_path = Path("data") / "datasetRecordsNew.json"
    logger.info("Dataset records written to %s", output_path.resolve())
    return output_path


def load_dataset_records(path: Path) -> list[dict]:
    logger.info("Loading dataset records from %s", path.resolve())
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def insert_into_database(records_path: Path) -> None:
    """
    Insert generated dataset records directly into the database.

    - Uses DATABASE_URL from the environment (same as Prisma).
    - Skips any record that already exists (by id, canonicalId, doi, or externalUrl).
    """
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL is not set in the environment; skipping DB insert.")
        return

    records = load_dataset_records(records_path)
    total = len(records)
    logger.info("Inserting %d dataset record(s) into the database (PostgreSQL)", total)

    # Using psycopg3; install with: pip install "psycopg[binary]"
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            for idx, rec in enumerate(records, start=1):
                created_ts = int(rec["created"])
                created_dt = datetime.fromtimestamp(created_ts)

                doi = rec.get("doi") or None
                external_url = rec.get("externalUrl") or None

                # Duplicate check by stable identifiers
                cur.execute(
                    """
                    SELECT id
                    FROM "PublishedDataset"
                    WHERE id = %s
                       OR doi = %s
                       OR ("externalUrl" IS NOT NULL AND "externalUrl" = %s)
                    """,
                    (rec["id"], doi, external_url),
                )
                existing = cur.fetchone()

                if existing:
                    done_pct = (idx / total) * 100 if total else 0
                    sys.stdout.write(
                        f"\r  {idx}/{total} ({done_pct:3.0f}%) - skipped existing id={existing['id']}"
                    )
                    continue

                # Insert into PublishedDataset
                cur.execute(
                    """
                    INSERT INTO "PublishedDataset" (
                        id,
                        "datasetId",
                        "canonicalId",
                        doi,
                        title,
                        description,
                        "versionTitle",
                        "studyTitle",
                        public,
                        status,
                        "containerId",
                        "publishedMetadata",
                        files,
                        data,
                        external,
                        "externalUrl",
                        created,
                        updated
                    )
                    VALUES (
                        %(id)s,
                        %(datasetId)s,
                        %(canonicalId)s,
                        %(doi)s,
                        %(title)s,
                        %(description)s,
                        %(versionTitle)s,
                        %(studyTitle)s,
                        %(public)s,
                        %(status)s,
                        %(containerId)s,
                        %(publishedMetadata)s,
                        %(files)s,
                        %(data)s,
                        %(external)s,
                        %(externalUrl)s,
                        %(created)s,
                        %(updated)s
                    )
                    """,
                    {
                        "id": rec["id"],
                        "datasetId": rec["datasetId"],
                        "canonicalId": rec["canonicalId"],
                        "doi": doi or "",
                        "title": rec["title"],
                        "description": rec.get("description", ""),
                        "versionTitle": rec.get("versionTitle", ""),
                        "studyTitle": rec.get("studyTitle", ""),
                        # New external records start as public-ready
                        "public": True,
                        "status": "ready",
                        "containerId": None,
                        "publishedMetadata": Json(rec.get("publishedMetadata", {})),
                        "files": Json(rec.get("files", [])),
                        "data": Json(rec.get("data", {})),
                        "external": rec.get("external", True),
                        "externalUrl": external_url,
                        "created": created_dt,
                        "updated": created_dt,
                    },
                )

                reg = rec.get("PublishedDatasetRegistrationDetails", {})
                cur.execute(
                    """
                    INSERT INTO "PublishedDatasetRegistrationDetails" (
                        id,
                        "publishedDatasetId",
                        "datasetSource",
                        "extractionMethod",
                        "extractionVersion",
                        created,
                        updated
                    )
                    VALUES (
                        gen_random_uuid(),
                        %s,
                        %s,
                        %s,
                        %s,
                        NOW(),
                        NOW()
                    )
                    """,
                    (
                        rec["id"],
                        reg.get("datasetSource", "Zenodo"),
                        reg.get("extractionMethod", "Automatic Registration"),
                        reg.get("extractionVersion", "0.1.0"),
                    ),
                )

                if idx % 25 == 0:
                    conn.commit()

                done_pct = (idx / total) * 100 if total else 0
                sys.stdout.write(f"\r  {idx}/{total} ({done_pct:3.0f}%)")

        conn.commit()

    sys.stdout.write("\n")
    logger.info("Database insert complete.")


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    data_dir = base_dir / "data"

    logger.info("=== ENVISION Combined Workflow ===")
    logger.info("Base directory: %s", base_dir)

    # 1) Scrape Zenodo and enrich metadata
    run_zenodo_scraper(output_dir=data_dir)

    # 2) Classify datasets using the SetFit classifier
    run_classifier_classify_only()

    # 3) Generate datasetRecordsNew.json for ingestion into the portal database
    output_path = run_dataset_record_generation()

    # 4) Insert directly into the database (skipping existing records)
    insert_into_database(output_path)

    logger.info("Combined workflow + DB insert complete.")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    main()

