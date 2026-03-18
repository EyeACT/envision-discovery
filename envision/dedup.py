#!/usr/bin/env python3
"""
ENVISION: Cross-Source Duplicate Detection

Detects duplicate dataset records across multiple sources (e.g., the same
dataset listed on both Zenodo and Figshare).  Uses the sentence-transformer
model already employed by the classifier to compute embeddings and identifies
near-duplicates via cosine similarity.

Usage:
    from envision.dedup import DedupChecker, run_dedup

    # From pre-loaded results dicts
    checker = DedupChecker(similarity_threshold=0.92)
    dupes = checker.find_duplicates({"zenodo": [...], "figshare": [...]})
    checker.save_report(dupes, "results/dedup_report.json")

    # From results directory (loads *_all_results.json files)
    dupes = run_dedup("results/", threshold=0.92)
"""

import json
import logging
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MODEL_NAME = "sentence-transformers/all-mpnet-base-v2"


def _tokenise_title(title: str, min_len: int = 4) -> set[str]:
    """Return the set of lower-cased tokens from *title* that are longer than
    *min_len* characters.  Used as a cheap pre-filter before full embedding
    comparison."""
    return {w.lower() for w in title.split() if len(w) > min_len}


# ---------------------------------------------------------------------------
# DedupChecker
# ---------------------------------------------------------------------------


class DedupChecker:
    """Detect duplicate dataset records across sources using embedding similarity."""

    def __init__(self, similarity_threshold: float = 0.92):
        """Initialize with a cosine similarity threshold for duplicate detection.

        Args:
            similarity_threshold: Minimum cosine similarity (0-1) between two
                record embeddings for them to be considered potential duplicates.
                Values >= 0.97 are flagged as ``merge`` candidates; lower values
                are flagged for manual ``review``.
        """
        self.threshold = similarity_threshold

    # ------------------------------------------------------------------
    # cheap pre-filter
    # ------------------------------------------------------------------

    @staticmethod
    def _quick_overlap(record_a: dict, record_b: dict) -> bool:
        """Return True if two records share at least one title word longer than
        4 characters.

        This is a cheap O(1)-per-pair filter that avoids computing the full
        cosine similarity for record pairs that are obviously unrelated.
        """
        tokens_a = _tokenise_title(record_a["title"])
        tokens_b = _tokenise_title(record_b["title"])
        return bool(tokens_a & tokens_b)

    # ------------------------------------------------------------------
    # main entry point
    # ------------------------------------------------------------------

    def find_duplicates(
        self, results_by_source: dict[str, list[dict]]
    ) -> list[dict]:
        """Find potential duplicates across sources.

        Args:
            results_by_source: Dict mapping source name to list of result dicts
                (as produced by the pipeline, with ``title``, ``description``,
                ``source``, ``source_id``, etc.)

        Returns:
            List of duplicate groups sorted by descending similarity, each a
            dict with:

            - ``records`` -- list of record summary dicts (source, source_id,
              title, url, label)
            - ``similarity`` -- float cosine similarity
            - ``suggested_action`` -- ``'merge'`` (>= 0.97) or ``'review'``
        """
        # Flatten all records with source tracking
        all_records: list[dict] = []
        for source, records in results_by_source.items():
            for r in records:
                all_records.append(
                    {
                        "source": r.get("source", source),
                        "source_id": r.get(
                            "source_id", r.get("zenodo_id", "")
                        ),
                        "title": r.get("title", ""),
                        "description": r.get("description", "")[:500],
                        "label": r.get("label", ""),
                        "url": r.get("url", ""),
                    }
                )

        if len(all_records) < 2:
            logger.info(
                "Fewer than 2 records across sources -- nothing to compare."
            )
            return []

        logger.info(
            "Computing embeddings for %d records from %d sources ...",
            len(all_records),
            len(results_by_source),
        )

        # Compute embeddings using sentence transformer
        model = SentenceTransformer(_MODEL_NAME)
        texts = [
            f"{r['title']} {r['description']}" for r in all_records
        ]
        embeddings = model.encode(
            texts, show_progress_bar=True, batch_size=64
        )

        # Normalize for cosine similarity
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms[norms == 0] = 1
        embeddings = embeddings / norms

        # Find cross-source duplicates.
        # Pre-filter: only compute full cosine similarity for pairs that share
        # at least one keyword token in their titles (cheap string overlap).
        duplicates: list[dict] = []
        seen_pairs: set[tuple[str, str]] = set()
        pairs_checked = 0

        for i in range(len(all_records)):
            for j in range(i + 1, len(all_records)):
                # Skip same-source comparisons
                if all_records[i]["source"] == all_records[j]["source"]:
                    continue

                # Cheap pre-filter: require at least one shared title word
                if not self._quick_overlap(all_records[i], all_records[j]):
                    continue

                pairs_checked += 1
                sim = float(np.dot(embeddings[i], embeddings[j]))

                if sim >= self.threshold:
                    pair_key = tuple(
                        sorted(
                            [
                                f"{all_records[i]['source']}:{all_records[i]['source_id']}",
                                f"{all_records[j]['source']}:{all_records[j]['source_id']}",
                            ]
                        )
                    )
                    if pair_key not in seen_pairs:
                        seen_pairs.add(pair_key)
                        duplicates.append(
                            {
                                "records": [
                                    {
                                        "source": all_records[i]["source"],
                                        "source_id": all_records[i][
                                            "source_id"
                                        ],
                                        "title": all_records[i]["title"][
                                            :100
                                        ],
                                        "url": all_records[i]["url"],
                                        "label": all_records[i]["label"],
                                    },
                                    {
                                        "source": all_records[j]["source"],
                                        "source_id": all_records[j][
                                            "source_id"
                                        ],
                                        "title": all_records[j]["title"][
                                            :100
                                        ],
                                        "url": all_records[j]["url"],
                                        "label": all_records[j]["label"],
                                    },
                                ],
                                "similarity": round(sim, 4),
                                "suggested_action": (
                                    "merge" if sim >= 0.97 else "review"
                                ),
                            }
                        )

        logger.info(
            "Pre-filter passed %d cross-source pairs; found %d duplicates "
            "(threshold=%.2f).",
            pairs_checked,
            len(duplicates),
            self.threshold,
        )

        # Sort by similarity descending
        duplicates.sort(key=lambda x: -x["similarity"])
        return duplicates

    # ------------------------------------------------------------------
    # reporting
    # ------------------------------------------------------------------

    def save_report(self, duplicates: list[dict], output_path: str) -> None:
        """Save dedup report as JSON.

        Args:
            duplicates: List of duplicate-group dicts as returned by
                :meth:`find_duplicates`.
            output_path: Destination file path (directories created as needed).
        """
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(
                {
                    "total_duplicate_pairs": len(duplicates),
                    "merge_candidates": sum(
                        1
                        for d in duplicates
                        if d["suggested_action"] == "merge"
                    ),
                    "review_candidates": sum(
                        1
                        for d in duplicates
                        if d["suggested_action"] == "review"
                    ),
                    "duplicates": duplicates,
                },
                f,
                indent=2,
            )
        logger.info(
            "Dedup report: %d pairs saved to %s", len(duplicates), output_path
        )


