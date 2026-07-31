#!/usr/bin/env python3
"""
Build the QGIS review package for the Castros IA Galicia MVP.

This does not create final archaeological labels. It creates provisional review
layers: points, seed buffers, raster crop windows, hard-negative candidates, and
task tables. Human/QGIS review is still required before training.
"""

from __future__ import annotations

import csv
import json
import math
import sqlite3
import struct
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MVP_DIR = PROJECT_ROOT / "data/processed/castros-trasancos-mvp"
OUT_DIR = PROJECT_ROOT / "data/qgis-review"

SRS_ID = 4326
POSITIVE_SPLITS = {"train", "val", "test", "test_o_val"}
TRASANCOS_BBOX = [-8.36, 43.40, -7.94, 43.68]
GENERATED_AT = "2026-07-31T00:00:00Z"


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, dialect="excel-tab"))


def write_tsv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, dialect="excel-tab")
        writer.writeheader()
        writer.writerows(rows)


def write_geojson(path: Path, name: str, features: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "type": "FeatureCollection",
        "name": name,
        "crs": {"type": "name", "properties": {"name": f"EPSG:{SRS_ID}"}},
        "features": features,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def as_float(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def review_priority(row: dict[str, str]) -> tuple[str, str, str]:
    dataset_use = row["dataset_use"]
    split = row["split"]
    record_type = row["record_type"]

    if dataset_use == "needs_geocoding":
        return (
            "P0",
            "Buscar coordenadas en PXOM/Xunta/PNOA antes de usar.",
            "geocode_then_reclassify",
        )
    if record_type == "conflict_neolithic_or_castro":
        return (
            "P0",
            "Resolver tipología castro/cercado neolítico; no usar como positivo.",
            "resolve_typology",
        )
    if dataset_use == "positive_o_val_holdout":
        return (
            "P0",
            "Verificar coordenada y dibujar polígono/buffer; mantener fuera de entrenamiento.",
            "verify_holdout_polygon",
        )
    if dataset_use == "positive_damaged_review":
        return (
            "P1",
            "Comprobar visibilidad/conservación; usar solo como caso de error o revisión.",
            "inspect_damaged_site",
        )
    if split in POSITIVE_SPLITS:
        return (
            "P1",
            "Verificar coordenada y dibujar polígono/buffer entrenable.",
            "draw_training_polygon",
        )
    if dataset_use == "review_only":
        return (
            "P2",
            "Reconciliar con fuente oficial o descartar.",
            "reconcile_or_discard",
        )
    return ("P3", "Revisar manualmente si entra en el MVP.", "manual_review")


def site_props(row: dict[str, str]) -> dict[str, str]:
    priority, action, decision = review_priority(row)
    return {
        "site_id": row["site_id"],
        "primary_name": row["primary_name"],
        "municipality": row["municipality"],
        "parish": row["parish"],
        "place": row["place"],
        "ga_code": row["ga_code"],
        "record_type": row["record_type"],
        "confidence": row["confidence"],
        "dataset_use": row["dataset_use"],
        "split": row["split"],
        "coord_source": row["coord_source"],
        "review_priority": priority,
        "qgis_action": action,
        "suggested_decision": decision,
        "notes": row["notes"],
    }


def point_feature(lon: float, lat: float, props: dict[str, str]) -> dict[str, Any]:
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": props,
    }


def buffer_polygon(lon: float, lat: float, radius_m: float, segments: int = 72) -> list[list[float]]:
    radius_earth = 6378137.0
    lat1 = math.radians(lat)
    lon1 = math.radians(lon)
    angular = radius_m / radius_earth
    ring = []
    for idx in range(segments):
        bearing = 2 * math.pi * idx / segments
        lat2 = math.asin(
            math.sin(lat1) * math.cos(angular)
            + math.cos(lat1) * math.sin(angular) * math.cos(bearing)
        )
        lon2 = lon1 + math.atan2(
            math.sin(bearing) * math.sin(angular) * math.cos(lat1),
            math.cos(angular) - math.sin(lat1) * math.sin(lat2),
        )
        ring.append([math.degrees(lon2), math.degrees(lat2)])
    ring.append(ring[0])
    return ring


def square_window(lon: float, lat: float, side_m: float = 512.0) -> list[list[float]]:
    half = side_m / 2
    meters_per_degree_lat = 111_320.0
    meters_per_degree_lon = meters_per_degree_lat * max(math.cos(math.radians(lat)), 0.1)
    dlat = half / meters_per_degree_lat
    dlon = half / meters_per_degree_lon
    return [
        [lon - dlon, lat - dlat],
        [lon + dlon, lat - dlat],
        [lon + dlon, lat + dlat],
        [lon - dlon, lat + dlat],
        [lon - dlon, lat - dlat],
    ]


def polygon_feature(ring: list[list[float]], props: dict[str, str]) -> dict[str, Any]:
    return {
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [ring]},
        "properties": props,
    }


