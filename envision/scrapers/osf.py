"""
ENVISION Discovery: OSF Scraper

Searches Open Science Framework for eye imaging datasets.
API docs: https://developer.osf.io/
Note: Unauthenticated rate limit is 100 requests/hour.
"""

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
)
from ..utils import request_with_backoff, ArchiveInspector

logger = logging.getLogger(__name__)

API_BASE = "https://api.osf.io/v2"


class OSFScraper:
    """Scrape OSF for eye imaging datasets."""

    def __init__(self, output_dir: Optional[Path] = None):
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})
        self.seen_ids: set[str] = set()
        self.output_dir = Path(output_dir) if output_dir else None

    def search(
        self,
        query: str,
        max_results: int = 50,
    ) -> list[DatasetMetadata]:
        """Search OSF for nodes matching query."""
        results = []
        url = f"{API_BASE}/nodes/"
        params = {
            "filter[title][contains]": query,
            "filter[public]": "true",
            "page[size]": 10,
        }

        while url and len(results) < max_results:
            resp = request_with_backoff(
                self.session, "get", url, params=params,
            )
            if resp is None:
                break
            data = resp.json()
            time.sleep(2.0)  # polite inter-request delay

            nodes = data.get("data", [])
            if not nodes:
                break

            for node in nodes:
                node_id = node.get("id")
                if not node_id or node_id in self.seen_ids:
                    continue
                self.seen_ids.add(node_id)

                meta = self._node_to_metadata(node)
                if meta:
                    results.append(meta)

            # Pagination
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
            time.sleep(3.0)
        return all_results

    def _get_files(self, node_id: str) -> list[dict]:
        """Fetch file list for an OSF node's osfstorage."""
        resp = request_with_backoff(
            self.session, "get",
            f"{API_BASE}/nodes/{node_id}/files/osfstorage/",
            params={"page[size]": 100},
        )
        if resp is None:
            return []
        time.sleep(2.0)  # polite inter-request delay
        try:
            return resp.json().get("data", [])
        except Exception as e:
            logger.debug(f"Could not parse OSF files for {node_id}: {e}")
            return []

    def _node_to_metadata(self, node: dict) -> DatasetMetadata | None:
        """Convert an OSF node to DatasetMetadata."""
        attrs = node.get("attributes", {})
        node_id = node.get("id", "")

        # Fetch files
        files_data = self._get_files(node_id)
        file_names = []
        file_types: set[str] = set()
        total_size = 0
        img_count = 0
        medical_count = 0
        archive_count = 0
        genomics_count = 0

        for f in files_data:
            f_attrs = f.get("attributes", {})
            name = f_attrs.get("name", "")
            size = f_attrs.get("size") or 0
            file_names.append(name)
            total_size += size

            name_lower = name.lower()
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

        # Description
        description = attrs.get("description", "")

        # Tags
        keywords = attrs.get("tags", [])

        # Creators / contributors
        creators = []
        contribs_url = node.get("relationships", {}).get("contributors", {}).get("links", {}).get("related", {}).get("href")
        # Skip fetching contributors to conserve rate limit

        # DOI / identifiers
        doi = None
        identifiers = node.get("relationships", {}).get("identifiers", {})
        # DOI would need additional API call; skip for rate limit reasons

        # Dates
        date_created = attrs.get("date_created", "")
        date_modified = attrs.get("date_modified", "")
        pub_year = date_created[:4] if date_created and len(date_created) >= 4 else None

        dates = []
        if date_created:
            dates.append({"dateValue": date_created[:10], "dateType": "Created"})
        if date_modified:
            dates.append({"dateValue": date_modified[:10], "dateType": "Updated"})

        # License
        license_name = None
        lic = node.get("relationships", {}).get("license", {})
        # Would need additional API call; skip

        return DatasetMetadata(
            source="osf",
            source_id=node_id,
            doi=doi,
            url=f"https://osf.io/{node_id}/",
            title=attrs.get("title", ""),
            description=description[:2000],
            keywords=keywords if isinstance(keywords, list) else [],
            file_names=file_names[:50],
            file_types=file_types,
            file_count=len(files_data),
            total_size_bytes=total_size,
            img_count=img_count,
            medical_count=medical_count,
            archive_count=archive_count,
            genomics_count=genomics_count,
            zip_contents=[],
            access_type="open" if attrs.get("public", True) else "restricted",
            license=license_name,
            creators=creators,
            publication_year=pub_year,
            dates=dates,
            related_identifiers=[],
            external_links=[],
        )
