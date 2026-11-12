"""Restricted records: kept by the Zenodo scraper, mapped to valid CDS
accessType values by the portal poster and the ADDF exporter."""

import json
from pathlib import Path

import pytest

from envision.scraper import ZenodoScraper
from envision.utils import CDS_ACCESS_TYPE, CDS_ACCESS_TYPE_DEFAULT

# The CDS dataset_description accessType controlled list.
CDS_ACCESS_TYPES = {
    "PublicOnScreenAccess",
    "PublicOnScreenAccessAndDownload",
    "PublicOnScreenAndApiAccess",
    "PublicDownloadSelfAttestationRequired",
    "PublicOnScreenAccessSelfAttestationRequired",
    "RestrictedDownload",
    "RestrictedOnScreenAccess",
    "CaseByCaseDownload",
    "CaseByCaseOnScreenAccess",
    "NonPublicAccessNoDetails",
    "Other",
}


def _hit(access_right, files=None, analysis=None):
    return {
        "id": 13895504,
        "metadata": {"access_right": access_right, "title": "CNVSeg"},
        "files": files or [],
        "_file_analysis": analysis or {"has_imaging_files": False, "has_archives": False},
        "_dataset_links": [],
        "_weblinks": [],
    }


@pytest.mark.parametrize("right", ["restricted", "embargoed", "closed"])
def test_record_with_hidden_files_is_kept(right):
    assert ZenodoScraper._keep_reason(_hit(right)) == "files_not_public"


def test_open_record_without_files_is_still_dropped():
    assert ZenodoScraper._keep_reason(_hit("open")) is None


def test_restricted_record_with_visible_non_image_files_is_not_kept_for_access():
    # files are listed, so the file-based reasons decide, not the access right
    files = [{"key": "code.py", "size": 10}]
    assert ZenodoScraper._keep_reason(_hit("restricted", files=files)) is None


def test_file_reasons_still_win_over_access():
    hit = _hit("restricted", analysis={"has_imaging_files": True})
    assert ZenodoScraper._keep_reason(hit) == "imaging_files"


def test_every_mapped_access_type_is_on_the_cds_list():
    assert set(CDS_ACCESS_TYPE.values()) <= CDS_ACCESS_TYPES
    assert CDS_ACCESS_TYPE_DEFAULT in CDS_ACCESS_TYPES
    assert CDS_ACCESS_TYPE["restricted"] == "CaseByCaseDownload"
    assert CDS_ACCESS_TYPE["closed"] == "NonPublicAccessNoDetails"


def test_cds_list_matches_the_schema_copy_when_present():
    schema = Path(__file__).resolve().parents[2] / "cds-specification" / "docs" / "schemas" / "dataset_description.schema.json"
    if not schema.exists():
        pytest.skip("cds-specification checkout not next to this repo")
    one_of = json.loads(schema.read_text(encoding="utf-8"))["properties"]["accessType"]["oneOf"]
    assert {o["const"] for o in one_of} == CDS_ACCESS_TYPES


def test_addf_exporter_uses_the_cds_mapping():
    from envision.addf_export import ADDFExporter
    from envision.metadata import DatasetMetadata

    for right, expected in (("restricted", "CaseByCaseDownload"),
                            ("closed", "NonPublicAccessNoDetails"),
                            ("open", "PublicOnScreenAccessAndDownload")):
        meta = DatasetMetadata(source="zenodo", source_id="1", title="t",
                               access_type=right)
        doc = ADDFExporter.to_dataset_description(
            meta, {"label": "EYE_IMAGING", "confidence": 0.99, "probabilities": {}})
        assert doc["accessType"] == expected


def test_poster_access_details():
    pytest.importorskip("cuid2")
    pytest.importorskip("markdownify")
    import add_dataset_records as poster

    d = poster._access_details({"access_request": True,
                                "access_request_url": "https://zenodo.org/records/13895504",
                                "access_conditions": "Email the form to the owner.",
                                "embargo_until": None})
    assert d == {"description": "Email the form to the owner.",
                 "url": "https://zenodo.org/records/13895504"}

    d = poster._access_details({"access_request": True, "access_request_url": None,
                                "access_conditions": None, "embargo_until": None})
    assert d["description"]  # CDS requires a non-empty description

    d = poster._access_details({"access_request": False, "access_request_url": None,
                                "access_conditions": None, "embargo_until": "2027-01-01"})
    assert d == {"description": "Embargoed until 2027-01-01."}

    d = poster._access_details({"access_request": False, "access_request_url": None,
                                "access_conditions": None, "embargo_until": None})
    assert d == {"description": ""}


def _raw(access_right, settings=None, legacy_conditions=None):
    raw = {"id": 13895504, "metadata": {"access_right": access_right, "title": "CNVSeg",
                                        "access_conditions": legacy_conditions},
           "files": []}
    if settings is not None:
        raw["_access_settings"] = settings
    return raw


def test_conditions_come_from_inveniordm_settings():
    from envision.cli import zenodo_record_to_metadata

    m = zenodo_record_to_metadata(_raw("restricted", {
        "allow_user_requests": True, "allow_guest_requests": True,
        "accept_conditions_text": "<p><code>Send&nbsp;an application email</code> to\n<b>x@y.org</b></p>"}))
    assert m.access_request is True
    assert m.access_conditions == "Send an application email to x@y.org"


def test_owner_not_taking_zenodo_requests_is_said():
    from envision.cli import zenodo_record_to_metadata

    m = zenodo_record_to_metadata(_raw("restricted", {
        "allow_user_requests": False, "allow_guest_requests": False}))
    assert m.access_request is True
    assert "contact the depositor" in m.access_conditions


def test_legacy_conditions_still_win_and_no_settings_is_unchanged():
    from envision.cli import zenodo_record_to_metadata

    m = zenodo_record_to_metadata(_raw("restricted", None, "Legacy text"))
    assert m.access_conditions == "Legacy text"
    m = zenodo_record_to_metadata(_raw("open"))
    assert m.access_request is False and m.access_conditions is None