def build_review_layers(
    sites: list[dict[str, str]],
    negatives: list[dict[str, str]],
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, str]], list[dict[str, str]]]:
    review_points: list[dict[str, Any]] = []
    positive_buffers: list[dict[str, Any]] = []
    tile_windows: list[dict[str, Any]] = []
    negative_points: list[dict[str, Any]] = []
    geocoding_tasks: list[dict[str, str]] = []
    review_tasks: list[dict[str, str]] = []

    for row in sites:
        lat = as_float(row["lat_wgs84"])
        lon = as_float(row["lon_wgs84"])
        priority, action, decision = review_priority(row)
        review_tasks.append(
            {
                "task_id": f"task-{len(review_tasks) + 1:04d}",
                "priority": priority,
                "site_id": row["site_id"],
                "primary_name": row["primary_name"],
                "municipality": row["municipality"],
                "parish": row["parish"],
                "dataset_use": row["dataset_use"],
                "split": row["split"],
                "has_coordinates": "yes" if lat is not None and lon is not None else "no",
                "qgis_action": action,
                "suggested_decision": decision,
                "notes": row["notes"],
            }
        )
        if lat is None or lon is None:
            geocoding_tasks.append(
                {
                    "site_id": row["site_id"],
                    "primary_name": row["primary_name"],
                    "municipality": row["municipality"],
                    "parish": row["parish"],
                    "ga_code": row["ga_code"],
                    "record_type": row["record_type"],
                    "dataset_use": row["dataset_use"],
                    "sources": row["sources"],
                    "urls": row["urls"],
                    "action": "Buscar coordenada oficial o descartar del MVP geoespacial.",
                }
            )
            continue

        props = site_props(row)
        review_points.append(point_feature(lon, lat, props))

        if row["split"] in POSITIVE_SPLITS:
            buffer_props = {
                **props,
                "buffer_radius_m": "120",
                "label_status": "seed_buffer_requires_visual_adjustment",
            }
            positive_buffers.append(polygon_feature(buffer_polygon(lon, lat, 120), buffer_props))

            tile_props = {
                **props,
                "tile_side_m": "512",
                "tile_status": "candidate_crop_window",
            }
            tile_windows.append(polygon_feature(square_window(lon, lat, 512), tile_props))

    for row in negatives:
        lat = as_float(row["lat_wgs84"])
        lon = as_float(row["lon_wgs84"])
        if lat is None or lon is None:
            continue
        props = {
            "negative_id": row["negative_id"],
            "status": row["status"],
            "use": row["use"],
            "review_priority": "P2",
            "qgis_action": "Comprobar en PNOA/LiDAR; aceptar solo si no parece arqueológico ni ambiguo.",
            "notes": row["notes"],
        }
        negative_points.append(point_feature(lon, lat, props))

    min_lon, min_lat, max_lon, max_lat = TRASANCOS_BBOX
    aoi = [
        polygon_feature(
            [
                [min_lon, min_lat],
                [max_lon, min_lat],
                [max_lon, max_lat],
                [min_lon, max_lat],
                [min_lon, min_lat],
            ],
            {
                "aoi_id": "trasancos_bbox",
                "name": "Trasancos MVP search area",
                "status": "review_area",
                "bbox_wgs84": ",".join(map(str, TRASANCOS_BBOX)),
            },
        )
    ]

    layers = {
        "review_points": review_points,
        "positive_seed_buffers_120m": positive_buffers,
        "tile_windows_512m": tile_windows,
        "hard_negative_candidates": negative_points,
        "trasancos_aoi": aoi,
    }
    return layers, review_tasks, geocoding_tasks


