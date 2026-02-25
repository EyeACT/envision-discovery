#!/usr/bin/env python3
"""
ENVISION Eye Imaging Dataset Scraper
=====================================
Scrapes Zenodo for eye imaging datasets with intelligent filtering.

Features:
- Filters for datasets only (resource_type=dataset)
- Inspects ZIP contents via HTTP Range requests (no full download needed)
- Detects external dataset links (GitHub, Kaggle, HuggingFace, etc.)
- Extracts weblinks to potential data files from descriptions
- Excludes GWAS/genomics files (fasta, h5ad, vcf, etc.)

Part of the ENVISION project by the FAIR Data Innovations Hub.
https://github.com/EyeACT/envision-discovery
"""

import os
import json
import time
import re
import requests
import logging
import struct
import io
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set, Optional, Tuple
from bs4 import BeautifulSoup

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# =============================================================================
# FILE TYPE DEFINITIONS
# =============================================================================

# Eye imaging file extensions to look for
EYE_IMAGING_EXTS = {
    # Standard image formats
    ".jpg",
    ".jpeg",
    ".png",
    ".tif",
    ".tiff",
    ".bmp",
    ".gif",
    # Medical imaging formats
    ".dcm",
    ".dicom",
    ".nii",
    ".nii.gz",
    # MATLAB/scientific
    ".mat",
    ".npy",
    ".npz",
    ".h5",
    ".hdf5",
    # OCT-specific formats
    ".fds",  # Topcon OCT
    ".e2e",  # Heidelberg OCT
    ".vol",  # Zeiss OCT volumes
    ".oct",  # Generic OCT
    ".fda",  # Optovue OCT
    ".img",  # Generic imaging
}

# Archive formats that may contain imaging data
ARCHIVE_EXTS = {".zip", ".tar", ".gz", ".tar.gz", ".rar", ".7z", ".tgz"}

# GWAS/Genomics extensions to EXCLUDE
GENOMICS_EXTS = {
    ".fasta",
    ".fa",
    ".fna",  # DNA/RNA sequences
    ".fastq",
    ".fq",  # Sequencing reads
    ".fastq.gz",
    ".fq.gz",  # Compressed reads
    ".h5ad",  # AnnData (single-cell RNA-seq)
    ".bam",
    ".sam",
    ".cram",  # Alignments
    ".vcf",
    ".bcf",
    ".vcf.gz",  # Variants
    ".bed",
    ".gtf",
    ".gff",
    ".gff3",  # Genomic annotations
    ".bigwig",
    ".bw",
    ".wig",  # Genomics tracks
    ".cel",
    ".idat",  # Microarray
    ".loom",  # Single-cell
    ".mtx",
    ".mtx.gz",  # Sparse matrices (often single-cell)
}

# External data hosting platforms to detect
DATA_PLATFORMS = [
    "github.com",
    "gitlab.com",
    "bitbucket.org",
    "kaggle.com",
    "kaggle.com/datasets",
    "drive.google.com",
    "docs.google.com",
    "huggingface.co",
    "hf.co",
    "osf.io",
    "cos.io",
    "dryad",
    "datadryad.org",
    "figshare.com",
    "dataverse",
    "mendeley.com/datasets",
    "ieee-dataport.org",
    "physionet.org",
    "synapse.org",
    "aws.amazon.com/s3",
    "s3.amazonaws.com",
    "storage.googleapis.com",
    "blob.core.windows.net",
]

# =============================================================================
# ZIP INSPECTOR (from zenodo_zip_inspector.py)
# =============================================================================


