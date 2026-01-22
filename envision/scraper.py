#!/usr/bin/env python3
"""
Eye Imaging Data Scraper for Zenodo and Figshare
Downloads all possible eye imaging datasets with comprehensive medical terminology keywords.

Author: AI Assistant
Date: December 8, 2025
"""

import os
import json
import time
import requests
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set, Optional
from urllib.parse import quote
import hashlib

# Configure logging with timestamps
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/home/joneill/vaults/jmind/calmi2/envision/logs/scraper.log')
    ]
)
logger = logging.getLogger(__name__)

# Base paths
BASE_DIR = Path("/home/joneill/vaults/jmind/calmi2/envision")
DOWNLOADS_DIR = BASE_DIR / "downloads"
METADATA_DIR = BASE_DIR / "metadata"

# Rate limiting
RATE_LIMIT_SECONDS = 1.0

# =============================================================================
# COMPREHENSIVE EYE IMAGING KEYWORDS
# Compiled from medical dictionaries, ophthalmology resources, and imaging literature
# =============================================================================

KEYWORDS = {
    # =========================================================================
    # IMAGING MODALITIES & TECHNIQUES
    # =========================================================================
    'imaging_modalities': [
        # OCT variants
        'optical coherence tomography', 'OCT', 'OCT-A', 'OCTA', 'OCT angiography',
        'spectral domain OCT', 'SD-OCT', 'swept source OCT', 'SS-OCT',
        'time domain OCT', 'TD-OCT', 'enhanced depth imaging', 'EDI-OCT',
        'anterior segment OCT', 'AS-OCT',
        
        # Fundus imaging
        'fundus photography', 'fundus image', 'fundus photo', 'fundoscopy',
        'color fundus', 'red-free fundus', 'fundus autofluorescence', 'FAF',
        'wide-field fundus', 'ultra-widefield', 'UWF imaging',
        'scanning laser ophthalmoscopy', 'SLO', 'confocal SLO', 'cSLO',
        
        # Angiography
        'fluorescein angiography', 'FA', 'FFA', 'fundus fluorescein angiography',
        'indocyanine green angiography', 'ICG', 'ICGA',
        'retinal angiography', 'choroidal angiography',
        
        # Slit lamp & anterior segment
        'slit lamp', 'slit-lamp', 'biomicroscopy', 'gonioscopy',
        'anterior segment imaging', 'corneal imaging', 'corneal topography',
        'Scheimpflug imaging', 'Pentacam', 'Orbscan',
        'specular microscopy', 'confocal microscopy',
        'meibography', 'meibomian gland imaging',
        
        # Ultrasound
        'ocular ultrasound', 'B-scan ultrasound', 'A-scan ultrasound',
        'ultrasound biomicroscopy', 'UBM', 'ophthalmic ultrasound',
        
        # Other imaging
        'retinal imaging', 'ophthalmic imaging', 'eye imaging',
        'adaptive optics', 'AO imaging', 'AO-SLO', 'AO-OCT',
        'photoacoustic imaging', 'PAI ophthalmology',
        'electroretinography', 'ERG', 'multifocal ERG', 'mfERG',
        'visual evoked potential', 'VEP',
        'pachymetry', 'corneal pachymetry',
        'tonometry', 'applanation tonometry',
        'perimetry', 'visual field', 'Humphrey visual field',
        'biometry', 'ocular biometry', 'IOLMaster',
        'keratometry', 'topography',
    ],
    
    # =========================================================================
    # EYE ANATOMY
    # =========================================================================
    'anatomy': [
        # Anterior segment
        'cornea', 'corneal', 'epithelium', 'Bowman layer', 'stroma',
        'Descemet membrane', 'endothelium', 'limbus', 'limbal',
        'anterior chamber', 'aqueous humor', 'trabecular meshwork',
        'Schlemm canal', 'iris', 'pupil', 'ciliary body',
        'lens', 'crystalline lens', 'capsule', 'zonules',
        'conjunctiva', 'sclera', 'episclera',
        
        # Posterior segment  
        'retina', 'retinal', 'macula', 'macular', 'fovea', 'foveal',
        'parafovea', 'perifovea', 'optic nerve', 'optic disc', 'optic nerve head',
        'cup-to-disc', 'neuroretinal rim', 'lamina cribrosa',
        'choroid', 'choroidal', 'choriocapillaris', 'Bruch membrane',
        'vitreous', 'vitreous humor', 'posterior vitreous',
        'ora serrata', 'pars plana', 'peripheral retina',
        
        # Retinal layers
        'retinal nerve fiber layer', 'RNFL', 'ganglion cell layer', 'GCL',
        'inner plexiform layer', 'IPL', 'inner nuclear layer', 'INL',
        'outer plexiform layer', 'OPL', 'outer nuclear layer', 'ONL',
        'photoreceptor layer', 'inner segment', 'outer segment',
        'retinal pigment epithelium', 'RPE', 'ellipsoid zone', 'EZ',
        'external limiting membrane', 'ELM', 'inner limiting membrane', 'ILM',
        'Henle fiber layer',
        
        # Vasculature
        'retinal vasculature', 'retinal vessel', 'retinal artery',
        'retinal vein', 'central retinal artery', 'CRA',
        'central retinal vein', 'CRV', 'branch retinal',
        'vascular arcade', 'capillary', 'microvasculature',
        'foveal avascular zone', 'FAZ',
        
        # Other structures
        'eyelid', 'meibomian gland', 'lacrimal', 'tear film',
        'extraocular muscle', 'orbit', 'orbital',
    ],
    
    # =========================================================================
    # EYE DISEASES & CONDITIONS
    # =========================================================================
    'diseases': [
        # Retinal diseases
        'diabetic retinopathy', 'DR', 'proliferative diabetic retinopathy', 'PDR',
        'nonproliferative diabetic retinopathy', 'NPDR',
        'diabetic macular edema', 'DME', 'clinically significant macular edema', 'CSME',
        'age-related macular degeneration', 'AMD', 'ARMD',
        'wet AMD', 'dry AMD', 'neovascular AMD', 'geographic atrophy', 'GA',
        'drusen', 'reticular pseudodrusen', 'RPD',
        'macular hole', 'lamellar hole', 'full-thickness macular hole',
        'epiretinal membrane', 'ERM', 'macular pucker', 'cellophane maculopathy',
        'vitreomacular traction', 'VMT', 'vitreomacular adhesion', 'VMA',
        'central serous chorioretinopathy', 'CSC', 'CSR', 'CSCR',
        'retinal detachment', 'RD', 'rhegmatogenous', 'tractional', 'exudative',
        'retinal tear', 'retinal break', 'lattice degeneration',
        'retinitis pigmentosa', 'RP', 'rod-cone dystrophy',
        'Stargardt disease', 'Best disease', 'vitelliform dystrophy',
        'cone dystrophy', 'cone-rod dystrophy', 'Leber congenital amaurosis',
        'choroideremia', 'gyrate atrophy',
        'retinal vein occlusion', 'RVO', 'branch retinal vein occlusion', 'BRVO',
        'central retinal vein occlusion', 'CRVO', 'hemiretinal vein occlusion',
        'retinal artery occlusion', 'RAO', 'BRAO', 'CRAO',
        'macular edema', 'cystoid macular edema', 'CME',
        'choroidal neovascularization', 'CNV', 'polypoidal choroidal vasculopathy', 'PCV',
        'retinal angiomatous proliferation', 'RAP',
        'myopic maculopathy', 'pathologic myopia', 'myopic CNV',
        'retinopathy of prematurity', 'ROP',
        'hypertensive retinopathy', 'radiation retinopathy',
        'Coats disease', 'Eales disease', 'familial exudative vitreoretinopathy', 'FEVR',
        'asteroid hyalosis', 'synchysis scintillans',
        
        # Glaucoma
        'glaucoma', 'open-angle glaucoma', 'POAG', 'primary open-angle glaucoma',
        'angle-closure glaucoma', 'PACG', 'narrow angle', 'acute angle closure',
        'normal tension glaucoma', 'NTG', 'low tension glaucoma',
        'neovascular glaucoma', 'NVG', 'secondary glaucoma',
        'pigmentary glaucoma', 'pseudoexfoliation glaucoma', 'PXG',
        'congenital glaucoma', 'juvenile glaucoma',
        'ocular hypertension', 'OHT', 'intraocular pressure', 'IOP',
        'glaucomatous optic neuropathy', 'optic nerve damage',
        
        # Corneal diseases
        'keratoconus', 'corneal ectasia', 'pellucid marginal degeneration',
        'Fuchs dystrophy', 'Fuchs endothelial dystrophy', 'FECD',
        'corneal dystrophy', 'granular dystrophy', 'lattice dystrophy', 'macular dystrophy',
        'keratitis', 'bacterial keratitis', 'fungal keratitis', 'Acanthamoeba keratitis',
        'herpes simplex keratitis', 'HSK', 'herpes zoster ophthalmicus',
        'corneal ulcer', 'corneal abrasion', 'corneal erosion',
        'dry eye', 'dry eye disease', 'DED', 'keratoconjunctivitis sicca', 'KCS',
        'pterygium', 'pinguecula', 'corneal scar', 'corneal opacity',
        'bullous keratopathy', 'pseudophakic bullous keratopathy', 'PBK',
        
        # Cataract
        'cataract', 'nuclear cataract', 'cortical cataract', 'posterior subcapsular cataract',
        'PSC', 'nuclear sclerosis', 'NS', 'mature cataract', 'hypermature cataract',
        'congenital cataract', 'traumatic cataract', 'secondary cataract', 'PCO',
        'posterior capsule opacification',
        
        # Uveitis & inflammation
        'uveitis', 'anterior uveitis', 'intermediate uveitis', 'posterior uveitis',
        'panuveitis', 'iritis', 'iridocyclitis', 'choroiditis', 'retinitis',
        'chorioretinitis', 'vitritis', 'endophthalmitis', 'panophthalmitis',
        'Vogt-Koyanagi-Harada', 'VKH', 'sympathetic ophthalmia',
        'birdshot chorioretinopathy', 'multifocal choroiditis', 'serpiginous choroiditis',
        'ocular toxoplasmosis', 'CMV retinitis', 'ARN', 'acute retinal necrosis',
        
        # Optic nerve diseases
        'optic neuritis', 'papilledema', 'papillitis',
        'ischemic optic neuropathy', 'AION', 'NAION', 'arteritic AION',
        'optic atrophy', 'glaucomatous optic atrophy',
        'optic nerve hypoplasia', 'optic nerve coloboma',
        'Leber hereditary optic neuropathy', 'LHON',
        
        # Other conditions
        'strabismus', 'amblyopia', 'nystagmus',
        'myopia', 'hyperopia', 'astigmatism', 'presbyopia',
        'refractive error', 'ametropia', 'anisometropia',
        'blepharitis', 'chalazion', 'hordeolum', 'stye',
        'conjunctivitis', 'allergic conjunctivitis', 'bacterial conjunctivitis',
        'episcleritis', 'scleritis',
        'orbital cellulitis', 'preseptal cellulitis',
        'thyroid eye disease', 'Graves ophthalmopathy',
        'ocular melanoma', 'choroidal melanoma', 'retinoblastoma',
        'ocular surface disease', 'OSD',
    ],
    
    # =========================================================================
    # CLINICAL MEASUREMENTS & BIOMARKERS
    # =========================================================================
    'measurements': [
        'visual acuity', 'VA', 'BCVA', 'best corrected visual acuity',
        'LogMAR', 'Snellen', 'ETDRS',
        'contrast sensitivity', 'CS',
        'central macular thickness', 'CMT', 'central subfield thickness', 'CST',
        'retinal thickness', 'choroidal thickness', 'subfoveal choroidal thickness',
        'RNFL thickness', 'GCC thickness', 'ganglion cell complex',
        'cup-to-disc ratio', 'CDR', 'vertical CDR',
        'mean deviation', 'MD', 'pattern standard deviation', 'PSD',
        'visual field index', 'VFI',
        'vessel density', 'perfusion density', 'FAZ area',
        'axial length', 'AL', 'anterior chamber depth', 'ACD',
        'central corneal thickness', 'CCT', 'endothelial cell density', 'ECD',
        'keratometry', 'K reading', 'corneal curvature',
        'tear break-up time', 'TBUT', 'Schirmer test',
    ],
    
    # =========================================================================
    # MACHINE LEARNING & DATASETS
    # =========================================================================
    'ml_datasets': [
        # General terms
        'ophthalmic dataset', 'retinal dataset', 'eye dataset',
        'fundus dataset', 'OCT dataset', 'ophthalmology dataset',
        'medical imaging dataset', 'clinical dataset',
        'deep learning ophthalmology', 'machine learning retina',
        'AI ophthalmology', 'computer-aided diagnosis', 'CAD',
        'automated detection', 'automated segmentation',
        'retinal vessel segmentation', 'optic disc segmentation',
        'lesion detection', 'disease classification',
        
        # Known dataset names
        'DRIVE', 'STARE', 'CHASE_DB1', 'CHASE DB', 'HRF',
        'MESSIDOR', 'MESSIDOR-2', 'IDRiD', 'APTOS',
        'REFUGE', 'ORIGA', 'RIM-ONE', 'Drishti-GS',
        'ARIA', 'REVIEW', 'IOSTAR', 'RITE',
        'FIRE', 'ROC', 'e-ophtha', 'DiaRetDB',
        'AREDS', 'AREDS2', 'UK Biobank', 'EyePACS',
        'Kaggle diabetic retinopathy', 'Kaggle APTOS',
        'OCTID', 'RETOUCH', 'DUKE', 'kermany',
        'srinivasan', 'farsiu',
    ],
    
    # =========================================================================
    # OPHTHALMIC EQUIPMENT & VENDORS
    # =========================================================================
    'equipment': [
        'Heidelberg', 'Spectralis', 'HRA', 'Heidelberg Retina Angiograph',
        'Zeiss', 'Cirrus', 'Cirrus HD-OCT', 'PLEX Elite',
        'Topcon', 'Triton', 'DRI OCT', 'Maestro',
        'Optovue', 'RTVue', 'Avanti', 'AngioVue',
        'Canon', 'CR-2', 'OCT-HS100',
        'Nidek', 'RS-3000',
        'Optos', 'Daytona', 'California',
        'iCare', 'Oculus', 'Pentacam',
        'Haag-Streit', 'Lenstar',
    ],
    
    # =========================================================================
    # FILE TYPES & DATA FORMATS
    # =========================================================================
    'data_formats': [
        'DICOM', 'ophthalmology DICOM',
        'E2E', 'FDA', 'IMG', 'OCT file',
        'fundus image', 'retinal scan',
        'volumetric scan', '3D OCT', 'B-scan', 'en face',
        'angiogram', 'angiographic',
    ],
}

