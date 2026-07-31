#!/usr/bin/env python3
"""Verify the generated QGIS annotation workspace."""

from __future__ import annotations

import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ANNOTATION_GPKG = PROJECT_ROOT / "data/annotations/castros_annotations.gpkg"
QGIS_REVIEW_TASKS = PROJECT_ROOT / "data/qgis-review/qgis_review_tasks.tsv"
NEGATIVE_CANDIDATES = PROJECT_ROOT / "data/processed/castros-trasancos-mvp/hard_negative_candidates.tsv"

EXPECTED_CONTENTS = {
    "labels_reviewed": "features",
    "negative_areas_reviewed": "features",
    "geocoded_sites_reviewed": "features",
    "site_review_decisions": "attributes",
    "negative_review_decisions": "attributes",
}

EXPECTED_GEOMETRIES = {
    "labels_reviewed": "POLYGON",
    "negative_areas_reviewed": "POLYGON",
    "geocoded_sites_reviewed": "POINT",
}


def main() -> None:
    if not ANNOTATION_GPKG.exists():
        raise SystemExit(f"Missing annotation GeoPackage: {ANNOTATION_GPKG}")

    conn = sqlite3.connect(ANNOTATION_GPKG)
    cur = conn.cursor()
    contents = dict(cur.execute("select table_name, data_type from gpkg_contents").fetchall())
    for table_name, data_type in EXPECTED_CONTENTS.items():
        actual = contents.get(table_name)
        if actual != data_type:
            raise SystemExit(f"{table_name}: expected data_type={data_type}, got {actual}")

    geometries = dict(cur.execute("select table_name, geometry_type_name from gpkg_geometry_columns").fetchall())
    for table_name, geometry_type in EXPECTED_GEOMETRIES.items():
        actual = geometries.get(table_name)
        if actual != geometry_type:
            raise SystemExit(f"{table_name}: expected geometry={geometry_type}, got {actual}")

    site_decisions = cur.execute("select count(*) from site_review_decisions").fetchone()[0]
    negative_decisions = cur.execute("select count(*) from negative_review_decisions").fetchone()[0]
    expected_site_decisions = max(sum(1 for _ in QGIS_REVIEW_TASKS.open(encoding="utf-8")) - 1, 0)
    expected_negative_decisions = max(sum(1 for _ in NEGATIVE_CANDIDATES.open(encoding="utf-8")) - 1, 0)
    if site_decisions != expected_site_decisions:
        raise SystemExit(f"Expected {expected_site_decisions} site decisions, got {site_decisions}")
    if negative_decisions != expected_negative_decisions:
        raise SystemExit(f"Expected {expected_negative_decisions} negative decisions, got {negative_decisions}")

    conn.close()
    print("annotation_workspace_ok")
    print(f"site_review_decisions={site_decisions}")
    print(f"negative_review_decisions={negative_decisions}")


if __name__ == "__main__":
    main()
