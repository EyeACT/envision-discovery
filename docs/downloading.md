# Downloading raw files

ENVISION can fetch the underlying data files after a record has been classified
as EYE_IMAGING. This is an **opt-in** step controlled by `--download`.

## Classification gate

Files are only downloaded when all of these hold:

1. The record is present in `results/{source}_eye_imaging.json` (i.e. the
   classifier labelled it `EYE_IMAGING`).
2. Its `prob_eye_imaging` is ≥ `--download-threshold` (default `0.80`).
3. The scraped metadata contains a populated `files` list with direct URLs.

Records that fail any of these checks are skipped and logged — never silently
downloaded.

## CLI flags

```
--download                     Enable the download step
--download-threshold FLOAT     Min EYE_IMAGING probability (default 0.80)
--download-dir PATH            Base output dir (default ./data/downloads)
```

## Examples

```bash
# Scrape already done; classify the 515 Zenodo records and download the hits
python -m envision --source zenodo --skip-scrape --download

# Only download very-high-confidence records
python -m envision --source all --download --download-threshold 0.95

# Custom output location (e.g. external disk)
python -m envision --source zenodo --skip-scrape --download \
    --download-dir /mnt/bigdisk/envision-downloads
```

## On-disk layout

```
data/downloads/
└── zenodo/
    ├── _download_log.jsonl              # append-only event log (one JSON obj per line)
    ├── 8254022/
    │   ├── manifest.json                # classification + file metadata + timings
    │   └── Data.zip                     # the actual file(s)
    ├── 10019686/
    │   ├── manifest.json
    │   └── Bay_Area_CCT_Example_October_2023.tar
    └── ...
```

### Per-record `manifest.json`

```json
{
  "source": "zenodo",
  "source_id": "8254022",
  "doi": "10.5281/zenodo.8254022",
  "url": "https://zenodo.org/records/8254022",
  "title": "Dataset for PT-OCT ANN Project",
  "prob_eye_imaging": 0.9998,
  "confidence_threshold": 0.80,
  "downloaded_at": "2026-04-14T17:12:03Z",
  "files": [
    {
      "name": "Data.zip",
      "url": "https://zenodo.org/api/records/8254022/files/Data.zip/content",
      "size_bytes": 316725248,
      "expected_size_bytes": 316725248,
      "checksum_source": "md5:258a8738e0e5bf2dc2094b75e8683cec",
      "file_id": "bc9e9cd7-445a-4821-a89a-826d05d0fed0",
      "status": "downloaded",
      "elapsed_s": 42.3
    }
  ]
}
```

### `_download_log.jsonl`

Append-only, one JSON object per event. Useful for auditing and for tallying
total bytes/time across resumed runs. Events include per-file `downloaded` /
`exists` / `failed` entries and a `run_complete` summary.

## Resume behaviour

- Files already on disk with the expected size are skipped (logged as `exists`).
- Partial downloads (`*.part`) are resumed when the server honours HTTP `Range`;
  otherwise the file restarts from zero.
- Failures retry with exponential backoff (up to 5 attempts); terminal failures
  are logged and the record's other files still attempt.

## Per-source notes

| Source     | File URLs populated at scrape time? | Notes                                                                  |
|------------|--------------------------------------|------------------------------------------------------------------------|
| Zenodo     | yes                                  | Raw JSON already on disk from prior scrapes works without re-scraping. |
| Figshare   | yes                                  | Uses `files[].download_url` from the article detail endpoint.          |
| Dryad      | yes                                  | Uses HATEOAS file links; resolved to absolute URLs.                    |
| Kaggle     | yes (dataset-level ZIP)              | Kaggle serves all files as one archive at `/datasets/download/{ref}`.  |
| OSF        | **no**                               | OSF rate limits prevent fetching file lists at scrape time.            |
| DataCite   | n/a                                  | Metadata-only; no file payload.                                        |
| NEI        | n/a                                  | Grants index; no files to download.                                    |

## Storage planning

Zenodo datasets can be multi-gigabyte. Before kicking off a large run:

```bash
# Sum sizes of all EYE_IMAGING records above threshold (rough estimate)
python3 -c "
import json, pathlib
eye = json.load(open('results/zenodo_eye_imaging.json'))
hi = [r for r in eye if r['prob_eye_imaging'] >= 0.80]
total = sum(r.get('size_mb', 0) for r in hi)
print(f'{len(hi)} records, ~{total/1024:.1f} GB total')
"
```
