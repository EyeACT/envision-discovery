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


class EyeImagingClassifier:
    """Standalone eye imaging dataset classifier.

    Classifies metadata records into 4 classes:
      - EYE_IMAGING: Actual eye imaging datasets (fundus, OCT, OCTA, etc.)
      - EYE_SOFTWARE: Code, tools, models for eye imaging (no actual data)
      - EDGE_CASE: Eye research papers, reviews, borderline items
      - NEGATIVE: Unrelated domains

    Usage:
        >>> from envision import EyeImagingClassifier
        >>> clf = EyeImagingClassifier()
        >>> clf.classify("Retinal OCT dataset for diabetic retinopathy")
        {'label': 'EYE_IMAGING', 'confidence': 0.999, 'probabilities': {...}}
    """

    LABELS = LABELS

    def __init__(self, model_path=None, device=None):
        """Load a trained classifier model.

        Args:
            model_path: Path to saved model directory, or None for default location.
            device: "cuda", "cpu", or None for auto-selection.
        """
        if device is None:
            device = self._select_device()
        self._device = device

        if model_path is None:
            model_path = Path(__file__).resolve().parent.parent / "models" / "setfit_v6"
        else:
            model_path = Path(model_path)

        if (model_path / "model.safetensors").exists():
            self._load_local(model_path)
        else:
            raise FileNotFoundError(
                f"No trained model found at {model_path}. "
                f"Train one with EyeImagingClassifier.train() or envision-train."
            )

    def _load_local(self, model_path):
        """Load model from local directory."""
        from sentence_transformers import SentenceTransformer
        import joblib

        self._encoder = SentenceTransformer(str(model_path), trust_remote_code=True)
        self._encoder = self._encoder.to(self._device)
        self._head = joblib.load(model_path / "model_head.pkl")

    @staticmethod
    def _select_device():
        """Auto-select best available GPU or fall back to CPU."""
        import subprocess
        try:
            result = subprocess.run(
                ['nvidia-smi', '--query-gpu=index,memory.free',
                 '--format=csv,noheader,nounits'],
                capture_output=True, text=True,
            )
            gpus = [(int(line.split(',')[0]), int(line.split(',')[1]))
                    for line in result.stdout.strip().split('\n')]
            best_gpu = max(gpus, key=lambda x: x[1])[0]
            os.environ["CUDA_VISIBLE_DEVICES"] = str(best_gpu)
        except Exception:
            os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")
        return "cuda" if torch.cuda.is_available() else "cpu"

    def classify(self, metadata):
        """Classify a single metadata record.

        Args:
            metadata: dict with 'title', 'description', and/or 'keywords',
                     or a plain text string.

        Returns:
            dict with 'label', 'confidence', and 'probabilities'.
        """
        if isinstance(metadata, str):
            text = metadata
        else:
            text = self.extract_text(metadata)
        return self._predict_batch([text])[0]

    def classify_batch(self, records, batch_size=16):
        """Classify multiple metadata records.

        Args:
            records: list of dicts (with title/description/keywords) or strings.
            batch_size: batch size for inference.

        Returns:
            list of classification result dicts.
        """
        texts = []
        for r in records:
            if isinstance(r, str):
                texts.append(r)
            else:
                texts.append(self.extract_text(r))

        all_results = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            all_results.extend(self._predict_batch(batch))
        return all_results

    def _predict_batch(self, texts):
        """Run prediction on a batch of text strings."""
        import numpy as np

        embeddings = self._encoder.encode(texts, convert_to_numpy=True)
        predictions = self._head.predict(embeddings)
        probabilities = self._head.predict_proba(embeddings)

        results = []
        for i in range(len(texts)):
            pred = predictions[i]
            probs = probabilities[i]

            if isinstance(pred, (int, float, np.integer)):
                pred_int = int(pred)
            else:
                pred_int = {
                    "NEGATIVE": 0, "EDGE_CASE": 1,
                    "EYE_SOFTWARE": 2, "EYE_IMAGING": 3,
                }.get(str(pred), 0)

            label = self.LABELS[pred_int]

            results.append({
                'label': label,
                'confidence': float(max(probs)),
                'probabilities': {
                    'NEGATIVE': float(probs[0]),
                    'EDGE_CASE': float(probs[1]),
                    'EYE_SOFTWARE': float(probs[2]),
                    'EYE_IMAGING': float(probs[3]),
                },
            })
        return results

    @classmethod
    def train(cls, output_dir=None, device=None):
        """Train a new classifier from the built-in training data.

        Args:
            output_dir: Directory to save the model. Defaults to models/setfit_v6.
            device: Device for training. None for auto-selection.

        Returns:
            EyeImagingClassifier instance with the trained model.
        """
        if device is None:
            device = cls._select_device()

        if output_dir is None:
            output_dir = Path(__file__).resolve().parent.parent / "models" / "setfit_v6"
        else:
            output_dir = Path(output_dir)

        train_texts = POSITIVE_EXAMPLES + SOFTWARE_EXAMPLES + EDGE_CASES + NEGATIVE_EXAMPLES
        train_labels = (
            [3] * len(POSITIVE_EXAMPLES) +
            [2] * len(SOFTWARE_EXAMPLES) +
            [1] * len(EDGE_CASES) +
            [0] * len(NEGATIVE_EXAMPLES)
        )

        train_dataset = Dataset.from_dict({
            "text": train_texts,
            "label": train_labels,
        })

        print(f"Training SetFit model with {MODEL_NAME}")
        print(f"  Training examples: {len(train_dataset)}")
        print(f"  Device: {device}")

        model = SetFitModel.from_pretrained(
            MODEL_NAME,
            labels=LABELS,
            device=device,
            trust_remote_code=True,
        )

        args = TrainingArguments(
            output_dir=str(output_dir / "checkpoints"),
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

        output_dir.mkdir(exist_ok=True, parents=True)
        model.save_pretrained(str(output_dir))
        print(f"Model saved to: {output_dir}")

        return cls(model_path=output_dir, device=device)

    @staticmethod
    def extract_text(metadata):
        """Compose classification text from metadata fields.

        Args:
            metadata: dict with 'title', 'description', and/or 'keywords'.

        Returns:
            Combined text string.
        """
        title = metadata.get('title', '')
        desc = EyeImagingClassifier.strip_html(metadata.get('description', ''))
        keywords = metadata.get('keywords', [])
        if isinstance(keywords, list):
            keywords = ' '.join(keywords)
        return f"{title} {desc} {keywords}".strip()

    @staticmethod
    def strip_html(text):
        """Remove HTML tags from text."""
        import re
        from html import unescape
        if not text:
            return ""
        clean = re.sub('<[^<]+?>', ' ', text)
        return unescape(clean).strip()


def main():
    """Run the Zenodo eye imaging classification pipeline."""
    from .pipeline import run_zenodo_pipeline
    run_zenodo_pipeline()


if __name__ == "__main__":
    main()
