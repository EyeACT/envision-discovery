"""
ENVISION Discovery: Multi-Source Scrapers

Provides scrapers for Figshare, Dryad, OSF, DataCite, Kaggle, and NEI,
all outputting DatasetMetadata instances.
"""

from .figshare import FigshareScraper
from .dryad import DryadScraper
from .osf import OSFScraper
from .datacite import DataCiteScraper
from .kaggle import KaggleScraper
from .nei import NEIScraper

__all__ = [
    "FigshareScraper",
    "DryadScraper",
    "OSFScraper",
    "DataCiteScraper",
    "KaggleScraper",
    "NEIScraper",
]
