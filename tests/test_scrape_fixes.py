"""Tests for the Zenodo scrape fixes: bounded retries with failure
reporting, cap/error detection per query, large ZIP central directories,
archive extension counts, and the Zenodo record adapter fields."""

import io
import zipfile

import pytest
import requests

from envision import utils
from envision.cli import zenodo_record_to_metadata
from envision.pipeline import _related_dois, _zip_file_types
from envision.scraper import ZenodoScraper, _term_status
from envision.utils import ArchiveInspector, PaginatedSearch, request_with_backoff


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(utils.time, "sleep", lambda s: None)
    import envision.scraper as scraper_mod
    monkeypatch.setattr(scraper_mod.time, "sleep", lambda s: None)


class FakeResponse:
    def __init__(self, status=200, payload=None, content=b"", headers=None):
        self.status_code = status
        self._payload = payload
        self.content = content
        self.text = str(payload)[:200] if payload is not None else ""
        self.headers = headers or {}

    def json(self):
        return self._payload

    def close(self):
        pass


class ScriptedSession:
    """Returns the scripted statuses in order, then repeats the last one."""

    def __init__(self, statuses):
        self.statuses = list(statuses)
        self.calls = 0

    def request(self, method, url, **kwargs):
        self.calls += 1
        status = self.statuses[min(self.calls - 1, len(self.statuses) - 1)]
        if isinstance(status, Exception):
            raise status
        return FakeResponse(status, payload={"ok": status})


# ---------------------------------------------------------------- backoff

def test_persistent_500_gives_up_and_is_reported():
    sess = ScriptedSession([500])
    failures = []
    assert request_with_backoff(sess, "get", "http://x", max_error_retries=3,
                                failures=failures, params={"q": "a"}) is None
    assert sess.calls == 4  # first try + 3 retries, not an endless loop
    assert failures and failures[0]["status"] == 500
    assert failures[0]["params"] == {"q": "a"} and failures[0]["attempts"] == 4


def test_transient_errors_then_success():
    sess = ScriptedSession([503, requests.exceptions.ConnectionError("boom"), 429, 200])
    failures = []
    resp = request_with_backoff(sess, "get", "http://x", failures=failures)
    assert resp is not None and resp.status_code == 200
    assert failures == []


def test_client_error_not_retried_but_reported():
    sess = ScriptedSession([400])
    failures = []
    assert request_with_backoff(sess, "get", "http://x", failures=failures) is None
    assert sess.calls == 1
    assert failures[0]["status"] == 400


def test_max_retries_still_bounds_rate_limits():
    sess = ScriptedSession([429])
    assert request_with_backoff(sess, "get", "http://x", max_retries=3) is None
    assert sess.calls == 3


# ------------------------------------------------------- search reporting

def _hit(i):
    return {"id": i + 1, "metadata": {"title": f"t{i}", "description": ""}, "files": []}


def _scraper(tmp_path, monkeypatch, pages, keep=True):
    """ZenodoScraper whose search requests return the given pages in order.

    A page is a list of hits, or None for a failed request.
    """
    import envision.scraper as scraper_mod

    sc = ZenodoScraper(tmp_path, resume=False)
    total = sum(len(p) for p in pages if p)
    calls = {"n": 0}

    def fake_request(session, method, url, failures=None, **kwargs):
        if kwargs.get("params", {}).get("size") == 1:
            return FakeResponse(200, {"hits": {"total": total, "hits": []}})
        page = pages[calls["n"]] if calls["n"] < len(pages) else []
        calls["n"] += 1
        if page is None:
            if failures is not None:
                failures.append({"url": url, "params": kwargs.get("params"),
                                 "status": 502, "error": "bad gateway", "attempts": 7})
            return None
        return FakeResponse(200, {"hits": {"total": total, "hits": page}})

    monkeypatch.setattr(scraper_mod, "request_with_backoff", fake_request)
    monkeypatch.setattr(sc, "_enrich_record", lambda rec, inspect: rec)
    monkeypatch.setattr(sc, "_should_keep", lambda rec: keep)
    return sc


def test_search_complete_is_ok(tmp_path, monkeypatch):
    sc = _scraper(tmp_path, monkeypatch, [[_hit(i) for i in range(25)], [_hit(99)]])
    out = sc.search("q", max_results=500, inspect_zips=False)
    assert len(out) == 26
    assert sc.searches[-1]["status"] == "ok"
    assert sc.searches[-1]["hits_seen"] == 26 == sc.searches[-1]["total"]


