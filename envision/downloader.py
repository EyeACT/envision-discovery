"""
ENVISION Discovery: File Downloader

Downloads raw data files for records classified as EYE_IMAGING.

Gate: only files attached to records with label == EYE_IMAGING and
confidence >= threshold are fetched. This is enforced by selecting
from results/{source}_eye_imaging.json.

Layout:
    data/downloads/{source}/{source_id}/{filename}
    data/downloads/{source}/{source_id}/manifest.json
    data/downloads/{source}/_download_log.jsonl   (append-only)

Resume: files already on disk with matching size are skipped. Partial
downloads (.part suffix) are resumed if the server honours Range.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import requests

from .metadata import DatasetMetadata

logger = logging.getLogger(__name__)

CHUNK_SIZE = 1024 * 1024  # 1 MiB
REQUEST_TIMEOUT = (30, 300)  # (connect, read) seconds
MAX_RETRIES = 5


@dataclass
class DownloadStats:
    records_attempted: int = 0
    files_downloaded: int = 0
    files_skipped: int = 0
    files_failed: int = 0
    total_bytes: int = 0


def _safe_filename(name: str) -> str:
    """Strip path separators and nulls; keep the basename only."""
    name = name.replace("\x00", "").strip()
    name = name.replace("\\", "/").split("/")[-1]
    return name or "unnamed"


def _safe_id(source_id: str) -> str:
    return str(source_id).replace("/", "_")


def _log_event(log_path: Path, event: dict):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    event = {"ts": datetime.utcnow().isoformat() + "Z", **event}
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


def _stream_download(
    url: str,
    dest: Path,
    expected_size: int | None,
    session: requests.Session,
) -> tuple[bool, int, str | None]:
    """Stream a URL to dest with resume + retries. Returns (ok, bytes_written, error)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")

    # Skip if already complete
    if dest.exists():
        actual = dest.stat().st_size
        if expected_size in (None, 0) or actual == expected_size:
            return True, 0, "exists"
        logger.warning(f"Size mismatch for {dest.name}: {actual} vs expected {expected_size}; redownloading")
        dest.unlink()

    for attempt in range(1, MAX_RETRIES + 1):
        resume_from = part.stat().st_size if part.exists() else 0
        headers = {"Range": f"bytes={resume_from}-"} if resume_from else {}

        try:
            with session.get(url, stream=True, timeout=REQUEST_TIMEOUT, headers=headers) as r:
                if resume_from and r.status_code == 200:
                    # Server ignored Range; restart from scratch
                    part.unlink(missing_ok=True)
                    resume_from = 0
                elif r.status_code not in (200, 206):
                    err = f"HTTP {r.status_code}"
                    if attempt == MAX_RETRIES:
                        return False, 0, err
                    time.sleep(min(2 ** attempt, 60))
                    continue

                mode = "ab" if resume_from else "wb"
                bytes_written = resume_from
                with open(part, mode) as f:
                    for chunk in r.iter_content(chunk_size=CHUNK_SIZE):
                        if not chunk:
                            continue
                        f.write(chunk)
                        bytes_written += len(chunk)

            # Verify size if we know it
            if expected_size and bytes_written != expected_size:
                err = f"short read: got {bytes_written}, expected {expected_size}"
                if attempt == MAX_RETRIES:
                    return False, bytes_written, err
                time.sleep(min(2 ** attempt, 60))
                continue

            part.rename(dest)
            return True, bytes_written - resume_from, None

        except requests.RequestException as e:
            if attempt == MAX_RETRIES:
                return False, 0, str(e)
            time.sleep(min(2 ** attempt, 60))

    return False, 0, "exceeded retries"


