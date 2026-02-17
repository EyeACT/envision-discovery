import json
import os
from typing import Callable
from cuid2 import cuid_wrapper
from datetime import datetime
from markdownify import markdownify as md

cuid_generator: Callable[[], str] = cuid_wrapper()

DATASET_RECORDS_FILE = "data/datasetRecords.json"
DATASET_RECORDS_OUTPUT_FILE = "data/datasetRecordsNew.json"
ZENODO_EYE_IMAGING_FILE = "results/zenodo_eye_imaging.json"


def generate_dataset_records():
    # Read the datasetRecords.json file

    dataset_records = []
    zenodo_eye_imaging = []

    # delete the output file if it exists
    if os.path.exists(DATASET_RECORDS_OUTPUT_FILE):
        os.remove(DATASET_RECORDS_OUTPUT_FILE)

    with open(DATASET_RECORDS_FILE, "r", encoding="utf-8") as f:
        dataset_records = json.load(f)

    dataset_starting_id = len(dataset_records) + 1

    # Read the zenodo_eye_imaging.json file
    with open(ZENODO_EYE_IMAGING_FILE, "r", encoding="utf-8") as f:
        zenodo_eye_imaging = json.load(f)

    for record in zenodo_eye_imaging:
        zenodo_id = record["zenodo_id"]

        # Get the file with the same zenodo_id in the data folder
        input_file_path = f"data/metadata/zenodo/{zenodo_id}.json"

        with open(input_file_path, "r", encoding="utf-8") as f:
            input_record = json.load(f)

            metadata = input_record["metadata"]

            description = md(
                metadata["description"] if "description" in metadata else ""
            )

            creators = []
            for creator in metadata["creators"]:
                creators.append(
                    {
                        "creatorName": creator["name"],
                        "nameType": "Personal",
                        "affiliation": [{"affiliationName": creator["affiliation"]}],
                    }
                )

            publication_date = (
                metadata["publication_date"] if "publication_date" in metadata else ""
            )
            publication_year = (
                publication_date.split("-")[0] if publication_date else ""
            )

            subjects = []
            for subject in metadata["keywords"] if "keywords" in metadata else []:
                subjects.append(
                    {
                        "subjectValue": subject,
                    }
                )

            sizes = []
            sizes.append(
                (
                    f"{record['size_mb']} MB"
                    if "size_mb" in record
                    else "No size available"
                )
            )

            # Zenodo returns created in ISO 8601 e.g. "2023-08-17T03:51:54.037332+00:00"
            created = (
                input_record["created"]
                if "created" in input_record
                else datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
            if isinstance(created, str) and "T" in created:
                created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            else:
                created_dt = datetime.strptime(created, "%Y-%m-%d %H:%M:%S")
            created_unix_timestamp = int(created_dt.timestamp())

            dataset_id = cuid_generator()

            dataset_record = {
                "id": dataset_starting_id,
                "canonicalId": dataset_id,
                "datasetId": dataset_id,
                "doi": metadata["doi"] if "doi" in metadata else "",
                "title": (
                    metadata["title"] if "title" in metadata else "No title available"
                ),
                "description": description,
                "versionTitle": metadata["version"] if "version" in metadata else "1",
                "studyTitle": (
                    metadata["studyTitle"] if "studyTitle" in metadata else ""
                ),
                "publishedMetadata": {
                    "studyDescription": {},
                    "readme": description,
                    "datasetDescription": {
                        "schema": "https://schema.envisionportal.io/v0.2.0/study_description.json",
                        "identifier": {
                            "identifierValue": (
                                metadata["doi"] if "doi" in metadata else ""
                            ),
                            "identifierType": "DOI",
                        },
                        "title": [
                            {
                                "titleValue": (
                                    metadata["title"] if "title" in metadata else ""
                                ),
                            },
                        ],
                        "version": (
                            metadata["version"] if "version" in metadata else "1"
                        ),
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
                        "fundingReference": [
                            {
                                "funderName": "",
                                "awardNumber": {"awardNumberValue": "", "awardURI": ""},
                                "awardTitle": "",
                            }
                        ],
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
                    "size": (
                        int(record["size_mb"] * 1024 * 1024)
                        if "size_mb" in record
                        else 0
                    ),
                    "fileCount": 0,
                    "viewCount": 0,
                    "labelingMethod": "",
                    "validationInfo": "",
                },
                "external": True,
                "externalUrl": record["url"],
                "created": str(created_unix_timestamp),
                # "created": "1707465600"
            }

        dataset_records.append(dataset_record)
        dataset_starting_id += 1

    with open(DATASET_RECORDS_OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(dataset_records, f, indent=4)

    return


if __name__ == "__main__":
    generate_dataset_records()
