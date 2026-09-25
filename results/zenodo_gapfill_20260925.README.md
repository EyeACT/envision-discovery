# Zenodo gap-fill, 2026-09-25

`zenodo_gapfill_20260925.json` holds 336 Zenodo records that belong in the
Zenodo scrape but are missing from `zenodo_all_results.json` (30,501 records,
April 24 2026). It has the same fields in the same order as that file and
the same sort (by record id as a string). No record appears in both files.
Concatenating the two is fine for listing and surveying records, but some
count fields are defined differently (see "Field definitions" below).

## What is in it

**From the April 14 scrape (266 records).** These were in the April 14
scrape (515 records) and are absent from the 30,501. The April 14 run used
OR-semantics queries (any word of a term); the 30,501 was built from a
cache of per-record JSON, not from a fresh search.
- 261 of the 266 still match the OR-semantics queries.
- 5 are superseded versions (Zenodo search returns only the latest
  version). For 4 of them the file holds the latest version instead, fetched,
  enriched and classified the same way as the rest (the label did not change
  for any of the 4):

  | April 14 id | latest id in this file |
  | --- | --- |
  | 10229781 | 21377326 |
  | 10307282 | 21374868 |
  | 10332073 | 21376922 |
  | 15719800 | 19183572 |

  The fifth, 17958965 (EYE_IMAGING), stays as it is: its latest version,
  19589156, is restricted and lists no files, while 17958965 has an open
  file. The provenance file names the latest id.
- 68 of these records fail the keep filter as fixed in this change (archives
  where inspection found no imaging members). They are included so nothing
  from the earlier scrape is lost, and they are flagged in the provenance
  file. 49 of the 68 have an archive that could not be listed. The scraper
  now keeps such records (see below), so a fresh scrape would keep those 49
  and drop the other 19.

**From the current queries (71 records).** The current search terms (AND
semantics, datasets only) return these today, and the 30,501 lacks them.
70 of the 71 pass the fixed keep filter. The exception is 17151869: its
SYN-OCT.zip has a central directory of about 108 MB, over the 64 MB
inspection cap, so the listing fails. It is in the file because it was also
in the April 14 scrape, so 266 + 71 - 1 = 336. The current scraper keeps it
too, because it now keeps records with an archive it cannot list.

Why the 71 were missing:
- 53 were created after April 24.
- 18 are older. Emulating the pre-fix keep filter on today's enrichment
  (`missing_cause` in the provenance file) splits them as follows:
  - 10 are archive-only records whose ZIP central directories are over
    64 KB (2,745 to 26,488 entries; a directory entry takes at least 46
    bytes, so anything over 1,424 entries cannot fit). The old inspector
    read only the last 64 KB, listed nothing for these, and the keep filter
    dropped them silently. That bug is fixed.
  - 1 is 17151869, described above. Both the old and the fixed filter
    dropped it.
  - 7 pass the pre-fix filter as enriched today, so the filter does not
    explain them. Two causes fit the evidence, and it does not decide
    between them:
    - An archive listing failed on April 24. The old code turned any failed
      HEAD or Range request, including a rate limit, into "no listing",
      logged it at debug level at most, and dropped the record. Such
      failures still happened in the September build: five of the seven
      have ZIPs that went unlisted, and in record 10778462 35 of 44 ZIPs
      went unlisted, while a later retry of one of those ZIPs listed it
      fine. Archive requests are now retried on 429 and 5xx.
    - The Zenodo stage never ran a fresh search for these records.

## Field definitions (differ from the 30,501)

The gap-fill was converted with `envision.cli.zenodo_record_to_metadata`.
The 30,501 was not, so these fields mean different things in the two files:
- `img_count`
  - In the 30,501: the count of top-level files with any imaging
    extension, including .dcm, .nii, .mat, .h5 and similar.
  - Here: top-level standard image files (.png, .jpg, .tif and similar)
    plus the imaging members counted inside archives. The medical and
    scientific formats are counted in `medical_count` instead.
- `medical_count`, `genomics_count`: always 0 in the 30,501 (never set).
  Here they are real counts.
- `external_links`
  - In the 30,501: every URL found in the description.
  - Here: the dataset links from related identifiers, plus description
    URLs classified as data platforms.
- `zip_file_types`, `related_dois`: always empty in the 30,501. Here they
  are filled in.

Do not compare or sum these fields across the two files until the 30,501 is
regenerated with the same converter. The survey (envision-eye-actionable)
reads none of them.

## How it was built

1. Records were fetched from the Zenodo API.
2. They were enriched with the fixed scraper (`ZenodoScraper._enrich_record`,
   whose ZIP inspection now reads central directories larger than 64 KB).
3. They were converted with `envision.cli.zenodo_record_to_metadata`.
4. They were classified with `envision.pipeline.run_pipeline`.

The provenance file, `zenodo_gapfill_20260925_provenance.json`, records per
record id:
- why it was included;
- the current search terms it matches;
- whether the fixed keep filter keeps it (`kept_by_fixed_filter`), and
  whether it would be kept once unlisted archives count
  (`kept_by_filter_keeping_unlisted_archives`, `unlisted_archives`);
- whether it is the latest version (`supersedes`, `superseded_by`,
  `latest_version_id`);
- its creation date;
- for the 18 older current-query records, `missing_cause` and
  `archive_entries`.

Superseded ids that were replaced stay in the provenance file with
`included: false`. No request failed while building the file.

Labels: 42 EYE_IMAGING and 294 NEGATIVE. Every record from the April 14
scrape, and every latest version that replaced one, has the same label it
had on April 14.
