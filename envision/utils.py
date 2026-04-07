"""
ENVISION Discovery: Shared Utilities

Exponential backoff, archive inspection, rate-limit-aware HTTP helpers,
and dynamic pagination used across all repository scrapers.
"""

import io
import logging
import math
import struct
import tarfile
import time
import zipfile
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

# ============================================================
# File type constants
# ============================================================

EYE_IMAGING_EXTS = {
    ".dcm", ".dicom", ".nii", ".nii.gz",
    ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp",
    ".gif", ".svg", ".webp",
    ".mat", ".h5", ".hdf5", ".npy", ".npz",
    ".mha", ".mhd", ".nrrd",
    ".e2e", ".fds", ".fda", ".oct", ".img",
}

GENOMICS_EXTS = {
    ".fasta", ".fa", ".fna", ".ffn", ".faa", ".frn",
    ".fastq", ".fq", ".fastq.gz", ".fq.gz",
    ".bam", ".sam", ".cram",
    ".vcf", ".bcf", ".vcf.gz",
    ".h5ad", ".loom", ".mtx",
    ".bed", ".bedgraph", ".bigwig", ".bw", ".wig",
    ".gff", ".gff3", ".gtf",
}

ARCHIVE_EXTS = {".zip", ".tar", ".gz", ".tar.gz", ".rar", ".7z", ".tgz"}


# ============================================================
# Exponential backoff HTTP request
# ============================================================

def request_with_backoff(
    session: requests.Session,
    method: str,
    url: str,
    max_retries: int = 0,
    base_delay: float = 2.0,
    max_delay: float = 300.0,
    **kwargs,
) -> Optional[requests.Response]:
    """Make an HTTP request with exponential backoff on rate limits and errors.

    Retries indefinitely by default (max_retries=0 means unlimited).
    Handles 429, 403, 5xx responses and connection errors with increasing
    delays: base_delay * 2^attempt, capped at max_delay.

    Args:
        session: requests.Session to use.
        method: HTTP method ("get" or "post").
        url: Request URL.
        max_retries: Maximum retry attempts. 0 = unlimited (never give up).
        base_delay: Initial delay in seconds.
        max_delay: Maximum delay cap in seconds.
        **kwargs: Passed to session.request (params, json, timeout, etc.)

    Returns:
        Response object, or None if max_retries > 0 and all retries exhausted.
    """
    kwargs.setdefault("timeout", 30)

    attempt = 0
    while True:
        try:
            response = session.request(method, url, **kwargs)

            if response.status_code == 200:
                return response

            if response.status_code in (429, 403):
                retry_after = response.headers.get("Retry-After")
                if retry_after:
                    try:
                        delay = min(float(retry_after), max_delay)
                    except ValueError:
                        delay = min(base_delay * (2 ** attempt), max_delay)
                else:
                    delay = min(base_delay * (2 ** attempt), max_delay)

                logger.warning(
                    f"Rate limited ({response.status_code}), "
                    f"waiting {delay:.0f}s (attempt {attempt + 1})"
                )
                time.sleep(delay)
                attempt += 1
                if max_retries > 0 and attempt >= max_retries:
                    break
                continue

            if response.status_code >= 500:
                delay = min(base_delay * (2 ** attempt), max_delay)
                logger.warning(
                    f"Server error ({response.status_code}) on {url}, "
                    f"retrying in {delay:.0f}s (attempt {attempt + 1})"
                )
                time.sleep(delay)
                attempt += 1
                if max_retries > 0 and attempt >= max_retries:
                    break
                continue

            # Other non-200 status: return as-is (client error, not retryable)
            response.raise_for_status()
            return response

        except requests.exceptions.Timeout:
            delay = min(base_delay * (2 ** attempt), max_delay)
            logger.warning(
                f"Timeout on {url}, retrying in {delay:.0f}s (attempt {attempt + 1})"
            )
            time.sleep(delay)
            attempt += 1
            if max_retries > 0 and attempt >= max_retries:
                break

        except requests.exceptions.ConnectionError:
            delay = min(base_delay * (2 ** attempt), max_delay)
            logger.warning(
                f"Connection error on {url}, retrying in {delay:.0f}s (attempt {attempt + 1})"
            )
            time.sleep(delay)
            attempt += 1
            if max_retries > 0 and attempt >= max_retries:
                break

        except requests.exceptions.RequestException as e:
            delay = min(base_delay * (2 ** attempt), max_delay)
            logger.warning(f"Request error on {url}: {e}, retrying in {delay:.0f}s (attempt {attempt + 1})")
            time.sleep(delay)
            attempt += 1
            if max_retries > 0 and attempt >= max_retries:
                break

    if max_retries > 0:
        logger.error(f"All {max_retries} retries exhausted for {url}")
    return None


