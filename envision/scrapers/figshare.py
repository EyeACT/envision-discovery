"""
ENVISION Discovery: Figshare Scraper

Searches Figshare for eye imaging datasets via their public API.
API docs: https://docs.figshare.com/
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
    extract_weblinks_from_description,
)

logger = logging.getLogger(__name__)

API_BASE = "https://api.figshare.com/v2"


class FigshareScraper:
    """Scrape Figshare for eye imaging datasets."""

    def __init__(self, output_dir: Optional[Path] = None):
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})
        self.seen_ids: set[int] = set()
        self.output_dir = Path(output_dir) if output_dir else None

    def search(
        self,
        query: str,
        max_results: int = 100,
        inspect_zips: bool = False,
    ) -> list[DatasetMetadata]:
        """Search Figshare for datasets matching query."""
        results = []
        page = 1
        page_size = 25

        while len(results) < max_results:
            payload = {
                "search_for": query,
                "item_type": 3,  # datasets only
                "page": page,
                "page_size": page_size,
            }

            for attempt in range(3):
                try:
                    resp = self.session.post(
                        f"{API_BASE}/articles/search",
                        json=payload,
                        timeout=30,
                    )
                    resp.raise_for_status()
                    articles = resp.json()
                    break
                except requests.exceptions.HTTPError as e:
                    if e.response is not None and e.response.status_code in (429, 403):
                        wait = 10 * (2 ** attempt)  # 10s, 20s, 40s
                        logger.warning(f"Rate limited ({e.response.status_code}), waiting {wait}s...")
                        time.sleep(wait)
                        continue
                    logger.warning(f"Figshare search error for '{query}': {e}")
                    break
                except Exception as e:
                    logger.warning(f"Figshare search error for '{query}': {e}")
                    break
            else:
                # All retries exhausted
                logger.warning(f"Figshare gave up after 3 retries for '{query}'")
                break

            if not articles:
                break

            for article in articles:
                article_id = article.get("id")
                if not article_id or article_id in self.seen_ids:
                    continue
                self.seen_ids.add(article_id)

                meta = self._article_to_metadata(article, inspect_zips)
                if meta:
                    results.append(meta)

            page += 1
            time.sleep(1.0)

            if len(articles) < page_size:
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
            logger.info(f"[{i}/{len(search_terms)}] Figshare: '{term}'")
            results = self.search(term, max_results=max_per_query, inspect_zips=inspect_zips)
            all_results.extend(results)
            logger.info(f"  Found {len(results)} (total: {len(all_results)})")
            time.sleep(5.0)
        return all_results

    def _article_to_metadata(
        self, article: dict, inspect_zips: bool = False
    ) -> DatasetMetadata | None:
        """Convert a Figshare article to DatasetMetadata."""
        # Fetch full article details for file list
        article_id = article.get("id")
        try:
            resp = self.session.get(f"{API_BASE}/articles/{article_id}", timeout=30)
            resp.raise_for_status()
            detail = resp.json()
        except Exception as e:
            logger.debug(f"Could not fetch Figshare article {article_id}: {e}")
            detail = article

        files = detail.get("files", [])
        file_names = [f.get("name", "") for f in files]
        file_types: set[str] = set()
        total_size = 0
        img_count = 0
        medical_count = 0
        archive_count = 0
        genomics_count = 0
        zip_contents: list[str] = []

        for f in files:
            name_lower = f.get("name", "").lower()
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
        description = detail.get("description", "")
        if description:
            from bs4 import BeautifulSoup

            try:
                description = BeautifulSoup(description, "html.parser").get_text()
            except Exception:
                pass

        # Keywords / tags
        tags = detail.get("tags", [])
        categories = [c.get("title", "") for c in detail.get("categories", [])]
        keywords = tags + categories

        # Creators
        creators = []
        for author in detail.get("authors", []):
            creators.append({
                "creatorName": author.get("full_name", ""),
                "nameType": "Personal",
            })

        # DOI
        doi = detail.get("doi")

        # Publication year
        pub_date = detail.get("published_date", "")
        pub_year = pub_date[:4] if pub_date and len(pub_date) >= 4 else None

        # License
        lic = detail.get("license", {})
        license_name = lic.get("name") if isinstance(lic, dict) else str(lic) if lic else None

        return DatasetMetadata(
            source="figshare",
            source_id=str(article_id),
            doi=doi,
            url=detail.get("url_public_html", f"https://figshare.com/articles/dataset/{article_id}"),
            title=detail.get("title", ""),
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
            access_type="open" if not detail.get("is_embargoed") else "embargoed",
            license=license_name,
            creators=creators,
            publication_year=pub_year,
            dates=[{"dateValue": pub_date, "dateType": "Available"}] if pub_date else [],
            related_identifiers=[],
            external_links=[],
        )
