#!/usr/bin/env python3
"""
Create the editable annotation workspace for QGIS.

The review package contains generated layers. This workspace contains the layers
that a human reviewer should edit: final positive polygons, confirmed negative
areas, corrected/geocoded points, and decision tables.
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
import struct
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
QGIS_REVIEW_DIR = PROJECT_ROOT / "data/qgis-review"
OUT_DIR = PROJECT_ROOT / "data/annotations"
OUT_PATH = OUT_DIR / "castros_annotations.gpkg"
SRS_ID = 4326
GENERATED_AT = "2026-07-31T00:00:00Z"


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, dialect="excel-tab"))


def empty_point_blob() -> bytes:
    header = b"GP" + bytes([0, 1]) + struct.pack("<i", SRS_ID)
    return header + struct.pack("<BIdd", 1, 1, 0.0, 0.0)


def create_base_gpkg(cur: sqlite3.Cursor) -> None:
    cur.executescript(
        """
        PRAGMA application_id=1196444487;
        PRAGMA user_version=10400;
        CREATE TABLE gpkg_spatial_ref_sys (
            srs_name TEXT NOT NULL,
            srs_id INTEGER NOT NULL PRIMARY KEY,
            organization TEXT NOT NULL,
            organization_coordsys_id INTEGER NOT NULL,
            definition TEXT NOT NULL,
            description TEXT
        );
        INSERT INTO gpkg_spatial_ref_sys VALUES
            ('Undefined Cartesian SRS', -1, 'NONE', -1, 'undefined', 'undefined Cartesian coordinate reference system'),
            ('Undefined geographic SRS', 0, 'NONE', 0, 'undefined', 'undefined geographic coordinate reference system'),
            ('WGS 84 geodetic', 4326, 'EPSG', 4326,
             'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]]',
             'longitude/latitude coordinates in decimal degrees on the WGS 84 spheroid');
        CREATE TABLE gpkg_contents (
            table_name TEXT NOT NULL PRIMARY KEY,
            data_type TEXT NOT NULL,
            identifier TEXT UNIQUE,
            description TEXT DEFAULT '',
            last_change DATETIME NOT NULL,
            min_x DOUBLE, min_y DOUBLE, max_x DOUBLE, max_y DOUBLE,
            srs_id INTEGER
        );
        CREATE TABLE gpkg_geometry_columns (
            table_name TEXT NOT NULL,
            column_name TEXT NOT NULL,
            geometry_type_name TEXT NOT NULL,
            srs_id INTEGER NOT NULL,
            z TINYINT NOT NULL,
            m TINYINT NOT NULL,
            PRIMARY KEY (table_name, column_name)
        );
        """
    )


def register_feature_layer(cur: sqlite3.Cursor, table_name: str, geom_type: str, description: str) -> None:
    cur.execute(
        """
        INSERT INTO gpkg_contents
        (table_name, data_type, identifier, description, last_change, min_x, min_y, max_x, max_y, srs_id)
        VALUES (?, 'features', ?, ?, ?, NULL, NULL, NULL, NULL, ?)
        """,
        (table_name, table_name, description, GENERATED_AT, SRS_ID),
    )
    cur.execute(
        "INSERT INTO gpkg_geometry_columns VALUES (?, 'geom', ?, ?, 0, 0)",
        (table_name, geom_type, SRS_ID),
    )


def register_attribute_table(cur: sqlite3.Cursor, table_name: str, description: str) -> None:
    cur.execute(
        """
        INSERT INTO gpkg_contents
        (table_name, data_type, identifier, description, last_change, min_x, min_y, max_x, max_y, srs_id)
        VALUES (?, 'attributes', ?, ?, ?, NULL, NULL, NULL, NULL, NULL)
        """,
        (table_name, table_name, description, GENERATED_AT),
    )


def create_annotation_layers(cur: sqlite3.Cursor) -> None:
    register_feature_layer(cur, "labels_reviewed", "POLYGON", "Human-reviewed positive archaeological label polygons")
    cur.execute(
        """
        CREATE TABLE labels_reviewed (
            fid INTEGER PRIMARY KEY AUTOINCREMENT,
            geom BLOB NOT NULL,
            label_id TEXT,
            site_id TEXT,
            primary_name TEXT,
            municipality TEXT,
            parish TEXT,
            source_split TEXT,
            final_split TEXT,
            label_class TEXT,
            label_geometry TEXT,
            confidence TEXT,
            review_status TEXT,
            source_basis TEXT,
            reviewed_by TEXT,
            reviewed_date TEXT,
            qgis_task_id TEXT,
            notes TEXT
        )
        """
    )

    register_feature_layer(cur, "negative_areas_reviewed", "POLYGON", "Human-reviewed negative training areas")
    cur.execute(
        """
        CREATE TABLE negative_areas_reviewed (
            fid INTEGER PRIMARY KEY AUTOINCREMENT,
            geom BLOB NOT NULL,
            negative_label_id TEXT,
            source_negative_id TEXT,
            final_split TEXT,
            negative_type TEXT,
            confidence TEXT,
            review_status TEXT,
            source_basis TEXT,
            reviewed_by TEXT,
            reviewed_date TEXT,
            notes TEXT
        )
        """
    )

    register_feature_layer(cur, "geocoded_sites_reviewed", "POINT", "Corrected/geocoded points created during review")
    cur.execute(
        """
        CREATE TABLE geocoded_sites_reviewed (
            fid INTEGER PRIMARY KEY AUTOINCREMENT,
            geom BLOB NOT NULL,
            site_id TEXT,
            primary_name TEXT,
            municipality TEXT,
            parish TEXT,
            geocode_source TEXT,
            geocode_confidence TEXT,
            reviewed_by TEXT,
            reviewed_date TEXT,
            notes TEXT
        )
        """
    )


def create_decision_tables(cur: sqlite3.Cursor) -> None:
    register_attribute_table(cur, "site_review_decisions", "One row per site review task")
    cur.execute(
        """
        CREATE TABLE site_review_decisions (
            decision_id TEXT PRIMARY KEY,
            task_id TEXT,
            priority TEXT,
            site_id TEXT,
            primary_name TEXT,
            municipality TEXT,
            parish TEXT,
            dataset_use TEXT,
            source_split TEXT,
            has_coordinates TEXT,
            qgis_action TEXT,
            suggested_decision TEXT,
            decision_status TEXT,
            final_decision TEXT,
            final_split TEXT,
            reviewed_by TEXT,
            reviewed_date TEXT,
            notes TEXT
        )
        """
    )

    review_tasks = read_tsv(QGIS_REVIEW_DIR / "qgis_review_tasks.tsv")
    for idx, row in enumerate(review_tasks, start=1):
        cur.execute(
            """
            INSERT INTO site_review_decisions
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', '', '', '', '', ?)
            """,
            (
                f"site-decision-{idx:04d}",
                row["task_id"],
                row["priority"],
                row["site_id"],
                row["primary_name"],
                row["municipality"],
                row["parish"],
                row["dataset_use"],
                row["split"],
                row["has_coordinates"],
                row["qgis_action"],
                row["suggested_decision"],
                row["notes"],
            ),
        )

    register_attribute_table(cur, "negative_review_decisions", "One row per generated hard-negative point")
    cur.execute(
        """
        CREATE TABLE negative_review_decisions (
            decision_id TEXT PRIMARY KEY,
            negative_id TEXT,
            decision_status TEXT,
            final_decision TEXT,
            final_split TEXT,
            reviewed_by TEXT,
            reviewed_date TEXT,
            notes TEXT
        )
        """
    )

    negatives = read_tsv(PROJECT_ROOT / "data/processed/castros-trasancos-mvp/hard_negative_candidates.tsv")
    for idx, row in enumerate(negatives, start=1):
        cur.execute(
            """
            INSERT INTO negative_review_decisions
            VALUES (?, ?, 'pending', '', '', '', '', ?)
            """,
            (f"negative-decision-{idx:04d}", row["negative_id"], row["notes"]),
        )


def write_readme(path: Path) -> None:
    path.write_text(
        """# Annotation workspace

