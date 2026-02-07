#!/usr/bin/env python3
"""
ENVISION: Eye Imaging Dataset Classification

SetFit Few-Shot Classifier for Eye Imaging Dataset Detection
Uses Alibaba-NLP/gte-large-en-v1.5 sentence transformer with 4-class classification:
  - 3: EYE_IMAGING - Actual eye imaging datasets (fundus, OCT, OCTA, cornea, etc.)
  - 2: EYE_SOFTWARE - Code, tools, models for eye imaging (no actual data)
  - 1: EDGE_CASE - Eye research (papers, reviews, non-imaging data)
  - 0: NEGATIVE - Not eye-related at all

Usage:
    python -m envision.classifier
"""

import json
import os
from pathlib import Path
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

import torch
from setfit import SetFitModel, Trainer, TrainingArguments
from datasets import Dataset

# Model configuration
MODEL_NAME = "Alibaba-NLP/gte-large-en-v1.5"
LABELS = ["NEGATIVE", "EDGE_CASE", "EYE_SOFTWARE", "EYE_IMAGING"]

# ============================================================
# TRAINING DATA - Curated examples
# ============================================================

# POSITIVE (label=2): Actual eye imaging datasets with real image data
POSITIVE_EXAMPLES = [
    # From white paper / known benchmarks
    "Dataset from fundus images for the study of diabetic retinopathy progression",
    "Optical Coherence Tomography Angiography-OCTA Dataset for Diabetic Retinopathy",
    "Indian Diabetic Retinopathy Image Dataset (IDRiD) — Segmentation and Grading Challenge",
    "Retinal Fundus Multi-Disease Image Dataset (RFMiD) 2.0",
    "Rotterdam EyePACS AIROGS train set - fundus images for glaucoma detection",
    "JustRAIGS challenge training data set - Justified Referral in AI Glaucoma Screening",
    "OLIVES Dataset: Ophthalmic Labels for Investigating Visual Eye Semantics",
    "RVD: A Handheld Device-Based Fundus Video Dataset for Retinal Vessel Segmentation",
    "High-resolution structural and functional retinal imaging in mice",
    "Multi-modal spatiotemporal phenotyping of human retinal organoid development",
    "2023 IEEE SPS Video and Image Processing (VIP) Cup: Ophthalmic Biomarker Detection",
    "DERMA-OCTA: OCT Angiography images for skin microvascular analysis",
    "Abca4 inhibition in a cone-rich rodent leads to Stargardt Disease OCT and fundus images",
    "Diabetic Glaucoma dataset combining ORIGA, REFUGE, ACRIMA fundus images",
    "OCT-A mosaicking dataset for retinal vessel analysis",
    "UTHealth - Fundus and Synthetic OCT-A Dataset (UT-FSOCTA)",
    "Myopic Maculopathy Analysis Challenge 2023 - fundus image dataset",
    "Retinal vessel segmentation challenge dataset DRIVE STARE CHASE_DB1",
    "Glaucoma OCT dataset with RNFL thickness measurements",
    "Age-related macular degeneration OCT B-scan image dataset",
    "Heidelberg Spectralis OCT scans for diabetic macular edema",
    "Zeiss Cirrus HD-OCT dataset for glaucoma progression analysis",
    "Topcon 3D OCT fundus and cross-sectional images",
    "Fluorescein angiography dataset for choroidal neovascularization",
    "Fundus photography dataset for optic disc and cup segmentation",
    "Retinal OCT images with drusen and geographic atrophy labels",
    "OCTA dataset showing foveal avascular zone measurements",
    "Corneal topography images for keratoconus detection",
    "Anterior segment OCT dataset for angle closure glaucoma",
    "Slit lamp photography dataset for cataract grading",
    "Multi-Disease Detection in Retinal Imaging dataset",
    "Retinal Wave Dataset - calcium imaging of developing retina",
    "Circuit mechanisms underlying embryonic retinal waves dataset",
    "Evaluation benchmark for natural robustness of retinal vessel segmentation",
    "GWAS Summary Statistics For Eye Imaging Traits",
    "Fundus vessel phenotypes quantitative trait dataset",
    "Probabilistic volumetric speckle suppression in OCT using deep learning",
    "Optical coherence tomography radiation cataract image dataset",
    "HRF-Seg+: A Multi-Structure Annotated Fundus Image Dataset",
    "Multimodal OCTA and Fundus Image dataset for diabetic retinopathy detection",
    "Iraqi Retinal Fundus Diabetic Retinopathy Dataset IRFDRD",
    "OCT Fundus Registration dataset for multimodal retinal analysis",
    "EyeLab: Python package for OCT and fundus image processing",
    "Fiji-mCNVImageAnalysisTool for choroidal neovascularization in OCTA",
    "Automatic Choroid Vascularity Index Calculation in OCT Images",
    "Topological characterization of the retinal microvascular network",
    "ResNet-50 classifiers and diffusion models trained on retinal fundus images",
    "JRC-Multi-Modal Retinal Vessel Segmentation dataset",
    "A Fundus Image Dataset for Domain Generalization in Joint Optic Disc and Cup Segmentation",
    "Flexible corneal neurotechnology reveals in-vivo pathological cornea imaging",
    "CeraMIRScan: Mid-infrared OCT Scan Dataset for ophthalmic applications",
    "qtOCT: quantitative transmission optical coherence tomography dataset",
    "Retinal S-cone specific anatomical and physiological data",
    "Nonlinear spatial integration allows the retina to detect the direction of motion",
    "Thrombospondin-1 Mediates Axon Regeneration in Retinal Ganglion Cells",
    "Metabolomics of mouse retina and optic nerve",
    "Optic nerve injury impairs intrinsic mechanisms underlying early eye imaging",
    "Metabolomics of ocular hypertensive rat optic nerve",
    "Mammalian animal and human retinal organ culture imaging data",
    "Data from Analysis of potential ischemic effect of intravitreal anti-VEGF OCT",
    "Photodynamic Ocular Drug Delivery System with OCT monitoring",
    "Spontaneous retinal reperfusion of capillary nonperfusion OCT and fundus",
    "Analysis on Multimodal Imaging of stealth Choroidal Neovascularization OCTA",
    "Longitudinal changes in retinal microstructures OCT imaging data",
    "Macular Drusen histology and OCT correlation dataset",
    "Data to Choroidal changes in intermediate age-related macular degeneration",
    "Generalized Analysis of Vessels in Eye GAVE Challenge dataset",
    "Automated fundus image quality assessment and segmentation dataset",
    "Diabetic Retinopathy Detection using Retinal Images dataset",
    "Optic disc localization using graph traversal algorithm dataset",
    "An Image Processing Algorithm to Detect Exudates in Fundus Images",
    "Binary operation based hard exudate detection fundus dataset",
    "A Review on Automatic Detection and Recognition of Hard Exudates",
    "A deep learning approach based on stochastic gradient descent for DR detection",
    "EXUDATES DETECTION FROM DIGITAL FUNDUS IMAGE dataset",
    "COMPARATIVE STUDY OF DIABETIC RETINOPATHY K-NN dataset",
    "AN AUTOMATIC SCREENING METHOD TO DETECT OPTIC DISC dataset",
    "Fundus Fluorescein Angiography imaging dataset",
    "Structural-Functional Transition in Glaucoma Assessment imaging data",
    "Identification of ocular disease from fundus images using deep learning",
    "To Assess Characteristics of Individuals with Disc Hemorrhage fundus imaging",
    "Prevalence Risk Factors Clinical Correlates Age-related Macular Degeneration imaging",
    "ResNet-n/DR Automated diagnosis of diabetic retinopathy fundus dataset",
    "Eye fundus oxygenation mapping from color retinographs dataset",
    "Machine learning classifiers for detection of glaucoma OCT dataset",
    "Enhancing Retinal Disease Detection with Swin Transformer fundus dataset",
    "Development of hybrid framework to characterize red lesions in fundus images",
    "Diabetic retinopathy classification using deep convolutional neural networks fundus",
    "EARLY DETECTION OF HIGH BLOOD PRESSURE AND DIABETIC RETINOPATHY fundus images",
    "Diagnosis Of Diabetic Retinopathy: fundus image analysis dataset",
    "FUNDUS IMAGES FOR DIAGNOSIS OF DIABETIC RETINOPATHY dataset",
    "A Comprehensive Survey of Deep Learning for Diabetic Retinopathy dataset",
    "anithaj17/RetinoNet-DR-Classification fundus image dataset",
    "AMikroulis/octopus OCT image processing dataset",
    "Retinal status analysis method based on feature extraction OCT dataset",
    "Data from Inactivation of adenosine receptor retinal imaging",
    "Polarisation camera dSTORM datasets of retinal cells",
    "Scanning dynamic light scattering optical coherence tomography retinal flow",
    "MedIMeta: multi-domain medical imaging including retinal fundus",
]