def geom_bbox(geometry: dict[str, Any]) -> tuple[float, float, float, float]:
    coords = geometry["coordinates"]
    if geometry["type"] == "Point":
        lon, lat = coords
        return lon, lat, lon, lat
    flat = coords[0]
    xs = [p[0] for p in flat]
    ys = [p[1] for p in flat]
    return min(xs), min(ys), max(xs), max(ys)


def layer_bbox(features: list[dict[str, Any]]) -> tuple[float | None, float | None, float | None, float | None]:
    if not features:
        return None, None, None, None
    boxes = [geom_bbox(feature["geometry"]) for feature in features]
    return (
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    )


def gpkg_blob(geometry: dict[str, Any]) -> bytes:
    header = b"GP" + bytes([0, 1]) + struct.pack("<i", SRS_ID)
    if geometry["type"] == "Point":
        lon, lat = geometry["coordinates"]
        wkb = struct.pack("<BIdd", 1, 1, lon, lat)
        return header + wkb
    if geometry["type"] == "Polygon":
        rings = geometry["coordinates"]
        payload = [struct.pack("<BII", 1, 3, len(rings))]
        for ring in rings:
            payload.append(struct.pack("<I", len(ring)))
            for lon, lat in ring:
                payload.append(struct.pack("<dd", lon, lat))
        return header + b"".join(payload)
    raise ValueError(f"Unsupported geometry type: {geometry['type']}")