Generated: 2026-07-31

Open `castros_annotations.gpkg` in QGIS together with `../qgis-review/castros_trasancos_qgis_review.gpkg`.

Editable layers:

- `labels_reviewed`: final positive polygons drawn by the human reviewer.
- `negative_areas_reviewed`: final negative polygons accepted by the human reviewer.
- `geocoded_sites_reviewed`: corrected/geocoded points for sites that were missing coordinates.
- `site_review_decisions`: one decision row per source site/task.
- `negative_review_decisions`: one decision row per generated hard-negative point.

Do not edit generated layers in `data/qgis-review`; copy or trace into these annotation layers.
""",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create the editable QGIS annotation workspace.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the existing annotation GeoPackage. Use only before human review or after backing it up.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if OUT_PATH.exists():
        if not args.force:
            print(f"Annotation workspace already exists; keeping {OUT_PATH}")
            print("Use --force only after backing up human QGIS edits.")
            return
        OUT_PATH.unlink()
    conn = sqlite3.connect(OUT_PATH)
    cur = conn.cursor()
    create_base_gpkg(cur)
    create_annotation_layers(cur)
    create_decision_tables(cur)
    conn.commit()
    conn.close()
    write_readme(OUT_DIR / "README_annotations.md")
    print(f"Wrote annotation workspace to {OUT_PATH}")
    print("editable_layers: labels_reviewed, negative_areas_reviewed, geocoded_sites_reviewed")
    print("decision_tables: site_review_decisions, negative_review_decisions")


if __name__ == "__main__":
    main()
