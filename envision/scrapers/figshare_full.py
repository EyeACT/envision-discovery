"""
ENVISION Discovery: uncapped Figshare keyword pull.

Self-contained (requests only; bs4 used when installed), so it runs from the
repo root without importing the envision package:

    python envision/scrapers/figshare_full.py search  --out results/figshare_full_20261006
    python envision/scrapers/figshare_full.py details --out results/figshare_full_20261006 \
        --metadata-dir data/metadata/figshare_full --mode and --item-types 1,2,3,4,9,11
    python envision/scrapers/figshare_full.py build   --out results/figshare_full_20261006 \
        --metadata-dir data/metadata/figshare_full --mode and --item-types 1,2,3,4,9,11

Search terms are read from SEARCH_TERMS in envision/scraper.py (parsed, not
imported). Two query modes are run and kept apart:

* ``and``: the term as Figshare's search_for (every word must match; this
  is Figshare's default for bare words).
* ``or``: every word of the term as its own query, hits unioned (any word of
  the term). Figshare's own OR operator is not used: "fundus OR fundus"
  returns about 13,000 datasets while "fundus" returns 1,504, so the
  operator does not mean OR there.

Paging: POST /v2/articles/search caps page/page_size and offset/limit at an
offset of 10,000 (5,000 for offset/limit). The X-Cursor response header,
sent back as an X-Cursor request header, pages past it (checked: "retina"
returns 16,051 ids through the cursor). A query is complete when a page
comes back short or without a cursor.

Rate limits: one request at a time with --delay seconds between requests
(default 1.0). 403, 429 and 5xx back off (Retry-After when given, else
30 s doubling to 600 s) and are retried up to 8 times. With
FIGSHARE_ACCESS_TOKEN in the environment, requests to api.figshare.com
carry "Authorization: token ..."; the token is never logged or written.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import logging
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

logger = logging.getLogger("figshare_full")

API = "https://api.figshare.com/v2"
USER_AGENT = "envision-discovery-figshare-full/1.0 (+https://github.com/EyeACT/envision-discovery)"
PAGE_SIZE = 1000
RETRY = (403, 429, 500, 502, 503, 504)

# Figshare item types (defined_type).
ITEM_TYPES = {
    1: "figure", 2: "media", 3: "dataset", 4: "fileset", 5: "poster", 6: "journal contribution",
    7: "presentation", 8: "thesis", 9: "software", 11: "online resource", 12: "preprint", 13: "book",
    14: "conference contribution", 15: "chapter", 16: "peer review", 17: "educational resource",
    18: "report", 19: "standard", 20: "composition", 21: "funding", 22: "physical object",
    23: "data management plan", 24: "workflow", 25: "monograph", 26: "performance", 27: "event",
    28: "service", 29: "model",
}

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".dcm", ".dicom", ".nii", ".gz", ".e2e",
              ".fds", ".fda", ".img", ".jp2", ".webp", ".npy", ".npz", ".mat", ".h5", ".hdf5", ".mha", ".mhd",
              ".nrrd", ".vol", ".oct", ".sdb", ".avi", ".mp4"}
ARCHIVE_EXTS = {".zip", ".tar", ".tgz", ".gz", ".bz2", ".xz", ".7z", ".rar", ".zst"}


def search_terms(repo: Path) -> tuple[list[str], str]:
    """SEARCH_TERMS from envision/scraper.py and the sha256 of that file."""
    src = (repo / "envision" / "scraper.py").read_text(encoding="utf-8")
    m = re.search(r"SEARCH_TERMS\s*=\s*(\[.*?\n\])", src, re.S)
    if not m:
        raise SystemExit("SEARCH_TERMS not found in envision/scraper.py")
    return list(ast.literal_eval(m.group(1))), hashlib.sha256(src.encode("utf-8")).hexdigest()


def or_words(terms: list[str]) -> list[str]:
    seen, out = set(), []
    for t in terms:
        for w in t.split():
            if w.lower() not in seen:
                seen.add(w.lower())
                out.append(w)
    return out


class Client:
    def __init__(self, delay: float = 1.0, max_tries: int = 8):
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
        self.token = os.environ.get("FIGSHARE_ACCESS_TOKEN", "").strip() or None
        self.delay, self.max_tries = delay, max_tries
        self._last = 0.0
        self.n_requests = 0
        self.n_backoffs = Counter()

    def _headers(self, url: str, extra: dict | None) -> dict:
        h = dict(extra or {})
        if self.token and (urlparse(url).hostname or "") == "api.figshare.com":
            h["Authorization"] = f"token {self.token}"
        return h

    def request(self, method: str, url: str, headers: dict | None = None, **kw) -> requests.Response | None:
        wait = 30.0
        for attempt in range(self.max_tries):
            gap = self.delay - (time.monotonic() - self._last)
            if gap > 0:
                time.sleep(gap)
            self._last = time.monotonic()
            self.n_requests += 1
            try:
                r = self.s.request(method, url, headers=self._headers(url, headers), timeout=(30, 180), **kw)
            except requests.RequestException as e:
                logger.warning("%s %s: %s (attempt %d)", method, url, type(e).__name__, attempt + 1)
                time.sleep(min(wait, 600))
                wait = min(wait * 2, 600)
                continue
            if r.status_code in RETRY:
                self.n_backoffs[r.status_code] += 1
                ra = r.headers.get("Retry-After")
                try:
                    sleep = float(ra) if ra else wait
                except ValueError:
                    sleep = wait
                logger.warning("%s %s -> %d, backing off %.0fs", method, url, r.status_code, sleep)
                time.sleep(min(sleep, 900))
                wait = min(wait * 2, 600)
                continue
            return r
        return None

    def search_all(self, query: str, item_type: int | None = None, cap: int | None = None):
        """(hits, complete, pages): every hit of one search_for query, by
        cursor. ``cap``: stop after this many hits (complete False)."""
        body = {"search_for": query, "page_size": PAGE_SIZE}
        if item_type is not None:
            body["item_type"] = item_type
        hits, cursor, pages = [], None, 0
        while True:
            r = self.request("POST", f"{API}/articles/search", json=body,
                             headers={"X-Cursor": cursor} if cursor else None)
            if r is None or r.status_code != 200:
                raise RuntimeError(f"search {query!r} page {pages + 1}: "
                                   f"{'gave up' if r is None else r.status_code} {'' if r is None else r.text[:200]}")
            page = r.json()
            pages += 1
            hits += page
            cursor = r.headers.get("X-Cursor")
            if len(page) < PAGE_SIZE or not cursor:
                return hits, True, pages
            if cap and len(hits) >= cap:
                return hits, False, pages

    def search_paged(self, query: str, item_type: int | None = None) -> list[dict]:
        """page/page_size paging (offset at most 10,000), for the self-check."""
        out, page = [], 1
        while True:
            body = {"search_for": query, "page": page, "page_size": PAGE_SIZE}
            if item_type is not None:
                body["item_type"] = item_type
            r = self.request("POST", f"{API}/articles/search", json=body)
            if r is None or r.status_code != 200:
                break
            d = r.json()
            out += d
            if len(d) < PAGE_SIZE:
                break
            page += 1
        return out


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write_json(path: Path, doc, indent=None):
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fp:
        json.dump(doc, fp, indent=indent, ensure_ascii=False)
    tmp.replace(path)


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------
def cmd_search(args):
    repo = Path(args.repo)
    terms, sha = search_terms(repo)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    hits_path = out.with_name(out.name + "_hits.json")
    state = json.loads(hits_path.read_text(encoding="utf-8")) if hits_path.is_file() else {
        "generated": _now(), "search_terms_source": "envision/scraper.py SEARCH_TERMS",
        "search_terms_sha256": sha, "n_terms": len(terms), "terms": terms, "queries": {}, "hits": {}}
    if state.get("search_terms_sha256") != sha:
        raise SystemExit("SEARCH_TERMS changed since this hits file was started; use a new --out")
    c = Client(delay=args.delay)
    jobs = []
    if "and" in args.modes:
        jobs += [("and", t, t) for t in terms]
    if "or" in args.modes:
        words = or_words(terms)
        jobs += [("or", w, w) for w in words]
    for mode, term, query in jobs:
        key = f"{mode}:{query}"
        if key in state["queries"] and state["queries"][key].get("complete") is not None:
            continue
        t0 = time.time()
        hits, complete, pages = c.search_all(query, cap=args.or_cap if mode == "or" else None)
        types = Counter()
        for h in hits:
            aid = str(h.get("id"))
            dt = h.get("defined_type")
            types[str(dt)] += 1
            e = state["hits"].get(aid)
            if e is None:
                e = state["hits"][aid] = {"defined_type": dt, "and": [], "or": []}
            if mode == "and" and "title" not in e:
                # or-only hits stay slim: the or pass is a measurement, not a pull
                e.update({"defined_type_name": h.get("defined_type_name"), "title": h.get("title"),
                          "doi": h.get("doi"), "published_date": h.get("published_date"),
                          "url_public_html": h.get("url_public_html")})
            if query not in e[mode]:
                e[mode].append(query)
        state["queries"][key] = {"mode": mode, "query": query, "n_hits": len(hits),
                                 "n_unique": len({h.get("id") for h in hits}), "complete": complete,
                                 "pages": pages, "by_type": dict(types), "seconds": round(time.time() - t0, 1),
                                 "searched_at": _now()}
        logger.info("%s %r: %d hits%s, %d pages", mode, query, len(hits), "" if complete else " (capped)", pages)
        _write_json(hits_path, state)
    state["finished"] = _now()
    state["backoffs"] = {str(k): v for k, v in c.n_backoffs.items()}
    _write_json(hits_path, state)
    print(json.dumps({"hits_file": str(hits_path), "unique_ids": len(state["hits"]),
                      "requests": c.n_requests}, indent=2))


def cmd_selfcheck(args):
    """Cursor paging returns the same ids as page paging for queries under
    the 10,000 offset cap."""
    c = Client(delay=args.delay)
    res = {}
    for q, it in (("fundus", 3), ("retinal OCT", None), ("glaucoma", None)):
        a = {h["id"] for h in c.search_all(q, item_type=it)[0]}
        b = {h["id"] for h in c.search_paged(q, item_type=it)}
        res[f"{q} (item_type {it})"] = {"cursor": len(a), "paged": len(b), "only_cursor": len(a - b),
                                        "only_paged": len(b - a)}
    print(json.dumps(res, indent=2))


# ---------------------------------------------------------------------------
# details
# ---------------------------------------------------------------------------
def selected_ids(state: dict, mode: str, item_types: set[int] | None) -> list[str]:
    out = []
    for aid, h in state["hits"].items():
        if mode == "and" and not h["and"]:
            continue
        if mode == "or" and not (h["or"] or h["and"]):
            continue
        if item_types and h.get("defined_type") not in item_types:
            continue
        out.append(aid)
    return sorted(out, key=int)


def _hits(args) -> dict:
    out = Path(args.out)
    return json.loads(out.with_name(out.name + "_hits.json").read_text(encoding="utf-8"))


def _types(s: str | None) -> set[int] | None:
    return {int(x) for x in s.split(",") if x.strip()} if s else None


def cmd_details(args):
    state = _hits(args)
    ids = selected_ids(state, args.mode, _types(args.item_types))
    md = Path(args.metadata_dir)
    md.mkdir(parents=True, exist_ok=True)
    c = Client(delay=args.delay)
    todo = [i for i in ids if not (md / f"{i}.json").is_file()]
    print(f"[details] {len(ids)} selected, {len(ids) - len(todo)} cached, {len(todo)} to fetch", flush=True)
    failed = {}
    fail_path = Path(args.out).with_name(Path(args.out).name + "_details_failed.json")
    if fail_path.is_file():
        failed = json.loads(fail_path.read_text(encoding="utf-8"))
    t0 = time.time()
    for n, aid in enumerate(todo, 1):
        r = c.request("GET", f"{API}/articles/{aid}")
        if r is None or r.status_code != 200:
            failed[aid] = "gave up" if r is None else f"HTTP {r.status_code}"
        else:
            try:
                doc = r.json()
            except ValueError:
                failed[aid] = "bad JSON"
            else:
                _write_json(md / f"{aid}.json", doc)
                failed.pop(aid, None)
        if n % 500 == 0 or n == len(todo):
            _write_json(fail_path, failed)
            rate = n / max(1e-6, time.time() - t0)
            print(f"[details] {n}/{len(todo)} ({rate * 3600:.0f}/h) failed {len(failed)} "
                  f"backoffs {dict(c.n_backoffs)}", flush=True)
    _write_json(fail_path, failed)


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------
def _text(html: str) -> str:
    if not html:
        return ""
    try:
        from bs4 import BeautifulSoup
        return BeautifulSoup(html, "html.parser").get_text(" ").strip()
    except Exception:  # noqa: BLE001
        return re.sub(r"<[^>]+>", " ", html).strip()


def _ext(name: str) -> str:
    n = name.lower()
    for multi in (".tar.gz", ".tar.bz2", ".tar.xz", ".nii.gz"):
        if n.endswith(multi):
            return multi
    return "." + n.rsplit(".", 1)[-1] if "." in n else ""


def access_type(a: dict) -> str:
    """open, embargoed, confidential, metadata_only or download_disabled."""
    if a.get("is_confidential"):
        return "confidential"
    if a.get("is_embargoed"):
        return "embargoed"
    if a.get("is_metadata_record"):
        return "metadata_only"
    if a.get("download_disabled"):
        return "download_disabled"
    return "open"


def to_record(a: dict, hit: dict) -> dict:
    files = []
    link_only = []
    for f in a.get("files") or []:
        item = {"id": f.get("id"), "name": f.get("name"), "size": int(f.get("size") or 0),
                "download_url": f.get("download_url"), "computed_md5": f.get("computed_md5") or None,
                "supplied_md5": f.get("supplied_md5") or None, "is_link_only": bool(f.get("is_link_only")),
                "mimetype": f.get("mimetype")}
        files.append(item)
        if item["is_link_only"] and item["download_url"]:
            link_only.append(item["download_url"])
    real = [f for f in files if not f["is_link_only"]]
    exts = Counter(_ext(f["name"] or "") for f in real)
    lic = a.get("license") or {}
    desc = _text(a.get("description") or "")
    tags = list(a.get("tags") or a.get("keywords") or [])
    cats = [c.get("title") for c in a.get("categories") or [] if c.get("title")]
    related = [m.get("link") or m.get("identifier") for m in a.get("related_materials") or []
               if isinstance(m, dict) and (m.get("link") or m.get("identifier"))]
    total = sum(f["size"] for f in real)
    return {
        "source": "figshare",
        "source_id": str(a.get("id")),
        "doi": a.get("doi") or None,
        "url": a.get("url_public_html") or f"https://figshare.com/articles/{a.get('id')}",
        "title": _text(a.get("title") or ""),
        "description": desc[:4000],
        "keywords": tags + cats,
        "item_type": a.get("defined_type"),
        "item_type_name": a.get("defined_type_name"),
        "published_date": a.get("published_date"),
        "created_date": a.get("created_date"),
        "modified_date": a.get("modified_date"),
        "version": a.get("version"),
        "group_id": a.get("group_id"),
        "license": lic.get("name") if isinstance(lic, dict) else (str(lic) if lic else None),
        "license_url": lic.get("url") if isinstance(lic, dict) else None,
        "access_type": access_type(a),
        # Data access requests: confidential, metadata-only and
        # download-disabled items are requested from the authors via the
        # article page; embargoed items open by themselves on embargo_date.
        "access_request": access_type(a) in ("confidential", "metadata_only", "download_disabled"),
        "access_request_url": (a.get("url_public_html") or f"https://figshare.com/articles/{a.get('id')}")
        if access_type(a) in ("confidential", "metadata_only", "download_disabled") else None,
        "access_conditions": _text(str(a.get("confidential_reason") or a.get("metadata_reason")
                                       or a.get("embargo_reason") or a.get("embargo_title") or "")) or None,
        "embargo_until": a.get("embargo_date") if a.get("is_embargoed") else None,
        "is_embargoed": bool(a.get("is_embargoed")),
        "embargo_type": a.get("embargo_type"),
        "embargo_date": a.get("embargo_date"),
        "is_confidential": bool(a.get("is_confidential")),
        "is_metadata_record": bool(a.get("is_metadata_record")),
        "download_disabled": bool(a.get("download_disabled")),
        "file_count": len(real),
        "link_only_file_count": len(link_only),
        "total_size_bytes": total,
        "size_mb": round(total / 1e6, 3),
        "file_names": [f["name"] for f in real][:200],
        "file_types": sorted(e for e in exts if e),
        "img_count": sum(n for e, n in exts.items() if e in IMAGE_EXTS and e != ".gz"),
        "archive_count": sum(n for e, n in exts.items() if e in ARCHIVE_EXTS or e.startswith(".tar")),
        "external_links": link_only + related,
        "files": files,
        "matched_terms_and": hit.get("and") or [],
        "matched_words_or": hit.get("or") or [],
    }


def cmd_build(args):
    state = _hits(args)
    types = _types(args.item_types)
    ids = selected_ids(state, args.mode, types)
    md = Path(args.metadata_dir)
    records, missing = [], []
    for aid in ids:
        p = md / f"{aid}.json"
        if not p.is_file():
            missing.append(aid)
            continue
        records.append(to_record(json.loads(p.read_text(encoding="utf-8")), state["hits"][aid]))
    out = Path(args.out)
    _write_json(out.with_suffix(".json"), records)
    # summary
    by_type = Counter(r["item_type_name"] for r in records)
    with_files = [r for r in records if r["file_count"]]
    arch = sum(1 for r in records if r["archive_count"])
    by_access = Counter(r["access_type"] for r in records)
    per_term = {}
    for t in state["terms"]:
        rs = [r for r in records if t in r["matched_terms_and"]]
        per_term[t] = {"records": len(rs), "by_item_type": dict(Counter(r["item_type_name"] for r in rs))}
    summary = {
        "generated": _now(), "mode": args.mode, "item_types": sorted(types) if types else "all",
        "records": len(records), "details_missing": missing, "by_item_type": dict(by_type),
        "by_access_type": dict(by_access), "records_with_files": len(with_files),
        "files": sum(r["file_count"] for r in records),
        "bytes": sum(r["total_size_bytes"] for r in records),
        "records_with_archives": arch,
        "archive_files": sum(r["archive_count"] for r in records),
        "records_with_image_ext_files": sum(1 for r in records if r["img_count"]),
        "records_over_15gb": sum(1 for r in records if r["total_size_bytes"] > 15e9),
        "per_term_and": per_term,
    }
    _write_json(out.with_name(out.name + "_summary.json"), summary, indent=2)
    print(json.dumps({k: v for k, v in summary.items() if k not in ("per_term_and", "details_missing")}, indent=2))
    print(f"details missing: {len(missing)}")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("search", "selfcheck", "details", "build"):
        s = sub.add_parser(name)
        s.add_argument("--out", default="results/figshare_full")
        s.add_argument("--repo", default=".")
        s.add_argument("--delay", type=float, default=1.0, help="seconds between requests (default 1.0)")
        s.add_argument("--metadata-dir", default="data/metadata/figshare_full")
        s.add_argument("--mode", choices=("and", "or"), default="and")
        s.add_argument("--item-types", default=None, help="comma-separated defined_type numbers (default all)")
        s.add_argument("--modes", default="and,or", help="search: query modes to run (default and,or)")
        s.add_argument("--or-cap", type=int, default=50_000,
                       help="search: stop an or-mode word query after this many hits (default 50000)")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args.modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    {"search": cmd_search, "selfcheck": cmd_selfcheck, "details": cmd_details, "build": cmd_build}[args.cmd](args)


if __name__ == "__main__":
    main()
