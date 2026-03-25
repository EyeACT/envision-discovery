"""
ENVISION Discovery: DataCite Meta-Search

Searches across 2,500+ repositories via DataCite's API.
Returns DOIs and metadata only (no file lists — DataCite is a DOI registry).
API docs: https://support.datacite.org/docs/api
"""

import logging
import time
from pathlib import Path
from typing import Optional

import requests

from ..metadata import DatasetMetadata
from ..scraper import SEARCH_TERMS
from ..utils import request_with_backoff, ArchiveInspector

logger = logging.getLogger(__name__)

API_BASE = "https://api.datacite.org/dois"


class DataCiteScraper:
    """Meta-search DataCite for eye imaging datasets across 2,500+ repos."""

    def __init__(self, output_dir: Optional[Path] = None):
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})
        self.seen_dois: set[str] = set()
        self.output_dir = Path(output_dir) if output_dir else None

    def search(
        self,
        query: str,
        max_results: int = 100,
    ) -> list[DatasetMetadata]:
        """Search DataCite for datasets matching query."""
        results = []
        page_number = 1
        page_size = 25

        while len(results) < max_results:
            resp = request_with_backoff(
                self.session,
                "get",
                API_BASE,
                params={
                    "query": query,
                    "resource-type-id": "dataset",
                    "page[size]": page_size,
                    "page[number]": page_number,
                },
            )
            if resp is None:
                logger.warning(f"DataCite search failed for '{query}' after retries")
                break
            data = resp.json()

            items = data.get("data", [])
            if not items:
                break

            for item in items:
                doi = item.get("id", "")
                if not doi or doi in self.seen_dois:
                    continue
                self.seen_dois.add(doi)

                meta = self._item_to_metadata(item)
                if meta:
                    results.append(meta)

            # Check pagination
            total_pages = data.get("meta", {}).get("totalPages", 1)
            if page_number >= total_pages:
                break

            page_number += 1
            time.sleep(1.0)

        return results

    def scrape(
        self,
        search_terms: list[str] | None = None,
        max_per_query: int = 100,
    ) -> list[DatasetMetadata]:
        """Run full scrape using all search terms."""
        if search_terms is None:
            search_terms = SEARCH_TERMS

        all_results = []
        for i, term in enumerate(search_terms, 1):
            logger.info(f"[{i}/{len(search_terms)}] DataCite: '{term}'")
            results = self.search(term, max_results=max_per_query)
            all_results.extend(results)
            logger.info(f"  Found {len(results)} (total: {len(all_results)})")
            time.sleep(2.0)
        return all_results

    def _item_to_metadata(self, item: dict) -> DatasetMetadata | None:
        """Convert a DataCite DOI record to DatasetMetadata."""
        attrs = item.get("attributes", {})
        doi = item.get("id", "")

        # Title
        titles = attrs.get("titles", [])
        title = titles[0].get("title", "") if titles else ""

        # Description
        descriptions = attrs.get("descriptions", [])
        description = ""
        for d in descriptions:
            if d.get("descriptionType") == "Abstract":
                description = d.get("description", "")
                break
        if not description and descriptions:
            description = descriptions[0].get("description", "")

        # Keywords / subjects
        keywords = [s.get("subject", "") for s in attrs.get("subjects", []) if s.get("subject")]

        # Creators
        creators = []
        for c in attrs.get("creators", []):
            creators.append({
                "creatorName": c.get("name", ""),
                "nameType": c.get("nameType", "Personal"),
            })

        # Dates
        dates = []
        for d in attrs.get("dates", []):
            dates.append({
                "dateValue": d.get("date", ""),
                "dateType": d.get("dateType", "Other"),
            })

        pub_year = str(attrs.get("publicationYear", ""))

        # License / rights
        rights = attrs.get("rightsList", [])
        license_name = rights[0].get("rights", "") if rights else None

        # Related identifiers
        related = []
        for rel in attrs.get("relatedIdentifiers", []):
            related.append({
                "relatedIdentifierValue": rel.get("relatedIdentifier", ""),
                "relatedIdentifierType": rel.get("relatedIdentifierType", "DOI"),
                "relationType": rel.get("relationType", "References"),
            })

        # URL
        url = attrs.get("url", f"https://doi.org/{doi}")

        # Publisher / source repo
        publisher = attrs.get("publisher", "")

        # Sizes
        sizes = attrs.get("sizes", [])

        # Formats (file types from DataCite metadata, not actual file listing)
        formats = attrs.get("formats", [])
        file_types = set()
        for fmt in formats:
            if fmt.startswith("."):
                file_types.add(fmt)
            elif "/" in fmt:
                # MIME type like "image/DICOM"
                file_types.add(fmt)

        return DatasetMetadata(
            source="datacite",
            source_id=doi,
            doi=doi,
            url=url,
            title=title,
            description=description[:2000],
            keywords=keywords,
            file_names=[],  # DataCite doesn't have file listings
            file_types=file_types,
            file_count=0,
            total_size_bytes=0,
            img_count=0,
            medical_count=0,
            archive_count=0,
            genomics_count=0,
            zip_contents=[],
            access_type=attrs.get("schemaVersion"),  # not directly available
            license=license_name,
            creators=creators,
            publication_year=pub_year if pub_year else None,
            dates=dates,
            related_identifiers=related,
            external_links=[],
        )
