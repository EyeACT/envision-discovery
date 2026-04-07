"""
ENVISION Discovery: OSF Scraper

Searches Open Science Framework for eye imaging datasets using the
/v2/search/ endpoint (full-text search across titles, descriptions, tags).

API docs: https://developer.osf.io/
Rate limits: Unauthenticated 100 req/hr. Authenticated (token) 10,000 req/day.

Set OSF_TOKEN env var for higher rate limits:
    export OSF_TOKEN=<your-personal-access-token>
Create tokens at: https://osf.io/settings/tokens
"""

import logging
import os
import re
import time
from html import unescape
from pathlib import Path
from typing import Optional

import requests

from ..metadata import DatasetMetadata
from ..scraper import (
    EYE_IMAGING_EXTS,
    ARCHIVE_EXTS,
    GENOMICS_EXTS,
    SEARCH_TERMS,
)
from ..utils import request_with_backoff, ArchiveInspector

logger = logging.getLogger(__name__)

API_BASE = "https://api.osf.io/v2"


class OSFScraper:
    """Scrape OSF for eye imaging datasets."""

    REQUEST_DELAY = 2.0  # seconds between every API call (proactive)

    def __init__(self, output_dir: Optional[Path] = None):
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})

        # Use token if available for higher rate limits
        token = os.environ.get("OSF_TOKEN")
        if token:
            self.session.headers.update({"Authorization": f"Bearer {token}"})
            logger.info("OSF: Using authenticated session (10,000 req/day)")
        else:
            logger.info("OSF: Unauthenticated (100 req/hr). Set OSF_TOKEN for higher limits.")

        self.metadata_dir = (Path(output_dir) if output_dir else Path.cwd() / "data") / "metadata" / "osf"
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        self.seen_ids = DatasetMetadata.existing_ids(self.metadata_dir)
        if self.seen_ids:
            logger.info(f"Resuming: {len(self.seen_ids)} existing OSF records")

    def _request(self, method, url_or_endpoint, **kwargs):
        """Make a rate-limited OSF API request."""
        time.sleep(self.REQUEST_DELAY)
        return request_with_backoff(self.session, method, url_or_endpoint, **kwargs)

    def search(
        self,
        query: str,
        max_results: int = 50,
    ) -> list[DatasetMetadata]:
        """Search OSF using the full-text search endpoint."""
        results = []
        url = f"{API_BASE}/search/"
        params = {
            "q": query,
            "page[size]": 25,
        }

        while url and len(results) < max_results:
            resp = self._request("get", url, params=params)
            if resp is None:
                break

            data = resp.json()
            items = data.get("data", [])
            if not items:
                break

            for item in items:
                if item is None:
                    continue
                item_id = item.get("id", "")
                item_type = item.get("type", "")

                if not item_id or item_id in self.seen_ids:
                    continue
                self.seen_ids.add(item_id)

                # Only process nodes and registrations (not users, files, etc.)
                if item_type not in ("nodes", "registrations"):
                    continue

                meta = self._item_to_metadata(item)
                if meta:
                    meta.save(self.metadata_dir)
                    results.append(meta)

            # Pagination — use next link
            url = data.get("links", {}).get("next")
            params = {}  # next URL has params embedded

        return results

    def scrape(
        self,
        search_terms: list[str] | None = None,
        max_per_query: int = 50,
    ) -> list[DatasetMetadata]:
        """Run full scrape using all search terms."""
        if search_terms is None:
            search_terms = SEARCH_TERMS

        all_results = []
        for i, term in enumerate(search_terms, 1):
            logger.info(f"[{i}/{len(search_terms)}] OSF: '{term}'")
            results = self.search(term, max_results=max_per_query)
            all_results.extend(results)
            logger.info(f"  Found {len(results)} (total: {len(all_results)})")
        return all_results

    def _get_files(self, item_id: str, item_type: str) -> list[dict]:
        """Fetch file list for an OSF node or registration."""
        endpoint = "registrations" if item_type == "registrations" else "nodes"
        resp = self._request(
            "get",
            f"{API_BASE}/{endpoint}/{item_id}/files/osfstorage/",
            params={"page[size]": 100},
        )
        if resp is None:
            return []
        try:
            return resp.json().get("data", [])
        except Exception:
            return []

    def _item_to_metadata(self, item: dict) -> DatasetMetadata | None:
        """Convert an OSF search result to DatasetMetadata."""
        attrs = item.get("attributes", {})
        item_id = item.get("id", "")
        item_type = item.get("type", "nodes")

        title = attrs.get("title", "")
        if not title:
            return None

        description = attrs.get("description", "")
        if description:
            description = unescape(re.sub("<[^<]+?>", " ", description)).strip()

        keywords = attrs.get("tags", [])
        if not isinstance(keywords, list):
            keywords = []

        # Fetch files
        files_data = self._get_files(item_id, item_type)
        file_names = []
        file_types: set[str] = set()
        total_size = 0
        img_count = 0
        medical_count = 0
        archive_count = 0
        genomics_count = 0
        zip_contents = []

        for f in files_data:
            f_attrs = f.get("attributes", {})
            name = f_attrs.get("name", "")
            size = f_attrs.get("size") or 0
            file_names.append(name)
            total_size += size

            name_lower = name.lower()
            for ext in sorted(
                EYE_IMAGING_EXTS | ARCHIVE_EXTS | GENOMICS_EXTS,
                key=len, reverse=True,
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
                        # Try to inspect archive contents
                        download_url = f.get("links", {}).get("download")
                        if download_url:
                            contents = ArchiveInspector.inspect_archive(
                                download_url, name, self.session
                            )
                            if contents:
                                summary = ArchiveInspector.summarize_contents(contents)
                                if summary.get("imaging_file_count", 0) > 0:
                                    img_count += summary["imaging_file_count"]
                                zip_contents.extend(contents[:20])
                    elif ext in GENOMICS_EXTS:
                        genomics_count += 1
                    break

        # Dates
        date_created = attrs.get("date_created", "")
        date_modified = attrs.get("date_modified", "")
        pub_year = date_created[:4] if date_created and len(date_created) >= 4 else None

        dates = []
        if date_created:
            dates.append({"dateValue": date_created[:10], "dateType": "Created"})
        if date_modified:
            dates.append({"dateValue": date_modified[:10], "dateType": "Updated"})

        return DatasetMetadata(
            source="osf",
            source_id=item_id,
            doi=None,
            url=f"https://osf.io/{item_id}/",
            title=title,
            description=description[:2000],
            keywords=keywords,
            file_names=file_names[:50],
            file_types=file_types,
            file_count=len(files_data),
            total_size_bytes=total_size,
            img_count=img_count,
            medical_count=medical_count,
            archive_count=archive_count,
            genomics_count=genomics_count,
            zip_contents=zip_contents,
            access_type="open" if attrs.get("public", True) else "restricted",
            license=None,
            creators=[],
            publication_year=pub_year,
            dates=dates,
            related_identifiers=[],
            external_links=[],
        )
