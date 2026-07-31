#!/usr/bin/env python3
"""Export a training manifest from reviewed annotation layers."""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ANNOTATION_GPKG = PROJECT_ROOT / "data/annotations/castros_annotations.gpkg"
OUT_DIR = PROJECT_ROOT / "data/training"
REPORTS_DIR = PROJECT_ROOT / "reports"

REQUIRED_POSITIVE_FIELDS = [
    "label_id",
    "site_id",
    "primary_name",
    "final_split",
    "label_class",
    "label_geometry",
    "confidence",
    "source_basis",
    "reviewed_by",
    "reviewed_date",
]
REQUIRED_NEGATIVE_FIELDS = [
    "negative_label_id",
    "final_split",
    "negative_type",
    "confidence",
    "source_basis",
    "reviewed_by",
    "reviewed_date",
]
ALLOWED_SPLITS = {"train", "val", "test", "test_o_val"}
ALLOWED_CONFIDENCE = {"high", "medium", "low"}


def write_tsv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, dialect="excel-tab")
        writer.writeheader()
        writer.writerows(rows)


def fetch_rows(cur: sqlite3.Cursor, table: str) -> list[dict[str, str]]:
    cur.execute(f"select * from {table}")
    fields = [item[0] for item in cur.description]
    rows = []
    for raw in cur.fetchall():
        row = {}
        for key, value in zip(fields, raw):
            if key == "geom":
                continue
            row[key] = "" if value is None else str(value)
        rows.append(row)
    return rows


def metadata_errors(rows: list[dict[str, str]], required_fields: list[str], label: str) -> list[str]:
    errors: list[str] = []
    for row in rows:
        row_id = row.get("label_id") or row.get("negative_label_id") or row.get("fid") or "unknown"
        missing = [field for field in required_fields if not row.get(field, "").strip()]
        if missing:
            errors.append(f"{label} {row_id}: missing {', '.join(missing)}")
        final_split = row.get("final_split", "").strip()
        if final_split and final_split not in ALLOWED_SPLITS:
            errors.append(f"{label} {row_id}: invalid final_split={final_split}")
        confidence = row.get("confidence", "").strip()
        if confidence and confidence not in ALLOWED_CONFIDENCE:
            errors.append(f"{label} {row_id}: invalid confidence={confidence}")
    return errors


def main() -> None:
    if not ANNOTATION_GPKG.exists():
        raise SystemExit("Annotation workspace missing; run make annotations first.")

    conn = sqlite3.connect(ANNOTATION_GPKG)
    cur = conn.cursor()
    positive_rows = fetch_rows(cur, "labels_reviewed")
    negative_rows = fetch_rows(cur, "negative_areas_reviewed")
    conn.close()

    accepted_positive = [row for row in positive_rows if row.get("review_status") == "accepted"]
    accepted_negative = [row for row in negative_rows if row.get("review_status") == "accepted"]
    positive_errors = metadata_errors(accepted_positive, REQUIRED_POSITIVE_FIELDS, "positive")
    negative_errors = metadata_errors(accepted_negative, REQUIRED_NEGATIVE_FIELDS, "negative")
    validation_errors = positive_errors + negative_errors

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    write_tsv(
        OUT_DIR / "training_labels_manifest.tsv",
        accepted_positive,
        [
            "fid",
            "label_id",
            "site_id",
            "primary_name",
            "municipality",
            "parish",
            "source_split",
            "final_split",
            "label_class",
            "label_geometry",
            "confidence",
            "review_status",
            "source_basis",
            "reviewed_by",
            "reviewed_date",
            "qgis_task_id",
            "notes",
        ],
    )
    write_tsv(
        OUT_DIR / "training_negatives_manifest.tsv",
        accepted_negative,
        [
            "fid",
            "negative_label_id",
            "source_negative_id",
            "final_split",
            "negative_type",
            "confidence",
            "review_status",
            "source_basis",
            "reviewed_by",
            "reviewed_date",
            "notes",
        ],
    )

    blocked = not accepted_positive or not accepted_negative or bool(validation_errors)
    lines = [
        "# Training readiness",
        "",
        "Generated: 2026-07-31",
        "",
        f"- Accepted positive polygons: {len(accepted_positive)}",
        f"- Accepted negative areas: {len(accepted_negative)}",
        f"- Metadata errors: {len(validation_errors)}",
        f"- Status: {'blocked' if blocked else 'ready_for_tile_export'}",
        "",
    ]
    if blocked:
        lines.extend(
            [
                "## Blocker",
                "",
                "Training export is blocked until QGIS review creates accepted features in both `labels_reviewed` and `negative_areas_reviewed`, with the required metadata filled.",
            ]
        )
        if validation_errors:
            lines.extend(["", "## Metadata errors", ""])
            lines.extend(f"- {error}" for error in validation_errors[:100])
            if len(validation_errors) > 100:
                lines.append(f"- ... {len(validation_errors) - 100} more")
    else:
        lines.extend(
            [
                "## Next",
                "",
                "Generate raster chips and convert reviewed polygons into YOLO/COCO/mask format.",
            ]
        )
    (REPORTS_DIR / "training_readiness.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"accepted_positive_polygons={len(accepted_positive)}")
    print(f"accepted_negative_areas={len(accepted_negative)}")
    print(f"metadata_errors={len(validation_errors)}")
    print(f"training_status={'blocked' if blocked else 'ready_for_tile_export'}")


if __name__ == "__main__":
    main()