# SOFTWARE (label=2): Code, tools, models for eye imaging (NOT actual data)
SOFTWARE_EXAMPLES = [
    # GitHub repos with code
    "linchundan88/Fundus-image-preprocessing: fundus image preprocessing Python code",
    "NIH-NEI/oct-image-segmentation-models: v0.8.2 trained model weights",
    "optic-nerve-cnn: First version of the software neural network",
    "Corneal-Endothelium-Data-Annotation-Tool: annotation labeling software",
    "FundusImageToolbox: Python package fundus image processing library",
    "OCTAVA: open-source toolbox quantitative analysis OCT angiography",
    "RetinoNet-DR-Classification: deep learning code diabetic retinopathy",
    "oct-to-tiff: command line tool OCT angiography converter",
    "optic-disc-segmentation-drishtigs: segmentation algorithm implementation",
    "QiYanPitt/AMDprogressCNN: Late AMD Fundus Image Prediction model",
    # Model weights only
    "Deep learning model weights trained on fundus images PyTorch",
    "Pretrained neural network OCT segmentation model weights only",
    "ResNet-50 classifiers trained on retinal fundus model weights",
    "ONNX model weights retinal vessel segmentation inference",
    "PyTorch checkpoint OCT layer segmentation neural network",
    "Segmentation model weights diabetic retinopathy detection",
    # Software packages
    "Python package retinal image preprocessing pip install",
    "MATLAB toolbox fundus image analysis code only",
    "ImageJ plugin OCT visualization and measurement",
    "Fiji macro optic nerve fiber layer analysis",
    "R package macular thickness statistical analysis",
    # Code repositories
    "Source code implementation retinal vessel extraction",
    "Algorithm implementation optic disc detection CNN",
    "Code repository deep learning diabetic retinopathy",
    "GitHub release fundus segmentation neural network",
    "Jupyter notebook tutorial OCT image classification",
    "Caserel: Open Source Software Computer-aided Segmentation Retinal Layers",
    "duke-lungmap-team/odifmap: image processing code publication",
    "young-oct/OCT-denoising: denoising algorithm code repository",
    "costapt/vess2ret: vessel to retina synthesis code",
]