class ZipInspector:
    """Inspect ZIP file contents without downloading the entire file."""

    @staticmethod
    def inspect_via_range(
        download_url: str, session: requests.Session, max_tail_bytes: int = 65536
    ) -> Optional[List[Dict]]:
        """
        Use HTTP Range requests to download only the ZIP central directory.

        ZIP files store the file listing at the END of the file,
        so we can download just the last ~64KB to get the complete manifest.

        Returns list of dicts with filename, compressed_size, uncompressed_size.
        """
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
        # Find End of Central Directory (EOCD) signature: 0x06054b50
        eocd_sig = b"\x50\x4b\x05\x06"
        eocd_pos = data.rfind(eocd_sig)

        if eocd_pos == -1:
            return None

        try:
            eocd = data[eocd_pos : eocd_pos + 22]
            if len(eocd) < 22:
                return None

            total_entries = struct.unpack("<H", eocd[10:12])[0]
            cd_size = struct.unpack("<I", eocd[12:16])[0]

            cd_start_in_chunk = eocd_pos - cd_size
            if cd_start_in_chunk < 0:
                return None

            files = []
            pos = cd_start_in_chunk

            for _ in range(total_entries):
                if pos + 46 > len(data):
                    break

                sig = data[pos : pos + 4]
                if sig != b"\x50\x4b\x01\x02":
                    break

                compressed_size = struct.unpack("<I", data[pos + 20 : pos + 24])[0]
                uncompressed_size = struct.unpack("<I", data[pos + 24 : pos + 28])[0]
                filename_len = struct.unpack("<H", data[pos + 28 : pos + 30])[0]
                extra_len = struct.unpack("<H", data[pos + 30 : pos + 32])[0]
                comment_len = struct.unpack("<H", data[pos + 32 : pos + 34])[0]

                filename_bytes = data[pos + 46 : pos + 46 + filename_len]
                try:
                    filename = filename_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    filename = filename_bytes.decode("cp437", errors="replace")

                files.append(
                    {
                        "filename": filename,
                        "compressed_size": compressed_size,
                        "uncompressed_size": uncompressed_size,
                        "is_directory": filename.endswith("/"),
                    }
                )

                pos += 46 + filename_len + extra_len + comment_len

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
            else:
                total_files += 1
                total_size += item.get("uncompressed_size", 0)

                filename = item.get("filename", "").lower()

                # Count extensions
                if "." in filename:
                    # Handle compound extensions like .nii.gz
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
    """
    Extract external dataset links from record metadata.
    Checks related_identifiers and description for known data platforms.
    """
    links = set()

    # Check related_identifiers
    related = record.get("metadata", {}).get("related_identifiers", [])
    for rel in related:
        if isinstance(rel, dict):
            url = rel.get("identifier", "")
        else:
            url = str(rel)

        url_lower = url.lower()
        if any(platform in url_lower for platform in DATA_PLATFORMS):
            links.add(url)

    return list(links)


def extract_weblinks_from_description(record: Dict) -> List[Dict]:
    """
    Extract weblinks to potential data files from description.
    Returns links with context about what they might contain.
    """
    desc = record.get("metadata", {}).get("description", "")
    if not desc:
        return []

    # Strip HTML tags for cleaner extraction
    try:
        soup = BeautifulSoup(desc, "html.parser")
        text = soup.get_text()
    except:
        text = desc

    links = []

    # Find all URLs
    url_pattern = r'https?://[^\s<>"\'\)\]]+(?:\.[^\s<>"\'\)\]]+)+'
    urls = re.findall(url_pattern, text)

    for url in urls:
        # Clean trailing punctuation
        url = url.rstrip(".,;:")
        url_lower = url.lower()

        link_info = {"url": url, "type": "unknown"}

        # Categorize the link
        if any(platform in url_lower for platform in DATA_PLATFORMS):
            link_info["type"] = "data_platform"
        elif any(ext in url_lower for ext in [".zip", ".tar", ".gz", ".7z"]):
            link_info["type"] = "archive_download"
        elif any(ext in url_lower for ext in [".jpg", ".png", ".tif", ".dcm", ".mat"]):
            link_info["type"] = "direct_file"
        elif "download" in url_lower or "data" in url_lower:
            link_info["type"] = "potential_download"
        elif "doi.org" in url_lower or "zenodo" in url_lower:
            link_info["type"] = "doi_reference"

        # Skip obvious non-data links
        skip_patterns = [
            "twitter.com",
            "facebook.com",
            "linkedin.com",
            "youtube.com",
            "vimeo.com",
            "creativecommons.org",
            "orcid.org",
            "scholar.google",
        ]
        if any(skip in url_lower for skip in skip_patterns):
            continue

        links.append(link_info)

    return links


