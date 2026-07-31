#!/usr/bin/env python3
"""Build a lightweight manifest of candidate raster windows."""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
QGIS_REVIEW_DIR = PROJECT_ROOT / "data/qgis-review"
OUT_DIR = PROJECT_ROOT / "data/raster-prep"
REPORTS_DIR = PROJECT_ROOT / "reports"


def lonlat_to_utm29(lon: float, lat: float) -> tuple[float, float]:
    a = 6378137.0
    f = 1 / 298.257223563
    k0 = 0.9996
    e = math.sqrt(f * (2 - f))
    e2 = e * e
    ep2 = e2 / (1 - e2)
    lat_rad = math.radians(lat)
    lon_rad = math.radians(lon)
    lon0 = math.radians((29 - 1) * 6 - 180 + 3)
    n = a / math.sqrt(1 - e2 * math.sin(lat_rad) ** 2)
    t = math.tan(lat_rad) ** 2
    c = ep2 * math.cos(lat_rad) ** 2
    aa = math.cos(lat_rad) * (lon_rad - lon0)
    m = a * (
        (1 - e2 / 4 - 3 * e2**2 / 64 - 5 * e2**3 / 256) * lat_rad
        - (3 * e2 / 8 + 3 * e2**2 / 32 + 45 * e2**3 / 1024) * math.sin(2 * lat_rad)
        + (15 * e2**2 / 256 + 45 * e2**3 / 1024) * math.sin(4 * lat_rad)
        - (35 * e2**3 / 3072) * math.sin(6 * lat_rad)
    )
    easting = k0 * n * (
        aa
        + (1 - t + c) * aa**3 / 6
        + (5 - 18 * t + t**2 + 72 * c - 58 * ep2) * aa**5 / 120
    ) + 500000.0
    northing = k0 * (
        m
        + n
        * math.tan(lat_rad)
        * (aa**2 / 2 + (5 - t + 9 * c + 4 * c**2) * aa**4 / 24 + (61 - 58 * t + t**2 + 600 * c - 330 * ep2) * aa**6 / 720)
    )
    return easting, northing


def bbox(coords: list[list[float]]) -> tuple[float, float, float, float]:
    xs = [coord[0] for coord in coords]
    ys = [coord[1] for coord in coords]
    return min(xs), min(ys), max(xs), max(ys)


def write_tsv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, dialect="excel-tab")
        writer.writeheader()
        writer.writerows(rows)


def build_manifest() -> list[dict[str, str]]:
    payload = json.loads((QGIS_REVIEW_DIR / "tile_windows_512m.geojson").read_text(encoding="utf-8"))
    rows = []
    for idx, feature in enumerate(payload["features"], start=1):
        props = feature["properties"]
        min_lon, min_lat, max_lon, max_lat = bbox(feature["geometry"]["coordinates"][0])
        center_lon = (min_lon + max_lon) / 2
        center_lat = (min_lat + max_lat) / 2
        center_e, center_n = lonlat_to_utm29(center_lon, center_lat)
        rows.append(
            {
                "tile_id": f"tile-tra-{idx:04d}",
                "site_id": props["site_id"],
                "primary_name": props["primary_name"],
                "municipality": props["municipality"],
                "split": props["split"],
                "dataset_use": props["dataset_use"],
                "center_lon_wgs84": f"{center_lon:.8f}",
                "center_lat_wgs84": f"{center_lat:.8f}",
                "center_easting_utm29": f"{center_e:.2f}",
                "center_northing_utm29": f"{center_n:.2f}",
                "bbox_wgs84": f"{min_lon:.8f},{min_lat:.8f},{max_lon:.8f},{max_lat:.8f}",
                "tile_side_m": "512",
                "required_sources": "pnoa_rgb; lidar_dem; hillshade; slope; lrm_msrm",
                "download_status": "pending_qgis_review",
            }
        )
    return rows


def write_report(rows: list[dict[str, str]]) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    by_split: dict[str, int] = {}
    by_municipality: dict[str, int] = {}
    for row in rows:
        by_split[row["split"]] = by_split.get(row["split"], 0) + 1
        by_municipality[row["municipality"]] = by_municipality.get(row["municipality"], 0) + 1
    lines = [
        "# Raster tile preparation plan",
        "",
        "Generated: 2026-07-31",
        "",
        f"- Candidate windows: {len(rows)}",
        "- Window side: 512 m",
        "- CRS for raster processing: EPSG:25829/UTM 29N",
        "- Download status: pending QGIS review",
        "",
        "## By split",
        "",
    ]
    for split, count in sorted(by_split.items()):
        lines.append(f"- {split}: {count}")
    lines.extend(["", "## By municipality", ""])
    for municipality, count in sorted(by_municipality.items()):
        lines.append(f"- {municipality}: {count}")
    lines.extend(
        [
            "",
            "## Rule",
            "",
            "Do not download/process rasters for a window until its source site has an accepted or follow-up decision in the annotation workspace.",
        ]
    )
    (REPORTS_DIR / "raster_tile_plan.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    rows = build_manifest()
    fields = [
        "tile_id",
        "site_id",
        "primary_name",
        "municipality",
        "split",
        "dataset_use",
        "center_lon_wgs84",
        "center_lat_wgs84",
        "center_easting_utm29",
        "center_northing_utm29",
        "bbox_wgs84",
        "tile_side_m",
        "required_sources",
        "download_status",
    ]
    write_tsv(OUT_DIR / "candidate_raster_tiles.tsv", rows, fields)
    write_report(rows)
    print(f"candidate_raster_tiles={len(rows)}")


if __name__ == "__main__":
    main()