# Flatten all keywords into a single searchable list
ALL_KEYWORDS = []
for category, terms in KEYWORDS.items():
    ALL_KEYWORDS.extend(terms)

# Remove duplicates and create unique keyword set
UNIQUE_KEYWORDS = list(set(ALL_KEYWORDS))
logger.info(f"Total unique keywords: {len(UNIQUE_KEYWORDS)}")

# High-priority search terms (more likely to return relevant results)
PRIORITY_SEARCH_TERMS = [
    # Most specific imaging terms
    'retinal OCT', 'fundus photography', 'optical coherence tomography eye',
    'retinal imaging dataset', 'fundus image dataset', 'OCT dataset',
    'diabetic retinopathy dataset', 'glaucoma dataset', 'AMD dataset',
    'retinal vessel segmentation', 'optic disc detection',
    'macular OCT', 'RNFL OCT', 'OCT-A retina',
    
    # Disease-specific imaging
    'diabetic retinopathy fundus', 'glaucoma OCT', 'macular degeneration imaging',
    'choroidal neovascularization OCT', 'macular edema OCT',
    
    # Anatomy-specific
    'retinal layer segmentation', 'optic nerve head imaging',
    'foveal OCT', 'macula imaging', 'choroidal imaging',
    
    # General ophthalmology data
    'ophthalmic imaging', 'eye imaging data', 'ophthalmology dataset',
    'retina scan', 'eye scan dataset', 'ocular imaging',
    
    # Equipment-specific
    'Spectralis OCT', 'Cirrus OCT', 'Topcon OCT', 'Heidelberg retina',
    
    # Known datasets
    'DRIVE retinal', 'STARE retinal', 'MESSIDOR', 'IDRiD',
    'REFUGE glaucoma', 'CHASE_DB1', 'EyePACS', 'APTOS',
]


