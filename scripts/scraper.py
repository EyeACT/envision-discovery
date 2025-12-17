#!/usr/bin/env python3
"""
ENVISION Zenodo Scraper
Collects eye imaging dataset metadata from Zenodo API.
"""

import json
import time
import requests
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# ============================================================
# SEARCH TERMS
# ============================================================

# Anatomy terms for wildcard combinations
BASE_ANATOMY = [
    "eye", "ophthalmic", "ocular", "retina", "retinal", "macula", "macular",
    "fovea", "foveal", "optic disc", "optic nerve head", "choroid", "choroidal",
    "cornea", "corneal", "anterior segment", "posterior segment", "vitreous",
    "lens", "iris", "sclera", "conjunctiva", "fundus"
]

# Data suffixes for wildcard patterns
DATA_SUFFIXES = ["imag*", "dataset", "data"]

# Generate wildcard combinations
WILDCARD_TERMS = [f"{base} {suffix}" for base in BASE_ANATOMY for suffix in DATA_SUFFIXES]

# Imaging modalities
IMAGING_MODALITIES = [
    "OCT", "optical coherence tomography", "fundus photography",
    "OCTA", "OCT angiography", "fluorescein angiography",
    "slit lamp", "corneal topography", "confocal microscopy",
    "scanning laser ophthalmoscopy", "adaptive optics"
]

# Eye diseases
DISEASES = [
    "diabetic retinopathy", "glaucoma", "macular degeneration", "AMD",
    "diabetic macular edema", "geographic atrophy", "drusen",
    "choroidal neovascularization", "keratoconus", "cataract"
]

# Equipment brands
EQUIPMENT = ["Zeiss", "Heidelberg", "Spectralis", "Cirrus", "Topcon", 
             "Maestro", "Triton", "Optos", "Nidek"]

# Benchmark datasets
BENCHMARKS = [
    "DRIVE dataset", "STARE dataset", "CHASE_DB1", "MESSIDOR",
    "IDRiD", "APTOS", "REFUGE", "RIM-ONE", "ORIGA", "EyePACS"
]

# Combine all search terms
SEARCH_TERMS = list(set(
    WILDCARD_TERMS + IMAGING_MODALITIES + DISEASES + EQUIPMENT + BENCHMARKS
))

# ============================================================
# SCRAPER CLASS
# ============================================================

class ZenodoScraper:
    """Scrapes metadata from Zenodo API."""
    
    BASE_URL = "https://zenodo.org/api/records"
    
    def __init__(self, output_dir: Path, max_results_per_term: int = 500):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.max_results = max_results_per_term
        self.session = requests.Session()
        self.scraped_ids = set()
        
    def search(self, query: str) -> list:
        """Search Zenodo for a query term."""
        results = []
        page = 1
        
        while len(results) < self.max_results:
            params = {
                "q": query,
                "size": 25,  # Zenodo max per page
                "page": page,
                "sort": "bestmatch"
            }
            
            try:
                resp = self.session.get(self.BASE_URL, params=params, timeout=30)
                resp.raise_for_status()
                data = resp.json()
                
                hits = data.get("hits", {}).get("hits", [])
                if not hits:
                    break
                    
                results.extend(hits)
                page += 1
                time.sleep(0.5)  # Rate limiting
                
            except requests.RequestException as e:
                print(f"  Error: {e}")
                break
                
        return results[:self.max_results]
    
    def save_record(self, record: dict) -> bool:
        """Save a record to disk if not already saved."""
        record_id = str(record.get("id", ""))
        if not record_id or record_id in self.scraped_ids:
            return False
            
        self.scraped_ids.add(record_id)
        output_file = self.output_dir / f"{record_id}.json"
        
        with open(output_file, "w") as f:
            json.dump(record, f, indent=2)
        return True
    
    def scrape_term(self, term: str) -> int:
        """Scrape all results for a search term."""
        results = self.search(term)
        saved = 0
        for record in results:
            if self.save_record(record):
                saved += 1
        return saved
    
    def run(self, max_workers: int = 4):
        """Run scraper with parallel processing."""
        print(f"Starting scrape with {len(SEARCH_TERMS)} search terms")
        print(f"Output directory: {self.output_dir}")
        print(f"Max results per term: {self.max_results}")
        print("=" * 60)
        
        total_saved = 0
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self.scrape_term, term): term 
                for term in SEARCH_TERMS
            }
            
            for i, future in enumerate(as_completed(futures), 1):
                term = futures[future]
                try:
                    saved = future.result()
                    total_saved += saved
                    print(f"[{i}/{len(SEARCH_TERMS)}] '{term}': +{saved} (total: {len(self.scraped_ids)})")
                except Exception as e:
                    print(f"[{i}/{len(SEARCH_TERMS)}] '{term}': ERROR - {e}")
        
        print("=" * 60)
        print(f"Scraping complete. Total unique records: {len(self.scraped_ids)}")
        return len(self.scraped_ids)


if __name__ == "__main__":
    output_dir = Path(__file__).parent.parent / "data" / "zenodo_metadata"
    scraper = ZenodoScraper(output_dir, max_results_per_term=500)
    scraper.run(max_workers=4)

