"""
ENVISION Discovery: Kaggle Scraper

Searches Kaggle for eye imaging datasets via their public API.
API docs: https://github.com/Kaggle/kaggle-api
"""

import json
import logging
import time
from pathlib import Path
from typing import Optional

import requests

from ..metadata import DatasetMetadata
from ..scraper import (
    EYE_IMAGING_EXTS,
    ARCHIVE_EXTS,
    GENOMICS_EXTS,
    SEARCH_TERMS,
    ZipInspector,
)

logger = logging.getLogger(__name__)

API_BASE = "https://www.kaggle.com/api/v1"


def _load_credentials() -> dict | None:
    """Load Kaggle API credentials.

    Supports three methods (checked in order):
      1. KAGGLE_API_TOKEN env var (new-style bearer token, starts with KGAT_)
      2. KAGGLE_USERNAME + KAGGLE_KEY env vars (legacy basic auth)
      3. ~/.kaggle/kaggle.json file (legacy basic auth)

    Returns dict with either {"bearer": token} or {"basic": (user, key)},
    or None if no credentials found.
    """
    import os

    # New-style API token (Bearer auth)
    api_token = os.environ.get("KAGGLE_API_TOKEN")
    if api_token:
        return {"bearer": api_token}

    # Legacy username + key (Basic auth)
    username = os.environ.get("KAGGLE_USERNAME")
    key = os.environ.get("KAGGLE_KEY")
    if username and key:
        return {"basic": (username, key)}

    kaggle_json = Path.home() / ".kaggle" / "kaggle.json"
    if kaggle_json.exists():
        try:
            creds = json.loads(kaggle_json.read_text())
            username = creds.get("username")
            key = creds.get("key")
            if username and key:
                return {"basic": (username, key)}
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Failed to parse {kaggle_json}: {e}")

    logger.warning(
        "Kaggle credentials not found. Set KAGGLE_API_TOKEN env var "
        "(new-style token starting with KGAT_), or KAGGLE_USERNAME + "
        "KAGGLE_KEY, or create ~/.kaggle/kaggle.json."
    )
    return None