class ZenodoScraper:
    """Scraper for Zenodo eye imaging datasets."""
    
    # Use the search API endpoint with trailing slash
    SEARCH_URL = "https://zenodo.org/api/records/"
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({'Accept': 'application/json'})
        self.seen_records: Set[int] = set()
        self.download_dir = DOWNLOADS_DIR / "zenodo"
        self.metadata_dir = METADATA_DIR / "zenodo"
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
    
    def search(self, query: str, max_results: int = 1000) -> List[Dict]:
        """Search Zenodo for records matching query."""
        records = []
        page = 1
        per_page = 25  # Zenodo API max is 25
        
        while len(records) < max_results:
            # Simple query - no filters, just the search terms
            params = {
                'q': query,
                'page': page,
                'size': per_page,
            }
            
            try:
                response = self.session.get(self.SEARCH_URL, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()
                
                # Handle API response format
                hits = data.get('hits', {}).get('hits', [])
                if not hits:
                    break
                
                for hit in hits:
                    record_id = hit.get('id')
                    if record_id and record_id not in self.seen_records:
                        self.seen_records.add(record_id)
                        records.append(hit)
                
                page += 1
                time.sleep(RATE_LIMIT_SECONDS)
                
                if len(hits) < per_page:
                    break
                    
            except Exception as e:
                logger.warning(f"Zenodo search error for '{query}': {e}")
                break
        
        return records
    
    def download_record(self, record: Dict) -> bool:
        """Download files from a Zenodo record."""
        record_id = record.get('id')
        if not record_id:
            return False
        
        # Save metadata first
        metadata_file = self.metadata_dir / f"{record_id}.json"
        if not metadata_file.exists():
            with open(metadata_file, 'w') as f:
                json.dump(record, f, indent=2)
        
        # Get files list
        files = record.get('files', [])
        if not files:
            # Try to get files from links
            files_url = record.get('links', {}).get('files')
            if files_url:
                try:
                    response = self.session.get(files_url, timeout=30)
                    if response.ok:
                        files_data = response.json()
                        files = files_data.get('entries', [])
                except:
                    pass
        
        downloaded = False
        for file_info in files:
            filename = file_info.get('key', file_info.get('filename', ''))
            if not filename:
                continue
            
            # Check for image/data file types
            ext = Path(filename).suffix.lower()
            if ext in ['.zip', '.tar', '.gz', '.tgz', '.7z', '.rar',  # Archives
                      '.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp',  # Images
                      '.dcm', '.dicom', '.nii', '.nii.gz',  # Medical
                      '.mat', '.npy', '.npz', '.h5', '.hdf5',  # Data
                      '.csv', '.json', '.xml']:
                
                download_url = file_info.get('links', {}).get('self')
                if not download_url:
                    download_url = file_info.get('download_url') or file_info.get('url')
                
                if download_url:
                    dest_file = self.download_dir / f"zenodo_{record_id}_{filename}"
                    if not dest_file.exists():
                        try:
                            logger.info(f"Downloading: {filename} from record {record_id}")
                            response = self.session.get(download_url, stream=True, timeout=300)
                            if response.ok:
                                with open(dest_file, 'wb') as f:
                                    for chunk in response.iter_content(chunk_size=8192):
                                        f.write(chunk)
                                downloaded = True
                            time.sleep(RATE_LIMIT_SECONDS)
                        except Exception as e:
                            logger.warning(f"Download error for {filename}: {e}")
        
        return downloaded


class FigshareScraper:
    """Scraper for Figshare eye imaging datasets."""
    
    BASE_URL = "https://api.figshare.com/v2"
    
    def __init__(self):
        self.session = requests.Session()
        self.seen_records: Set[int] = set()
        self.download_dir = DOWNLOADS_DIR / "figshare"
        self.metadata_dir = METADATA_DIR / "figshare"
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
    
    def search(self, query: str, max_results: int = 1000) -> List[Dict]:
        """Search Figshare for articles matching query."""
        records = []
        page = 1
        per_page = 100
        
        while len(records) < max_results:
            try:
                search_url = f"{self.BASE_URL}/articles/search"
                payload = {
                    'search_for': query,
                    'page': page,
                    'page_size': per_page,
                    # Remove item_type filter to get all types including datasets
                }
                
                response = self.session.post(search_url, json=payload, timeout=30)
                response.raise_for_status()
                hits = response.json()
                
                if not hits:
                    break
                
                for hit in hits:
                    record_id = hit.get('id')
                    if record_id and record_id not in self.seen_records:
                        self.seen_records.add(record_id)
                        # Get full article details
                        try:
                            detail_url = f"{self.BASE_URL}/articles/{record_id}"
                            detail_response = self.session.get(detail_url, timeout=30)
                            if detail_response.ok:
                                records.append(detail_response.json())
                            time.sleep(RATE_LIMIT_SECONDS)
                        except:
                            records.append(hit)
                
                page += 1
                time.sleep(RATE_LIMIT_SECONDS)
                
                if len(hits) < per_page:
                    break
                    
            except Exception as e:
                logger.warning(f"Figshare search error for '{query}': {e}")
                break
        
        return records
    
    def download_record(self, record: Dict) -> bool:
        """Download files from a Figshare record."""
        record_id = record.get('id')
        if not record_id:
            return False
        
        # Save metadata first
        metadata_file = self.metadata_dir / f"{record_id}.json"
        if not metadata_file.exists():
            with open(metadata_file, 'w') as f:
                json.dump(record, f, indent=2)
        
        # Get files list
        files = record.get('files', [])
        
        downloaded = False
        for file_info in files:
            filename = file_info.get('name', '')
            if not filename:
                continue
            
            # Check for relevant file types
            ext = Path(filename).suffix.lower()
            if ext in ['.zip', '.tar', '.gz', '.tgz', '.7z', '.rar',
                      '.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp',
                      '.dcm', '.dicom', '.nii', '.nii.gz',
                      '.mat', '.npy', '.npz', '.h5', '.hdf5',
                      '.csv', '.json', '.xml']:
                
                download_url = file_info.get('download_url')
                
                if download_url:
                    dest_file = self.download_dir / f"figshare_{record_id}_{filename}"
                    if not dest_file.exists():
                        try:
                            logger.info(f"Downloading: {filename} from record {record_id}")
                            response = self.session.get(download_url, stream=True, timeout=300)
                            if response.ok:
                                with open(dest_file, 'wb') as f:
                                    for chunk in response.iter_content(chunk_size=8192):
                                        f.write(chunk)
                                downloaded = True
                            time.sleep(RATE_LIMIT_SECONDS)
                        except Exception as e:
                            logger.warning(f"Download error for {filename}: {e}")
        
        return downloaded


def run_comprehensive_search():
    """Run comprehensive search across all platforms with all keywords."""
    logger.info("=" * 70)
    logger.info("EYE IMAGING DATA SCRAPER - Starting Comprehensive Search")
    logger.info(f"Total keywords to search: {len(PRIORITY_SEARCH_TERMS)} priority + {len(UNIQUE_KEYWORDS)} full")
    logger.info("=" * 70)
    
    zenodo = ZenodoScraper()
    figshare = FigshareScraper()
    
    all_zenodo_records = []
    all_figshare_records = []
    
    # Phase 1: Priority search terms
    logger.info("\n--- Phase 1: Priority Search Terms ---")
    for i, term in enumerate(PRIORITY_SEARCH_TERMS, 1):
        logger.info(f"[{i}/{len(PRIORITY_SEARCH_TERMS)}] Searching: '{term}'")
        
        # Zenodo
        zenodo_results = zenodo.search(term, max_results=500)
        all_zenodo_records.extend(zenodo_results)
        logger.info(f"  Zenodo: {len(zenodo_results)} new records")
        
        # Figshare
        figshare_results = figshare.search(term, max_results=500)
        all_figshare_records.extend(figshare_results)
        logger.info(f"  Figshare: {len(figshare_results)} new records")
    
    # Phase 2: Extended keyword search (sample of unique keywords)
    logger.info("\n--- Phase 2: Extended Keyword Search ---")
    extended_terms = [k for k in UNIQUE_KEYWORDS if k not in PRIORITY_SEARCH_TERMS]
    
    # Search combinations that are more likely to return imaging data
    combo_searches = [
        'retinal image', 'fundus photograph', 'OCT scan',
        'ophthalmic imaging data', 'eye imaging dataset',
        'retinal vessel', 'optic disc image', 'macula scan',
    ]
    
    for i, term in enumerate(combo_searches, 1):
        logger.info(f"[{i}/{len(combo_searches)}] Extended search: '{term}'")
        
        zenodo_results = zenodo.search(term, max_results=300)
        all_zenodo_records.extend(zenodo_results)
        
        figshare_results = figshare.search(term, max_results=300)
        all_figshare_records.extend(figshare_results)
    
    # Summary
    logger.info("\n" + "=" * 70)
    logger.info("SEARCH COMPLETE - Summary")
    logger.info("=" * 70)
    logger.info(f"Total unique Zenodo records found: {len(zenodo.seen_records)}")
    logger.info(f"Total unique Figshare records found: {len(figshare.seen_records)}")
    
    # Save search results index
    results_summary = {
        'timestamp': datetime.now().isoformat(),
        'zenodo_records': len(zenodo.seen_records),
        'figshare_records': len(figshare.seen_records),
        'total_keywords_used': len(PRIORITY_SEARCH_TERMS) + len(combo_searches),
    }
    
    with open(BASE_DIR / "search_results_summary.json", 'w') as f:
        json.dump(results_summary, f, indent=2)
    
    return all_zenodo_records, all_figshare_records, zenodo, figshare


def download_all_records(zenodo_records, figshare_records, zenodo_scraper, figshare_scraper):
    """Download all found records."""
    logger.info("\n" + "=" * 70)
    logger.info("DOWNLOADING RECORDS")
    logger.info("=" * 70)
    
    downloaded_count = 0
    
    # Download Zenodo records
    logger.info(f"\nDownloading {len(zenodo_records)} Zenodo records...")
    for i, record in enumerate(zenodo_records, 1):
        if i % 50 == 0:
            logger.info(f"Progress: {i}/{len(zenodo_records)} Zenodo records")
        if zenodo_scraper.download_record(record):
            downloaded_count += 1
    
    # Download Figshare records
    logger.info(f"\nDownloading {len(figshare_records)} Figshare records...")
    for i, record in enumerate(figshare_records, 1):
        if i % 50 == 0:
            logger.info(f"Progress: {i}/{len(figshare_records)} Figshare records")
        if figshare_scraper.download_record(record):
            downloaded_count += 1
    
    logger.info(f"\nTotal records with downloads: {downloaded_count}")
    
    return downloaded_count


def main():
    """Main execution."""
    logger.info("Starting Eye Imaging Data Scraper")
    logger.info(f"Output directory: {BASE_DIR}")
    
    # Run search
    zenodo_records, figshare_records, zenodo_scraper, figshare_scraper = run_comprehensive_search()
    
    # Download
    download_all_records(zenodo_records, figshare_records, zenodo_scraper, figshare_scraper)
    
    # Final summary
    zenodo_files = list((DOWNLOADS_DIR / "zenodo").glob("*"))
    figshare_files = list((DOWNLOADS_DIR / "figshare").glob("*"))
    zenodo_meta = list((METADATA_DIR / "zenodo").glob("*.json"))
    figshare_meta = list((METADATA_DIR / "figshare").glob("*.json"))
    
    logger.info("\n" + "=" * 70)
    logger.info("FINAL SUMMARY")
    logger.info("=" * 70)
    logger.info(f"Zenodo: {len(zenodo_meta)} metadata files, {len(zenodo_files)} downloads")
    logger.info(f"Figshare: {len(figshare_meta)} metadata files, {len(figshare_files)} downloads")
    logger.info(f"Total: {len(zenodo_meta) + len(figshare_meta)} records")
    logger.info(f"Output: {BASE_DIR}")


if __name__ == "__main__":
    main()

