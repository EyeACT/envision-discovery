#!/usr/bin/env python3
"""
ENVISION Dataset Scraper
========================
Scrapes Zenodo for eye imaging datasets with intelligent filtering.

Features:
- Filters for datasets only (resource_type=dataset)
- Inspects ZIP contents via HTTP Range requests (no full download needed)
- Detects external dataset links (GitHub, Kaggle, HuggingFace, etc.)
- Extracts weblinks to potential data files from descriptions
- Excludes GWAS/genomics files (fasta, h5ad, vcf, etc.)
- Resumable: skips previously scraped records

Part of the ENVISION project by the FAIR Data Innovations Hub.
https://github.com/EyeACT/envision-discovery
"""

import json
import logging
import re
import struct
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

import requests
from bs4 import BeautifulSoup

from .utils import request_with_backoff, ArchiveInspector, PaginatedSearch, EYE_IMAGING_EXTS as UTILS_IMAGING_EXTS, GENOMICS_EXTS as UTILS_GENOMICS_EXTS, ARCHIVE_EXTS as UTILS_ARCHIVE_EXTS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# =============================================================================
# FILE TYPE DEFINITIONS
# =============================================================================

EYE_IMAGING_EXTS = {
    # Standard image formats
    ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".gif",
    # Medical imaging formats
    ".dcm", ".dicom", ".nii", ".nii.gz",
    # MATLAB/scientific
    ".mat", ".npy", ".npz", ".h5", ".hdf5",
    # OCT-specific formats
    ".fds", ".e2e", ".vol", ".oct", ".fda", ".img",
}

ARCHIVE_EXTS = {".zip", ".tar", ".gz", ".tar.gz", ".rar", ".7z", ".tgz"}
# archives that hold many files and that ArchiveInspector cannot list
MULTI_FILE_ARCHIVE_EXTS = (".rar", ".7z")

GENOMICS_EXTS = {
    ".fasta", ".fa", ".fna",
    ".fastq", ".fq", ".fastq.gz", ".fq.gz",
    ".h5ad",
    ".bam", ".sam", ".cram",
    ".vcf", ".bcf", ".vcf.gz",
    ".bed", ".gtf", ".gff", ".gff3",
    ".bigwig", ".bw", ".wig",
    ".cel", ".idat",
    ".loom",
    ".mtx", ".mtx.gz",
}

DATA_PLATFORMS = [
    "github.com", "gitlab.com", "bitbucket.org",
    "kaggle.com",
    "drive.google.com",
    "huggingface.co", "hf.co",
    "osf.io",
    "dryad", "datadryad.org",
    "figshare.com",
    "dataverse",
    "mendeley.com/datasets",
    "ieee-dataport.org",
    "physionet.org",
    "synapse.org",
    "s3.amazonaws.com",
    "storage.googleapis.com",
    "blob.core.windows.net",
]


# =============================================================================
# ZIP INSPECTOR
# =============================================================================