class KaggleScraper:
    """Scrape Kaggle for eye imaging datasets."""

    def __init__(self, output_dir: Optional[Path] = None):
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})
        self.seen_refs: set[str] = set()
        self.output_dir = Path(output_dir) if output_dir else None

        creds = _load_credentials()
        if creds and "bearer" in creds:
            self.session.headers.update({"Authorization": f"Bearer {creds['bearer']}"})
        elif creds and "basic" in creds:
            self.session.auth = creds["basic"]
        else:
            logger.warning("KaggleScraper initialised without API credentials")

    def search(
        self,
        query: str,
        max_results: int = 100,
        inspect_zips: bool = False,
    ) -> list[DatasetMetadata]:
        """Search Kaggle for datasets matching query."""
        results = []
        page = 1

        while len(results) < max_results:
            params = {
                "search": query,
                "page": page,
                "filetype": "all",
            }

            for attempt in range(3):
                try:
                    resp = self.session.get(
                        f"{API_BASE}/datasets/list",
                        params=params,
                        timeout=30,
                    )
                    resp.raise_for_status()
                    datasets = resp.json()
                    break
                except requests.exceptions.HTTPError as e:
                    if e.response is not None and e.response.status_code in (429, 403):
                        wait = 10 * (2 ** attempt)  # 10s, 20s, 40s
                        logger.warning(f"Rate limited ({e.response.status_code}), waiting {wait}s...")
                        time.sleep(wait)
                        continue
                    logger.warning(f"Kaggle search error for '{query}': {e}")
                    break
                except Exception as e:
                    logger.warning(f"Kaggle search error for '{query}': {e}")
                    break
            else:
                # All retries exhausted
                logger.warning(f"Kaggle gave up after 3 retries for '{query}'")
                break

            if not datasets:
                break

            for dataset in datasets:
                ref = dataset.get("ref")
                if not ref or ref in self.seen_refs:
                    continue
                self.seen_refs.add(ref)

                meta = self._dataset_to_metadata(dataset, inspect_zips)
                if meta:
                    results.append(meta)

            page += 1
            time.sleep(1.0)

            # Kaggle returns 20 results per page by default
            if len(datasets) < 20:
                break

        return results

    def scrape(
        self,
        search_terms: list[str] | None = None,
        max_per_query: int = 100,
        inspect_zips: bool = False,
    ) -> list[DatasetMetadata]:
        """Run full scrape using all search terms."""
        if search_terms is None:
            search_terms = SEARCH_TERMS

        all_results = []
        for i, term in enumerate(search_terms, 1):
            logger.info(f"[{i}/{len(search_terms)}] Kaggle: '{term}'")
            results = self.search(term, max_results=max_per_query, inspect_zips=inspect_zips)
            all_results.extend(results)
            logger.info(f"  Found {len(results)} (total: {len(all_results)})")
            time.sleep(5.0)
        return all_results

    def _dataset_to_metadata(
        self, dataset: dict, inspect_zips: bool = False
    ) -> DatasetMetadata | None:
        """Convert a Kaggle dataset to DatasetMetadata."""
        ref = dataset.get("ref", "")
        parts = ref.split("/", 1)
        if len(parts) != 2:
            logger.debug(f"Invalid Kaggle dataset ref: {ref}")
            return None
        owner_slug, dataset_slug = parts

        # Fetch file listing via the view endpoint
        files = []
        try:
            resp = self.session.get(
                f"{API_BASE}/datasets/view/{owner_slug}/{dataset_slug}",
                timeout=30,
            )
            resp.raise_for_status()
            detail = resp.json()
            files = detail.get("files", [])
        except Exception as e:
            logger.debug(f"Could not fetch Kaggle dataset files for {ref}: {e}")
            detail = dataset

        file_names = [f.get("name", "") for f in files]
        file_types: set[str] = set()
        total_size = dataset.get("totalBytes", 0) or 0
        img_count = 0
        medical_count = 0
        archive_count = 0
        genomics_count = 0
        zip_contents: list[str] = []

        for f in files:
            name_lower = f.get("name", "").lower()

            for ext in sorted(
                EYE_IMAGING_EXTS | ARCHIVE_EXTS | GENOMICS_EXTS,
                key=len,
                reverse=True,
            ):
                if name_lower.endswith(ext):
                    file_types.add(ext)
                    if ext in EYE_IMAGING_EXTS:
                        if ext in {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".gif"}:
                            img_count += 1
                        else:
                            medical_count += 1
                    elif ext in ARCHIVE_EXTS:
                        archive_count += 1
                    elif ext in GENOMICS_EXTS:
                        genomics_count += 1
                    break

            # ZIP inspection
            if inspect_zips and name_lower.endswith(".zip"):
                download_url = (
                    f"https://www.kaggle.com/api/v1/datasets/download/"
                    f"{owner_slug}/{dataset_slug}/{f.get('name', '')}"
                )
                try:
                    contents = ZipInspector.inspect_via_range(
                        download_url, self.session
                    )
                    if contents:
                        summary = ZipInspector.summarize_contents(contents)
                        zip_contents.extend(
                            summary.get("sample_imaging_files", [])
                        )
                except Exception:
                    pass

        # Description (subtitle serves as short description)
        description = dataset.get("subtitle", "")

        # Keywords / tags
        tags_raw = dataset.get("tags", [])
        keywords = []
        for tag in tags_raw:
            if isinstance(tag, dict):
                keywords.append(tag.get("name", tag.get("ref", "")))
            else:
                keywords.append(str(tag))
        keywords = [k for k in keywords if k]

        # Creators
        creators = []
        creator_name = dataset.get("creatorName", "")
        if creator_name:
            creators.append({
                "creatorName": creator_name,
                "nameType": "Personal",
            })

        # License
        license_name = dataset.get("licenseName")

        # URL
        url = f"https://www.kaggle.com/datasets/{ref}"

        return DatasetMetadata(
            source="kaggle",
            source_id=ref,
            doi=None,
            url=url,
            title=dataset.get("title", ""),
            description=description[:2000],
            keywords=keywords,
            file_names=file_names[:50],
            file_types=file_types,
            file_count=len(files),
            total_size_bytes=total_size,
            img_count=img_count,
            medical_count=medical_count,
            archive_count=archive_count,
            genomics_count=genomics_count,
            zip_contents=zip_contents,
            access_type="open",
            license=license_name,
            creators=creators,
            publication_year=None,
            dates=[],
            related_identifiers=[],
            external_links=[],
        )
