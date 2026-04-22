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
)
from ..utils import request_with_backoff, ArchiveInspector

logger = logging.getLogger(__name__)

API_BASE = "https://datadryad.org/api/v2"


class DryadScraper:
    """Scrape Dryad for eye imaging datasets."""

    REQUEST_DELAY = 1.5  # seconds between every API call (proactive)

    def __init__(self, output_dir: Optional[Path] = None):
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})
        self.metadata_dir = (Path(output_dir) if output_dir else Path.cwd() / "data") / "metadata" / "dryad"
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        self.seen_ids = DatasetMetadata.existing_ids(self.metadata_dir)
        if self.seen_ids:
            logger.info(f"Resuming: {len(self.seen_ids)} existing Dryad records")

    def _request(self, method, url_or_endpoint, **kwargs):
        """Make a rate-limited Dryad API request."""
        time.sleep(self.REQUEST_DELAY)
        return request_with_backoff(self.session, method, url_or_endpoint, **kwargs)

    def search(
        self,
        query: str,
        max_results: int = 100,
        inspect_zips: bool = True,
    ) -> list[DatasetMetadata]:
        """Search Dryad for datasets matching query."""
        results = []
        page = 1
        per_page = 25

        while len(results) < max_results:
            resp = self._request(
                "get", f"{API_BASE}/search",
                params={"q": query, "page": page, "per_page": per_page},
            )
            if resp is None:
                break
            data = resp.json()

            datasets = data.get("_embedded", {}).get("stash:datasets", [])
            if datasets is None or not datasets:
                break

            for ds in datasets:
                ds_id = str(ds.get("identifier", ""))
                safe_id = ds_id.replace("/", "_")
                if not ds_id or safe_id in self.seen_ids:
                    continue
                self.seen_ids.add(safe_id)

                meta = self._dataset_to_metadata(ds, inspect_zips)
                if meta:
                    meta.save(self.metadata_dir)
                    results.append(meta)

            total_pages = data.get("total_pages", 1)
            if page >= total_pages:
                break

            page += 1

        return results

    def scrape(
        self,
        search_terms: list[str] | None = None,
        max_per_query: int = 100,
        inspect_zips: bool = True,
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
        return all_results

    def _get_files(self, doi: str, version_id: str | None = None) -> list[dict]:
        """Fetch file list for the latest version of a dataset."""
        try:
            encoded_doi = doi.replace("/", "%2F")
            resp = self._request(
                "get",
                f"{API_BASE}/datasets/{encoded_doi}/versions",
                timeout=30,
            )
            if resp is None:
                return []
            versions = resp.json().get("_embedded", {}).get("stash:versions", [])
            if not versions:
                return []

            # Use the HATEOAS link from the latest version — the versionNumber
            # is a display number, not a path parameter
            latest = versions[-1]
            files_href = (latest.get("_links", {})
                          .get("stash:files", {})
                          .get("href"))
            if not files_href:
                return []

            files_resp = self._request(
                "get",
                f"https://datadryad.org{files_href}",
                timeout=30,
            )
            if files_resp is None:
                return []
            return files_resp.json().get("_embedded", {}).get("stash:files", [])
        except Exception as e:
            logger.debug(f"Could not fetch Dryad files for {doi}: {e}")
            return []

    def _dataset_to_metadata(
        self, ds: dict, inspect_zips: bool = True
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
        download_files: list[dict] = []

        for f in files:
            name_lower = f.get("path", "").lower()
            total_size += f.get("size", 0)

            f_url = f.get("download_url") or f.get("_links", {}).get("stash:download", {}).get("href")
            if f_url and not f_url.startswith("http"):
                f_url = f"https://datadryad.org{f_url}"
            if f_url:
                download_files.append({
                    "name": f.get("path", ""),
                    "size_bytes": f.get("size", 0),
                    "url": f_url,
                    "file_id": f.get("id") or f.get("fileId"),
                    "checksum": f.get("digest") or f.get("md5"),
                })

            # Always extract the file extension
            if "." in name_lower:
                raw_ext = "." + name_lower.rsplit(".", 1)[-1]
                file_types.add(raw_ext)

            # Categorize known extensions
            for ext in sorted(
                EYE_IMAGING_EXTS | ARCHIVE_EXTS | GENOMICS_EXTS,
                key=len,
                reverse=True,
            ):
                if name_lower.endswith(ext):
                    file_types.add(ext)  # add compound ext too (e.g. .tar.gz)
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

            # Archive inspection (ZIP and TAR)
            if inspect_zips and any(name_lower.endswith(ext) for ext in ARCHIVE_EXTS):
                download_url = f.get("download_url")
                if download_url:
                    try:
                        contents = ArchiveInspector.inspect_archive(
                            download_url, f.get("path", ""), self.session
                        )
                        if contents:
                            zip_contents.extend(contents[:50])
                            for zf in contents:
                                if "." in zf:
                                    file_types.add("." + zf.rsplit(".", 1)[-1].lower())
                            summary = ArchiveInspector.summarize_contents(contents)
                            img_count += summary.get("imaging_file_count", 0)
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
            description=abstract[:10_000],
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
            files=download_files,
        )
