# Figshare keyword pull

## Why the old Figshare scrape stopped at 2,000

`FigshareScraper` searched datasets only, 100 results per search term
(`--max-per-query` default), with page/page_size paging. The April 14 2026
scrape (`results/figshare_all_results.json`) therefore holds exactly 2,000
records.

## What changed

- No per-term cap by default for Figshare. `--max-per-query N` still caps it.
- Pages follow the `X-Cursor` response header (sent back as an `X-Cursor`
  request header). page/page_size paging stops at an offset of 10,000
  (HTTP 422 PaginationOffsetExceeded) and offset/limit at 5,000; the cursor
  does not ("retina" across all item types returns 16,051 ids). Cursor and
  page paging return the same ids for queries under the cap.
- Item types: figure, media, dataset, fileset (1 to 4). These can hold image
  files. Journal contributions, theses and software are left out.
- `access_type` now distinguishes open, embargoed, confidential,
  metadata_only and download_disabled.

## Query semantics

Bare words in `search_for` must all match (AND), the same as the Zenodo
scraper's AND-required queries. Figshare's `OR` operator does not behave as
OR ("fundus OR fundus" returns about 13,000 datasets, "fundus" 1,504), and
running one query per word instead (any word matches) passed 490,000 items
after 27 of about 75 words, because words such as "eye", "image" and
"optical" match most of Figshare. AND is the only surveyable choice.

## Full pull tool

`envision/scrapers/figshare_full.py` runs a reproducible pull in phases and
needs only `requests` (`bs4` optional):

```
python envision/scrapers/figshare_full.py search  --out results/figshare_full_<date> --modes and
python envision/scrapers/figshare_full.py details --out results/figshare_full_<date> \
    --metadata-dir data/metadata/figshare_full --mode and --item-types 1,2,3,4
python envision/scrapers/figshare_full.py build   --out results/figshare_full_<date> \
    --metadata-dir data/metadata/figshare_full --mode and --item-types 1,2,3,4
```

- `search` writes `<out>_hits.json`: every hit id with the terms it matched
  and per-query counts, plus the sha256 of `envision/scraper.py` so a pull is
  tied to one version of `SEARCH_TERMS`. It resumes per query.
- `selfcheck` compares cursor and page paging on a few queries.
- `details` fetches each article's JSON (files, license, access fields) at
  `--delay` seconds per request and resumes from the cached files.
- `build` writes `<out>.json` (one record per article, with file names,
  sizes, download URLs and md5) and `<out>_summary.json` (counts by item type,
  access type and term).

Set `FIGSHARE_ACCESS_TOKEN` for authenticated requests; the token is only
sent to api.figshare.com and is never logged or written.

The 2026-10-06 AND search over the 47 terms found 13,603 unique items
across all item types (figure 5,633, dataset 4,873, journal contribution
1,762, media 646, thesis 314, other few); 11,152 are figures, media,
datasets or filesets.
