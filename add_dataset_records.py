import json
import os
from typing import Callable
from cuid2 import cuid_wrapper
from datetime import datetime
import requests
from markdownify import markdownify as md
from dotenv import load_dotenv

load_dotenv()

cuid_generator: Callable[[], str] = cuid_wrapper()

# --- Configuration ---
DATASET_RECORDS_OUTPUT_FILE = "data/datasetRecord.json"
ZENODO_EYE_IMAGING_FILE = "results/zenodo_eye_imaging.json"

API_KEY = os.getenv("EXTERNAL_API_KEY")
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:3000")


def generate_dataset_records():
    """Read Zenodo eye-imaging records and write normalised dataset records to disk."""
    dataset_records = []

    # Start fresh — remove any previously generated output file
    if os.path.exists(DATASET_RECORDS_OUTPUT_FILE):
        os.remove(DATASET_RECORDS_OUTPUT_FILE)

    dataset_starting_id = 1

    # Load the filtered Zenodo eye-imaging result set
    with open(ZENODO_EYE_IMAGING_FILE, "r", encoding="utf-8") as f:
        zenodo_eye_imaging = json.load(f)

    for record in zenodo_eye_imaging:
        zenodo_id = record["zenodo_id"]

        # Each Zenodo record has a pre-fetched metadata file on disk
        input_file_path = f"data/metadata/zenodo/{zenodo_id}.json"

        with open(input_file_path, "r", encoding="utf-8") as f:
            input_record = json.load(f)

        metadata = input_record["metadata"]

        # Convert HTML description to Markdown
        description = md(metadata.get("description", ""))

        # Map Zenodo creator objects to the portal schema
        creators = []
        for creator in metadata.get("creators", []):
            creators.append(
                {
                    "creatorName": creator["name"],
                    "nameType": "Personal",
                    "affiliation": [
                        {"affiliationName": creator.get("affiliation", "")}
                    ],
                }
            )

        publication_date = metadata.get("publication_date", "")
        publication_year = publication_date.split("-")[0] if publication_date else ""

        # Keywords become subjects in the portal schema
        subjects = [{"subjectValue": kw} for kw in metadata.get("keywords", [])]

        # Size in MB from the result set, converted to a human-readable string
        sizes = [
            f"{record['size_mb']} MB" if "size_mb" in record else "No size available"
        ]

        # Parse the ISO 8601 creation timestamp from Zenodo into a Unix timestamp
        created_raw = input_record.get(
            "created", datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        if isinstance(created_raw, str) and "T" in created_raw:
            created_dt = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
        else:
            created_dt = datetime.strptime(created_raw, "%Y-%m-%d %H:%M:%S")
        created_unix_timestamp = int(created_dt.timestamp())

        dataset_id = cuid_generator()

        dataset_record = {
            "id": dataset_starting_id,
            "canonicalId": dataset_id,
            "datasetId": dataset_id,
            "doi": metadata.get("doi", ""),
            "title": metadata.get("title", "No title available"),
            "description": description,
            "versionTitle": metadata.get("version", "1"),
            "studyTitle": metadata.get("studyTitle", ""),
            "publishedMetadata": {
                "studyDescription": {},
                "readme": description,
                "datasetDescription": {
                    "schema": "https://schema.envisionportal.io/v0.2.0/study_description.json",
                    "identifier": {
                        "identifierValue": metadata.get("doi", ""),
                        "identifierType": "DOI",
                    },
                    "title": [{"titleValue": metadata.get("title", "")}],
                    "version": metadata.get("version", "1"),
                    "creator": creators,
                    "publicationYear": publication_year,
                    "date": [
                        {
                            "dateValue": publication_date,
                            "dateType": "Available",
                            "dateInformation": "Date dataset made available on Zenodo",
                        }
                    ],
                    "resourceType": {
                        "resourceTypeValue": (
                            metadata["resource_type"]["title"]
                            if "resource_type" in metadata
                            and "title" in metadata["resource_type"]
                            else "No resource type available"
                        ),
                        "resourceTypeGeneral": "Dataset",
                    },
                    "datasetDeIdentLevel": {
                        "deIdentType": "NoDeIdentification",
                        "deIdentDirect": False,
                        "deIdentHIPAA": False,
                        "deIdentDates": False,
                        "deIdentNonarr": False,
                        "deIdentKAnon": False,
                        "deIdentDetails": "No de-identification details available",
                    },
                    "datasetConsent": {
                        "consentType": "ConsentSpecifiedNotElsewhereCategorised",
                        "consentNoncommercial": False,
                        "consentGeogRestrict": False,
                        "consentResearchType": False,
                        "consentGeneticOnly": False,
                        "consentNoMethods": False,
                        "consentsDetails": "",
                    },
                    "description": [
                        {
                            "descriptionValue": description,
                            "descriptionType": "Abstract",
                        }
                    ],
                    "language": "en",
                    "relatedIdentifier": [],
                    "subject": subjects,
                    "managingOrganization": {"name": ""},
                    "accessType": "PublicOnScreenAccessAndDownload",
                    "accessDetails": {"description": ""},
                    "rights": [
                        {
                            "rightsName": (
                                metadata["license"]["name"]
                                if "license" in metadata
                                and "name" in metadata["license"]
                                else "No license available"
                            ),
                        }
                    ],
                    "publisher": {"publisherName": "Zenodo"},
                    "size": sizes,
                    "fundingReference": [],
                    "format": [],
                },
                "datasetStructureDescription": {
                    "schema": "https://schema.aireadi.org/v0.1.1/dataset_structure_description.json",
                    "directoryList": [],
                    "metadataFileList": [],
                },
                "healthsheet": {},
            },
            "files": [],
            "data": {
                # Convert MB to bytes for the portal schema
                "size": (
                    int(record["size_mb"] * 1024 * 1024) if "size_mb" in record else 0
                ),
                "fileCount": 0,
                "viewCount": 0,
                "labelingMethod": "",
                "validationInfo": "",
            },
            "external": True,
            "externalUrl": record["url"],
            "created": str(created_unix_timestamp),
            "PublishedDatasetRegistrationDetails": {
                "datasetSource": "Zenodo",
                "extractionMethod": "Automatic Registration",
                "extractionVersion": "0.1.0",
            },
        }

        dataset_records.append(dataset_record)
        dataset_starting_id += 1

    with open(DATASET_RECORDS_OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(dataset_records, f, indent=4)

    print(
        f"Generated {len(dataset_records)} dataset records → {DATASET_RECORDS_OUTPUT_FILE}"
    )


def add_dataset_records_to_database():
    """POST each generated dataset record to the portal API."""
    endpoint = f"{API_BASE_URL}/api/discover/dataset/external"

    print(f"Posting records to {endpoint}")

    with open(DATASET_RECORDS_OUTPUT_FILE, "r", encoding="utf-8") as f:
        dataset_records = json.load(f)

    for record in dataset_records:
        payload = {
            "title": record["title"],
            "datasetId": record["datasetId"],
            "canonicalId": record["canonicalId"],
            "created": record["created"],
            "data": record["data"],
            "description": record["description"],
            "doi": record["doi"],
            "externalUrl": record["externalUrl"],
            "files": record["files"],
            "publishedMetadata": record["publishedMetadata"],
            "studyTitle": record["studyTitle"],
            "updated": record["created"],
            "versionTitle": record["versionTitle"],
            "PublishedDatasetRegistrationDetails": record[
                "PublishedDatasetRegistrationDetails"
            ],
        }

        try:
            response = requests.post(
                endpoint,
                headers={"x-api-key": f"{API_KEY}"},
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
            print(f"[{response.status_code}] Added: {record['title']}")
        except requests.exceptions.RequestException as e:
            print(f"[ERROR] Failed to add '{record['title']}': {e}")

        break


if __name__ == "__main__":
    generate_dataset_records()
    add_dataset_records_to_database()