class ZipInspector:
    """Inspect ZIP file contents via HTTP Range requests without full download.

    ZIP files store the central directory (file listing) at the END of the file,
    so we download only the last ~64KB to get the complete manifest.
    """

    @staticmethod
    def inspect_via_range(
        download_url: str,
        session: requests.Session,
        max_tail_bytes: int = 65536,
    ) -> Optional[List[Dict]]:
        """Download only the ZIP central directory and parse file listing."""
        headers = {"Range": f"bytes=-{max_tail_bytes}"}
        try:
            resp = session.get(download_url, headers=headers, timeout=60)
            if resp.status_code not in (200, 206):
                return None
        except requests.RequestException:
            return None
        return ZipInspector._parse_central_directory(resp.content)

    @staticmethod
    def _parse_central_directory(data: bytes) -> Optional[List[Dict]]:
        """Parse ZIP central directory to extract file listing."""
        eocd_pos = data.rfind(b"\x50\x4b\x05\x06")
        if eocd_pos == -1:
            return None

        try:
            eocd = data[eocd_pos : eocd_pos + 22]
            if len(eocd) < 22:
                return None

            total_entries = struct.unpack("<H", eocd[10:12])[0]
            cd_size = struct.unpack("<I", eocd[12:16])[0]

            cd_start = eocd_pos - cd_size
            if cd_start < 0:
                return None

            files = []
            pos = cd_start
            for _ in range(total_entries):
                if pos + 46 > len(data):
                    break
                if data[pos : pos + 4] != b"\x50\x4b\x01\x02":
                    break

                compressed = struct.unpack("<I", data[pos + 20 : pos + 24])[0]
                uncompressed = struct.unpack("<I", data[pos + 24 : pos + 28])[0]
                name_len = struct.unpack("<H", data[pos + 28 : pos + 30])[0]
                extra_len = struct.unpack("<H", data[pos + 30 : pos + 32])[0]
                comment_len = struct.unpack("<H", data[pos + 32 : pos + 34])[0]

                name_bytes = data[pos + 46 : pos + 46 + name_len]
                try:
                    filename = name_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    filename = name_bytes.decode("cp437", errors="replace")

                files.append({
                    "filename": filename,
                    "compressed_size": compressed,
                    "uncompressed_size": uncompressed,
                    "is_directory": filename.endswith("/"),
                })
                pos += 46 + name_len + extra_len + comment_len

            return files
        except Exception:
            return None

    @staticmethod
    def summarize_contents(contents: List[Dict]) -> Dict:
        """Generate summary statistics from ZIP contents."""
        if not contents:
            return {}

        extensions = {}
        total_files = 0
        total_dirs = 0
        total_size = 0
        imaging_files = []
        genomics_files = []

        for item in contents:
            if item.get("is_directory"):
                total_dirs += 1
                continue

            total_files += 1
            total_size += item.get("uncompressed_size", 0)
            filename = item.get("filename", "").lower()

            if "." in filename:
                for ext in sorted(
                    EYE_IMAGING_EXTS | GENOMICS_EXTS | ARCHIVE_EXTS,
                    key=len,
                    reverse=True,
                ):
                    if filename.endswith(ext):
                        extensions[ext] = extensions.get(ext, 0) + 1
                        if ext in EYE_IMAGING_EXTS:
                            imaging_files.append(filename)
                        elif ext in GENOMICS_EXTS:
                            genomics_files.append(filename)
                        break

        return {
            "total_files": total_files,
            "total_directories": total_dirs,
            "total_uncompressed_bytes": total_size,
            "file_types": dict(sorted(extensions.items(), key=lambda x: -x[1])[:20]),
            "imaging_file_count": len(imaging_files),
            "genomics_file_count": len(genomics_files),
            "sample_imaging_files": imaging_files[:10],
            "sample_genomics_files": genomics_files[:5],
        }


# =============================================================================
# LINK EXTRACTION
# =============================================================================

def extract_dataset_links(record: Dict) -> List[str]:
    """Extract external dataset links from related_identifiers."""
    links = set()
    related = record.get("metadata", {}).get("related_identifiers", [])
    for rel in related:
        url = rel.get("identifier", "") if isinstance(rel, dict) else str(rel)
        if any(p in url.lower() for p in DATA_PLATFORMS):
            links.add(url)
    return list(links)


def extract_weblinks_from_description(record: Dict) -> List[Dict]:
    """Extract weblinks to potential data files from HTML description."""
    desc = record.get("metadata", {}).get("description", "")
    if not desc:
        return []

    try:
        text = BeautifulSoup(desc, "html.parser").get_text()
    except Exception:
        text = desc

    skip = {
        "twitter.com", "facebook.com", "linkedin.com",
        "youtube.com", "vimeo.com", "creativecommons.org",
        "orcid.org", "scholar.google",
    }

    links = []
    for url in re.findall(r"https?://[^\s<>\"'\)\]]+(?:\.[^\s<>\"'\)\]]+)+", text):
        url = url.rstrip(".,;:")
        low = url.lower()

        if any(s in low for s in skip):
            continue

        link_type = "unknown"
        if any(p in low for p in DATA_PLATFORMS):
            link_type = "data_platform"
        elif any(ext in low for ext in [".zip", ".tar", ".gz", ".7z"]):
            link_type = "archive_download"
        elif any(ext in low for ext in [".jpg", ".png", ".tif", ".dcm", ".mat"]):
            link_type = "direct_file"
        elif "download" in low or "data" in low:
            link_type = "potential_download"
        elif "doi.org" in low or "zenodo" in low:
            link_type = "doi_reference"

        links.append({"url": url, "type": link_type})

    return links