# =============================================================================
# FILE ANALYSIS
# =============================================================================


def analyze_record_files(record: Dict, session: requests.Session) -> Dict:
    """
    Analyze a Zenodo record's files, including ZIP contents via Range requests.

    Returns comprehensive file analysis including:
    - Top-level file types
    - ZIP contents (inspected without full download)
    - Imaging vs genomics detection
    """
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
    }

    imaging_found = False
    genomics_found = False

    for f in files:
        filename = f.get("key", "").lower()
        size = f.get("size", 0)

        analysis["top_level_files"].append(
            {
                "name": f.get("key", ""),
                "size": size,
            }
        )

        # Check for imaging files
        if any(filename.endswith(ext) for ext in EYE_IMAGING_EXTS):
            imaging_found = True
            analysis["imaging_file_count"] += 1
            analysis["total_imaging_size"] += size

        # Check for genomics files
        if any(filename.endswith(ext) for ext in GENOMICS_EXTS):
            genomics_found = True
            analysis["genomics_count"] += 1

        # Inspect ZIP files via Range request
        if filename.endswith(".zip"):
            analysis["has_archives"] = True
            analysis["archive_count"] += 1
            analysis["total_archive_size"] += size

            # Get download URL
            download_url = f.get("links", {}).get("self")
            if download_url:
                try:
                    zip_contents = ZipInspector.inspect_via_range(download_url, session)

                    if zip_contents:
                        summary = ZipInspector.summarize_contents(zip_contents)
                        analysis["zip_contents"][filename] = summary

                        # Check for imaging files inside ZIP
                        if summary.get("imaging_file_count", 0) > 0:
                            imaging_found = True
                            analysis["zip_imaging_files"].extend(
                                summary.get("sample_imaging_files", [])
                            )

                        # Check for genomics files inside ZIP
                        if summary.get("genomics_file_count", 0) > 0:
                            genomics_found = True
                            analysis["zip_genomics_files"].extend(
                                summary.get("sample_genomics_files", [])
                            )

                except Exception as e:
                    logger.debug(f"Could not inspect ZIP {filename}: {e}")

        # Handle other archive types
        elif any(filename.endswith(ext) for ext in ARCHIVE_EXTS):
            analysis["has_archives"] = True
            analysis["archive_count"] += 1
            analysis["total_archive_size"] += size

    analysis["has_imaging_files"] = imaging_found
    analysis["has_genomics_only"] = genomics_found and not imaging_found

    return analysis


# =============================================================================
# ENHANCED ZENODO SCRAPER
# =============================================================================


