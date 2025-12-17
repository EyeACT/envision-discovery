#!/usr/bin/env python3
"""
ENVISION Zenodo Scraper
Collects eye imaging dataset metadata from Zenodo API.

Full version with 249 search terms including:
- Anatomy wildcards
- Disease patterns
- Equipment brands (Zeiss, Heidelberg, Spectralis, etc.)
- Imaging modalities (OCT, OCTA, fundus, etc.)
- Benchmark datasets (DRIVE, STARE, MESSIDOR, etc.)
- AI/ML specific terms
"""

import json
import time
import requests
import logging
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# ============================================================
# SEARCH TERMS (249 unique terms)
# ============================================================

# Eye anatomy terms
EYE_ANATOMY = [
    "retina", "retinal", "macula", "macular", "fovea", "foveal",
    "cornea", "corneal", "choroid", "choroidal", "optic disc",
    "optic nerve", "RNFL", "anterior segment", "posterior segment",
    "vitreous", "lens", "iris", "sclera", "conjunctiva",
]

# Eye diseases
EYE_DISEASES = [
    "diabetic retinopathy", "glaucoma", "macular degeneration", "AMD",
    "cataract", "keratoconus", "macular edema", "retinal detachment",
    "retinitis pigmentosa", "uveitis", "drusen", "CNV", "DME",
    "myopia", "hyperopia", "retinal vein occlusion", "retinal artery occlusion",
]

# Equipment brands
EQUIPMENT_BRANDS = [
    "Zeiss", "Heidelberg", "Spectralis", "Cirrus", "Topcon",
    "Maestro", "Triton", "Optovue", "Optos", "Canon", "Nidek",
    "Kowa", "Haag-Streit", "Huvitz", "Tomey",
]

# Imaging modalities
MODALITIES = [
    "OCT", "optical coherence tomography", "OCTA", "OCT-A",
    "fundus", "SLO", "scanning laser", "fluorescein angiography",
    "ICG", "ICGA", "slit-lamp", "slit lamp", "Scheimpflug",
    "ultrasound biomicroscopy", "UBM",
]

# Benchmark datasets
BENCHMARK_DATASETS = [
    "DRIVE dataset", "STARE dataset", "MESSIDOR", "IDRiD",
    "REFUGE dataset", "EyePACS", "APTOS", "CHASE_DB1",
    "ORIGA", "RIM-ONE", "OCTID", "ARIA dataset", "DRIONS-DB",
    "Drishti-GS", "HRF dataset", "FIRE dataset", "FIVES",
    "Duke OCT", "Kermany OCT", "ODIR dataset", "PALM dataset",
    "GAMMA dataset", "RIGA dataset", "G1020", "iChallenge",
]

# Build search terms with wildcards
SEARCH_TERMS = []

# Anatomy + imag* / dataset / data
for a in EYE_ANATOMY:
    SEARCH_TERMS.extend([f"{a} imag*", f"{a} dataset", f"{a} data"])

# Disease + imag* / dataset
for d in EYE_DISEASES:
    SEARCH_TERMS.extend([f"{d} imag*", f"{d} dataset"])

# Eye/ocular + anatomy + imag*
for a in ["retina", "macula", "cornea", "fundus", "optic"]:
    SEARCH_TERMS.extend([f"eye {a} imag*", f"ocular {a} imag*"])

# Equipment brands with modality combinations
for b in EQUIPMENT_BRANDS:
    SEARCH_TERMS.extend([f"{b} OCT", f"{b} fundus", f"{b} retina*", f"{b} ophthalmol*"])

# Modalities with data suffixes
for m in MODALITIES:
    SEARCH_TERMS.extend([f"{m} dataset", f"{m} data", f"{m} imag*"])

# General ophthalmology wildcards
SEARCH_TERMS.extend([
    "ophthalmol* imag*", "ophthalmol* dataset",
    "eye imag* dataset", "ocular imag* dataset",
    "retinal imag* dataset", "fundus imag* dataset",
    "ophthalmic imag* data",
])

# Benchmark datasets
SEARCH_TERMS.extend(BENCHMARK_DATASETS)

# AI/ML specific terms
SEARCH_TERMS.extend([
    "retinal deep learning", "fundus neural network",
    "OCT machine learning", "glaucoma detection dataset",
    "diabetic retinopathy classification", "retinal vessel segmentation",
    "optic disc segmentation", "macular hole detection",
])

# Deduplicate while preserving order
seen = set()
SEARCH_TERMS = [x for x in SEARCH_TERMS if not (x.lower() in seen or seen.add(x.lower()))]

# ============================================================
# FILE TYPE DETECTION
# ============================================================