# =============================================================================
# FILE ANALYSIS
# =============================================================================

def analyze_record_files(record: Dict, session: requests.Session) -> Dict:
    """Analyze a record's files, including ZIP contents via Range requests."""
    files = record.get("files", [])

    analysis = {
        "has_imaging_files": False,
        "has_archives": False,
        "has_genomics_only": False,
        "imaging_file_count": 0,
        "archive_count": 0,
        "genomics_count": 0,
        "total_imaging_size": 0,
        "total_archive_size": 0,
        "top_level_files": [],
        "zip_contents": {},
        "zip_imaging_files": [],
        "zip_genomics_files": [],
        # Multi-file archives whose member list could not be read (listing
        # failed, e.g. a ZIP central directory over max_cd_bytes, a server
        # that ignores Range, or a format we cannot list such as .rar/.7z).
        # "Not listed" is not "no imaging inside": _should_keep keeps these.
        "uninspectable_archives": [],
    }

    imaging_found = False
    genomics_found = False

    for f in files:
        filename = f.get("key", "").lower()
        size = f.get("size", 0)

        analysis["top_level_files"].append({"name": f.get("key", ""), "size": size})

        if any(filename.endswith(ext) for ext in EYE_IMAGING_EXTS):
            imaging_found = True
            analysis["imaging_file_count"] += 1
            analysis["total_imaging_size"] += size

        if any(filename.endswith(ext) for ext in GENOMICS_EXTS):
            genomics_found = True
            analysis["genomics_count"] += 1

        if filename.endswith(".zip") or filename.endswith((".tar.gz", ".tgz", ".tar")):
            analysis["has_archives"] = True
            analysis["archive_count"] += 1
            analysis["total_archive_size"] += size

            download_url = f.get("links", {}).get("self")
            listed = False
            if download_url:
                try:
                    archive_files = ArchiveInspector.inspect_archive(download_url, filename, session)
                    listed = archive_files is not None
                    if archive_files:
                        summary = ArchiveInspector.summarize_contents(archive_files)
                        analysis["zip_contents"][filename] = summary

                        if summary.get("imaging_file_count", 0) > 0:
                            imaging_found = True
                            analysis["zip_imaging_files"].extend(
                                summary.get("imaging_files", [])
                            )
                        if summary.get("genomics_file_count", 0) > 0:
                            genomics_found = True
                            analysis["zip_genomics_files"].extend(
                                summary.get("genomics_files", [])
                            )
                except Exception as e:
                    logger.debug(f"Could not inspect archive {filename}: {e}")
            if not listed:
                analysis["uninspectable_archives"].append(
                    {"name": f.get("key", ""), "size": size,
                     "reason": "listing failed" if download_url else "no download link"})

        elif any(filename.endswith(ext) for ext in ARCHIVE_EXTS):
            analysis["has_archives"] = True
            analysis["archive_count"] += 1
            analysis["total_archive_size"] += size
            if filename.endswith(MULTI_FILE_ARCHIVE_EXTS):
                # .rar / .7z: no Range lister; a single-file .gz is not
                # listed here because its name already says what it holds
                analysis["uninspectable_archives"].append(
                    {"name": f.get("key", ""), "size": size, "reason": "format not listable"})

    analysis["has_imaging_files"] = imaging_found
    analysis["has_genomics_only"] = genomics_found and not imaging_found

    return analysis


# =============================================================================
# ZENODO SCRAPER
# =============================================================================