class ZenodoScraper:
    """
    Zenodo scraper with ZIP inspection and link detection.
    """

    SEARCH_URL = "https://zenodo.org/api/records/"

    def __init__(self, output_dir: Path, resume: bool = True):
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})
        self.seen_records: Set[int] = set()
        self.output_dir = Path(output_dir)
        self.metadata_dir = self.output_dir / "metadata" / "zenodo"
        self.metadata_dir.mkdir(parents=True, exist_ok=True)

        # Load existing records to avoid re-scraping
        if resume:
            existing = list(self.metadata_dir.glob("*.json"))
            for f in existing:
                try:
                    record_id = int(f.stem)
                    self.seen_records.add(record_id)
                except ValueError:
                    pass
            if self.seen_records:
                logger.info(
                    f"Resuming: loaded {len(self.seen_records)} existing records"
                )

        # Stats
        self.stats = {
            "total_searched": 0,
            "datasets_found": 0,
            "with_imaging_files": 0,
            "with_dataset_links": 0,
            "with_genomics_only": 0,
            "zips_inspected": 0,
            "skipped_existing": 0,
        }

    def search(
        self,
        query: str,
        max_results: int = 1000,
        datasets_only: bool = True,
        inspect_zips: bool = True,
    ) -> List[Dict]:
        """
        Search Zenodo with enhanced metadata extraction.

        Args:
            query: Search query string
            max_results: Maximum results per query
            datasets_only: Filter for resource_type=dataset only
            inspect_zips: Use HTTP Range requests to inspect ZIP contents
        """
        records = []
        page = 1
        per_page = 25

        while len(records) < max_results:
            full_query = query
            if datasets_only:
                full_query = f"({query}) AND resource_type.type:dataset"

            params = {
                "q": full_query,
                "page": page,
                "size": per_page,
            }

            try:
                # Rate limiting with exponential backoff
                max_retries = 3
                for attempt in range(max_retries):
                    response = self.session.get(
                        self.SEARCH_URL, params=params, timeout=30
                    )

                    if response.status_code == 429:
                        wait_time = 5 * (2**attempt)  # 5, 10, 20 seconds
                        logger.warning(
                            f"Rate limited, waiting {wait_time}s (attempt {attempt + 1}/{max_retries})"
                        )
                        time.sleep(wait_time)
                        continue

                    response.raise_for_status()
                    break
                else:
                    logger.warning(f"Max retries exceeded for query '{query}'")
                    break

                hits = response.json().get("hits", {}).get("hits", [])

                if not hits:
                    break

                for hit in hits:
                    record_id = hit.get("id")
                    if record_id and record_id not in self.seen_records:
                        self.seen_records.add(record_id)
                        self.stats["total_searched"] += 1
                    elif record_id in self.seen_records:
                        self.stats["skipped_existing"] += 1
                        continue

                        # Enrich record with analysis
                        enriched = self._enrich_record(hit, inspect_zips)

                        # Filter: keep if has imaging files OR dataset links
                        # Exclude if ONLY has genomics files
                        if self._should_keep(enriched):
                            records.append(enriched)
                            self._save_metadata(enriched)
                            self.stats["datasets_found"] += 1

                page += 1
                time.sleep(2.0)  # Rate limit - 2 sec between pages

                if len(hits) < per_page:
                    break

            except Exception as e:
                logger.warning(f"Search error for '{query}': {e}")
                break

        return records

    def _enrich_record(self, record: Dict, inspect_zips: bool = True) -> Dict:
        """Add enhanced metadata to a record."""

        # Extract dataset links
        dataset_links = extract_dataset_links(record)
        if dataset_links:
            self.stats["with_dataset_links"] += 1

        # Extract weblinks from description
        weblinks = extract_weblinks_from_description(record)

        # Analyze files (including ZIP contents)
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

        # Add enriched fields
        record["_file_analysis"] = file_analysis
        record["_dataset_links"] = dataset_links
        record["_weblinks"] = weblinks
        record["_platform"] = "zenodo"
        record["_enriched_at"] = datetime.now().isoformat()

        return record

    def _should_keep(self, record: Dict) -> bool:
        """Determine if record should be kept based on analysis."""
        analysis = record.get("_file_analysis", {})

        # Exclude if ONLY genomics files (no imaging)
        if analysis.get("has_genomics_only"):
            return False

        # Keep if has imaging files
        if analysis.get("has_imaging_files"):
            return True

        # Keep if has dataset links (even without files)
        if record.get("_dataset_links"):
            return True

        # Keep if has potential data weblinks
        weblinks = record.get("_weblinks", [])
        if any(
            l.get("type") in ["data_platform", "archive_download", "direct_file"]
            for l in weblinks
        ):
            return True

        # Keep if has archives (might contain imaging data)
        if analysis.get("has_archives"):
            return True

        return False

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
# SEARCH TERMS
# =============================================================================

