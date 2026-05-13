import json
import os
import re
from typing import Callable
from cuid2 import cuid_wrapper
from datetime import datetime
from html import unescape
import requests
from markdownify import markdownify as md
from dotenv import load_dotenv
import contextlib

load_dotenv()

cuid_generator: Callable[[], str] = cuid_wrapper()

# const fileSchema: z.ZodType = z.lazy(() =>
#   z.array(
#     z.union([
#       z.object({
#         label: z.string(),
#         children: z.array(fileSchema),
#       }),
#       z.object({
#         name: z.string(),
#       }),
#     ]),
#   ),
# );

# const datasetSchema = z.object({
#   title: z.string(),
#   created: z.string(),
#   data: z.any(),
#   datasetId: z.string(),
#   canonicalId: z.string(),
#   description: z.string(),
#   doi: z.string().optional(),
#   externalUrl: z.string(),
#   files: fileSchema,
#   publishedMetadata: z.any(),
#   studyTitle: z.string(),
#   updated: z.string(),
#   versionTitle: z.string(),
#   PublishedDatasetRegistrationDetails: z.object({
#     datasetSource: z.string(),
#     extractionMethod: z.string(),
#     extractionVersion: z.string(),
#   }),
# });

# --- Configuration ---
DATASET_RECORDS_OUTPUT_FILE = "data/datasetRecord.json"

# All repository sources and their eye_imaging result files
SOURCES = {
    "zenodo": "results/zenodo_eye_imaging.json",
    "datacite": "results/datacite_eye_imaging.json",
    "figshare": "results/figshare_eye_imaging.json",
    "kaggle": "results/kaggle_eye_imaging.json",
    "dryad": "results/dryad_eye_imaging.json",
    "nei": "results/nei_eye_imaging.json",
    "osf": "results/osf_eye_imaging.json",
}

# Metadata directories (pre-fetched per-record JSON, if available)
METADATA_DIRS = {
    "zenodo": "data/metadata/zenodo",
    "datacite": "data/metadata/datacite",
    "figshare": "data/metadata/figshare",
    "kaggle": "data/metadata/kaggle",
    "dryad": "data/metadata/dryad",
    "nei": "data/metadata/nei",
    "osf": "data/metadata/osf",
}

API_KEY = os.getenv("EXTERNAL_API_KEY")
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:3000")


def _clean_html(text):
    """Strip HTML tags and unescape entities."""
    if not text:
        return ""
    clean = re.sub("<[^<]+?>", " ", text)
    return unescape(clean).strip()


def _build_affiliation_list(value):
    """Return affiliation as a list of dictionary entries."""
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, dict):
        items = value  # in this instance iterate through dictionary keys and assume they are affiliation names
    elif isinstance(value, list):
        items = value
    else:
        items = []

    return [{"affiliationName": a} if isinstance(a, str) else a for a in items if a]


def _extract_iso_date(value):
    """Return YYYY-MM-DD when value contains a parseable date; otherwise empty string."""
    if value is None:
        return ""

    raw = str(value).strip()
    if not raw:
        return ""

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        return raw

    # Treat year-only values (e.g. "2023") as incomplete for this field.
    if re.fullmatch(r"\d{4}", raw):
        return ""

    with contextlib.suppress(ValueError):
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date().isoformat()

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d"):
        with contextlib.suppress(ValueError):
            return datetime.strptime(raw, fmt).date().isoformat()

    return ""