# ============================================================
# Archive inspection (ZIP + TAR via HTTP Range requests)
# ============================================================

class ArchiveInspector:
    """Inspect archive contents without downloading the full file.

    Supports:
    - ZIP files via HTTP Range requests (reads central directory at end of file)
    - TAR.GZ files via partial download (first/last N bytes)
    - Plain TAR files via Range requests
    """

    @staticmethod
    def inspect_zip_via_range(
        url: str, session: requests.Session, max_bytes: int = 65536
    ) -> Optional[List[str]]:
        """Read ZIP central directory via HTTP Range request.

        Downloads only the last max_bytes of the file to extract the
        file listing from the ZIP central directory.
        """
        try:
            # Get file size
            head = session.head(url, timeout=15, allow_redirects=True)
            if head.status_code != 200:
                return None

            size = int(head.headers.get("Content-Length", 0))
            if size == 0:
                return None

            # Download last N bytes (where central directory lives)
            start = max(0, size - max_bytes)
            resp = session.get(
                url,
                headers={"Range": f"bytes={start}-{size - 1}"},
                timeout=30,
            )

            if resp.status_code not in (200, 206):
                return None

            try:
                zf = zipfile.ZipFile(io.BytesIO(resp.content))
                return [info.filename for info in zf.infolist() if not info.is_dir()]
            except (zipfile.BadZipFile, Exception):
                return None

        except Exception as e:
            logger.debug(f"ZIP inspect failed for {url}: {e}")
            return None

    @staticmethod
    def inspect_tar_via_range(
        url: str, session: requests.Session, max_bytes: int = 131072
    ) -> Optional[List[str]]:
        """Inspect tar/tar.gz contents by downloading first max_bytes.

        For .tar.gz, the file listing is at the beginning of the archive
        after decompression, so we download the first N bytes and try to
        parse the tar header entries.
        """
        try:
            # Download first N bytes
            resp = session.get(
                url,
                headers={"Range": f"bytes=0-{max_bytes - 1}"},
                timeout=30,
            )

            if resp.status_code not in (200, 206):
                return None

            content = io.BytesIO(resp.content)
            filenames = []

            try:
                # Try as gzipped tar first
                import gzip
                try:
                    decompressed = gzip.GzipFile(fileobj=content)
                    tf = tarfile.open(fileobj=decompressed, mode="r|")
                except Exception:
                    content.seek(0)
                    tf = tarfile.open(fileobj=content, mode="r|")

                for member in tf:
                    if member.isfile():
                        filenames.append(member.name)
                    if len(filenames) > 500:
                        break  # enough to characterize the archive

            except (tarfile.TarError, EOFError, Exception):
                pass  # partial download, expected to hit EOF

            return filenames if filenames else None

        except Exception as e:
            logger.debug(f"TAR inspect failed for {url}: {e}")
            return None

    @classmethod
    def inspect_archive(
        cls, url: str, filename: str, session: requests.Session
    ) -> Optional[List[str]]:
        """Inspect any supported archive format by URL and filename."""
        lower = filename.lower()

        if lower.endswith(".zip"):
            return cls.inspect_zip_via_range(url, session)
        elif lower.endswith((".tar.gz", ".tgz")):
            return cls.inspect_tar_via_range(url, session)
        elif lower.endswith(".tar"):
            return cls.inspect_tar_via_range(url, session)

        return None

    @staticmethod
    def summarize_contents(filenames: List[str]) -> Dict:
        """Summarize archive contents by file type."""
        imaging_count = 0
        genomics_count = 0
        other_count = 0
        imaging_files = []
        genomics_files = []

        for fname in filenames:
            lower = fname.lower()
            ext = "." + lower.rsplit(".", 1)[-1] if "." in lower else ""

            # Check compound extensions
            if lower.endswith(".nii.gz"):
                ext = ".nii.gz"
            elif lower.endswith(".tar.gz"):
                ext = ".tar.gz"
            elif lower.endswith(".fastq.gz"):
                ext = ".fastq.gz"
            elif lower.endswith(".fq.gz"):
                ext = ".fq.gz"
            elif lower.endswith(".vcf.gz"):
                ext = ".vcf.gz"

            if ext in EYE_IMAGING_EXTS:
                imaging_count += 1
                imaging_files.append(fname)
            elif ext in GENOMICS_EXTS:
                genomics_count += 1
                genomics_files.append(fname)
            else:
                other_count += 1

        return {
            "total_files": len(filenames),
            "imaging_file_count": imaging_count,
            "genomics_file_count": genomics_count,
            "other_file_count": other_count,
            "imaging_files": imaging_files[:20],
            "genomics_files": genomics_files[:10],
        }


