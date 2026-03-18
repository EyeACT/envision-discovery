"""
ENVISION Discovery: Dryad Scraper

Searches Dryad for eye imaging datasets via their public API.
API docs: https://datadryad.org/api/v2/docs/
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
    ZipInspector,
)

logger = logging.getLogger(__name__)

API_BASE = "https://datadryad.org/api/v2"


class DryadScraper:
    """Scrape Dryad for eye imaging datasets."""

    def __init__(self, output_dir: Optional[Path] = None):
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})
        self.seen_ids: set[str] = set()
        self.output_dir = Path(output_dir) if output_dir else None

    def search(
        self,
        query: str,
        max_results: int = 100,
        inspect_zips: bool = False,
    ) -> list[DatasetMetadata]:
        """Search Dryad for datasets matching query."""
        results = []
        page = 1
        per_page = 25

        while len(results) < max_results:
            try:
                resp = self.session.get(
                    f"{API_BASE}/search",
                    params={"q": query, "page": page, "per_page": per_page},
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                logger.warning(f"Dryad search error for '{query}': {e}")
                break

            datasets = data.get("_embedded", {}).get("stash:datasets", [])
            if not datasets:
                break

            for ds in datasets:
                ds_id = ds.get("identifier")
                if not ds_id or ds_id in self.seen_ids:
                    continue
                self.seen_ids.add(ds_id)

                meta = self._dataset_to_metadata(ds, inspect_zips)
                if meta:
                    results.append(meta)

            total_pages = data.get("total_pages", 1)
            if page >= total_pages:
                break

            page += 1
            time.sleep(1.5)

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
            logger.info(f"[{i}/{len(search_terms)}] Dryad: '{term}'")
            results = self.search(term, max_results=max_per_query, inspect_zips=inspect_zips)
            all_results.extend(results)
            logger.info(f"  Found {len(results)} (total: {len(all_results)})")
            time.sleep(2.0)
        return all_results

    def _get_files(self, doi: str, version_id: str | None = None) -> list[dict]:
        """Fetch file list for a dataset version."""
        try:
            # Try to get the latest version's files
            encoded_doi = doi.replace("/", "%2F")
            resp = self.session.get(
                f"{API_BASE}/datasets/{encoded_doi}/versions",
                timeout=30,
            )
            resp.raise_for_status()
            versions = resp.json().get("_embedded", {}).get("stash:versions", [])
            if not versions:
                return []

            latest = versions[-1]
            version_num = latest.get("versionNumber", 1)

            files_resp = self.session.get(
                f"{API_BASE}/datasets/{encoded_doi}/versions/{version_num}/files",
                timeout=30,
            )
            files_resp.raise_for_status()
            return files_resp.json().get("_embedded", {}).get("stash:files", [])
        except Exception as e:
            logger.debug(f"Could not fetch Dryad files for {doi}: {e}")
            return []

    def _dataset_to_metadata(
        self, ds: dict, inspect_zips: bool = False
    ) -> DatasetMetadata | None:
        """Convert a Dryad dataset to DatasetMetadata."""
        doi = ds.get("identifier", "")

        # Fetch files
        files = self._get_files(doi)
        file_names = [f.get("path", "") for f in files]
        file_types: set[str] = set()
        total_size = 0
        img_count = 0
        medical_count = 0
        archive_count = 0
        genomics_count = 0
        zip_contents: list[str] = []

        for f in files:
            name_lower = f.get("path", "").lower()
            total_size += f.get("size", 0)

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
                download_url = f.get("download_url")
                if download_url:
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

        # Description
        abstract = ds.get("abstract", "")

        # Keywords
        keywords = []
        for kw in ds.get("keywords", []):
            if isinstance(kw, str):
                keywords.append(kw)

        # Creators
        creators = []
        for author in ds.get("authors", []):
            name = f"{author.get('firstName', '')} {author.get('lastName', '')}".strip()
            creators.append({
                "creatorName": name,
                "nameType": "Personal",
            })

        # License
        license_name = ds.get("license", "")

        # Dates
        pub_date = ds.get("publicationDate", "")
        pub_year = pub_date[:4] if pub_date and len(pub_date) >= 4 else None

        # Related works
        related = []
        for rel in ds.get("relatedWorks", []):
            related.append({
                "relatedIdentifierValue": rel.get("identifier", ""),
                "relatedIdentifierType": rel.get("identifierType", "DOI"),
                "relationType": rel.get("relationship", "References"),
            })

        return DatasetMetadata(
            source="dryad",
            source_id=doi,
            doi=doi if doi.startswith("doi:") or "/" in doi else None,
            url=f"https://datadryad.org/stash/dataset/{doi}",
            title=ds.get("title", ""),
            description=abstract[:2000],
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
            publication_year=pub_year,
            dates=[{"dateValue": pub_date, "dateType": "Available"}] if pub_date else [],
            related_identifiers=related,
            external_links=[],
        )