def _build_record_from_result(record, source):
    """Build a portal-schema dataset record from a classifier result entry."""
    title = _clean_html(record.get("title", "No title available"))

    # if title is empty or only whitespace, ignore this record by returning None
    if not title or title.isspace():
        print(
            f"  Skipping record with empty title for source_id: {record.get('source_id', '')} (source: {source})"
        )
        return None

    description = record.get("description", "")
    if description:
        description = (
            md(_clean_html(description)) if "<" in description else description
        )
    doi = record.get("doi", "")
    url = record.get("url", "")
    keywords = record.get("keywords", [])
    if isinstance(keywords, str):
        keywords = [keywords]
    # Flatten any single-string entries using angle-bracket encoding: "<kw1><kw2>..."
    parsed_keywords = []
    for kw in keywords:
        if isinstance(kw, str) and kw.startswith("<") and "><" in kw:
            parsed_keywords.extend(re.findall(r"<([^<>]+)>", kw))
        elif isinstance(kw, str):
            parsed_keywords.extend([k.strip() for k in kw.split(",") if k.strip()])
        else:
            parsed_keywords.append(kw)
    keywords = parsed_keywords
    subjects = [{"subjectValue": kw} for kw in keywords]

    # Try to get richer metadata from pre-fetched files
    source_id = record.get("source_id", record.get("zenodo_id", ""))

    sources_requiring_transformation = ["dryad", "kaggle", "datacite"]

    # if dryad, kaggle, or datacite is in the source_id, convert the / to _ to match the filename format in the metadata directory
    if source in sources_requiring_transformation and "/" in source_id:
        source_id = source_id.replace("/", "_")

    metadata_dir = os.path.normpath(METADATA_DIRS.get(source))
    creators = []
    publication_date = ""
    publication_date_source = ""
    publication_year = ""
    license_name = "No license available"
    sizes = [f"{record.get('size_mb', 0)} MB"]
    metadata_created_raw = ""
    metadata_modified_raw = ""
    metadata_registered_raw = ""

    if metadata_dir and source_id:
        meta_path = os.path.join(metadata_dir, f"{source_id}.json")

        if not os.path.exists(meta_path):
            print(
                f"  Skipping record: metadata file not found for source_id: {source_id} (source: {source}) at expected path: {meta_path}"
            )
            return None
        else:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            m = meta.get("metadata", meta)
            creators.extend(
                {
                    "creatorName": c.get("creatorName", c.get("name", "")),
                    "nameType": c.get("nameType", "Personal"),
                    "affiliation": _build_affiliation_list(c.get("affiliation")),
                }
                for c in (m.get("creators") or meta.get("creators", []))
            )
            metadata_created_raw = meta.get("created", "")
            metadata_modified_raw = meta.get("modified", "")
            metadata_registered_raw = meta.get("registered", "")

            publication_date = _extract_iso_date(
                m.get("publication_date", "") or meta.get("publication_date", "")
            )
            if publication_date:
                publication_date_source = "publication_date"

            if not publication_date:
                dates_list = m.get("dates", []) or meta.get("dates", [])
                _dates_fallback = None
                for d in dates_list:
                    if isinstance(d, dict) and d.get("dateValue"):
                        candidate = _extract_iso_date(d["dateValue"])
                        if candidate:
                            if d.get("dateType") == "StartDate":
                                publication_date = candidate
                                publication_date_source = "dates[StartDate]"
                                break
                            elif _dates_fallback is None:
                                _dates_fallback = candidate
                if not publication_date and _dates_fallback:
                    publication_date = _dates_fallback
                    publication_date_source = "dates"
            if not publication_date:
                publication_date = _extract_iso_date(metadata_registered_raw)
                if publication_date:
                    publication_date_source = "registered"
            if not publication_date:
                publication_date = _extract_iso_date(metadata_created_raw)
                if publication_date:
                    publication_date_source = "created"
            if not publication_date:
                publication_date = _extract_iso_date(metadata_modified_raw)
                if publication_date:
                    publication_date_source = "modified"


            print(
                f"    Extracted publication date: {publication_date} from metadata for source_id: {source_id} (source: {source})"
            )

            publication_year = (
                publication_date.split("-")[0]
                if publication_date
                else str(
                    m.get("publication_year", "") or meta.get("publication_year", "")
                )
            )

            if "license" in m and isinstance(m["license"], dict):
                license_name = (
                    m["license"].get("name") or m["license"].get("id") or license_name
                )
            if "license" in m and isinstance(m["license"], str):
                license_name = m["license"] or license_name

            if not description and m.get("description"):
                description = md(_clean_html(m["description"]))

    # If no creators from metadata, use what's in the result
    if not creators and record.get("creators"):
        for c in record["creators"]:
            if isinstance(c, dict):
                creators.append(
                    {
                        "creatorName": c.get("name", str(c)),
                        "nameType": "Personal",
                        "affiliation": [],
                    }
                )
            else:
                creators.append(
                    {
                        "creatorName": str(c),
                        "nameType": "Personal",
                        "affiliation": [],
                    }
                )

    # Timestamp
    if publication_date_source in {"created", "modified", "registered"}:
        created_raw = (
            metadata_registered_raw
            or metadata_created_raw
            or metadata_modified_raw
            or publication_date
            or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
    else:
        created_raw = (
            publication_date
            or metadata_created_raw
            or metadata_modified_raw
            or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
    print(
        f"    Using publication date: {publication_date} for source_id: {source_id} (source: {source}) {created_raw}"
    )

    if isinstance(created_raw, str) and "T" in created_raw:
        try:
            created_dt = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
        except ValueError:
            created_dt = datetime.now()
    else:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            with contextlib.suppress(ValueError, TypeError):
                created_dt = datetime.strptime(str(created_raw), fmt)
                break
        else:
            created_dt = datetime.now()
    print(
        f"    Parsed created datetime: {created_dt} from raw value: {created_raw} for source_id: {source_id} (source: {source})"
    )
    created_unix_timestamp = int(created_dt.timestamp())

    dataset_id = cuid_generator()

    return {
        "canonicalId": dataset_id,
        "datasetId": dataset_id,
        "doi": doi,
        "title": title,
        "description": description,
        "versionTitle": record.get("version", "1"),
        "studyTitle": "",
        "publishedMetadata": {
            "studyDescription": {},
            "readme": description,
            "datasetDescription": {
                "schema": "https://schema.envisionportal.io/v0.2.0/study_description.json",
                "identifier": {
                    "identifierValue": doi,
                    "identifierType": "DOI",
                },
                "title": [{"titleValue": title}],
                "version": record.get("version", "1"),
                "creator": creators,
                "publicationYear": publication_year,
                "date": (
                    [
                        {
                            "dateValue": publication_date,
                            "dateType": "Available",
                            "dateInformation": (
                                f"Date dataset made available on {source.capitalize()}"
                            ),
                        }
                    ]
                    if publication_date
                    else []
                ),
                "resourceType": {
                    "resourceTypeValue": "Dataset",
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
                "rights": [{"rightsName": license_name}],
                "publisher": {"publisherName": source.capitalize()},
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
            "size": int(record.get("size_mb", 0) * 1024 * 1024),
            "fileCount": record.get("file_count", 0),
            "viewCount": 0,
            "labelingMethod": "",
            "validationInfo": "",
        },
        "external": True,
        "externalUrl": url,
        "created": str(created_unix_timestamp),
        "PublishedDatasetRegistrationDetails": {
            "datasetSource": source.capitalize(),
            "extractionMethod": "Automatic Registration",
            "extractionVersion": "0.2.0",
        },
    }


def generate_dataset_records():
    """Read eye-imaging records from all sources and write normalised dataset records."""
    dataset_records = []

    if os.path.exists(DATASET_RECORDS_OUTPUT_FILE):
        os.remove(DATASET_RECORDS_OUTPUT_FILE)

    seen_dois = set()

    for source, result_file in SOURCES.items():
        if not os.path.exists(result_file):
            print(f"  Skipping {source}: {result_file} not found")
            continue

        with open(result_file, "r", encoding="utf-8") as f:
            records = json.load(f)

        source_count = 0
        for record in records:
            # Deduplicate by DOI across sources
            doi = record.get("doi", "")
            doi = doi.lower() if isinstance(doi, str) else ""
            if doi:
                if doi in seen_dois:
                    continue
                seen_dois.add(doi)

            dataset_record = _build_record_from_result(record, source)

            if dataset_record is None:
                continue

            dataset_record["id"] = len(dataset_records) + 1
            dataset_records.append(dataset_record)
            source_count += 1

        print(f"  {source}: {source_count} records (from {len(records)} eye_imaging)")

    with open(DATASET_RECORDS_OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(dataset_records, f, indent=4)

    print(
        f"\nGenerated {len(dataset_records)} dataset records -> {DATASET_RECORDS_OUTPUT_FILE}"
    )


def add_dataset_records_to_database():
    """POST each generated dataset record to the portal API."""
    endpoint = f"{API_BASE_URL}/api/discover/dataset/external"

    print(f"Posting records to {endpoint}")

    with open(DATASET_RECORDS_OUTPUT_FILE, "r", encoding="utf-8") as f:
        dataset_records = json.load(f)

    success = 0
    failed = 0
    for record in dataset_records:
        payload = {
            "title": record["title"] or "No title available",
            "datasetId": record["datasetId"],
            "canonicalId": record["canonicalId"],
            "created": str(record["created"]),
            "data": record["data"],
            "description": record.get("description") or "",
            "doi": record["doi"] or "",
            "externalUrl": record.get("externalUrl") or "",
            "files": record.get("files") or [],
            "publishedMetadata": record["publishedMetadata"],
            "studyTitle": record.get("studyTitle") or "",
            "updated": str(record["created"]),
            "versionTitle": str(record.get("versionTitle") or "1"),
            "PublishedDatasetRegistrationDetails": record[
                "PublishedDatasetRegistrationDetails"
            ],
        }

        try:
            print(
                f"  Posting '{record['title'][:60]}'... for Date Created: {record['created']}"
            )
            response = requests.post(
                endpoint,
                headers={"x-api-key": f"{API_KEY}"},
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
            success += 1
        except requests.exceptions.RequestException as e:
            print(f"  [ERROR] Failed to add '{record['title'][:60]}': {e}")
            failed += 1

    print(f"\nPosted {success} records ({failed} failed)")


if __name__ == "__main__":
    generate_dataset_records()
    # add_dataset_records_to_database()
