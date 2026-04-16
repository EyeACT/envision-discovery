"""
ENVISION Discovery: Unified Dataset Metadata

Provides a source-agnostic DatasetMetadata dataclass for representing
dataset records from Zenodo, Figshare, Dryad, OSF, DataCite, etc.

Every scraper saves per-record JSON files to data/metadata/{source}/.
This module handles serialization, deserialization, and resume.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class DatasetMetadata:
    """Source-agnostic dataset metadata for classification and ADDF export.

    This dataclass normalizes metadata from multiple repository APIs into
    a common structure used by the classifier and ADDF exporter.
    """

    # Identity
    source: str  # "zenodo", "figshare", "dryad", "osf", "datacite"
    source_id: str
    doi: str | None = None
    url: str = ""

    # Text for classification
    title: str = ""
    description: str = ""  # HTML-stripped
    keywords: list[str] = field(default_factory=list)

    # File inventory
    file_names: list[str] = field(default_factory=list)
    file_types: set[str] = field(default_factory=set)
    file_count: int = 0
    total_size_bytes: int = 0
    img_count: int = 0
    medical_count: int = 0
    archive_count: int = 0
    genomics_count: int = 0
    zip_contents: list[str] = field(default_factory=list)

    # Downloadable file manifest. Each entry:
    #   {"name": str, "size_bytes": int, "url": str,
    #    "file_id": str | None, "checksum": str | None}
    # Populated by scrapers when the source API exposes direct download links.
    # Consumed by envision.downloader when --download is passed.
    files: list[dict] = field(default_factory=list)

    # Access & rights
    access_type: str | None = None
    license: str | None = None

    # Provenance
    creators: list[dict] = field(default_factory=list)
    publication_year: str | None = None
    dates: list[dict] = field(default_factory=list)

    # Links
    related_identifiers: list[dict] = field(default_factory=list)
    external_links: list[str] = field(default_factory=list)

    def to_classifier_text(self) -> str:
        """Compose text for classification (title + description + keywords)."""
        parts = [self.title, self.description]
        if self.keywords:
            parts.append(" ".join(self.keywords))
        return " ".join(p for p in parts if p).strip()

    @property
    def size_mb(self) -> float:
        """Total size in megabytes."""
        return round(self.total_size_bytes / (1024 * 1024), 1)

    def save(self, metadata_dir: Path):
        """Save this record as JSON to metadata_dir/{source_id}.json."""
        metadata_dir.mkdir(parents=True, exist_ok=True)
        safe_id = str(self.source_id).replace("/", "_")
        path = metadata_dir / f"{safe_id}.json"
        d = asdict(self)
        d["file_types"] = sorted(d["file_types"])  # set → list for JSON
        with open(path, "w") as f:
            json.dump(d, f, indent=2)

    @classmethod
    def load(cls, path: Path) -> DatasetMetadata:
        """Load a DatasetMetadata from a JSON file."""
        with open(path) as f:
            d = json.load(f)
        d["file_types"] = set(d.get("file_types", []))
        return cls(**d)

    @staticmethod
    def load_dir(metadata_dir: Path) -> list[DatasetMetadata]:
        """Load all records from a metadata directory."""
        records = []
        if not metadata_dir.exists():
            return records
        for jf in sorted(metadata_dir.glob("*.json")):
            try:
                records.append(DatasetMetadata.load(jf))
            except Exception as e:
                logger.warning(f"Failed to load {jf}: {e}")
        return records

    @staticmethod
    def existing_ids(metadata_dir: Path) -> set[str]:
        """Get source_ids of already-scraped records for resume."""
        ids = set()
        if not metadata_dir.exists():
            return ids
        for jf in metadata_dir.glob("*.json"):
            ids.add(jf.stem)
        return ids
