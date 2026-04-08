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
    """Scrape OSF for eye imaging datasets.

    OSF rate limits:
      - Unauthenticated: 100 requests/hour (hard hourly window)
      - Authenticated (OSF_TOKEN): ~10,000 requests/day

    This scraper tracks request count and pauses at the hourly limit
    until the window resets, rather than hammering 403s for hours.
    """

    REQUEST_DELAY = 2.0   # seconds between every API call (proactive)
    HOURLY_LIMIT = 95     # stay under 100/hr with a safety margin
    HOURLY_LIMIT_AUTH = 400  # ~10K/day = ~400/hr with margin

    def __init__(self, output_dir: Optional[Path] = None):
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})

        token = os.environ.get("OSF_TOKEN")
        if token:
            self.session.headers.update({"Authorization": f"Bearer {token}"})
            self._rate_limit = self.HOURLY_LIMIT_AUTH
            logger.info(f"OSF: Authenticated (~{self._rate_limit} req/hr)")
        else:
            self._rate_limit = self.HOURLY_LIMIT
            logger.info(f"OSF: Unauthenticated ({self._rate_limit} req/hr). Set OSF_TOKEN for more.")

        self._request_count = 0
        self._window_start = time.time()

        self.metadata_dir = (Path(output_dir) if output_dir else Path.cwd() / "data") / "metadata" / "osf"
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        self.seen_ids = DatasetMetadata.existing_ids(self.metadata_dir)
        if self.seen_ids:
            logger.info(f"Resuming: {len(self.seen_ids)} existing OSF records")

    def _request(self, method, url_or_endpoint, **kwargs):
        """Make a rate-limited OSF API request, respecting the hourly window."""
        # Check if we've hit the hourly limit
        elapsed = time.time() - self._window_start
        if self._request_count >= self._rate_limit:
            wait = max(0, 3600 - elapsed) + 5  # wait until window resets + buffer
            if wait > 0:
                logger.info(
                    f"  OSF: {self._request_count} requests in {elapsed/60:.0f}min, "
                    f"pausing {wait/60:.1f}min until hourly window resets"
                )
                time.sleep(wait)
            self._request_count = 0
            self._window_start = time.time()

        # Reset window if an hour has passed
        if elapsed >= 3600:
            self._request_count = 0
            self._window_start = time.time()

        time.sleep(self.REQUEST_DELAY)
        self._request_count += 1
        return request_with_backoff(
            self.session, method, url_or_endpoint, max_retries=5, **kwargs
        )

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

        # Skip file fetching — OSF rate limits are too strict (100 req/hr)
        # and the classifier only needs title + description + tags.
        # File details would cost 1-3 API calls per record.
        file_names = []
        file_types: set[str] = set()
        total_size = 0
        img_count = 0
        medical_count = 0
        archive_count = 0
        genomics_count = 0
        zip_contents = []

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
