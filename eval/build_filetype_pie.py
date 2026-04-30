"""Curated pie chart of imaging-indicative file types in the EYE_IMAGING
records, scoped for EnvisionPortal/EyeACT's clinical eye-imaging mission.

Allow-list rationale
--------------------
INCLUDED (actual eye-imaging file bytes or container thereof):
  Stills           .jpg/.jpeg, .png, .tif/.tiff, .bmp
  DICOM            .dcm
  OCT-native       .e2e (Heidelberg Spectralis), .oct
  Medical volume   .nii, .mha
  Cine / video     .cine, .mp4, .mov, .avi  (slit-lamp, OCTA sweeps)
  Array container  .mat (MATLAB; common for OCT volumes & retinal arrays)
  Other imaging    .ppm, .raw

EXCLUDED (not the kind of imaging EyeACT is trying to catalogue):
  Documents/code   .pdf, .docx, .xls(x), .csv, .md, .txt, .json, .py, .r,
                   .ipynb, .html, .xml, .sav, .db
  Archives         .zip, .rar, .7z, .tar, .gz
  Animations       .gif, .eps, .svg          # illustrations, not data
  Confocal micros. .lsm, .lif, .czi, .ims, .mcs, .nd2
                   (cell-level microscopy is research adjacent, but the
                    poster is about clinical imaging discovery)
  Promo/training   .wmv, .mpg, .m4v, .flv, .mkv, .heic
  ML weights       .pkl, .pth
"""

from __future__ import annotations

import json
import glob
from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent

# Each tuple: (display_label, [extensions or MIME types to merge]).
# Order here is the slice order in the legend (largest first by convention).
ALLOW = [
    ("JPEG",          {".jpg", ".jpeg", "image/jpeg"}),
    ("PNG",           {".png", "image/png"}),
    ("TIFF",          {".tif", ".tiff", "image/tiff"}),
    ("BMP",           {".bmp"}),
    ("DICOM (.dcm)",  {".dcm"}),
    ("OCT (.e2e/.oct)", {".e2e", ".oct"}),
    ("MATLAB (.mat)", {".mat"}),
    ("Video (.mp4/.mov/.avi/.cine)",
                      {".mp4", ".mov", ".avi", ".cine"}),
    ("Medical volume (.nii/.mha)",
                      {".nii", ".mha"}),
    ("Other (.ppm/.raw)",
                      {".ppm", ".raw"}),
]
ALLOWED_FLAT = {e for _, exts in ALLOW for e in exts}


def main():
    label_records = Counter()       # records that carry ≥1 ext in this label
    label_occurrences = Counter()   # raw count, summed across records
    excluded_imaging_like = Counter()  # extensions we deliberately dropped

    # Things we explicitly want to track as "we deliberately excluded these"
    excluded_track = {
        ".gif", ".eps", ".svg",
        ".lsm", ".lif", ".czi", ".ims", ".mcs", ".nd2",
        ".wmv", ".mpg", ".m4v", ".flv", ".mkv", ".heic",
    }

    total_eye = 0
    records_with_any_imaging = 0

    for path in sorted(glob.glob(str(ROOT / "results" / "*_eye_imaging.json"))):
        with open(path) as f:
            recs = json.load(f)
        for r in recs:
            total_eye += 1
            ft = [e.lower().strip() for e in (r.get("file_types") or []) if e]
            saw_any_imaging = False

            for label, exts in ALLOW:
                hit = any(e in exts for e in ft)
                if hit:
                    label_records[label] += 1
                    saw_any_imaging = True
                # Count every occurrence (a record can have multiple files of one type)
                for e in ft:
                    if e in exts:
                        label_occurrences[label] += 1

            for e in ft:
                if e in excluded_track:
                    excluded_imaging_like[e] += 1

            if saw_any_imaging:
                records_with_any_imaging += 1

    print(f"Total EYE_IMAGING records: {total_eye}")
    print(f"Records carrying ≥1 imaging extension (curated set): "
          f"{records_with_any_imaging}")
    print()
    print("Per-label counts (records / occurrences):")
    for label, _ in ALLOW:
        print(f"  {label:40s}  {label_records[label]:4d} / "
              f"{label_occurrences[label]:4d}")
    print()
    print("Deliberately excluded extensions (with counts), for transparency:")
    for ext, n in sorted(excluded_imaging_like.items(), key=lambda x: -x[1]):
        print(f"  {ext:10s}  {n:3d}")

    # ── Pie chart ────────────────────────────────────────────────────
    sizes = [label_records[label] for label, _ in ALLOW]
    labels = [label for label, _ in ALLOW]
    # Drop any zero-count slice (cleaner)
    pairs = [(l, s) for l, s in zip(labels, sizes) if s > 0]
    pairs.sort(key=lambda x: -x[1])
    labels, sizes = zip(*pairs)

    total_slices = sum(sizes)

    # Matplotlib pie. Use a colorblind-friendly qualitative palette
    # (tab10 is fine; we have <=10 slices typically).
    colors = plt.cm.tab10.colors[:len(sizes)]

    fig, ax = plt.subplots(figsize=(11, 7), dpi=160)
    wedges, _ = ax.pie(
        sizes,
        startangle=90,
        counterclock=False,
        colors=colors,
        wedgeprops=dict(edgecolor="white", linewidth=1.2),
    )

    legend_labels = [
        f"{lbl}  ({n}, {n/total_slices*100:.1f}%)"
        for lbl, n in zip(labels, sizes)
    ]
    ax.legend(
        wedges, legend_labels,
        title="File type   (records, share)",
        loc="center left",
        bbox_to_anchor=(1.0, 0.5),
        frameon=False,
        fontsize=11,
        title_fontsize=11,
    )

    ax.set_title(
        f"Imaging-indicative file types in ENVISION EYE_IMAGING records\n"
        f"({records_with_any_imaging:,} of {total_eye:,} records carry ≥1 "
        f"imaging extension; {total_slices:,} record-coverage slices shown)",
        fontsize=12, pad=16,
    )

    excluded_summary = ", ".join(
        f"{ext} ({n})" for ext, n in
        sorted(excluded_imaging_like.items(), key=lambda x: -x[1])[:10]
    ) or "none"
    fig.text(
        0.02, 0.02,
        "Curated for EnvisionPortal / EyeACT clinical-imaging scope.\n"
        f"Excluded (animations / microscopy / promo): {excluded_summary}.\n"
        "Documents, archives, code, and tabular formats excluded by design.",
        fontsize=8.5, color="dimgray", ha="left", va="bottom",
    )

    plt.tight_layout(rect=(0, 0.06, 1, 1))

    out = ROOT / "paper" / "envision_filetype_pie.png"
    out.parent.mkdir(exist_ok=True, parents=True)
    fig.savefig(out, dpi=200, bbox_inches="tight", facecolor="white")
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()