def run_download(
    source: str,
    metadata_records: list[DatasetMetadata],
    eye_imaging_results: list[dict],
    download_dir: Path | str,
    confidence_threshold: float = 0.80,
    session: requests.Session | None = None,
) -> DownloadStats:
    """Download files for EYE_IMAGING records above threshold.

    Args:
        source: Source name (e.g. "zenodo"). Used for directory layout and logs.
        metadata_records: DatasetMetadata records (with files populated) for this source.
        eye_imaging_results: Entries from results/{source}_eye_imaging.json. Used as
            the classification gate: only records present here (with confidence >=
            threshold) are downloaded.
        download_dir: Base directory. Files land under {download_dir}/{source}/{source_id}/.
        confidence_threshold: Minimum EYE_IMAGING confidence required (default 0.80).
        session: Optional requests.Session (one is created if omitted).

    Returns:
        DownloadStats with aggregate counts.
    """
    download_dir = Path(download_dir)
    source_dir = download_dir / source
    source_dir.mkdir(parents=True, exist_ok=True)
    log_path = source_dir / "_download_log.jsonl"

    session = session or requests.Session()
    session.headers.setdefault("User-Agent", "envision-discovery/0.1 downloader")

    # Build lookup: source_id -> DatasetMetadata
    by_id = {str(m.source_id): m for m in metadata_records}

    # Select records that pass the gate
    selected = [
        r for r in eye_imaging_results
        if r.get("label") == "EYE_IMAGING"
        and r.get("prob_eye_imaging", r.get("confidence", 0)) >= confidence_threshold
    ]

    print(f"\n  Download gate: {len(selected):,}/{len(eye_imaging_results):,} "
          f"records pass confidence >= {confidence_threshold}", flush=True)
    if not selected:
        return DownloadStats()

    stats = DownloadStats()
    stats.records_attempted = len(selected)

    for i, result in enumerate(selected, 1):
        source_id = str(result.get("source_id", ""))
        meta = by_id.get(source_id)
        if meta is None:
            print(f"  [{i}/{len(selected)}] {source_id}: metadata missing on disk, skipping", flush=True)
            _log_event(log_path, {"source_id": source_id, "event": "metadata_missing"})
            continue

        files = meta.files or []
        if not files:
            print(f"  [{i}/{len(selected)}] {source_id}: no downloadable files in metadata", flush=True)
            _log_event(log_path, {"source_id": source_id, "event": "no_files"})
            continue

        record_dir = source_dir / _safe_id(source_id)
        record_dir.mkdir(parents=True, exist_ok=True)

        total = sum(f.get("size_bytes") or 0 for f in files)
        size_gb = total / (1024**3)
        print(f"  [{i}/{len(selected)}] {source_id}: {len(files)} file(s), "
              f"{size_gb:.2f} GB  conf={result.get('prob_eye_imaging', 0):.3f}", flush=True)

        manifest_entries = []
        for f in files:
            name = _safe_filename(f.get("name", ""))
            url = f.get("url", "")
            expected = f.get("size_bytes") or None
            dest = record_dir / name

            if not url:
                _log_event(log_path, {"source_id": source_id, "file": name, "event": "no_url"})
                stats.files_failed += 1
                continue

            t0 = time.time()
            ok, written, status = _stream_download(url, dest, expected, session)
            elapsed = time.time() - t0

            entry = {
                "name": name,
                "url": url,
                "size_bytes": dest.stat().st_size if dest.exists() else 0,
                "expected_size_bytes": expected,
                "checksum_source": f.get("checksum"),
                "file_id": f.get("file_id"),
                "status": status if status else ("downloaded" if ok else "failed"),
                "elapsed_s": round(elapsed, 1),
            }
            manifest_entries.append(entry)

            _log_event(log_path, {
                "source_id": source_id, "file": name,
                "event": entry["status"], "bytes": written,
                "elapsed_s": entry["elapsed_s"],
            })

            if ok:
                if status == "exists":
                    stats.files_skipped += 1
                else:
                    stats.files_downloaded += 1
                    stats.total_bytes += written
                mb = dest.stat().st_size / (1024**2)
                print(f"      {'✓' if status != 'exists' else '·'} {name} ({mb:,.1f} MB, {elapsed:.1f}s)", flush=True)
            else:
                stats.files_failed += 1
                print(f"      ✗ {name}: {status}", flush=True)

        # Per-record manifest
        manifest_path = record_dir / "manifest.json"
        manifest = {
            "source": source,
            "source_id": source_id,
            "doi": result.get("doi"),
            "url": result.get("url"),
            "title": result.get("title"),
            "prob_eye_imaging": result.get("prob_eye_imaging"),
            "confidence_threshold": confidence_threshold,
            "downloaded_at": datetime.utcnow().isoformat() + "Z",
            "files": manifest_entries,
        }
        with open(manifest_path, "w", encoding="utf-8") as mf:
            json.dump(manifest, mf, indent=2)

    # Final summary line to log
    _log_event(log_path, {
        "event": "run_complete", "source": source,
        "records_attempted": stats.records_attempted,
        "files_downloaded": stats.files_downloaded,
        "files_skipped": stats.files_skipped,
        "files_failed": stats.files_failed,
        "total_bytes": stats.total_bytes,
    })

    total_gb = stats.total_bytes / (1024**3)
    print(
        f"\n  Download summary [{source}]: "
        f"{stats.files_downloaded} new, {stats.files_skipped} existing, "
        f"{stats.files_failed} failed ({total_gb:.2f} GB written)",
        flush=True,
    )
    return stats