def create_gpkg(path: Path, layers: dict[str, list[dict[str, Any]]]) -> None:
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    cur = conn.cursor()
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
            last_change DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
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

    for table_name, features in layers.items():
        geom_type = "POINT" if table_name in {"review_points", "hard_negative_candidates"} else "POLYGON"
        property_names = sorted({key for feature in features for key in feature["properties"].keys()})
        columns_sql = ", ".join(f'"{name}" TEXT' for name in property_names)
        cur.execute(
            f'CREATE TABLE "{table_name}" (fid INTEGER PRIMARY KEY AUTOINCREMENT, geom BLOB NOT NULL'
            + (f", {columns_sql}" if columns_sql else "")
            + ")"
        )
        min_x, min_y, max_x, max_y = layer_bbox(features)
        cur.execute(
            """
            INSERT INTO gpkg_contents
            (table_name, data_type, identifier, description, last_change, min_x, min_y, max_x, max_y, srs_id)
            VALUES (?, 'features', ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                table_name,
                table_name,
                "Castros IA Galicia QGIS review layer",
                GENERATED_AT,
                min_x,
                min_y,
                max_x,
                max_y,
                SRS_ID,
            ),
        )
        cur.execute(
            "INSERT INTO gpkg_geometry_columns VALUES (?, 'geom', ?, ?, 0, 0)",
            (table_name, geom_type, SRS_ID),
        )
        if not features:
            continue
        field_list = ["geom", *property_names]
        placeholders = ", ".join("?" for _ in field_list)
        columns = ", ".join(f'"{field}"' for field in field_list)
        sql = f'INSERT INTO "{table_name}" ({columns}) VALUES ({placeholders})'
        for feature in features:
            values = [gpkg_blob(feature["geometry"])]
            for name in property_names:
                values.append(str(feature["properties"].get(name, ""))[:3000])
            cur.execute(sql, values)
    conn.commit()
    conn.close()


def write_readme(path: Path, layers: dict[str, list[dict[str, Any]]], review_tasks: list[dict[str, str]], geocoding_tasks: list[dict[str, str]]) -> None:
    lines = [
        "# Paquete QGIS de revisión - Castros IA Galicia",
        "",
        "Generado: 2026-07-31",
        "",
        "## Qué es",
        "",
        "Paquete ligero para abrir en QGIS y pasar del inventario de puntos a etiquetas revisables. No contiene rasters PNOA/LiDAR ni etiquetas arqueológicas finales.",
        "",
        "## Archivos principales",
        "",
        "- `castros_trasancos_qgis_review.gpkg`: GeoPackage con todas las capas de revisión.",
        f"- `review_points.geojson`: {len(layers['review_points'])} puntos con coordenadas.",
        f"- `positive_seed_buffers_120m.geojson`: {len(layers['positive_seed_buffers_120m'])} buffers provisionales de positivos train/val/test/test_o_val.",
        f"- `tile_windows_512m.geojson`: {len(layers['tile_windows_512m'])} ventanas candidatas para futuros recortes raster.",
        f"- `hard_negative_candidates.geojson`: {len(layers['hard_negative_candidates'])} negativos difíciles generados para revisión.",
        "- `trasancos_aoi.geojson`: caja de trabajo del MVP.",
        "- `qgis_review_tasks.tsv`: cola completa de revisión.",
        "- `geocoding_tasks.tsv`: filas sin coordenadas que hay que resolver antes de usarlas.",
        "",
        "## Conteos",
        "",
    ]
    for name, features in layers.items():
        lines.append(f"- {name}: {len(features)}")
    lines.extend(
        [
            f"- qgis_review_tasks: {len(review_tasks)}",
            f"- geocoding_tasks: {len(geocoding_tasks)}",
            "",
            "## Orden de revisión",
            "",
            "1. Abrir `castros_trasancos_qgis_review.gpkg` en QGIS.",
            "2. Cargar PNOA/IGN como mapa base y, cuando estén descargados, hillshade/MSRM LiDAR.",
            "3. Resolver primero `P0`: O Val, conflictos tipológicos y filas sin coordenadas.",
            "4. Revisar `positive_seed_buffers_120m`: ajustar a croa/muralla o descartar si el punto cae mal.",
            "5. Revisar `hard_negative_candidates`: aceptar solo negativos visualmente claros.",
            "6. Guardar las decisiones en una capa nueva, no sobrescribir las capas generadas.",
            "",
            "## Regla de seguridad",
            "",
            "Los buffers de 120 m son semillas geométricas, no perímetros arqueológicos. Sirven para localizar y recortar; la etiqueta final debe salir de revisión visual y fuente contrastada.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sites = read_tsv(MVP_DIR / "castros_trasancos_master.tsv")
    negatives = read_tsv(MVP_DIR / "hard_negative_candidates.tsv")
    layers, review_tasks, geocoding_tasks = build_review_layers(sites, negatives)

    for name, features in layers.items():
        write_geojson(OUT_DIR / f"{name}.geojson", name, features)
    create_gpkg(OUT_DIR / "castros_trasancos_qgis_review.gpkg", layers)
    write_tsv(
        OUT_DIR / "qgis_review_tasks.tsv",
        review_tasks,
        [
            "task_id",
            "priority",
            "site_id",
            "primary_name",
            "municipality",
            "parish",
            "dataset_use",
            "split",
            "has_coordinates",
            "qgis_action",
            "suggested_decision",
            "notes",
        ],
    )
    write_tsv(
        OUT_DIR / "geocoding_tasks.tsv",
        geocoding_tasks,
        ["site_id", "primary_name", "municipality", "parish", "ga_code", "record_type", "dataset_use", "sources", "urls", "action"],
    )
    write_readme(OUT_DIR / "README_qgis_review.md", layers, review_tasks, geocoding_tasks)
    print(f"Wrote QGIS review package to {OUT_DIR}")
    for name, features in layers.items():
        print(f"{name}: {len(features)}")
    print(f"qgis_review_tasks: {len(review_tasks)}")
    print(f"geocoding_tasks: {len(geocoding_tasks)}")


if __name__ == "__main__":
    main()