SEARCH_TERMS = [
    # Imaging modalities
    "retinal OCT", "fundus photography", "optical coherence tomography eye",
    "retinal imaging dataset", "fundus image dataset", "ophthalmic OCT dataset",
    "macular OCT", "RNFL OCT", "OCT-A retina",
    # Disease-specific
    "diabetic retinopathy dataset", "glaucoma dataset", "AMD dataset",
    "diabetic retinopathy fundus", "glaucoma OCT", "macular degeneration imaging",
    "choroidal neovascularization OCT", "macular edema OCT",
    # Anatomy-specific
    "retinal layer segmentation", "optic nerve head imaging",
    "retinal vessel segmentation", "optic disc detection",
    "foveal OCT", "macula imaging", "choroidal imaging",
    # General
    "ophthalmic imaging", "eye imaging data", "ophthalmology dataset",
    "retina scan", "eye scan dataset", "ocular imaging",
    # Equipment-specific
    "Spectralis OCT", "Cirrus OCT", "Topcon OCT", "Heidelberg retina",
    # Known benchmark datasets
    "DRIVE retinal", "STARE retinal", "MESSIDOR", "IDRiD",
    "REFUGE glaucoma", "CHASE_DB1", "EyePACS", "APTOS",
    # Cornea / anterior segment
    "corneal topography", "slit lamp imaging", "anterior segment OCT",
    "meibography", "corneal imaging dataset",
]


def _build_zenodo_query(term: str) -> str:
    """Convert a human-readable search term into an AND-required Elasticsearch query.

    Zenodo's Elasticsearch treats multi-word queries as OR by default, so
    "retinal OCT" matches any record with "retinal" OR "OCT" (~1,300 results).
    This rewrites terms to use the + (required) operator so every word must
    be present, and adds -October for standalone "OCT" to avoid date matches.

    Single-word terms are left unchanged.
    """
    words = term.split()
    if len(words) == 1:
        return term

    parts = []
    for word in words:
        if re.match(r"^OCT$", word):
            parts.append("+OCT -October")
        else:
            parts.append(f"+{word}")
    return " ".join(parts)