# ---------------------------------------------------------------------------
# Standalone convenience function
# ---------------------------------------------------------------------------


def run_dedup(
    results_dir: str, threshold: float = 0.92
) -> list[dict]:
    """Load all results files and find cross-source duplicates.

    Scans *results_dir* for ``*_all_results.json`` files, groups them by
    source name (derived from the filename prefix, e.g.
    ``zenodo_all_results.json`` -> ``zenodo``), and runs
    :class:`DedupChecker`.

    Args:
        results_dir: Path to the directory containing
            ``*_all_results.json`` files.
        threshold: Cosine similarity threshold passed to
            :class:`DedupChecker`.

    Returns:
        List of duplicate-group dicts (see :meth:`DedupChecker.find_duplicates`).
    """
    results_path = Path(results_dir)
    if not results_path.is_dir():
        raise FileNotFoundError(
            f"Results directory does not exist: {results_dir}"
        )

    results_by_source: dict[str, list[dict]] = {}
    for fp in sorted(results_path.glob("*_all_results.json")):
        source_name = fp.name.replace("_all_results.json", "")
        logger.info("Loading %s (%s) ...", fp.name, source_name)
        with open(fp) as f:
            records = json.load(f)
        results_by_source[source_name] = records
        logger.info("  -> %d records", len(records))

    if not results_by_source:
        logger.warning(
            "No *_all_results.json files found in %s", results_dir
        )
        return []

    total = sum(len(v) for v in results_by_source.values())
    logger.info(
        "Loaded %d records across %d sources: %s",
        total,
        len(results_by_source),
        ", ".join(
            f"{k} ({len(v)})" for k, v in results_by_source.items()
        ),
    )

    checker = DedupChecker(similarity_threshold=threshold)
    duplicates = checker.find_duplicates(results_by_source)

    # Auto-save report alongside the results
    report_path = results_path / "dedup_report.json"
    checker.save_report(duplicates, str(report_path))

    return duplicates
