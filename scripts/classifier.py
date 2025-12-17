#!/usr/bin/env python3
"""
ENVISION SetFit Classifier
Few-shot classification of eye imaging datasets using sentence transformers.

STATUS: Work in progress. Training data is synthetic and limited.
Results require manual validation before use.
"""

import json
from pathlib import Path
from datetime import datetime

import torch
from setfit import SetFitModel, Trainer, TrainingArguments
from datasets import Dataset

# ============================================================
# TRAINING DATA
# ============================================================

# POSITIVE: Actual ophthalmic imaging datasets
POSITIVE_EXAMPLES = [
    "Dataset from fundus images for diabetic retinopathy progression",
    "Fundus photography dataset for glaucoma detection screening",
    "Retinal fundus multi-disease image dataset RFMiD",
    "Rotterdam EyePACS AIROGS fundus images glaucoma",
    "Indian Diabetic Retinopathy Image Dataset IDRiD fundus",
    "DRIVE STARE retinal vessel segmentation fundus dataset",
    "Optic disc cup segmentation fundus photography",
    "Diabetic retinopathy classification fundus images",
    "Age-related macular degeneration AMD fundus dataset",
    "Optical coherence tomography OCT retinal imaging dataset",
    "OCT B-scan retinal layer segmentation dataset",
    "Macular OCT images drusen geographic atrophy",
    "RNFL thickness OCT glaucoma progression dataset",
    "Retinal OCT volume scans macula imaging",
    "Heidelberg Spectralis OCT retinal scans",
    "Zeiss Cirrus OCT macular imaging dataset",
    "OCTA optical coherence tomography angiography retinal",
    "OCT angiography foveal avascular zone dataset",
    "Corneal topography keratoconus detection images",
    "Anterior segment OCT angle closure glaucoma",
    "Slit lamp photography cataract grading",
    "Fluorescein angiography choroidal neovascularization",
    "Corneal confocal microscopy nerve imaging",
    "OLIVES dataset ophthalmic labels visual examination",
    "Human developing retina atlas single cell",
    "MESSIDOR diabetic retinopathy fundus screening",
    "CHASE_DB1 retinal vessel segmentation dataset",
    "HRF high resolution fundus image dataset",
    "REFUGE glaucoma challenge fundus dataset",
] * 3  # Replicate for balance

# EDGE CASES: Eye research but NOT imaging datasets
EDGE_CASES = [
    "Deep learning review diabetic retinopathy detection survey",
    "Machine learning methods glaucoma diagnosis review",
    "Advances optical coherence tomography technology review",
    "Clinical guidelines diabetic eye screening protocol",
    "Artificial intelligence ophthalmology comprehensive review",
    "Genetic factors macular degeneration GWAS meta-analysis",
    "Molecular mechanisms retinal ganglion cell death",
    "Pharmacological treatment diabetic macular edema",
    "Visual acuity outcomes anti-VEGF therapy clinical trial",
    "Python package retinal image preprocessing code",
    "Deep learning framework fundus segmentation code only",
    "OCT image reconstruction algorithm implementation",
    "Eye tracking attention research gaze estimation",
    "Pupil dilation response emotional stimuli dataset",
    "Iris recognition biometric authentication dataset",
    "Drosophila compound eye development gene expression",
    "Zebrafish eye regeneration molecular analysis",
    "Mouse retinal development transcriptomics RNA-seq",
] * 3

# NEGATIVE: NOT eye imaging (including false positive patterns)
NEGATIVE_EXAMPLES = [
    # Cardiovascular OCT (false positives)
    "Intravascular OCT IVOCT coronary artery imaging",
    "OCT atherosclerotic plaque morphology segmentation",
    "Cardiovascular OCT coronary artery disease imaging",
    "Coronary OCT intravascular ultrasound IVUS imaging",
    "Aortic dataset segmentation vascular imaging",
    # Endoscopic imaging (false positives)
    "Stereo endoscopic dataset surgical imaging",
    "Endoscopy video dataset gastrointestinal",
    "Colonoscopy image dataset polyp detection",
    # Industrial OCT/CT (false positives)
    "Industrial OCT material inspection dataset",
    "XCT foam reconstruction industrial imaging",
    "Ceramic quality inspection OCT dataset",
    "Pharmaceutical tablet coating OCT analysis",
    "Art conservation painting OCT analysis",
    "Micro-CT nodular cast iron imaging",
    # Dental/Skin OCT (false positives)
    "Dental OCT tooth structure analysis imaging",
    "Skin OCT dermatology imaging dataset",
    "Dermoscopy skin lesion classification",
    # Lung imaging (false positives)
    "OPULM lung imaging pulmonary dataset",
    "Chest CT lung nodule detection",
    # Other medical non-eye
    "Brain MRI Alzheimer disease detection dataset",
    "Cardiac CT angiography coronary disease",
    "Mammography breast cancer screening",
    "Histopathology slide cancer diagnosis",
    # General negatives
    "Climate change coral reef ecosystem dataset",
    "Stock market prediction historical data",
    "Natural language processing benchmark NLP",
    "Speech recognition multilingual corpus",
    "Satellite imagery land use classification",
    "Wildlife camera trap image dataset",
]