class ZenodoScraper:
    """Scrape Zenodo for eye imaging datasets with ZIP inspection."""

    SEARCH_URL = "https://zenodo.org/api/records/"
    # Zenodo's search API refuses to page past this many hits per query
    # (page * size > 10,000 returns HTTP 400). Queries above it must be
    # split (run_scrape does this by creation date).
    MAX_API_RESULTS = 10_000

    def __init__(self, output_dir: Path, resume: bool = True):
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})
        self.seen_records: Set[int] = set()
        self.output_dir = Path(output_dir)
        self.metadata_dir = self.output_dir / "metadata" / "zenodo"
        self.metadata_dir.mkdir(parents=True, exist_ok=True)

        if resume:
            for f in self.metadata_dir.glob("*.json"):
                try:
                    self.seen_records.add(int(f.stem))
                except ValueError:
                    pass
            if self.seen_records:
                logger.info(f"Resuming: {len(self.seen_records)} existing records")

        self.stats = {
            "total_searched": 0,
            "datasets_found": 0,
            "with_imaging_files": 0,
            "with_dataset_links": 0,
            "with_genomics_only": 0,
            "zips_inspected": 0,
            "skipped_existing": 0,
            "kept_uninspectable_archive": 0,
        }
        # Failed HTTP requests (filled by request_with_backoff) and one
        # entry per search() call; run_scrape turns these into
        # scrape_query_report.json.
        self.failures: List[Dict] = []
        self.searches: List[Dict] = []

    def get_count(self, query: str, datasets_only: bool = True,
                   start_date: str = None, end_date: str = None) -> Optional[int]:
        """Get total result count for a query without fetching records.

        Returns None (not 0) when the request fails, so callers can tell a
        failed count from an empty result.
        """
        full_query = query
        if datasets_only:
            full_query = f"({query}) AND resource_type.type:dataset"
        if start_date and end_date:
            full_query += f" AND created:[{start_date} TO {end_date}]"

        resp = request_with_backoff(
            self.session, "get", self.SEARCH_URL,
            params={"q": full_query, "size": 1},
            failures=self.failures,
        )
        if resp is None:
            return None
        try:
            return int(resp.json().get("hits", {}).get("total", 0))
        except (ValueError, TypeError) as e:
            self.failures.append({"url": self.SEARCH_URL, "params": {"q": full_query},
                                  "status": resp.status_code, "error": f"bad JSON: {e}"})
            return None

    def search(
        self,
        query: str,
        max_results: int = 1000,
        datasets_only: bool = True,
        inspect_zips: bool = True,
    ) -> List[Dict]:
        """Search Zenodo, enrich records, and filter for eye imaging datasets.

        Every call appends a summary to self.searches with the reported
        total, the hits actually paged through, and a status: "ok",
        "capped" (stopped by max_results or the API result cap while hits
        remained) or "error" (a page request failed; details are in
        self.failures). Before, a failed page or an exception ended the loop
        silently and looked exactly like a query with no more results.
        """
        records = []
        page = 1
        per_page = 25
        full_query = query
        if datasets_only:
            full_query = f"({query}) AND resource_type.type:dataset"
        entry = {"query": full_query, "total": None, "hits_seen": 0,
                 "kept": 0, "kept_uninspectable": 0, "status": "ok", "error": None}
        self.searches.append(entry)

        while True:
            if len(records) >= max_results:
                if entry["total"] is not None and entry["hits_seen"] < entry["total"]:
                    entry["status"] = "capped"
                break
            if (page - 1) * per_page >= self.MAX_API_RESULTS:
                entry["status"] = "capped"
                logger.warning(
                    f"  Query hit the Zenodo {self.MAX_API_RESULTS:,} result cap: {full_query}"
                )
                break

            params = {"q": full_query, "page": page, "size": per_page}

            try:
                n_fail = len(self.failures)
                response = request_with_backoff(
                    self.session, "get", self.SEARCH_URL, params=params,
                    failures=self.failures,
                )
                if response is None:
                    entry["status"] = "error"
                    entry["error"] = (self.failures[n_fail:] or [{}])[-1]
                    break

                payload = response.json().get("hits", {})
                if entry["total"] is None:
                    entry["total"] = payload.get("total")
                hits = payload.get("hits", [])
                if not hits:
                    break
                entry["hits_seen"] += len(hits)

                for hit in hits:
                    record_id = hit.get("id")
                    if not record_id:
                        continue
                    if record_id in self.seen_records:
                        self.stats["skipped_existing"] += 1
                        continue

                    self.seen_records.add(record_id)
                    self.stats["total_searched"] += 1

                    enriched = self._enrich_record(hit, inspect_zips)
                    if self._should_keep(enriched):
                        records.append(enriched)
                        self._save_metadata(enriched)
                        self.stats["datasets_found"] += 1
                        entry["kept"] += 1
                        if self._keep_reason(enriched) == "uninspectable_archive":
                            self.stats["kept_uninspectable_archive"] += 1
                            entry["kept_uninspectable"] += 1

                page += 1
                time.sleep(2.0)

                if len(hits) < per_page:
                    break

            except Exception as e:
                logger.warning(f"Search error for '{query}': {e}")
                entry["status"] = "error"
                entry["error"] = f"{type(e).__name__}: {e}"[:300]
                break

        return records

    def _enrich_record(self, record: Dict, inspect_zips: bool = True) -> Dict:
        """Add file analysis, dataset links, and weblinks to a record."""
        dataset_links = extract_dataset_links(record)
        if dataset_links:
            self.stats["with_dataset_links"] += 1

        weblinks = extract_weblinks_from_description(record)

        if inspect_zips:
            file_analysis = analyze_record_files(record, self.session)
            if file_analysis.get("has_imaging_files"):
                self.stats["with_imaging_files"] += 1
            if file_analysis.get("has_genomics_only"):
                self.stats["with_genomics_only"] += 1
            if file_analysis.get("zip_contents"):
                self.stats["zips_inspected"] += len(file_analysis["zip_contents"])
        else:
            file_analysis = {"has_imaging_files": False, "has_archives": False}

        record["_file_analysis"] = file_analysis
        record["_dataset_links"] = dataset_links
        record["_weblinks"] = weblinks
        record["_platform"] = "zenodo"
        record["_enriched_at"] = datetime.now().isoformat()

        return record

    def _should_keep(self, record: Dict) -> bool:
        """Keep record if it likely contains eye imaging data."""
        return self._keep_reason(record) is not None

    @staticmethod
    def _keep_reason(record: Dict) -> Optional[str]:
        """Why a record is kept, or None when it is dropped."""
        analysis = record.get("_file_analysis", {})

        if analysis.get("has_genomics_only"):
            return None
        if analysis.get("has_imaging_files"):
            return "imaging_files"
        if record.get("_dataset_links"):
            return "dataset_links"

        weblinks = record.get("_weblinks", [])
        if any(
            l.get("type") in ["data_platform", "archive_download", "direct_file"]
            for l in weblinks
        ):
            return "weblinks"

        # Archives: kept when inspection found imaging files inside ...
        if analysis.get("has_archives") and analysis.get("zip_contents"):
            for zip_summary in analysis["zip_contents"].values():
                if zip_summary.get("imaging_file_count", 0) > 0:
                    return "imaging_in_archive"
        # ... or when an archive could not be listed at all: an unreadable
        # listing says nothing about the contents (before, such records were
        # dropped silently, e.g. SYN-OCT.zip with a 108 MB central directory)
        if analysis.get("uninspectable_archives"):
            return "uninspectable_archive"

        return None

    def _save_metadata(self, record: Dict):
        """Save enriched record metadata to JSON."""
        record_id = record.get("id")
        filepath = self.metadata_dir / f"{record_id}.json"
        with open(filepath, "w") as f:
            json.dump(record, f, indent=2)

    def print_stats(self):
        """Print scraping statistics."""
        logger.info("\n" + "=" * 60)
        logger.info("SCRAPING STATISTICS")
        logger.info("=" * 60)
        for key, value in self.stats.items():
            logger.info(f"  {key}: {value:,}")


