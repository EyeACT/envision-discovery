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

        if filename.endswith(".zip"):
            analysis["has_archives"] = True
            analysis["archive_count"] += 1
            analysis["total_archive_size"] += size

            download_url = f.get("links", {}).get("self")
            if download_url:
                try:
                    zip_contents = ZipInspector.inspect_via_range(download_url, session)
                    if zip_contents:
                        summary = ZipInspector.summarize_contents(zip_contents)
                        analysis["zip_contents"][filename] = summary

                        if summary.get("imaging_file_count", 0) > 0:
                            imaging_found = True
                            analysis["zip_imaging_files"].extend(
                                summary.get("sample_imaging_files", [])
                            )
                        if summary.get("genomics_file_count", 0) > 0:
                            genomics_found = True
                            analysis["zip_genomics_files"].extend(
                                summary.get("sample_genomics_files", [])
                            )
                except Exception as e:
                    logger.debug(f"Could not inspect ZIP {filename}: {e}")

        elif any(filename.endswith(ext) for ext in ARCHIVE_EXTS):
            analysis["has_archives"] = True
            analysis["archive_count"] += 1
            analysis["total_archive_size"] += size

    analysis["has_imaging_files"] = imaging_found
    analysis["has_genomics_only"] = genomics_found and not imaging_found

    return analysis


# =============================================================================
# ZENODO SCRAPER
# =============================================================================

SEARCH_TERMS = [
    # Imaging modalities
    "retinal OCT", "fundus photography", "optical coherence tomography eye",
    "retinal imaging dataset", "fundus image dataset", "OCT dataset",
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


class ZenodoScraper:
    """Scrape Zenodo for eye imaging datasets with ZIP inspection."""

    SEARCH_URL = "https://zenodo.org/api/records/"

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
        }

    def search(
        self,
        query: str,
        max_results: int = 1000,
        datasets_only: bool = True,
        inspect_zips: bool = True,
    ) -> List[Dict]:
        """Search Zenodo, enrich records, and filter for eye imaging datasets."""
        records = []
        page = 1
        per_page = 25

        while len(records) < max_results:
            full_query = query
            if datasets_only:
                full_query = f"({query}) AND resource_type.type:dataset"

            params = {"q": full_query, "page": page, "size": per_page}

            try:
                for attempt in range(3):
                    response = self.session.get(
                        self.SEARCH_URL, params=params, timeout=30
                    )
                    if response.status_code == 429:
                        wait = 5 * (2 ** attempt)
                        logger.warning(f"Rate limited, waiting {wait}s")
                        time.sleep(wait)
                        continue
                    response.raise_for_status()
                    break
                else:
                    logger.warning(f"Max retries exceeded for '{query}'")
                    break

                hits = response.json().get("hits", {}).get("hits", [])
                if not hits:
                    break

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

                page += 1
                time.sleep(2.0)

                if len(hits) < per_page:
                    break

            except Exception as e:
                logger.warning(f"Search error for '{query}': {e}")
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
        analysis = record.get("_file_analysis", {})

        if analysis.get("has_genomics_only"):
            return False
        if analysis.get("has_imaging_files"):
            return True
        if record.get("_dataset_links"):
            return True

        weblinks = record.get("_weblinks", [])
        if any(
            l.get("type") in ["data_platform", "archive_download", "direct_file"]
            for l in weblinks
        ):
            return True

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

    for i, term in enumerate(SEARCH_TERMS, 1):
        logger.info(f"\n[{i}/{len(SEARCH_TERMS)}] Searching: '{term}'")

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
        time.sleep(3.0)

    summary = {
        "timestamp": datetime.now().isoformat(),
        "stats": scraper.stats,
        "total_records": len(all_records),
        "search_terms_used": len(SEARCH_TERMS),
    }
    with open(output_dir / "scrape_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    scraper.print_stats()
    return all_records


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
