"""
ENVISION Discovery: Unified Dataset Metadata

Provides a source-agnostic DatasetMetadata dataclass for representing
dataset records from Zenodo, Figshare, Dryad, OSF, DataCite, etc.
"""

from __future__ import annotations

from dataclasses import dataclass, field


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