EYE_IMAGING_EXTENSIONS = {
    '.dcm', '.dicom', '.nii', '.nii.gz', '.hdr', '.img',
    '.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp',
    '.tif', '.tiff', '.jp2', '.vol', '.e2e', '.fda', '.fds', '.oct',
    '.dat', '.raw', '.mat', '.h5', '.hdf5', '.npy', '.npz', '.pkl',
}

ARCHIVE_EXTENSIONS = {'.zip', '.tar', '.tar.gz', '.tgz', '.gz', '.bz2', '.rar', '.7z'}


def analyze_files(files: list) -> dict:
    """Analyze files in a Zenodo record."""
    analysis = {
        'has_imaging_files': False,
        'has_archives': False,
        'imaging_file_count': 0,
        'archive_count': 0,
        'total_size': 0,
    }
    
    for f in files:
        filename = f.get('key', '').lower()
        size = f.get('size', 0)
        analysis['total_size'] += size
        
        # Check for imaging files
        for ext in EYE_IMAGING_EXTENSIONS:
            if filename.endswith(ext):
                analysis['has_imaging_files'] = True
                analysis['imaging_file_count'] += 1
                break
        
        # Check for archives
        for ext in ARCHIVE_EXTENSIONS:
            if filename.endswith(ext):
                analysis['has_archives'] = True
                analysis['archive_count'] += 1
                break
    
    return analysis


# ============================================================
# SCRAPER CLASS
# ============================================================

class ZenodoScraper:
    """Scrapes metadata from Zenodo API with rate limiting."""
    
    BASE_URL = "https://zenodo.org/api/records"
    
    def __init__(self, output_dir: Path, max_results_per_term: int = 500):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.max_results = max_results_per_term
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'EnvisionPortal-Scraper/1.0'
        })
        self.scraped_ids = set()
        
    def search(self, query: str) -> list:
        """Search Zenodo for a query term with pagination."""
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
                
                if resp.status_code == 429:
                    # Rate limited - wait and retry
                    retry_after = int(resp.headers.get('Retry-After', 60))
                    logger.warning(f"Rate limited. Waiting {retry_after}s...")
                    time.sleep(retry_after)
                    continue
                
                resp.raise_for_status()
                data = resp.json()
                
                hits = data.get("hits", {}).get("hits", [])
                if not hits:
                    break
                    
                results.extend(hits)
                page += 1
                time.sleep(0.5)  # Rate limiting between pages
                
            except requests.RequestException as e:
                logger.error(f"Error searching '{query}': {e}")
                break
                
        return results[:self.max_results]
    
    def save_record(self, record: dict) -> bool:
        """Save a record to disk if not already saved."""
        record_id = str(record.get("id", ""))
        if not record_id or record_id in self.scraped_ids:
            return False
        
        # Analyze files
        files = record.get('files', [])
        file_analysis = analyze_files(files)
        record['_file_analysis'] = file_analysis
        
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
        logger.info(f"Starting Zenodo scrape with {len(SEARCH_TERMS)} search terms")
        logger.info(f"Output directory: {self.output_dir}")
        logger.info(f"Max results per term: {self.max_results}")
        logger.info(f"Workers: {max_workers}")
        logger.info("=" * 60)
        
        start_time = datetime.now()
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self.scrape_term, term): term 
                for term in SEARCH_TERMS
            }
            
            for i, future in enumerate(as_completed(futures), 1):
                term = futures[future]
                try:
                    saved = future.result()
                    logger.info(f"[{i}/{len(SEARCH_TERMS)}] '{term}': +{saved} (total: {len(self.scraped_ids)})")
                except Exception as e:
                    logger.error(f"[{i}/{len(SEARCH_TERMS)}] '{term}': ERROR - {e}")
        
        # Summary
        elapsed = (datetime.now() - start_time).total_seconds() / 60
        logger.info("=" * 60)
        logger.info("SCRAPING COMPLETE")
        logger.info(f"Runtime: {elapsed:.1f} minutes")
        logger.info(f"Total unique records: {len(self.scraped_ids)}")
        
        # Count records with data
        with_images = sum(1 for f in self.output_dir.glob("*.json") 
                        if json.load(open(f)).get('_file_analysis', {}).get('has_imaging_files'))
        with_archives = sum(1 for f in self.output_dir.glob("*.json") 
                          if json.load(open(f)).get('_file_analysis', {}).get('has_archives'))
        
        logger.info(f"Records with imaging files: {with_images}")
        logger.info(f"Records with archives: {with_archives}")
        logger.info("=" * 60)
        
        return len(self.scraped_ids)


if __name__ == "__main__":
    # Default output to data/zenodo_metadata in parent directory
    output_dir = Path(__file__).parent.parent / "data" / "zenodo_metadata"
    
    logger.info(f"Search terms: {len(SEARCH_TERMS)}")
    
    scraper = ZenodoScraper(output_dir, max_results_per_term=500)
    scraper.run(max_workers=4)