# ============================================================
# CLASSIFIER
# ============================================================

class EyeImagingClassifier:
    """SetFit-based classifier for eye imaging datasets."""
    
    LABELS = ["NEGATIVE", "EDGE_CASE", "EYE_IMAGING"]
    DATA_EXTENSIONS = {
        '.dcm', '.dicom', '.nii', '.nii.gz', '.jpg', '.jpeg', '.png',
        '.tif', '.tiff', '.bmp', '.mat', '.h5', '.hdf5', '.npy', '.npz',
        '.zip', '.tar', '.gz', '.rar', '.7z'
    }
    DATASET_HOSTS = [
        'kaggle.com', 'github.com', 'huggingface.co', 'drive.google.com',
        'dropbox.com', 'osf.io', 'mendeley.com', 'dryad'
    ]
    
    def __init__(self, model_name: str = "thenlper/gte-large"):
        self.model_name = model_name
        self.model = None
        
    def train(self, epochs: int = 2, batch_size: int = 16):
        """Train the SetFit model."""
        print(f"Training SetFit model with {self.model_name}")
        
        # Prepare training data
        texts = POSITIVE_EXAMPLES + EDGE_CASES + NEGATIVE_EXAMPLES
        labels = (
            [2] * len(POSITIVE_EXAMPLES) + 
            [1] * len(EDGE_CASES) + 
            [0] * len(NEGATIVE_EXAMPLES)
        )
        
        train_ds = Dataset.from_dict({"text": texts, "label": labels})
        
        # Initialize model
        self.model = SetFitModel.from_pretrained(
            self.model_name,
            labels=self.LABELS
        )
        
        # Train
        args = TrainingArguments(
            batch_size=batch_size,
            num_epochs=epochs,
            report_to="none",
        )
        
        trainer = Trainer(model=self.model, args=args, train_dataset=train_ds)
        trainer.train()
        
        print("Training complete!")
        return self.model
    
    def has_data(self, record: dict) -> tuple:
        """Check if record has data files or dataset links."""
        files = record.get('files', [])
        for f in files:
            name = f.get('key', f.get('name', '')).lower()
            for ext in self.DATA_EXTENSIONS:
                if name.endswith(ext):
                    return True, "data_files"
        
        desc = record.get('metadata', {}).get('description', '').lower()
        for host in self.DATASET_HOSTS:
            if host in desc:
                return True, "dataset_link"
        
        return False, None
    
    def get_text(self, record: dict) -> str:
        """Extract text from record for classification."""
        title = record.get('metadata', {}).get('title', record.get('title', ''))
        desc = record.get('metadata', {}).get('description', '')
        keywords = record.get('metadata', {}).get('keywords', [])
        if isinstance(keywords, list):
            keywords = ' '.join(keywords)
        return f"{title} {desc} {keywords}"[:1000]
    
    def classify(self, records: list) -> list:
        """Classify a list of records."""
        if self.model is None:
            raise ValueError("Model not trained. Call train() first.")
        
        # Filter to records with data
        data_records = []
        for r in records:
            has_data, data_type = self.has_data(r)
            if has_data:
                r['_data_type'] = data_type
                data_records.append(r)
        
        print(f"Classifying {len(data_records)} records with data...")
        
        # Batch classify
        texts = [self.get_text(r) for r in data_records]
        predictions = self.model.predict(texts)
        probabilities = self.model.predict_proba(texts)
        
        results = []
        for i, r in enumerate(data_records):
            pred = predictions[i]
            probs = probabilities[i]
            
            if isinstance(pred, str):
                label = pred
            else:
                label = self.LABELS[int(pred)]
            
            results.append({
                'id': str(r.get('id', '')),
                'title': r.get('metadata', {}).get('title', '')[:150],
                'url': f"https://zenodo.org/records/{r.get('id', '')}",
                'label': label,
                'prob_eye_imaging': float(probs[2]),
                'confidence': float(max(probs)),
            })
        
        return results
    
    def save(self, output_dir: Path):
        """Save the trained model."""
        if self.model:
            self.model.save_pretrained(str(output_dir))
            print(f"Model saved to {output_dir}")


if __name__ == "__main__":
    # Example usage
    classifier = EyeImagingClassifier()
    classifier.train()
    
    # Load metadata and classify
    metadata_dir = Path(__file__).parent.parent / "data" / "zenodo_metadata"
    records = []
    for f in metadata_dir.glob("*.json"):
        with open(f) as fp:
            records.append(json.load(fp))
    
    results = classifier.classify(records)
    eye_imaging = [r for r in results if r['label'] == 'EYE_IMAGING']
    
    print(f"\nFound {len(eye_imaging)} eye imaging datasets")
    
    # Save results
    output_file = Path(__file__).parent.parent / "results" / "zenodo_eye_imaging.json"
    with open(output_file, 'w') as f:
        json.dump(eye_imaging, f, indent=2)