PRIORITY_SEARCH_TERMS = [
    # Most specific imaging terms
    "retinal OCT",
    "fundus photography",
    "optical coherence tomography eye",
    "retinal imaging dataset",
    "fundus image dataset",
    "OCT dataset",
    "diabetic retinopathy dataset",
    "glaucoma dataset",
    "AMD dataset",
    "retinal vessel segmentation",
    "optic disc detection",
    "macular OCT",
    "RNFL OCT",
    "OCT-A retina",
    # Disease-specific imaging
    "diabetic retinopathy fundus",
    "glaucoma OCT",
    "macular degeneration imaging",
    "choroidal neovascularization OCT",
    "macular edema OCT",
    # Anatomy-specific
    "retinal layer segmentation",
    "optic nerve head imaging",
    "foveal OCT",
    "macula imaging",
    "choroidal imaging",
    # General ophthalmology data
    "ophthalmic imaging",
    "eye imaging data",
    "ophthalmology dataset",
    "retina scan",
    "eye scan dataset",
    "ocular imaging",
    # Equipment-specific
    "Spectralis OCT",
    "Cirrus OCT",
    "Topcon OCT",
    "Heidelberg retina",
    # Known datasets
    "DRIVE retinal",
    "STARE retinal",
    "MESSIDOR",
    "IDRiD",
    "REFUGE glaucoma",
    "CHASE_DB1",
    "EyePACS",
    "APTOS",
    # Cornea/anterior segment
    "corneal topography",
    "slit lamp imaging",
    "anterior segment OCT",
    "meibography",
    "corneal imaging dataset",
]


def run_scrape(
    output_dir: Path,
    datasets_only: bool = True,
    inspect_zips: bool = True,
    max_per_query: int = 500,
) -> List[Dict]:
    """
    Run full scrape with ZIP inspection and link detection.
    """
    logger.info("=" * 70)
    logger.info("ENVISION Zenodo Scraper")
    logger.info("=" * 70)
    logger.info(f"Output: {output_dir}")
    logger.info(f"Datasets only: {datasets_only}")
    logger.info(f"ZIP inspection: {inspect_zips}")
    logger.info(f"Search terms: {len(PRIORITY_SEARCH_TERMS)}")

    scraper = ZenodoScraper(output_dir)
    all_records = []

    for i, term in enumerate(PRIORITY_SEARCH_TERMS, 1):
        logger.info(f"\n[{i}/{len(PRIORITY_SEARCH_TERMS)}] Searching: '{term}'")

        results = scraper.search(
            term,
            max_results=max_per_query,
            datasets_only=datasets_only,
            inspect_zips=inspect_zips,
        )

        all_records.extend(results)
        logger.info(
            f"  Found {len(results)} matching datasets (total: {len(all_records)})"
        )

        # Pause between search terms to avoid rate limiting
        time.sleep(3.0)

    # Save summary
    summary = {
        "timestamp": datetime.now().isoformat(),
        "stats": scraper.stats,
        "total_records": len(all_records),
        "search_terms_used": len(PRIORITY_SEARCH_TERMS),
    }

    with open(output_dir / "scrape_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    scraper.print_stats()

    return all_records


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="ENVISION Zenodo Scraper")
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path(
            "/home/joneill/Nextcloud/vaults/jmind/calmi2/envision-discovery/data"
        ),
        help="Output directory for scraped data",
    )
    parser.add_argument(
        "--all-types",
        action="store_true",
        help="Include all resource types, not just datasets",
    )
    parser.add_argument(
        "--no-zip-inspect",
        action="store_true",
        help="Skip ZIP content inspection (faster but less info)",
    )
    parser.add_argument(
        "--max-per-query", type=int, default=500, help="Maximum results per search term"
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