# EDGE CASES (label=1): Eye/vision research but NOT actual imaging datasets
EDGE_CASES = [
    # Papers about eye imaging (not datasets)
    "A Review of Deep Learning Methods for Diabetic Retinopathy Detection",
    "Survey of Machine Learning Techniques for Glaucoma Diagnosis",
    "Advances in Optical Coherence Tomography Technology Review Article",
    "Clinical Guidelines for Diabetic Eye Screening",
    "Comparison of OCT Devices: A Systematic Review",
    "Deep Learning in Ophthalmology: A Comprehensive Review",
    "Artificial Intelligence in Retinal Disease Detection Review",
    "State of the Art in Fundus Image Analysis Survey",
    "Future Directions in Ophthalmic Imaging Technology",
    "Machine Learning for Age-Related Macular Degeneration: A Review",
    # Eye research but not imaging
    "Genetic factors in age-related macular degeneration GWAS meta-analysis",
    "Molecular mechanisms of retinal ganglion cell death in glaucoma",
    "Pharmacological treatment options for diabetic macular edema",
    "Risk factors for progression of diabetic retinopathy clinical study",
    "Visual acuity outcomes after anti-VEGF therapy clinical trial",
    "Intraocular pressure measurement techniques comparison study",
    "Epidemiology of myopia in Asian populations survey",
    "Cataract surgery outcomes in diabetic patients retrospective analysis",
    "Color vision deficiency prevalence in school children",
    "Visual field testing protocols for glaucoma clinical practice",
    # Non-imaging eye data
    "Electronic health records analysis of glaucoma treatment patterns",
    "Patient-reported outcomes in dry eye disease questionnaire data",
    "Healthcare costs of diabetic eye disease economic analysis",
    "Ophthalmologist workforce distribution geographic study",
    "Barriers to diabetic eye screening qualitative interview data",
    "Adherence to glaucoma medication patient diary data",
    "Visual impairment and quality of life survey responses",
    "Telemedicine in ophthalmology implementation analysis",
    "Eye care access in rural communities demographic data",
    "Waiting times for cataract surgery administrative data",
    # Code/software without data
    "Python package for retinal image preprocessing",
    "Deep learning framework for fundus image segmentation code only",
    "OCT image reconstruction algorithm implementation",
    "Retinal vessel extraction software repository",
    "Optic disc detection neural network model weights",
    "Diabetic retinopathy grading API documentation",
    "Fundus image augmentation library code",
    "DICOM viewer for ophthalmic images software",
    "OCT visualization toolkit implementation",
    "Retinal layer segmentation algorithm code repository",
    # Adjacent but different imaging
    "Brain MRI analysis for Alzheimer's disease detection",
    "Cardiac CT angiography for coronary artery disease",
    "Dermatology skin lesion classification dataset",
    "Dental X-ray caries detection images",
    "Chest X-ray pneumonia detection dataset",
    "Mammography breast cancer screening images",
    "Histopathology slide analysis for cancer diagnosis",
    "Ultrasound imaging for liver disease assessment",
    "PET scan analysis for neurological disorders",
    "Spine MRI for degenerative disc disease",
    # Vision/eye related but not ophthalmic imaging
    "Eye tracking data for attention research",
    "Gaze estimation dataset for human-computer interaction",
    "Pupil dilation response to emotional stimuli",
    "Saccade patterns in reading comprehension study",
    "Visual search behavior eye movement data",
    "Fixation duration analysis for cognitive load",
    "Eye blink detection for drowsiness monitoring",
    "Iris recognition biometric dataset",
    "Facial expression analysis including eye region",
    "Driver attention monitoring eye tracking",
    # Generic OCT (not ophthalmic)
    "OCT for industrial material inspection dataset",
    "Optical coherence tomography in dermatology skin imaging",
    "OCT imaging of atherosclerotic plaque in arteries",
    "Dental OCT for tooth structure analysis",
    "OCT for art conservation painting analysis",
    "Industrial OCT for semiconductor inspection",
    "OCT in cardiology intravascular imaging",
    "Non-destructive testing using OCT",
    "OCT for pharmaceutical tablet coating analysis",
    "Ceramic quality inspection using OCT",
    # Biological research with eye terms
    "Drosophila compound eye development gene expression",
    "Zebrafish eye regeneration molecular analysis",
    "Mouse retinal development transcriptomics",
    "Chicken embryo eye formation RNA sequencing",
    "Frog photoreceptor electrophysiology recordings",
    "Squid giant axon eye homolog studies",
    "Insect compound eye optics physics modeling",
    "Cephalopod camera eye evolution genomics",
    "Spider eye arrangement morphological analysis",
    "Mantis shrimp visual system spectral analysis",
    # Ambiguous terms that aren't eye imaging
    "Digital fundus thermometry for fever screening",
    "Ocular surface temperature measurement",
    "Tear film stability analysis without imaging",
    "Contrast sensitivity function psychophysics",
    "Dark adaptation curve measurements",
    "Electroretinography signal analysis only",
    "Visual evoked potential recordings",
    "Optical properties of crystalline lens in vitro",
    "Corneal biomechanics simulation data",
    "Aqueous humor proteomics analysis",
]

