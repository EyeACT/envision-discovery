"""
ENVISION Discovery: ADDF-Aligned Export

Exports classified dataset records as ADDF (AI-READI Data Format) schema JSON.
Produces dataset_description.json and dataset_structure_description.json files
per the schema at https://schema.aireadi.org/v0.1.0/

Reference schema files:
  /tmp/addf-schema/main/v1.0.0/dataset_description.json
  /tmp/addf-schema/main/v1.0.0/dataset_structure_description.json
"""

import json
from pathlib import Path

from .metadata import DatasetMetadata

SCHEMA_BASE = "https://schema.aireadi.org/v0.1.0"

# Publisher names by source
PUBLISHER_MAP = {
    "zenodo": "Zenodo",
    "figshare": "Figshare",
    "dryad": "Dryad Digital Repository",
    "osf": "Open Science Framework",
    "datacite": "DataCite",
}

# Extension to MIME type mapping for common eye imaging formats
EXT_TO_MIME = {
    ".dcm": "image/DICOM",
    ".dicom": "image/DICOM",
    ".nii": "application/nifti",
    ".nii.gz": "application/nifti+gzip",
    ".mat": "application/x-matlab",
    ".h5": "application/x-hdf5",
    ".hdf5": "application/x-hdf5",
    ".npy": "application/x-numpy",
    ".npz": "application/x-numpy+zip",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".bmp": "image/bmp",
    ".gif": "image/gif",
    ".fds": "application/x-topcon-oct",
    ".e2e": "application/x-heidelberg-oct",
    ".vol": "application/x-zeiss-oct",
    ".oct": "application/x-oct",
    ".fda": "application/x-optovue-oct",
    ".img": "application/octet-stream",
    ".zip": "application/zip",
    ".tar": "application/x-tar",
    ".gz": "application/gzip",
    ".csv": "text/csv",
    ".json": "application/json",
    ".txt": "text/plain",
    ".pdf": "application/pdf",
    ".xml": "application/xml",
}

# MeSH codes for common ophthalmic terms
OPHTHALMIC_MESH = {
    "retina": {"code": "D012160", "term": "Retina"},
    "retinal": {"code": "D012160", "term": "Retina"},
    "fundus": {"code": "D005654", "term": "Fundoscopy"},
    "oct": {"code": "D041623", "term": "Tomography, Optical Coherence"},
    "optical coherence tomography": {"code": "D041623", "term": "Tomography, Optical Coherence"},
    "diabetic retinopathy": {"code": "D003930", "term": "Diabetic Retinopathy"},
    "glaucoma": {"code": "D005901", "term": "Glaucoma"},
    "macular degeneration": {"code": "D008268", "term": "Macular Degeneration"},
    "amd": {"code": "D008268", "term": "Macular Degeneration"},
    "cornea": {"code": "D003315", "term": "Cornea"},
    "corneal": {"code": "D003315", "term": "Cornea"},
    "optic nerve": {"code": "D009900", "term": "Optic Nerve"},
    "optic disc": {"code": "D009898", "term": "Optic Disk"},
    "cataract": {"code": "D002386", "term": "Cataract"},
    "ophthalmology": {"code": "D009885", "term": "Ophthalmology"},
    "eye imaging": {"code": "D003941", "term": "Diagnostic Imaging"},
    "octa": {"code": "D041623", "term": "Tomography, Optical Coherence"},
}

# Modality detection from file extensions
MODALITY_MAP = {
    ".dcm": {"name": "retinal_imaging", "term": "Retinal Imaging", "ncit": "C168215"},
    ".dicom": {"name": "retinal_imaging", "term": "Retinal Imaging", "ncit": "C168215"},
    ".fds": {"name": "retinal_oct", "term": "Optical Coherence Tomography", "mesh": "D041623"},
    ".e2e": {"name": "retinal_oct", "term": "Optical Coherence Tomography", "mesh": "D041623"},
    ".vol": {"name": "retinal_oct", "term": "Optical Coherence Tomography", "mesh": "D041623"},
    ".oct": {"name": "retinal_oct", "term": "Optical Coherence Tomography", "mesh": "D041623"},
    ".fda": {"name": "retinal_oct", "term": "Optical Coherence Tomography", "mesh": "D041623"},
    ".nii": {"name": "volumetric_imaging", "term": "Volumetric Imaging", "ncit": "C188577"},
    ".nii.gz": {"name": "volumetric_imaging", "term": "Volumetric Imaging", "ncit": "C188577"},
    ".jpg": {"name": "retinal_photography", "term": "Fundus Photography", "mesh": "D005654"},
    ".jpeg": {"name": "retinal_photography", "term": "Fundus Photography", "mesh": "D005654"},
    ".png": {"name": "retinal_photography", "term": "Fundus Photography", "mesh": "D005654"},
    ".tif": {"name": "retinal_photography", "term": "Fundus Photography", "mesh": "D005654"},
    ".tiff": {"name": "retinal_photography", "term": "Fundus Photography", "mesh": "D005654"},
}


