"""
ENVISION Discovery: Multi-Source Scrapers

Provides scrapers for Figshare, Dryad, OSF, and DataCite,
all outputting DatasetMetadata instances.
"""

from .figshare import FigshareScraper
from .dryad import DryadScraper
from .osf import OSFScraper
from .datacite import DataCiteScraper

__all__ = [
    "FigshareScraper",
    "DryadScraper",
    "OSFScraper",
    "DataCiteScraper",
]