# ============================================================
# Dynamic pagination with date-range subdivision
# ============================================================

class PaginatedSearch:
    """Dynamic pagination that subdivides date ranges when results exceed API caps.

    Inspired by the PubMed 9999-record cap workaround: when a query returns
    more results than the API can paginate through, split the date range
    into proportional intervals and recurse.

    Works with any API that supports date-range filtering and returns a total
    result count.

    Usage:
        paginator = PaginatedSearch(
            count_fn=my_count_function,    # (query, start, end) -> int
            fetch_fn=my_fetch_function,    # (query, start, end, max_results) -> list
            api_max=10000,                 # max results the API can return
        )
        all_results = paginator.search("retinal OCT", "2010-01-01", "2026-12-31")
    """

    def __init__(
        self,
        count_fn: Callable,
        fetch_fn: Callable,
        api_max: int = 10000,
        date_format: str = "%Y-%m-%d",
    ):
        """
        Args:
            count_fn: Callable(query, start_date, end_date) -> int
                Returns the total number of results for a query in a date range.
            fetch_fn: Callable(query, start_date, end_date, max_results) -> list
                Returns results for a query in a date range, up to max_results.
            api_max: Maximum results the API can return per query.
            date_format: Date string format used by the API.
        """
        self.count_fn = count_fn
        self.fetch_fn = fetch_fn
        self.api_max = api_max
        self.date_format = date_format

    def search(
        self, query: str, start_date: str, end_date: str, seen: set = None
    ) -> list:
        """Search with automatic date-range subdivision if needed.

        Args:
            query: Search query string.
            start_date: Start of date range (inclusive).
            end_date: End of date range (inclusive).
            seen: Set of already-seen IDs for deduplication.

        Returns:
            List of all results across subdivided ranges.
        """
        if seen is None:
            seen = set()

        count = self.count_fn(query, start_date, end_date)
        if count == 0:
            return []

        logger.info(
            f"  Date range {start_date} to {end_date}: {count} results"
        )

        # If count fits within API cap, fetch normally
        if count <= self.api_max:
            results = self.fetch_fn(query, start_date, end_date, self.api_max)
            # Deduplicate
            new_results = []
            for r in results:
                rid = self._get_id(r)
                if rid and rid not in seen:
                    seen.add(rid)
                    new_results.append(r)
            return new_results

        # Count exceeds cap — subdivide date range proportionally
        intervals = math.ceil(count / self.api_max)
        logger.info(
            f"  Count {count} exceeds cap {self.api_max}, "
            f"subdividing into {intervals} date slices"
        )

        sd = datetime.strptime(start_date, self.date_format).date()
        ed = datetime.strptime(end_date, self.date_format).date()
        total_days = (ed - sd).days + 1

        if total_days <= 1:
            # Can't subdivide further — just fetch what we can
            logger.warning(
                f"  Cannot subdivide single day with {count} results, "
                f"fetching first {self.api_max}"
            )
            results = self.fetch_fn(query, start_date, end_date, self.api_max)
            new_results = []
            for r in results:
                rid = self._get_id(r)
                if rid and rid not in seen:
                    seen.add(rid)
                    new_results.append(r)
            return new_results

        slice_days = max(1, math.ceil(total_days / intervals))
        all_results = []
        slice_start = sd

        while slice_start <= ed:
            slice_end = min(slice_start + timedelta(days=slice_days - 1), ed)
            s_str = slice_start.strftime(self.date_format)
            e_str = slice_end.strftime(self.date_format)

            # Recurse — the sub-slice may itself need further subdivision
            sub_results = self.search(query, s_str, e_str, seen)
            all_results.extend(sub_results)

            slice_start = slice_end + timedelta(days=1)

        return all_results

    @staticmethod
    def _get_id(record) -> Optional[str]:
        """Extract a unique ID from a record for deduplication."""
        if isinstance(record, dict):
            return str(
                record.get("id")
                or record.get("doi")
                or record.get("source_id")
                or record.get("identifier")
                or id(record)
            )
        return str(id(record))