# =============================================================================
# ENTRY POINT
# =============================================================================

def run_scrape(
    output_dir: Path,
    datasets_only: bool = True,
    inspect_zips: bool = True,
    max_per_query: int = 500,
) -> List[Dict]:
    """Run full scrape with ZIP inspection and link detection."""
    logger.info("=" * 70)
    logger.info("ENVISION Dataset Scraper")
    logger.info("=" * 70)
    logger.info(f"Output: {output_dir}")
    logger.info(f"Datasets only: {datasets_only}")
    logger.info(f"ZIP inspection: {inspect_zips}")
    logger.info(f"Search terms: {len(SEARCH_TERMS)}")

    scraper = ZenodoScraper(output_dir)
    all_records = []

    # Set up paginated search for queries that exceed API limits
    def count_fn(query, start_date, end_date):
        return scraper.get_count(query, datasets_only=datasets_only,
                                 start_date=start_date, end_date=end_date)

    def fetch_fn(query, start_date, end_date, max_results):
        date_clause = f" AND created:[{start_date} TO {end_date}]"
        return scraper.search(
            query + date_clause,
            max_results=max_results,
            datasets_only=datasets_only,
            inspect_zips=inspect_zips,
        )

    paginator = PaginatedSearch(
        count_fn=count_fn,
        fetch_fn=fetch_fn,
        api_max=max_per_query,
        date_format="%Y-%m-%d",
    )

    # Upper bound for date slicing is today, not a hard-coded year, so
    # records created after a fixed end date are not silently excluded.
    end_date = datetime.now().strftime("%Y-%m-%d")
    term_report = []

    for i, term in enumerate(SEARCH_TERMS, 1):
        query = _build_zenodo_query(term)
        logger.info(f"\n[{i}/{len(SEARCH_TERMS)}] Searching: '{term}' -> q='{query}'")
        n_searches = len(scraper.searches)
        n_problems = len(paginator.problems)

        # Check count first — use pagination if exceeds max_per_query
        total_count = scraper.get_count(query, datasets_only=datasets_only)

        if total_count is None:
            logger.warning(f"  Count request failed for '{term}', searching without a count")
            results = scraper.search(
                query,
                max_results=max_per_query,
                datasets_only=datasets_only,
                inspect_zips=inspect_zips,
            )
        elif total_count > max_per_query:
            logger.info(
                f"  Total results ({total_count}) exceeds cap ({max_per_query}), "
                f"using date-range pagination"
            )
            results = paginator.search(query, "2010-01-01", end_date)
        else:
            results = scraper.search(
                query,
                max_results=max_per_query,
                datasets_only=datasets_only,
                inspect_zips=inspect_zips,
            )

        all_records.extend(results)
        term_report.append(_term_status(
            term, query, total_count,
            scraper.searches[n_searches:], paginator.problems[n_problems:],
        ))
        logger.info(
            f"  Found {len(results)} matching datasets (total: {len(all_records)})"
            f" [{term_report[-1]['status']}]"
        )
        time.sleep(3.0)

    problems = [t for t in term_report if t["status"] != "ok"]
    summary = {
        "timestamp": datetime.now().isoformat(),
        "stats": scraper.stats,
        "total_records": len(all_records),
        "search_terms_used": len(SEARCH_TERMS),
        "terms_with_problems": len(problems),
        "failed_requests": len(scraper.failures),
        "kept_uninspectable_archive": scraper.stats["kept_uninspectable_archive"],
    }
    with open(output_dir / "scrape_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    with open(output_dir / "scrape_query_report.json", "w") as f:
        json.dump({"terms": term_report, "failed_requests": scraper.failures}, f, indent=2)

    for t in problems:
        logger.warning(
            f"  {t['status'].upper()}: '{t['term']}' total={t['total']} "
            f"hits_seen={t['hits_seen']} ({len(t['slice_problems'])} bad date slices)"
        )
    logger.info(
        f"Query report: {len(problems)} term(s) capped or errored, "
        f"{len(scraper.failures)} failed request(s) -> "
        f"{output_dir / 'scrape_query_report.json'}"
    )

    if scraper.stats["kept_uninspectable_archive"]:
        logger.warning(
            f"{scraper.stats['kept_uninspectable_archive']} record(s) kept only because an "
            f"archive could not be listed (see _file_analysis.uninspectable_archives)"
        )
    scraper.print_stats()
    return all_records


def _term_status(term: str, query: str, total: Optional[int],
                 searches: List[Dict], slice_problems: List[Dict]) -> Dict:
    """Summarise one search term: did we page through everything it matched?

    status is "error" if the count or any page request failed, "capped" if
    any search or date slice stopped with hits remaining, else "ok".
    """
    statuses = {s["status"] for s in searches} | {p["status"] for p in slice_problems}
    if total is None:
        statuses.add("error")
    status = "error" if "error" in statuses else "capped" if "capped" in statuses else "ok"
    return {
        "term": term,
        "query": query,
        "total": total,
        "hits_seen": sum(s["hits_seen"] for s in searches),
        "kept": sum(s["kept"] for s in searches),
        "kept_uninspectable": sum(s.get("kept_uninspectable", 0) for s in searches),
        "status": status,
        "searches": searches,
        "slice_problems": slice_problems,
    }


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="ENVISION Dataset Scraper")
    parser.add_argument(
        "--output", "-o", type=Path, default=Path.cwd() / "data",
        help="Output directory for scraped data",
    )
    parser.add_argument(
        "--all-types", action="store_true",
        help="Include all resource types, not just datasets",
    )
    parser.add_argument(
        "--no-zip-inspect", action="store_true",
        help="Skip ZIP content inspection (faster but less info)",
    )
    parser.add_argument(
        "--max-per-query", type=int, default=500,
        help="Maximum results per search term",
    )

    args = parser.parse_args()
    run_scrape(
        output_dir=args.output,
        datasets_only=not args.all_types,
        inspect_zips=not args.no_zip_inspect,
        max_per_query=args.max_per_query,
    )


if __name__ == "__main__":
    main()