# NEGATIVE (label=0): Clearly not eye-related
NEGATIVE_EXAMPLES = [
    # Completely unrelated domains
    "Climate change impact on coral reef ecosystems dataset",
    "COVID-19 genome sequencing and variant analysis",
    "Electric vehicle battery performance testing data",
    "Social media sentiment analysis Twitter dataset",
    "Stock market prediction historical price data",
    "Natural language processing benchmark dataset",
    "Robot navigation and path planning simulation",
    "Music genre classification audio features",
    "Speech recognition multilingual corpus",
    "Protein structure prediction AlphaFold data",
    "Urban traffic flow optimization dataset",
    "Earthquake seismic wave recordings",
    "Satellite imagery land use classification",
    "Agricultural crop yield prediction dataset",
    "Air quality monitoring sensor data",
    "Ocean temperature salinity measurements",
    "Forest fire detection and spread modeling",
    "Wind turbine power output dataset",
    "Solar panel efficiency measurements",
    "Smart grid energy consumption patterns",
    # Biology but not eye
    "Human gut microbiome metagenomic sequencing",
    "Cancer cell line drug response screening",
    "Plant root architecture phenotyping images",
    "Bacterial biofilm formation time lapse",
    "Yeast protein interaction network",
    "Mouse brain connectome neural tracing",
    "Human genome whole exome sequencing",
    "Single cell RNA sequencing pancreas",
    "Epigenome methylation profiling data",
    "Metabolomics of liver disease samples",
    # Computer science
    "Image classification benchmark ImageNet",
    "Object detection COCO dataset",
    "Face recognition LFW dataset",
    "Handwriting recognition MNIST digits",
    "Autonomous driving perception dataset",
    "Video action recognition UCF101",
    "3D point cloud semantic segmentation",
    "Document layout analysis dataset",
    "Scene text recognition benchmark",
    "Pose estimation human keypoints",
    # Random technical
    "Compiler optimization benchmark suite",
    "Database query performance testing",
    "Network intrusion detection logs",
    "Software bug report classification",
    "Code review comment sentiment",
    "API usage pattern analysis",
    "Container orchestration metrics",
    "Microservice latency measurements",
    "Cloud resource utilization data",
    "DevOps pipeline performance metrics",
    # Humanities and social science
    "Historical newspaper digitization project",
    "Archaeological site survey mapping",
    "Linguistic corpus for dialect analysis",
    "Museum artifact catalog metadata",
    "Legal case document classification",
    "Political speech transcript analysis",
    "Immigration policy document corpus",
    "Educational assessment score data",
    "Survey responses on housing affordability",
    "Census demographic statistics",
    # More random
    "Weather forecast model output data",
    "Cryptocurrency transaction network",
    "Hotel review sentiment dataset",
    "Recipe ingredient network analysis",
    "Movie recommendation collaborative filtering",
    "Book summary text generation",
    "News article topic classification",
    "Sports statistics player performance",
    # Taxonomy papers with FIGURES (major false positive pattern)
    "FIGURES 1-10 in Taxonomic revision of genus species description",
    "Figs 12-19 in Review of insect family Hemiptera Pentatomidae",
    "FIGURES 45-53 in Introduction to Scydmaeninae Coleoptera beetles",
    "FIGURE 6 in Additions to the description of new beetle species",
    "Figs 7-11 in Review of Parachinavia insect taxonomy",
    "FIGURES 14-19 in World genera of arthropod taxonomy review",
    "FIGURE 15 in Combining morphological and molecular data new species",
    "Figure 4 in The neurocranium of fish species morphology anatomy",
    "FIGURES 64-68 in Franz and Nogunius genus description taxonomy",
    "FIGURES 211-215 in Introduction to beetle family Coleoptera",
    "Figs 1-5 in New species description and taxonomic placement",
    "FIGURES 102-104 in curse of Horaeomorphus taxonomy revision",
    "FIGURE 33 in Kirkegaardia polychaete worm new species",
    # Non-ophthalmic medical imaging
    "lymph node ultrasound image dataset pathology",
    "PDAC tumour and vessel segmentation pancreatic cancer",
    "Aortic valve calcification CT scan imaging",
    "Atherosclerotic plaque OCT cardiovascular imaging",
    "Lung nodule detection chest X-ray dataset",
    "Brain MRI Alzheimer disease classification",
    "Cardiac ultrasound echocardiography dataset",
    "Mammography breast cancer detection images",
    "Skin lesion dermoscopy melanoma dataset",
    "Liver CT segmentation dataset",
    # Fossils and paleontology
    "Fosil bivalvo fossil bivalve specimen",
    "Fossil shell morphology museum specimen",
    "Paleontology specimen 3D scan dataset",
    # Robotics with "eye" in name but not ophthalmic
    "Hand-eye camera calibration robotics dataset",
    "Robot eye camera sensor data manipulation",
    "Machine vision inspection camera system",
    # Acoustic and non-optical imaging
    "NAH rectangular plate Nearfield Acoustic Holography",
    "Ultrasound transducer beam pattern dataset",
    "Sonar imaging underwater acoustic data",
    "Gaming leaderboard historical data",
    "E-commerce product catalog data",
    "Tourism destination visitor statistics",
    "Fashion image style classification",
    "Food image recognition dataset",
    "Indoor scene recognition benchmark",
    "Texture classification material images",
    "Furniture detection room layout",
    "Vehicle make model classification",
    "Bird species identification dataset",
    "Flower recognition 102 categories",
    "Dog breed classification Stanford Dogs",
    "Butterfly species identification images",
    "Insect pest detection agricultural",
    "Fish species classification underwater",
    "Wildlife camera trap image dataset",
    "Plankton microscopy classification",
    "Cell microscopy segmentation HeLa",
    "Pollen grain identification dataset",
    "Mineral classification geological samples",
    "Timber species identification wood",
    "Fabric defect detection textile",
    # FALSE POSITIVES from manual review of v6 results
    # Acousto-optics and general optics (not eye)
    "Broadband acousto-optic modulators on Silicon Nitride photonics",
    "Artifacts in Optical Projection Tomography general imaging",
    "Optic flow and odometry data from intelrealsense camera robotics",
    "Interstitial null-distance time-domain diffuse optical spectroscopy",
    # Climate/Earth/Geography
    "iris-esmf-regrid Earth System Modeling Framework climate software",
    "Altotiberina Low-angle normal fault seismic seismology",
    "Refined Terrace Extraction Method geography terrain analysis",
    "Lithospheric structure geological analysis dataset",
    "integrated multi-scale approach to habitat modelling ecology",
    "global variations in directional solar radiation exposure geography",
    "IRIS Carbon Mapping Project carbon emissions dataset",
    "Improved River Slope Datasets United States Hydrofabrics hydrology",
    # Cancer/Medical (non-ophthalmic)
    "Tracking Carboplatin Chemoresistance in Ovarian Cancer dataset",
    "Subtype identification clear cell renal cell carcinoma kidney cancer",
    "aortic dataset cardiovascular vessel segmentation",
    "Deep learning aneurysm detection CT angiography brain vessels",
    "Images from carotid artery patients cardiovascular disease",
    "post-dive precordial subclavian Doppler ultrasound diving medicine",
    "Deep Learning Segmentation Atherosclerotic Plaque cardiovascular",
    "pLGG Radioimmunomics pediatric low-grade glioma brain tumor",
    "Ex Vivo MRI Frontotemporal Lobar Degeneration brain imaging",
    "Intracranial Sonodynamic Therapy brain treatment dataset",
    # Insects/Animals (non-ophthalmic)
    "Adult female Aedes albopictus mosquito specimen imaging",
    "Female pupa Aedes albopictus mosquito developmental imaging",
    "Comparative larval ontogeny fish species developmental anatomy",
    "Hadzinia ferrani Opiliones Nemastomatidae spider taxonomy",
    "First record genus Tanaostigma Hymenoptera Chalcidoidea wasp taxonomy",
    "Refractive index tomography chitin bristles chaetae marine worms",
    "Methodology labeled image datasets entomological specimens insects",
    # Chemistry/Physics/Materials Science
    "Newman-planar-elasticity computational physics simulation",
    "Enhanced Photoactivity Carbon Nanodots Zinc Phthalocyanine photochemistry",
    "Fluorescein-switching lateral flow assay chemistry biosensor",
    "CtBP2 MD trajectories molecular dynamics protein simulation",
    "All-atom accelerated molecular dynamics Filamin-A protein",
    "QuantumScents molecular chemistry scent compound dataset",
    "Influence Firing Temperature Silver-Aluminium Paste solar cell fabrication",
    "Boron-Emitter Development TOPCon c-Si Solar Cells photovoltaics",
    "Photo-physical characterization brominated fluorophore chemistry",
    "MicroED datasets hemin biotin electron crystallography",
    "Quantifying impact electric field computational physics",
    "Accurate Modeling Bromide Iodide Hydration molecular chemistry",
    "Carrier Diffusion Recombination semiconductor physics perovskite",
    "Nanoparticle doping molten-core fiber optics materials",
    "Grain orientation angle incidence beam polarization materials",
    "Observing impacts luminescence spectroscopy materials",
    "magnetic topology neutral trapping plasma physics tokamak",
    "Unraveling hierarchical structure saturated monoacid triglycerides lipids",
    # General microscopy/imaging (non-eye)
    "Training data bead stacks Zeiss microscope calibration beads",
    "COLMAP outputs Gaussian Splatting Reconstruction 3D computer vision",
    "Direct STORM imaging transcription element microscopy super-resolution",
    "Cross-polarized light microscopy Coccospheres marine microfossils",
    "Cryo-electron microscopy thin vitreous biological samples cryoEM",
    "Raw confocal imaging FRAP protein dynamics general microscopy",
    "Evaluation strategy image acquisition protocols confocal microscopy",
    "STORM Vectashield datasets Tubulin cytoskeleton microscopy",
    "Objective evaluation image quality planning CT radiation therapy",
    "In Situ Volumetric Imaging FRESH 3D Bioprinted Constructs bioprinting",
    "Thermal-plex fluidic-free rapid sequential multiplexed imaging proteomics",
    # Brain/Neuro imaging (not eye)
    "Histological validation per-bundle water diffusion brain tractography",
    "Large-scale in vivo acquisition brain vasculature cerebral vessels",
    "Chronic social defeat stress meningeal neutrophilia brain inflammation",
    "Tracing pathways high-resolution tractography brain connectivity",
    "BRAVE-NET Fully Automated Arterial Brain Vessel segmentation",
    "Correlated variability primate superior colliculus brain neural",
    # Other non-eye datasets
    "Widefield time-lapse Drosophila embryos developmental biology fly",
    "Transcriptomic profiling immune cells pleural effusions lung cancer",
    "3D-printed adapters standardized radiometric photometric calibration equipment",
    "Patterns Gene Expression Splicing Allele-Specific Expression genomics",
    "Modular Tunable Gene Expression Sensing synthetic biology circuits",
    "FIGURE characterisation stem proliferating cells generic figure",
    "Project Gap Junctions microelectrode array electrophysiology",
    "Objective Autonomic Signatures Tinnitus hearing audiology",
    "IML-DKFZ/fd-shifts machine learning code repository",
    "Aspergillus flavus germination fungal pathogen imaging",
    "Intrapartum Ultrasound Grand Challenge obstetric fetal imaging",
    "Correlating Spectral Properties complex mineral samples mineralogy",
    "YOLO Based Machine Learning general object detection computer vision",
    "Freehand ultrasound without external trackers general ultrasound imaging",
    "scRNAseq datasets cranial myogenic progenitors muscle development",
    "Confocal fluorescence microscopy dentinal porosity dental imaging",
    "Circadian rapid eye movement sleep expression sleep research polysomnography",
    "Label-free metabolic fingerprinting motile mammalian spermatozoa fertility",
    "OCT IMAGE DATASET RADIATION DERMATITIS skin dermatology",
    "Tissue-Level Dimerization Analysis AtLEA proteins Arabidopsis plant biology",
    "Ear Datasets hearing auditory speech recognition",
    "Exchange interaction FAD biradical magnetic resonance chemistry",
    "AF driver detection pulmonary vein area cardiac arrhythmia",
    "Roman-Multi-Planetary-data astronomy exoplanet detection",
    "Compatible interaction experiment Aegilops cylindrica wheat pathogen plant",
    "Raw EOG Data electrooculography electrical eye movement recording",
    "CEAP-360VR Continuous Physiological Behavioral Emotion VR annotation",
    "Pultruded carbon fiber profiles 3D x-ray tomography composites materials",
    "Optical electronic signal stabilization plasmonic fiber optic gas sensor",
    "Propulsion nano microcones traveling ultrasound wave acoustic manipulation",
    "Shear Shock Waves Haptic Holography Focused Ultrasound haptics",
    "CeraMIRScan Mid-infrared OCT Ceramic Quality industrial inspection",
    "Dosage effect Copy Number Variation Epilepsy genetic neurology",
    "Field-Effect Transistor Plasmonic Fiber Optic Gate Electrode electronics",
    "Early Onset TAAD cohort genetic cardiovascular aortic disease",
    # Exact titles of remaining false positives from v6 run3
    "Transcriptomic profiling of immune cells in pleural effusions identifies macrophages",
    "fqjin/skin-segmentation skin lesion segmentation code",
    "Subtype identification and clinical application of clear cell renal cell carcinoma",
    "A dataset of global variations in directional solar radiation exposure for ocular surface",
    "Pre-training with simulated ultrasound images for breast mass segmentation",
    "aortic dataset for DB-SNet cardiovascular aortic segmentation",
    "Ground truth labels for BRAVE-NET Fully Automated Arterial Brain Vessel Segmentation",
    "AstroFatheddin/Roman-Multi-Planetary-data astronomy exoplanet",
    "Dataset for Segmentation and Multi-Timepoint Tracking of 3D Cancer Organoids",
    "Dataset_1 of AF driver detection in pulmonary vein area cardiac arrhythmia",
    "Data from Dichoptic metacontrast masking functions to infer transmission delay",
    "IRIS Carbon Mapping Project Curated Dataset carbon emissions",
]