class ADDFExporter:
    """Export classified dataset metadata as ADDF schema JSON."""

    @staticmethod
    def to_dataset_description(meta: DatasetMetadata, classification: dict) -> dict:
        """Map DatasetMetadata + classification to ADDF dataset_description.json."""
        # Identifier
        identifier = {}
        if meta.doi:
            identifier = {
                "identifierValue": meta.doi,
                "identifierType": "DOI",
            }
        else:
            identifier = {
                "identifierValue": meta.url,
                "identifierType": "URL",
            }

        # Title
        title = [{"titleValue": meta.title}]

        # Creator
        creator = []
        for c in meta.creators:
            entry = {"creatorName": c.get("creatorName", "")}
            name_type = c.get("nameType")
            if name_type:
                entry["nameType"] = name_type
            creator.append(entry)
        if not creator:
            creator = [{"creatorName": "Unknown", "nameType": "Personal"}]

        # Resource type
        label = classification.get("label", "EYE_IMAGING")
        resource_type_value = {
            "EYE_IMAGING": "Eye Imaging Dataset",
            "EYE_SOFTWARE": "Eye Imaging Software",
            "EDGE_CASE": "Eye Research Data",
            "NEGATIVE": "Dataset",
        }.get(label, "Dataset")

        resource_type = {
            "resourceTypeValue": resource_type_value,
            "resourceTypeGeneral": "Dataset" if label != "EYE_SOFTWARE" else "Software",
        }

        # Description
        description = []
        if meta.description:
            description.append({
                "descriptionValue": meta.description[:2000],
                "descriptionType": "Abstract",
            })

        # Subject (keywords + MeSH terms for ophthalmic keywords)
        subject = []
        seen_subjects = set()
        for kw in meta.keywords:
            if kw and kw not in seen_subjects:
                seen_subjects.add(kw)
                entry = {"subjectValue": kw}

                # Check for MeSH mapping
                kw_lower = kw.lower()
                for term_key, mesh_info in OPHTHALMIC_MESH.items():
                    if term_key in kw_lower:
                        entry["subjectIdentifier"] = {
                            "classificationCode": mesh_info["code"],
                            "subjectScheme": "Medical Subject Headings (MeSH)",
                            "schemeURI": "https://meshb.nlm.nih.gov/",
                            "valueURI": f"https://meshb.nlm.nih.gov/record/ui?ui={mesh_info['code']}",
                        }
                        break

                subject.append(entry)

        # Add classification label as subject
        if label in ("EYE_IMAGING", "EYE_SOFTWARE"):
            subject.append({"subjectValue": "Eye Imaging"})
            subject.append({
                "subjectValue": "Ophthalmology",
                "subjectIdentifier": {
                    "classificationCode": "D009885",
                    "subjectScheme": "Medical Subject Headings (MeSH)",
                    "schemeURI": "https://meshb.nlm.nih.gov/",
                    "valueURI": "https://meshb.nlm.nih.gov/record/ui?ui=D009885",
                },
            })

        # Access type
        access_type_map = {
            "open": "PublicOnScreenAccess",
            "embargoed": "PublicOnScreenAccess",
            "restricted": "RestrictedAccess",
            "closed": "RestrictedAccess",
        }
        access_type = access_type_map.get(meta.access_type, "PublicOnScreenAccess")

        # Rights
        rights = []
        if meta.license:
            rights.append({"rightsName": meta.license})

        # Size
        size = []
        if meta.total_size_bytes > 0:
            size_mb = meta.size_mb
            if size_mb >= 1024:
                size.append(f"{size_mb / 1024:.1f} GB")
            else:
                size.append(f"{size_mb:.1f} MB")
        if meta.file_count > 0:
            size.append(f"{meta.file_count} files")

        # Format (file types to MIME)
        format_list = []
        seen_formats = set()
        for ext in sorted(meta.file_types):
            mime = EXT_TO_MIME.get(ext, f"application/octet-stream")
            if mime not in seen_formats:
                seen_formats.add(mime)
                format_list.append(mime)

        # Publisher
        publisher = {
            "publisherName": PUBLISHER_MAP.get(meta.source, meta.source.capitalize()),
        }

        # Related identifiers
        related_identifiers = []
        for rel in meta.related_identifiers:
            related_identifiers.append({
                "relatedIdentifierValue": rel.get("relatedIdentifierValue", ""),
                "relatedIdentifierType": rel.get("relatedIdentifierType", "URL"),
                "relationType": rel.get("relationType", "References"),
                "resourceTypeGeneral": "Other",
            })
        for link in meta.external_links:
            if isinstance(link, str) and link not in {
                r.get("relatedIdentifierValue") for r in related_identifiers
            }:
                related_identifiers.append({
                    "relatedIdentifierValue": link,
                    "relatedIdentifierType": "URL",
                    "relationType": "References",
                    "resourceTypeGeneral": "Other",
                })

        # Dates
        date_list = []
        for d in meta.dates:
            date_list.append({
                "dateValue": d.get("dateValue", ""),
                "dateType": d.get("dateType", "Other"),
            })

        # Build the document
        doc = {
            "schema": f"{SCHEMA_BASE}/dataset_description.json",
            "identifier": identifier,
            "title": title,
            "creator": creator,
            "publicationYear": meta.publication_year or "",
            "date": date_list,
            "resourceType": resource_type,
            "description": description,
            "language": "en",
            "subject": subject,
            "accessType": access_type,
            "rights": rights,
            "publisher": publisher,
            "size": size,
            "format": format_list,
        }

        if related_identifiers:
            doc["relatedIdentifier"] = related_identifiers

        return doc

    @staticmethod
    def to_structure_description(meta: DatasetMetadata) -> dict:
        """Infer directory structure from file inventory.

        Creates ADDF dataset_structure_description.json with directoryList
        entries for detected modalities based on file extensions.
        """
        # Detect modalities from file types
        detected_modalities: dict[str, dict] = {}
        for ext in meta.file_types:
            modality_info = MODALITY_MAP.get(ext)
            if modality_info and modality_info["name"] not in detected_modalities:
                detected_modalities[modality_info["name"]] = modality_info

        # Also check zip contents
        for zf in meta.zip_contents:
            zf_lower = zf.lower()
            for ext, modality_info in MODALITY_MAP.items():
                if zf_lower.endswith(ext) and modality_info["name"] not in detected_modalities:
                    detected_modalities[modality_info["name"]] = modality_info

        # Build directory list
        directory_list = []
        for mod_name, mod_info in detected_modalities.items():
            entry = {
                "directoryName": mod_name,
                "directoryType": "dataType",
                "directoryDescription": f"Contains {mod_info['term']} data",
                "relatedTerm": [
                    {
                        "relatedTermValue": mod_info["term"],
                        "relatedTermIdentifier": [],
                    }
                ],
            }

            # Add NCIT or MeSH identifier
            if "ncit" in mod_info:
                entry["relatedTerm"][0]["relatedTermIdentifier"].append({
                    "relatedTermClassificationCode": mod_info["ncit"],
                    "relatedTermScheme": "NCI Thesaurus (NCIT)",
                    "relatedTermSchemeURI": "https://ncim.nci.nih.gov/",
                    "relatedTermValueURI": f"https://ncit.nci.nih.gov/ncitbrowser/pages/concept_details.jsf?dictionary=NCI%20Thesaurus&code={mod_info['ncit']}",
                })
            elif "mesh" in mod_info:
                entry["relatedTerm"][0]["relatedTermIdentifier"].append({
                    "relatedTermClassificationCode": mod_info["mesh"],
                    "relatedTermScheme": "Medical Subject Headings (MeSH)",
                    "relatedTermSchemeURI": "https://meshb.nlm.nih.gov/",
                    "relatedTermValueURI": f"https://meshb.nlm.nih.gov/record/ui?ui={mod_info['mesh']}",
                })

            directory_list.append(entry)

        return {
            "schema": f"{SCHEMA_BASE}/dataset_structure_description.json",
            "directoryList": directory_list,
        }

    @staticmethod
    def export_record(
        meta: DatasetMetadata,
        classification: dict,
        output_dir: Path,
    ) -> tuple[Path, Path]:
        """Write ADDF JSON files for one classified record."""
        record_dir = output_dir / meta.source / meta.source_id
        record_dir.mkdir(parents=True, exist_ok=True)

        desc = ADDFExporter.to_dataset_description(meta, classification)
        desc_path = record_dir / "dataset_description.json"
        with open(desc_path, "w") as f:
            json.dump(desc, f, indent=2)

        struct = ADDFExporter.to_structure_description(meta)
        struct_path = record_dir / "dataset_structure_description.json"
        with open(struct_path, "w") as f:
            json.dump(struct, f, indent=2)

        return desc_path, struct_path

    @staticmethod
    def export_batch(
        records: list[tuple[DatasetMetadata, dict]],
        output_dir: Path,
    ) -> list[tuple[Path, Path]]:
        """Export all classified records as ADDF-format JSON.

        Args:
            records: list of (DatasetMetadata, classification_dict) tuples.
            output_dir: Base output directory.

        Returns:
            List of (desc_path, struct_path) tuples.
        """
        output_dir = Path(output_dir)
        paths = []
        for meta, classification in records:
            desc_path, struct_path = ADDFExporter.export_record(
                meta, classification, output_dir
            )
            paths.append((desc_path, struct_path))
        return paths
