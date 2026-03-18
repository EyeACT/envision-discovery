"""
ENVISION Discovery: NEI (National Eye Institute) Scraper

Searches for NEI-funded research projects via the NIH RePORTER API that may
have associated eye imaging datasets.

API docs: https://api.reporter.nih.gov/

NOTE: NEI does not maintain its own dataset catalog. This scraper uses two
complementary approaches:

  1. NIH RePORTER API (implemented) -- Finds NEI-funded research projects whose
     titles or terms match our search queries. These are *projects*, not datasets
     directly. The downstream classifier will determine whether a given project
     is likely to have produced or shared a relevant eye imaging dataset.

  2. NIH/NLM dbGaP search (future work) -- dbGaP (Database of Genotypes and
     Phenotypes) hosts controlled-access datasets from NIH-funded studies.
     A future enhancement could query dbGaP for NEI-associated studies that
     include phenotypic imaging data. This is not yet implemented.

Rate limit: NIH RePORTER allows ~1 request per second.
"""

import logging
import time
from pathlib import Path
from typing import Optional

import requests

from ..metadata import DatasetMetadata
from ..scraper import SEARCH_TERMS

logger = logging.getLogger(__name__)

API_BASE = "https://api.reporter.nih.gov/v2/projects/search"


class NEIScraper:
    """Scrape NIH RePORTER for NEI-funded projects that may share eye imaging data.

    This scraper finds NEI-funded *projects* that may have associated datasets,
    not datasets directly. The classifier will determine relevance.
    """

    def __init__(self, output_dir: Optional[Path] = None):
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
        })
        self.seen_project_nums: set[str] = set()
        self.output_dir = Path(output_dir) if output_dir else None

    def search(
        self,
        query: str,
        max_results: int = 100,
    ) -> list[DatasetMetadata]:
        """Search NIH RePORTER for NEI-funded projects matching query.

        Args:
            query: Search text to match against project titles and terms.
            max_results: Maximum number of results to return for this query.

        Returns:
            List of DatasetMetadata records for matching NEI projects.
        """
        results = []
        offset = 0
        limit = 25

        while len(results) < max_results:
            payload = {
                "criteria": {
                    "agencies": ["NEI"],
                    "advanced_text_search": {
                        "operator": "and",
                        "search_field": "projecttitle,terms",
                        "search_text": query,
                    },
                },
                "offset": offset,
                "limit": limit,
            }

            try:
                resp = self.session.post(
                    API_BASE,
                    json=payload,
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                logger.warning(f"NIH RePORTER search error for '{query}': {e}")
                break

            projects = data.get("results", [])
            if not projects:
                break

            for project in projects:
                project_num = project.get("project_num")
                if not project_num or project_num in self.seen_project_nums:
                    continue
                self.seen_project_nums.add(project_num)

                meta = self._project_to_metadata(project)
                if meta:
                    results.append(meta)

            total = data.get("meta", {}).get("total", 0)
            offset += limit

            if offset >= total:
                break

            time.sleep(1.5)

        return results

    def scrape(
        self,
        search_terms: list[str] | None = None,
        max_per_query: int = 100,
    ) -> list[DatasetMetadata]:
        """Run full scrape using all search terms.

        Args:
            search_terms: List of queries to search. Defaults to SEARCH_TERMS.
            max_per_query: Maximum results per search term.

        Returns:
            Combined list of DatasetMetadata records across all search terms.
        """
        if search_terms is None:
            search_terms = SEARCH_TERMS

        all_results = []
        for i, term in enumerate(search_terms, 1):
            logger.info(f"[{i}/{len(search_terms)}] NEI (RePORTER): '{term}'")
            results = self.search(term, max_results=max_per_query)
            all_results.extend(results)
            logger.info(f"  Found {len(results)} (total: {len(all_results)})")
            time.sleep(2.0)
        return all_results

    def _project_to_metadata(self, project: dict) -> DatasetMetadata | None:
        """Convert an NIH RePORTER project record to DatasetMetadata.

        Args:
            project: A single project dict from the RePORTER API response.

        Returns:
            DatasetMetadata instance, or None if essential fields are missing.
        """
        project_num = project.get("project_num", "")
        if not project_num:
            return None

        # Build project URL from application_id
        application_id = project.get("appl_id", "")
        if application_id:
            url = f"https://reporter.nih.gov/project-details/{application_id}"
        else:
            url = f"https://reporter.nih.gov/project-details/{project_num}"

        # Extract keywords from semicolon-separated terms
        terms_raw = project.get("terms", "") or ""
        keywords = [t.strip() for t in terms_raw.split(";") if t.strip()]

        # Extract PI names
        creators = []
        for pi in project.get("pi_names", []) or []:
            if isinstance(pi, dict):
                name = pi.get("full_name", "") or pi.get("last_name", "")
            elif isinstance(pi, str):
                name = pi
            else:
                continue
            if name:
                creators.append({
                    "creatorName": name,
                    "nameType": "Personal",
                })

        # Publication year from fiscal_year
        fiscal_year = project.get("fiscal_year")
        pub_year = str(fiscal_year) if fiscal_year else None

        # Description
        abstract = project.get("abstract_text", "") or ""

        # Dates
        dates = []
        start_date = project.get("project_start_date")
        end_date = project.get("project_end_date")
        if start_date:
            dates.append({"dateValue": start_date, "dateType": "StartDate"})
        if end_date:
            dates.append({"dateValue": end_date, "dateType": "EndDate"})

        return DatasetMetadata(
            source="nei",
            source_id=project_num,
            doi=None,
            url=url,
            title=project.get("project_title", "") or "",
            description=abstract[:2000],
            keywords=keywords,
            file_names=[],
            file_types=set(),
            file_count=0,
            total_size_bytes=0,
            img_count=0,
            medical_count=0,
            archive_count=0,
            genomics_count=0,
            zip_contents=[],
            access_type="unknown",
            license=None,
            creators=creators,
            publication_year=pub_year,
            dates=dates,
            related_identifiers=[],
            external_links=[],
        )
