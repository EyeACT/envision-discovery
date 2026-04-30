"""Method schematic for the ENVISION discovery pipeline.

Five-stage flow rendered left-to-right:
  1. Sources    (7 repositories)
  2. Harvest    (47 ophthalmology queries; per-record metadata pulled)
  3. Inspect    (HTTP Range reads of ZIP/TAR central directories)
  4. Classify   (SetFit head over all-mpnet-base-v2; binary EYE_IMAGING/NEGATIVE)
  5. Gate       (download files only when EYE_IMAGING and confidence ≥ 0.80)

Renders as PNG so it embeds cleanly into a poster slide.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

ROOT = Path(__file__).resolve().parent.parent

STAGES = [
    {
        "title": "Sources",
        "subtitle": "7 repositories",
        "lines": [
            "Zenodo · Figshare",
            "Dryad · OSF",
            "DataCite · Kaggle",
            "NIH RePORTER (NEI)",
        ],
        "color": "#3b6fa8",
    },
    {
        "title": "Harvest",
        "subtitle": "47 ophthalmic queries",
        "lines": [
            "OCT, fundus, OCTA,",
            "retina, glaucoma,",
            "macula, choroid, …",
            "→ per-record metadata",
        ],
        "color": "#4a8fc7",
    },
    {
        "title": "Inspect",
        "subtitle": "Archive contents",
        "lines": [
            "HTTP Range reads of",
            "ZIP / TAR central dirs",
            "(no archive download)",
            "→ true file listings",
        ],
        "color": "#5fa8d3",
    },
    {
        "title": "Classify",
        "subtitle": "SetFit · all-mpnet-base-v2",
        "lines": [
            "title + description +",
            "keywords + file types",
            "→ EYE_IMAGING / NEGATIVE",
            "with class probabilities",
        ],
        "color": "#7bbfdc",
    },
    {
        "title": "Gate & download",
        "subtitle": "Confidence-thresholded",
        "lines": [
            "EYE_IMAGING and",
            "P(eye_imaging) ≥ 0.80",
            "→ download to EP",
            "(else: metadata only)",
        ],
        "color": "#a3d4ea",
    },
]

# Headline metrics across the bottom
METRICS = [
    ("42,524", "records harvested"),
    ("6,602", "EYE_IMAGING"),
    ("0.961", "test accuracy"),
    ("0.936", "EYE_IMAGING F1"),
    ("30/33", "manual spot-check (90.9%)"),
]


def _box(ax, x, y, w, h, color, title, subtitle, lines):
    """Draw a stage box.

    Layout (top to bottom inside the box):
      - title bar (colored, ~22% of h)
      - subtitle line (italic, in the body color)
      - blank gap
      - up to 4 body lines, evenly spaced
    """
    # Outer rounded frame
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.02,rounding_size=0.06",
        linewidth=1.6,
        edgecolor=color,
        facecolor="white",
    ))
    # Title bar (filled)
    title_h = 0.22 * h
    ax.add_patch(FancyBboxPatch(
        (x, y + h - title_h), w, title_h,
        boxstyle="round,pad=0.0,rounding_size=0.06",
        linewidth=0,
        facecolor=color,
    ))
    ax.text(
        x + w / 2, y + h - title_h / 2, title,
        ha="center", va="center", fontsize=14, fontweight="bold",
        color="white",
    )
    # Subtitle directly under the bar
    subtitle_y = y + h - title_h - 0.18
    ax.text(
        x + w / 2, subtitle_y, subtitle,
        ha="center", va="center", fontsize=10, color=color, style="italic",
    )
    # Body lines fill the remaining space evenly
    body_top = subtitle_y - 0.30
    body_bot = y + 0.18
    n_lines = max(1, len(lines))
    if n_lines == 1:
        positions = [(body_top + body_bot) / 2]
    else:
        positions = [
            body_top - i * (body_top - body_bot) / (n_lines - 1)
            for i in range(n_lines)
        ]
    for ln, ly in zip(lines, positions):
        ax.text(
            x + w / 2, ly, ln,
            ha="center", va="center", fontsize=10, color="#222222",
        )


def main():
    n = len(STAGES)
    fig_w, fig_h = 16, 7.0
    fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=160)
    ax.set_xlim(0, fig_w)
    ax.set_ylim(0, fig_h)
    ax.set_aspect("equal")
    ax.axis("off")

    # Layout: 5 boxes evenly spaced, with arrows between them
    box_w = 2.7
    box_h = 3.0
    gap = (fig_w - n * box_w) / (n + 1)
    box_y = 2.6

    centers = []
    for i, st in enumerate(STAGES):
        x = gap + i * (box_w + gap)
        _box(ax, x, box_y, box_w, box_h, st["color"],
             st["title"], st["subtitle"], st["lines"])
        centers.append((x + box_w / 2, box_y + box_h / 2))

    # Arrows between consecutive boxes
    for i in range(n - 1):
        x1 = centers[i][0] + box_w / 2 + 0.05
        x2 = centers[i + 1][0] - box_w / 2 - 0.05
        y = box_y + box_h / 2
        ar = FancyArrowPatch(
            (x1, y), (x2, y),
            arrowstyle="-|>", mutation_scale=18,
            linewidth=2.0, color="#444",
        )
        ax.add_patch(ar)

    # Title
    ax.text(
        fig_w / 2, fig_h - 0.6,
        "ENVISION discovery pipeline",
        ha="center", va="center", fontsize=20, fontweight="bold",
        color="#1d3a5e",
    )
    ax.text(
        fig_w / 2, fig_h - 1.1,
        "Multi-source harvesting → archive-aware metadata → "
        "few-shot classification → confidence-gated ingestion",
        ha="center", va="center", fontsize=11, style="italic",
        color="#555",
    )

    # Headline metrics row across the bottom
    metric_y = 1.05
    metric_w = fig_w / len(METRICS)
    for i, (val, lbl) in enumerate(METRICS):
        cx = (i + 0.5) * metric_w
        ax.text(
            cx, metric_y + 0.45, val,
            ha="center", va="center", fontsize=22, fontweight="bold",
            color="#1d3a5e",
        )
        ax.text(
            cx, metric_y - 0.05, lbl,
            ha="center", va="center", fontsize=9.5, color="#444",
        )
    # Divider line above metrics
    ax.plot(
        [0.4, fig_w - 0.4], [metric_y + 1.0, metric_y + 1.0],
        color="#cccccc", linewidth=0.8,
    )

    # Footer
    ax.text(
        0.4, 0.25,
        "github.com/EyeACT/envision-discovery   ·   "
        "github.com/EyeACT/envision-classifier",
        ha="left", va="center", fontsize=8.5, color="#888",
    )

    out = ROOT / "paper" / "envision_method_schematic.png"
    out.parent.mkdir(exist_ok=True, parents=True)
    fig.savefig(out, dpi=200, bbox_inches="tight", facecolor="white")
    print(f"Saved: {out}")


if __name__ == "__main__":
    main()
