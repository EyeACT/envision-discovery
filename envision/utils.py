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
    max_error_retries: int = 6,
    failures: Optional[list] = None,
    **kwargs,
) -> Optional[requests.Response]:
    """Make an HTTP request with exponential backoff on rate limits and errors.

    Two retry budgets:

    - 429 (rate limited) is retried with backoff, honouring Retry-After.
      max_retries bounds the total attempts; 0 means unlimited, so a long
      rate-limit window is waited out instead of dropping data.
    - 403, 5xx, timeouts and connection errors are retried at most
      max_error_retries times. These can be permanent (a restricted file,
      a query the server always fails on), and retrying them forever used
      to hang a whole scrape on one bad request.

    Any request that ends without a 200 (a non-retryable 4xx, or an
    exhausted budget) is logged at WARNING and, when a ``failures`` list is
    passed, appended to it as a dict so callers can report what was missed
    instead of treating it as "no results".

    Args:
        session: requests.Session to use.
        method: HTTP method ("get" or "post").
        url: Request URL.
        max_retries: Maximum total attempts. 0 = unlimited for 429.
        base_delay: Initial delay in seconds.
        max_delay: Maximum delay cap in seconds.
        max_error_retries: Retries for 403/5xx/network errors (0 = unlimited).
        failures: Optional list that receives one dict per failed request.
        **kwargs: Passed to session.request (params, json, timeout, etc.)

    Returns:
        Response object, or None if the request failed.
    """
    kwargs.setdefault("timeout", 30)

    attempt = 0
    error_attempts = 0
    tries = 0
    last_status = None
    last_error = ""

    def _delay(n: int) -> float:
        return min(base_delay * (2 ** n), max_delay)

    while True:
        if max_retries > 0 and attempt >= max_retries:
            break
        if max_error_retries > 0 and error_attempts > max_error_retries:
            break
        try:
            tries += 1
            response = session.request(method, url, **kwargs)
            last_status = response.status_code

            if response.status_code == 200:
                return response

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                try:
                    delay = min(float(retry_after), max_delay) if retry_after else _delay(attempt)
                except ValueError:
                    delay = _delay(attempt)
                logger.warning(
                    f"Rate limited (429), waiting {delay:.0f}s (attempt {attempt + 1})"
                )
                time.sleep(delay)
                attempt += 1
                continue

            if response.status_code == 403 or response.status_code >= 500:
                delay = _delay(error_attempts)
                last_error = response.text[:200]
                logger.warning(
                    f"HTTP {response.status_code} on {url}, retrying in {delay:.0f}s "
                    f"(error attempt {error_attempts + 1})"
                )
                time.sleep(delay)
                attempt += 1
                error_attempts += 1
                continue

            # Other 4xx client errors are not retryable
            last_error = response.text[:200]
            break

        except requests.exceptions.RequestException as e:
            delay = _delay(error_attempts)
            last_status = None
            last_error = f"{type(e).__name__}: {e}"[:200]
            logger.warning(
                f"{type(e).__name__} on {url}, retrying in {delay:.0f}s "
                f"(error attempt {error_attempts + 1})"
            )
            time.sleep(delay)
            attempt += 1
            error_attempts += 1

    logger.warning(
        f"Request failed after {tries} attempt(s): {url} "
        f"params={kwargs.get('params')} status={last_status} {last_error[:120]}"
    )
    if failures is not None:
        failures.append({
            "url": url,
            "params": kwargs.get("params"),
            "status": last_status,
            "error": last_error,
            "attempts": tries,
        })
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

        Downloads the last max_bytes of the file. When the central directory
        is larger than that (archives with thousands of members, which is
        exactly what image datasets look like), the end-of-central-directory
        record in the tail gives the directory's offset and size, and a
        second Range request fetches the whole directory (up to
        max_cd_bytes). Before this, any ZIP with a directory over 64 KB
        was reported as uninspectable.
        """
        try:
            # Get file size
            head = ArchiveInspector._call(session.head, url, timeout=15, allow_redirects=True)
            if head.status_code != 200:
                return None

            size = int(head.headers.get("Content-Length", 0))
            if size == 0:
                return None

            tail = ArchiveInspector._range_get(url, session, max(0, size - max_bytes), size - 1)
            if tail is None:
                return None

            names = ArchiveInspector._zip_names(tail)
            if names is not None:
                return names

            cd = ArchiveInspector._central_directory_span(tail)
            if cd is None:
                return None
            cd_offset, cd_size = cd
            if cd_size > ArchiveInspector.max_cd_bytes or cd_offset >= size:
                logger.info(f"ZIP central directory too large ({cd_size} bytes) for {url}")
                return None
            full = ArchiveInspector._range_get(url, session, cd_offset, size - 1)
            if full is None:
                return None
            return ArchiveInspector._zip_names(full)

        except Exception as e:
            logger.debug(f"ZIP inspect failed for {url}: {e}")
            return None

    # Largest central directory fetched by the second Range request.
    max_cd_bytes = 64 * 1024 * 1024

    # HEAD and Range requests are retried on these (a rate-limited or
    # briefly failing file server). Before, one such answer made the archive
    # look unlistable: in the September gap-fill build 35 of the 44 ZIPs of
    # one record went unlisted and listed fine when asked again later.
    RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
    max_tries = 5
    max_retry_delay = 120.0

    @staticmethod
    def _call(fn, url, **kwargs):
        """``fn(url, **kwargs)`` (session.head or session.get) with retries on
        RETRY_STATUSES, honouring Retry-After. Returns the last response."""
        tries = ArchiveInspector.max_tries
        for n in range(tries):
            resp = fn(url, **kwargs)
            if resp.status_code not in ArchiveInspector.RETRY_STATUSES or n == tries - 1:
                return resp
            try:
                delay = float(resp.headers.get("Retry-After") or 2.0 * 2 ** n)
            except ValueError:
                delay = 2.0 * 2 ** n
            delay = min(delay, ArchiveInspector.max_retry_delay)
            try:
                resp.close()
            except Exception:
                pass
            logger.info(f"Archive request got {resp.status_code}, retrying in {delay:.0f}s: {url}")
            time.sleep(delay)
        return resp

    @staticmethod
    def _range_get(url: str, session: requests.Session, start: int, end: int) -> Optional[bytes]:
        """GET bytes start..end inclusive; None unless the server honours Range."""
        resp = ArchiveInspector._call(session.get, url, headers={"Range": f"bytes={start}-{end}"},
                                      timeout=60, stream=True)
        try:
            if resp.status_code == 206 or (resp.status_code == 200 and start == 0):
                return resp.content
            return None
        finally:
            resp.close()

    @staticmethod
    def _zip_names(data: bytes) -> Optional[List[str]]:
        """List member names from a buffer that ends with a ZIP central directory."""
        try:
            zf = zipfile.ZipFile(io.BytesIO(data))
            return [info.filename for info in zf.infolist() if not info.is_dir()]
        except Exception:
            return None

    @staticmethod
    def _central_directory_span(tail: bytes) -> Optional[tuple]:
        """(offset, size) of the central directory from the EOCD in a file tail.

        Handles ZIP64 archives, whose 32-bit EOCD fields are 0xFFFFFFFF and
        whose real values live in the ZIP64 end record.
        """
        eocd = tail.rfind(b"PK\x05\x06")
        if eocd == -1 or eocd + 22 > len(tail):
            return None
        cd_size, cd_offset = struct.unpack("<II", tail[eocd + 12:eocd + 20])
        if cd_offset == 0xFFFFFFFF or cd_size == 0xFFFFFFFF:
            z64 = tail.rfind(b"PK\x06\x06", 0, eocd)
            if z64 == -1 or z64 + 56 > len(tail):
                return None
            cd_size, cd_offset = struct.unpack("<QQ", tail[z64 + 40:z64 + 56])
        return cd_offset, cd_size

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
            resp = ArchiveInspector._call(
                session.get,
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
        file_types: Dict[str, int] = {}

        for fname in filenames:
            lower = fname.lower()
            base = lower.rsplit("/", 1)[-1]
            ext = "." + base.rsplit(".", 1)[-1] if "." in base else ""

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

            if ext:
                file_types[ext] = file_types.get(ext, 0) + 1

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
            # extension -> member count over ALL members, not just imaging
            "file_types": dict(sorted(file_types.items(), key=lambda kv: -kv[1])),
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
        # One entry per date slice that could not be fully collected:
        # {"query", "start", "end", "count", "status": "error"|"capped"}
        self.problems: List[Dict] = []

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
        if count is None:
            # The count request failed. Returning [] here used to drop the
            # whole slice silently; record it so the run report shows it.
            logger.warning(f"  Count failed for {start_date} to {end_date}, slice skipped")
            self.problems.append({"query": query, "start": start_date, "end": end_date,
                                  "count": None, "status": "error"})
            return []
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
            self.problems.append({"query": query, "start": start_date, "end": end_date,
                                  "count": count, "status": "capped"})
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