def test_search_failed_page_is_error_not_silent(tmp_path, monkeypatch):
    sc = _scraper(tmp_path, monkeypatch, [[_hit(i) for i in range(25)], None])
    out = sc.search("q", max_results=500, inspect_zips=False)
    assert len(out) == 25
    entry = sc.searches[-1]
    assert entry["status"] == "error" and entry["error"]["status"] == 502
    assert sc.failures


def test_search_stops_at_api_cap(tmp_path, monkeypatch):
    sc = _scraper(tmp_path, monkeypatch, [[_hit(i + 25 * p) for i in range(25)] for p in range(4)])
    sc.MAX_API_RESULTS = 50
    sc.search("q", max_results=10_000, inspect_zips=False)
    entry = sc.searches[-1]
    assert entry["status"] == "capped" and entry["hits_seen"] == 50 and entry["total"] == 100


def test_get_count_failure_is_none(tmp_path, monkeypatch):
    import envision.scraper as scraper_mod

    sc = ZenodoScraper(tmp_path, resume=False)
    monkeypatch.setattr(scraper_mod, "request_with_backoff", lambda *a, **k: None)
    assert sc.get_count("q") is None


def test_paginator_reports_failed_slice():
    p = PaginatedSearch(count_fn=lambda q, s, e: None, fetch_fn=lambda *a: [], api_max=10)
    assert p.search("q", "2020-01-01", "2020-12-31") == []
    assert p.problems[0]["status"] == "error"


def test_paginator_reports_capped_single_day():
    p = PaginatedSearch(count_fn=lambda q, s, e: 50,
                        fetch_fn=lambda q, s, e, m: [{"id": i} for i in range(m)], api_max=10)
    out = p.search("q", "2020-01-01", "2020-01-01")
    assert len(out) == 10
    assert p.problems[0]["status"] == "capped"


def test_term_status_rollup():
    ok = {"status": "ok", "hits_seen": 3, "kept": 1}
    bad = {"status": "capped", "hits_seen": 5, "kept": 2}
    assert _term_status("t", "q", 3, [ok], [])["status"] == "ok"
    assert _term_status("t", "q", 8, [ok, bad], [])["status"] == "capped"
    assert _term_status("t", "q", None, [ok], [])["status"] == "error"
    r = _term_status("t", "q", 8, [ok], [{"status": "error"}])
    assert r["status"] == "error" and r["hits_seen"] == 3


# ------------------------------------------------------ archive inspection

class RangeSession:
    """Serves one in-memory file with HEAD and Range support."""

    def __init__(self, data: bytes):
        self.data = data
        self.ranges = []

    def head(self, url, **kwargs):
        return FakeResponse(200, headers={"Content-Length": str(len(self.data))})

    def get(self, url, headers=None, **kwargs):
        rng = headers["Range"].split("=", 1)[1]
        a, b = (int(x) for x in rng.split("-"))
        self.ranges.append((a, b))
        return FakeResponse(206, content=self.data[a:b + 1])