def main():
    """Train and run the 4-class eye imaging classifier."""
    import csv
    from collections import Counter
    
    # Configuration - edit for your environment
    BASE_DIR = Path(__file__).resolve().parent.parent
    # Use new clean scraped data (datasets only, with ZIP inspection)
    METADATA_DIR = BASE_DIR / "data" / "metadata" / "zenodo"
    OUTPUT_DIR = BASE_DIR / "models" / "setfit_v6"
    RESULTS_DIR = BASE_DIR / "results"
    
    # GPU setup - use GPU with most free memory
    import subprocess
    try:
        result = subprocess.run(['nvidia-smi', '--query-gpu=index,memory.free', '--format=csv,noheader,nounits'],
                                capture_output=True, text=True)
        gpus = [(int(line.split(',')[0]), int(line.split(',')[1])) for line in result.stdout.strip().split('\n')]
        best_gpu = max(gpus, key=lambda x: x[1])[0]
        os.environ["CUDA_VISIBLE_DEVICES"] = str(best_gpu)
        print(f"Selected GPU {best_gpu} with most free memory")
    except:
        os.environ["CUDA_VISIBLE_DEVICES"] = "0"
    DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
    
    print("=" * 70)
    print("ENVISION: Eye Imaging Dataset Classifier (4-class)")
    print(f"Model: {MODEL_NAME}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"Device: {DEVICE}")
    if DEVICE == "cuda":
        print(f"GPU: {torch.cuda.get_device_name(0)}")
    print("=" * 70)
    
    print(f"\nTraining examples:")
    print(f"  POSITIVE (eye imaging): {len(POSITIVE_EXAMPLES)}")
    print(f"  SOFTWARE (code/tools): {len(SOFTWARE_EXAMPLES)}")
    print(f"  EDGE_CASE (research): {len(EDGE_CASES)}")
    print(f"  NEGATIVE (unrelated): {len(NEGATIVE_EXAMPLES)}")
    
    # Prepare dataset
    print(f"\nPreparing training dataset...")
    train_texts = POSITIVE_EXAMPLES + SOFTWARE_EXAMPLES + EDGE_CASES + NEGATIVE_EXAMPLES
    train_labels = (
        [3] * len(POSITIVE_EXAMPLES) +
        [2] * len(SOFTWARE_EXAMPLES) +
        [1] * len(EDGE_CASES) +
        [0] * len(NEGATIVE_EXAMPLES)
    )
    
    train_dataset = Dataset.from_dict({
        "text": train_texts,
        "label": train_labels
    })
    print(f"Training dataset: {len(train_dataset)} examples")
    
    # Check for --classify-only flag to skip training
    import sys
    classify_only = '--classify-only' in sys.argv
    
    if classify_only and (OUTPUT_DIR / "model.safetensors").exists():
        # Load existing model
        print(f"\n{'='*70}")
        print(f"Loading existing model from {OUTPUT_DIR}")
        print("=" * 70)
        
        # Workaround for SetFit bug with local model loading
        from sentence_transformers import SentenceTransformer
        import joblib
        
        # Load the sentence transformer backbone
        st_model = SentenceTransformer(str(OUTPUT_DIR), trust_remote_code=True)
        st_model = st_model.to(DEVICE)
        
        # Load the classification head
        model_head = joblib.load(OUTPUT_DIR / "model_head.pkl")
        
        # Create a minimal wrapper for predictions
        class LoadedModel:
            def __init__(self, encoder, head, labels):
                self.encoder = encoder
                self.head = head
                self.labels = labels
            
            def predict(self, texts):
                embeddings = self.encoder.encode(texts, convert_to_numpy=True)
                return self.head.predict(embeddings)
            
            def predict_proba(self, texts):
                embeddings = self.encoder.encode(texts, convert_to_numpy=True)
                return self.head.predict_proba(embeddings)
        
        model = LoadedModel(st_model, model_head, LABELS)
        print("Model loaded successfully")
    else:
        # Train model
        print(f"\n{'='*70}")
        print(f"Training SetFit model with {MODEL_NAME}")
        print("=" * 70)
        
        model = SetFitModel.from_pretrained(
            MODEL_NAME,
            labels=LABELS,
            device=DEVICE,
            trust_remote_code=True,
        )
        
        args = TrainingArguments(
            output_dir=str(OUTPUT_DIR / "checkpoints"),
            batch_size=16,
            num_epochs=2,
            evaluation_strategy="no",
            save_strategy="no",
            logging_steps=50,
        )
        
        trainer = Trainer(
            model=model,
            args=args,
            train_dataset=train_dataset,
        )
        
        print("Starting training...")
        trainer.train()
        
        # Save model
        OUTPUT_DIR.mkdir(exist_ok=True, parents=True)
        model.save_pretrained(str(OUTPUT_DIR))
        print(f"Model saved to: {OUTPUT_DIR}")
    
    # Load and classify Zenodo records
    print(f"\n{'='*70}")
    print("Classifying Zenodo records")
    print("=" * 70)
    
    # Eye imaging file formats
    # Standard image formats
    IMG_EXTS = {'.jpg', '.jpeg', '.png', '.tif', '.tiff', '.bmp', '.gif'}
    # Medical/scientific imaging formats (eye imaging specific)
    MEDICAL_EXTS = {
        '.dcm', '.dicom',           # DICOM (standard medical)
        '.nii', '.nii.gz',          # NIfTI (neuroimaging, OCT volumes)
        '.mat',                      # MATLAB (common for OCT data)
        '.h5', '.hdf5',             # HDF5 (large imaging datasets) - NOT h5ad
        '.npy', '.npz',             # NumPy arrays
        # OCT-specific formats
        '.fds',                      # Topcon OCT
        '.e2e',                      # Heidelberg OCT
        '.vol',                      # Zeiss OCT volumes
        '.img',                      # Generic imaging
        '.oct',                      # Generic OCT
        '.fda',                      # Optovue OCT
    }
    # Archive formats (may contain imaging data)
    ARCH_EXTS = {'.zip', '.tar', '.gz', '.tar.gz', '.rar', '.7z'}
    
    # GWAS/Genomics file types to EXCLUDE (these are not eye imaging)
    GENOMICS_EXTS = {
        '.fasta', '.fa', '.fna',    # DNA/RNA sequences
        '.fastq', '.fq',            # Sequencing reads
        '.fastq.gz', '.fq.gz',      # Compressed reads
        '.h5ad',                     # AnnData (single-cell RNA-seq)
        '.bam', '.sam', '.cram',    # Alignments
        '.vcf', '.bcf', '.vcf.gz',  # Variants
        '.bed', '.gtf', '.gff',     # Genomic annotations
        '.gff3', '.bigwig', '.bw',  # More genomics
        '.cel', '.idat',            # Microarray
        '.loom',                     # Single-cell
    }
    
    ALL_DATA_EXTS = IMG_EXTS | MEDICAL_EXTS | ARCH_EXTS
    
    # External dataset link patterns
    DATASET_LINK_PATTERNS = [
        'kaggle.com', 'huggingface.co', 'github.com',
        'drive.google.com', 'osf.io', 'datadryad.org', 'dryad.org',
        'figshare.com', 'dataverse', 'openneuro.org',
        'physionet.org', 'synapse.org', 'grand-challenge.org'
    ]
    
    import re
    from html import unescape
    
    def strip_html(text):
        """Remove HTML tags from text."""
        if not text:
            return ""
        clean = re.sub('<[^<]+?>', ' ', text)
        return unescape(clean).strip()
    
    def extract_dataset_links(record):
        """Extract external dataset links from description and related identifiers."""
        links = []
        
        # Check description for links
        desc = record.get('metadata', {}).get('description', '')
        if desc:
            # Find URLs in description
            url_pattern = r'https?://[^\s<>"\']+|www\.[^\s<>"\']+' 
            urls = re.findall(url_pattern, desc)
            for url in urls:
                for pattern in DATASET_LINK_PATTERNS:
                    if pattern in url.lower():
                        links.append(url)
                        break
        
        # Check related_identifiers
        related = record.get('metadata', {}).get('related_identifiers', [])
        for rel in related:
            ident = rel.get('identifier', '')
            if any(p in ident.lower() for p in DATASET_LINK_PATTERNS):
                links.append(ident)
        
        # Check custom _dataset_links field from scraper
        custom_links = record.get('_dataset_links', [])
        if custom_links:
            for link in custom_links:
                if isinstance(link, str):
                    links.append(link)
                elif isinstance(link, dict):
                    # Handle dict format like {"url": "...", "type": "..."}
                    url = link.get('url', link.get('identifier', ''))
                    if url:
                        links.append(str(url))
        
        # Check _weblinks from scraper (data_platform type = GitHub, Kaggle, etc.)
        weblinks = record.get('_weblinks', [])
        for wl in weblinks:
            if isinstance(wl, dict) and wl.get('type') == 'data_platform':
                url = wl.get('url', '')
                if url:
                    links.append(str(url))
        
        # Deduplicate - ensure all items are strings
        unique_links = []
        seen = set()
        for link in links:
            link_str = str(link) if not isinstance(link, str) else link
            if link_str and link_str not in seen:
                seen.add(link_str)
                unique_links.append(link_str)
        
        return unique_links
    
    def has_data_files_or_links(record):
        """Check if record has data files OR external dataset links.
        Excludes records that ONLY have genomics files (GWAS, RNA-seq, etc.)
        """
        files = record.get('files', [])
        has_imaging_files = False
        has_only_genomics = True
        
        for f in files:
            name = f.get('key', '').lower()
            
            # Check for genomics files (to exclude)
            is_genomics = any(name.endswith(ext) for ext in GENOMICS_EXTS)
            
            # Check for imaging/data files
            is_imaging = any(name.endswith(ext) for ext in ALL_DATA_EXTS)
            
            if is_imaging and not is_genomics:
                has_imaging_files = True
                has_only_genomics = False
            elif is_imaging and is_genomics:
                # File matches both - consider as genomics
                pass
            elif not is_genomics and is_imaging:
                has_only_genomics = False
        
        # Include if has imaging files (and not only genomics)
        if has_imaging_files:
            return True
        
        # Check for external dataset links (still include these)
        if extract_dataset_links(record):
            return True
        
        return False
    
    def get_record_text(record):
        """Extract text for classification."""
        title = record.get('metadata', {}).get('title', record.get('title', ''))
        desc = strip_html(record.get('metadata', {}).get('description', ''))
        keywords = record.get('metadata', {}).get('keywords', [])
        if isinstance(keywords, list):
            keywords = ' '.join(keywords)
        return f"{title} {desc} {keywords}"
    
    def get_file_details(record):
        """Extract detailed file information."""
        files = record.get('files', [])
        
        file_names = []
        file_types = set()
        total_size = 0
        img_count = 0
        medical_count = 0
        archive_count = 0
        genomics_count = 0
        
        for f in files:
            name = f.get('key', '')
            size = f.get('size', 0)
            name_lower = name.lower()
            
            file_names.append(name)
            total_size += size
            
            # Check for genomics files first (to exclude from imaging counts)
            is_genomics = False
            for ext in sorted(GENOMICS_EXTS, key=len, reverse=True):
                if name_lower.endswith(ext):
                    file_types.add(ext)
                    genomics_count += 1
                    is_genomics = True
                    break
            
            if is_genomics:
                continue
            
            # Extract extension for imaging files
            for ext in sorted(ALL_DATA_EXTS, key=len, reverse=True):  # Check longer exts first
                if name_lower.endswith(ext):
                    file_types.add(ext)
                    if ext in IMG_EXTS:
                        img_count += 1
                    elif ext in MEDICAL_EXTS:
                        medical_count += 1
                    elif ext in ARCH_EXTS:
                        archive_count += 1
                    break
        
        return {
            'file_names': file_names[:20],  # First 20 files
            'file_types': sorted(file_types),
            'file_count': len(files),
            'img_count': img_count,
            'medical_count': medical_count,
            'archive_count': archive_count,
            'genomics_count': genomics_count,
            'total_size': total_size,
        }
    
    def get_metadata_details(record):
        """Extract rich metadata."""
        meta = record.get('metadata', {})
        
        # Keywords
        keywords = meta.get('keywords', [])
        if isinstance(keywords, str):
            keywords = [keywords]
        
        # Description (truncated, HTML stripped)
        desc = strip_html(meta.get('description', ''))[:500]
        
        # Related DOIs
        related_dois = []
        for rel in meta.get('related_identifiers', []):
            if rel.get('scheme') == 'doi':
                related_dois.append(rel.get('identifier', ''))
        
        return {
            'description': desc,
            'keywords': keywords[:10],  # First 10 keywords
            'access_right': meta.get('access_right', 'unknown'),
            'license': meta.get('license', {}).get('id', 'unknown'),
            'resource_type': meta.get('resource_type', {}).get('type', 'unknown'),
            'doi': meta.get('doi', ''),
            'related_dois': related_dois[:5],  # First 5 related DOIs
        }
    
    # Load records (each file is a single record)
    records = []
    json_files = list(METADATA_DIR.glob("*.json"))
    print(f"Found {len(json_files):,} metadata files")
    
    for json_file in sorted(json_files):
        try:
            with open(json_file) as f:
                record = json.load(f)
            # Add zenodo_id from record
            record['_zenodo_id'] = str(record.get('id', json_file.stem))
            if has_data_files_or_links(record):
                records.append(record)
        except Exception as e:
            pass  # Skip malformed files
    
    print(f"Loaded {len(records):,} records with data files or dataset links")
    
    # Classify
    print("Classifying...")
    BATCH_SIZE = 16  # Reduced batch size to avoid OOM during classification
    all_results = []
    
    for i in range(0, len(records), BATCH_SIZE):
        batch_records = records[i:i+BATCH_SIZE]
        batch_texts = [get_record_text(r) for r in batch_records]
        
        predictions = model.predict(batch_texts)
        probabilities = model.predict_proba(batch_texts)
        
        for j, r in enumerate(batch_records):
            pred = predictions[j]
            probs = probabilities[j]
            
            # Get detailed file info
            file_details = get_file_details(r)
            metadata_details = get_metadata_details(r)
            dataset_links = extract_dataset_links(r)
            
            # Handle both string labels and integer predictions (including numpy types)
            import numpy as np
            if isinstance(pred, (int, float, np.integer)):
                pred_int = int(pred)
            else:
                pred_int = {"NEGATIVE": 0, "EDGE_CASE": 1, "EYE_SOFTWARE": 2, "EYE_IMAGING": 3}.get(str(pred), 0)
            label = LABELS[pred_int]
            
            result = {
                # Identifiers
                'zenodo_id': r['_zenodo_id'],
                'doi': metadata_details['doi'],
                'url': f"https://zenodo.org/records/{r['_zenodo_id']}",
                
                # Classification
                'label': label,
                'confidence': float(max(probs)),
                'prob_eye_imaging': float(probs[3]),
                'prob_software': float(probs[2]),
                'prob_edge': float(probs[1]),
                'prob_negative': float(probs[0]),
                
                # Metadata
                'title': r.get('metadata', {}).get('title', '')[:200],
                'description': metadata_details['description'],
                'keywords': metadata_details['keywords'],
                'access_right': metadata_details['access_right'],
                'license': metadata_details['license'],
                'resource_type': metadata_details['resource_type'],
                
                # File details
                'file_types': file_details['file_types'],
                'file_names': file_details['file_names'],
                'file_count': file_details['file_count'],
                'img_count': file_details['img_count'],
                'medical_count': file_details['medical_count'],
                'archive_count': file_details['archive_count'],
                'genomics_count': file_details['genomics_count'],
                'size_mb': round(file_details['total_size'] / (1024*1024), 1),
                
                # External links
                'dataset_links': dataset_links,
                'related_dois': metadata_details['related_dois'],
            }
            
            all_results.append(result)
        
        if (i + BATCH_SIZE) % 500 == 0:
            print(f"  Processed {min(i + BATCH_SIZE, len(records)):,} / {len(records):,}")
    
    # Analyze results
    eye_imaging = [r for r in all_results if r['label'] == 'EYE_IMAGING']
    software = [r for r in all_results if r['label'] == 'EYE_SOFTWARE']
    edge_cases = [r for r in all_results if r['label'] == 'EDGE_CASE']
    negative = [r for r in all_results if r['label'] == 'NEGATIVE']
    
    print(f"\n{'='*70}")
    print("CLASSIFICATION RESULTS")
    print("=" * 70)
    print(f"  EYE_IMAGING:  {len(eye_imaging):,}")
    print(f"  EYE_SOFTWARE: {len(software):,}")
    print(f"  EDGE_CASE:    {len(edge_cases):,}")
    print(f"  NEGATIVE:     {len(negative):,}")
    
    # Analyze file types in eye imaging results
    print(f"\n{'='*70}")
    print("FILE TYPE DISTRIBUTION (EYE_IMAGING)")
    print("=" * 70)
    type_counts = Counter()
    for r in eye_imaging:
        for ft in r['file_types']:
            type_counts[ft] += 1
    for ft, count in type_counts.most_common(15):
        print(f"  {ft}: {count:,}")
    
    # Confidence distribution
    print(f"\n{'='*70}")
    print("CONFIDENCE DISTRIBUTION (EYE_IMAGING)")
    print("=" * 70)
    high_conf = [r for r in eye_imaging if r['confidence'] >= 0.95]
    med_conf = [r for r in eye_imaging if 0.80 <= r['confidence'] < 0.95]
    low_conf = [r for r in eye_imaging if r['confidence'] < 0.80]
    print(f"  High (≥0.95):    {len(high_conf):,}")
    print(f"  Medium (0.80-0.95): {len(med_conf):,}")
    print(f"  Lower (<0.80):   {len(low_conf):,}")
    
    # Records with external links
    with_links = [r for r in eye_imaging if r['dataset_links']]
    print(f"\n  Records with external dataset links: {len(with_links):,}")
    
    # Save results
    RESULTS_DIR.mkdir(exist_ok=True, parents=True)
    
    # Sort by confidence, then size
    eye_imaging.sort(key=lambda x: (-x['prob_eye_imaging'], -x['size_mb']))
    software.sort(key=lambda x: (-x['confidence'], -x['size_mb']))
    
    with open(RESULTS_DIR / 'zenodo_eye_imaging.json', 'w') as f:
        json.dump(eye_imaging, f, indent=2)
    
    with open(RESULTS_DIR / 'zenodo_software.json', 'w') as f:
        json.dump(software, f, indent=2)
    
    with open(RESULTS_DIR / 'zenodo_all_results.json', 'w') as f:
        json.dump(all_results, f, indent=2)
    
    print(f"\n{'='*70}")
    print("OUTPUT FILES")
    print("=" * 70)
    print(f"  Results: {RESULTS_DIR}")
    print(f"    - zenodo_eye_imaging.json ({len(eye_imaging):,} records)")
    print(f"    - zenodo_software.json ({len(software):,} records)")
    print(f"    - zenodo_all_results.json ({len(all_results):,} records)")
    print(f"  Model: {OUTPUT_DIR}")
    print(f"\nTimestamp: {datetime.now().isoformat()}")


if __name__ == "__main__":
    main()