def _zip_bytes(n, prefix="retina/img_"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
        for i in range(n):
            zf.writestr(f"{prefix}{i:05d}.png", b"x")
        zf.writestr("labels.csv", b"a,b")
    return buf.getvalue()


def test_small_zip_listed_from_tail():
    sess = RangeSession(_zip_bytes(10))
    names = ArchiveInspector.inspect_zip_via_range("u", sess)
    assert len(names) == 11 and len(sess.ranges) == 1


def test_large_central_directory_is_fetched():
    data = _zip_bytes(3000)  # central directory is far larger than 64 KB
    sess = RangeSession(data)
    names = ArchiveInspector.inspect_zip_via_range("u", sess)
    assert names is not None and len(names) == 3001
    assert len(sess.ranges) == 2


def test_central_directory_span_zip64():
    import struct
    cd_off, cd_size = 5_000_000_000, 1234
    z64 = (b"PK\x06\x06" + struct.pack("<Q", 44) + struct.pack("<HHII", 45, 45, 0, 0)
           + struct.pack("<QQQQ", 1, 1, cd_size, cd_off))
    loc = b"PK\x06\x07" + struct.pack("<IQI", 0, 123, 1)
    eocd = b"PK\x05\x06" + struct.pack("<HHHHIIH", 0, 0, 0xFFFF, 0xFFFF,
                                        0xFFFFFFFF, 0xFFFFFFFF, 0)
    assert ArchiveInspector._central_directory_span(b"junk" + z64 + loc + eocd) == (cd_off, cd_size)


def test_summarize_contents_counts_all_extensions():
    s = ArchiveInspector.summarize_contents(
        ["a/x.png", "a/y.PNG", "a/scan.nii.gz", "a/readme", "v1.2/notes.txt"])
    assert s["file_types"] == {".png": 2, ".nii.gz": 1, ".txt": 1}
    assert s["imaging_file_count"] == 3


# ------------------------------------------------------- record adapter

RAW = {
    "id": 42,
    "doi": "10.5281/zenodo.42",
    "metadata": {
        "title": "Fundus set",
        "description": "<p>Images</p>",
        "access_right": "open",
        "keywords": ["retina"],
        "license": {"id": "cc-by-4.0"},
        "publication_date": "2024-05-01",
        "related_identifiers": [
            {"identifier": "10.1000/abc", "relation": "isSupplementTo", "scheme": "doi"},
            {"identifier": "https://doi.org/10.2000/XYZ", "relation": "cites", "scheme": "url"},
            {"identifier": "https://github.com/x/y", "relation": "isSupplementTo", "scheme": "url"},
        ],
    },
    "files": [
        {"key": f"img_{i}.png", "size": 10, "links": {"self": f"u{i}"}} for i in range(25)
    ] + [
        {"key": "vol.nii.gz", "size": 5, "links": {"self": "v"}},
        {"key": "reads.fastq.gz", "size": 5, "links": {"self": "r"}},
        {"key": "all.zip", "size": 100, "links": {"self": "z"}},
    ],
    "_file_analysis": {
        "zip_contents": {
            "all.zip": {"imaging_file_count": 7, "imaging_files": ["d/a.tif"],
                        "file_types": {".tif": 7, ".csv": 1}},
        },
    },
    "_dataset_links": ["https://github.com/x/y"],
    "_weblinks": [{"url": "https://kaggle.com/d", "type": "data_platform"},
                  {"url": "https://doi.org/10.1/z", "type": "doi_reference"}],
}


def test_adapter_fills_counts_and_archive_fields():
    m = zenodo_record_to_metadata(RAW)
    assert m.file_count == 28 and len(m.file_names) == 28
    assert m.img_count == 25 + 7
    assert m.medical_count == 1 and m.genomics_count == 1 and m.archive_count == 1
    assert ".nii.gz" in m.file_types and ".fastq.gz" in m.file_types
    assert m.zip_file_types == {".tif": 7, ".csv": 1}
    assert m.zip_contents == ["d/a.tif"]
    assert m.external_links == ["https://github.com/x/y", "https://kaggle.com/d"]
    assert len(m.related_identifiers) == 3
    assert m.license == "cc-by-4.0" and m.publication_year == "2024"


def test_pipeline_derivations():
    m = zenodo_record_to_metadata(RAW)
    assert _zip_file_types(m) == {".tif": 7, ".csv": 1}
    assert _related_dois(m) == ["10.1000/abc", "10.2000/XYZ"]
    m.zip_file_types = {}
    m.zip_contents = ["x/a.png", "x/b.PNG", "x/c.json"]
    assert _zip_file_types(m) == {".png": 2, ".json": 1}


# ---------------------------------------------- archives that cannot be listed

def _files(*names):
    return [{"key": n, "size": 1000, "links": {"self": f"https://z/{n}"}} for n in names]


def _analyze(monkeypatch, files, listing):
    """analyze_record_files with inspect_archive returning ``listing``
    (a list of member names, None for a failed listing, or an exception)."""
    import envision.scraper as scraper_mod

    def fake_inspect(url, filename, session):
        if isinstance(listing, Exception):
            raise listing
        return listing

    monkeypatch.setattr(scraper_mod.ArchiveInspector, "inspect_archive", staticmethod(fake_inspect))
    return scraper_mod.analyze_record_files({"files": files}, session=None)


def _record(analysis):
    return {"_file_analysis": analysis, "_dataset_links": [], "_weblinks": []}


def test_unlisted_archive_is_kept_not_dropped(monkeypatch):
    # e.g. SYN-OCT.zip: central directory over max_cd_bytes -> inspector None
    a = _analyze(monkeypatch, _files("SYN-OCT.zip", "readme.txt"), None)
    assert [u["name"] for u in a["uninspectable_archives"]] == ["SYN-OCT.zip"]
    assert a["uninspectable_archives"][0]["reason"] == "listing failed"
    assert ZenodoScraper._keep_reason(_record(a)) == "uninspectable_archive"
    # an exception while listing is the same
    a = _analyze(monkeypatch, _files("x.tar.gz"), requests.ConnectionError("reset"))
    assert ZenodoScraper._keep_reason(_record(a)) == "uninspectable_archive"


def test_listed_archive_without_imaging_is_still_dropped(monkeypatch):
    a = _analyze(monkeypatch, _files("code.zip"), ["src/a.py", "README.md"])
    assert a["uninspectable_archives"] == []
    assert ZenodoScraper._keep_reason(_record(a)) is None
    a = _analyze(monkeypatch, _files("empty.zip"), [])          # listed, empty
    assert a["uninspectable_archives"] == [] and ZenodoScraper._keep_reason(_record(a)) is None
    a = _analyze(monkeypatch, _files("fundus.zip"), ["d/1.png"])
    assert ZenodoScraper._keep_reason(_record(a)) == "imaging_files"


def test_rar_and_7z_are_unlisted_but_single_gz_is_not(monkeypatch):
    a = _analyze(monkeypatch, _files("octs.rar", "b.7z"), None)
    assert [u["reason"] for u in a["uninspectable_archives"]] == ["format not listable"] * 2
    assert ZenodoScraper._keep_reason(_record(a)) == "uninspectable_archive"
    a = _analyze(monkeypatch, _files("table.csv.gz"), None)
    assert a["uninspectable_archives"] == [] and ZenodoScraper._keep_reason(_record(a)) is None
    # genomics-only records stay dropped
    a = _analyze(monkeypatch, _files("reads.fastq.gz", "x.rar"), None)
    assert ZenodoScraper._keep_reason(_record(a)) is None


def test_search_counts_records_kept_for_an_unlisted_archive(tmp_path, monkeypatch):
    sc = _scraper(tmp_path, monkeypatch, [[_hit(0), _hit(1)]])
    monkeypatch.setattr(sc, "_should_keep", ZenodoScraper._should_keep.__get__(sc))
    unlisted = {"uninspectable_archives": [{"name": "a.zip"}], "has_archives": True}

    def enrich(rec, inspect):
        rec.update(_record(unlisted if rec["id"] == 1 else {"has_imaging_files": True}))
        return rec

    monkeypatch.setattr(sc, "_enrich_record", enrich)
    out = sc.search("q", max_results=500)
    assert len(out) == 2
    entry = sc.searches[-1]
    assert entry["kept"] == 2 and entry["kept_uninspectable"] == 1
    assert sc.stats["kept_uninspectable_archive"] == 1
    assert _term_status("t", "q", 2, [entry], [])["kept_uninspectable"] == 1


class FlakySession(RangeSession):
    """RangeSession whose first ``n_fail`` HEAD and GET answers are 429."""

    def __init__(self, data, n_fail):
        super().__init__(data)
        self.n_fail = {"head": n_fail, "get": n_fail}

    def head(self, url, **kwargs):
        if self.n_fail["head"]:
            self.n_fail["head"] -= 1
            return FakeResponse(429, headers={"Retry-After": "1"})
        return super().head(url, **kwargs)

    def get(self, url, headers=None, **kwargs):
        if self.n_fail["get"]:
            self.n_fail["get"] -= 1
            return FakeResponse(503)
        return super().get(url, headers=headers, **kwargs)


def test_archive_listing_retries_rate_limits(monkeypatch):
    slept = []
    monkeypatch.setattr(utils.time, "sleep", lambda s: slept.append(s))
    names = ArchiveInspector.inspect_zip_via_range("u", FlakySession(_zip_bytes(10), 2))
    assert names is not None and len(names) == 11
    assert slept == [1.0, 1.0, 2.0, 4.0]          # Retry-After for the HEADs, backoff for the GETs


def test_archive_listing_gives_up_after_max_tries(monkeypatch):
    slept = []
    monkeypatch.setattr(utils.time, "sleep", lambda s: slept.append(s))
    sess = FlakySession(_zip_bytes(10), 99)
    assert ArchiveInspector.inspect_zip_via_range("u", sess) is None
    assert len(slept) == ArchiveInspector.max_tries - 1
