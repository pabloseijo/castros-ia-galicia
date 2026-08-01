#!/usr/bin/env python3
"""Build an autonomous first-pass morphology review package.

This is not a replacement for archaeological interpretation. It converts the P0
review queue into reproducible provisional geometries and a balanced v1 control
set with official orthophoto thumbnails, so the next modelling steps can start
without waiting on a hand-built QGIS session.
"""

from __future__ import annotations

import csv
import json
import math
import sqlite3
import struct
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_SEED = PROJECT_ROOT / "data/morphology-bank/morphology_control_review_seed.tsv"
OUT_DIR = PROJECT_ROOT / "data/morphology-autoreview-v1"
REPORTS_DIR = PROJECT_ROOT / "reports"

GENERATED_AT = "2026-08-01T00:00:00Z"
SRS_ID = 4326
USER_AGENT = "Mozilla/5.0 castros-ia-galicia/1.0 morphology-autoreview"

ES_WMS_BASE = "https://www.ign.es/wms-inspire/pnoa-ma"
ES_WMS_LAYER = "OI.OrthoimageCoverage"
PT_WMS_BASE = "https://cartografia.dgterritorio.gov.pt/wms/ortos2021"
PT_WMS_LAYER = "Ortos2021-RGB"

POSITIVE_PROXY_TARGETS = {
    "large_castrexo_civitas_hint": 24,
    "coastal_promontory_hint": 38,
    "earthwork_or_wall_hint": 38,
}

NEGATIVE_TYPE_TARGETS = {
    "megalithic_mound": 50,
    "historic_fortification": 30,
    "megalithic_mound;rock_art_surface": 8,
    "roman_built_context": 6,
    "rock_art_surface": 4,
    "historic_fortification;roman_built_context": 2,
    "mining_or_quarry": 1,
}

POINT_LAYER_NAMES = {"p0_points", "control_set_v1_points"}


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, dialect="excel-tab"))


def write_tsv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, dialect="excel-tab", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_geojson(path: Path, name: str, features: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "type": "FeatureCollection",
        "name": name,
        "crs": {"type": "name", "properties": {"name": f"EPSG:{SRS_ID}"}},
        "features": features,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_float(value: str) -> float | None:
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def p0_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in rows if row.get("review_priority") == "P0"]


def stratified_take(rows: list[dict[str, str]], target: int, group_fields: list[str]) -> list[dict[str, str]]:
    groups: dict[tuple[str, ...], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        key = tuple(row.get(field, "") for field in group_fields)
        groups[key].append(row)
    for group_rows in groups.values():
        group_rows.sort(key=lambda row: (row.get("country", ""), row.get("province_or_district", ""), row.get("municipality", ""), row.get("name", "")))
    selected: list[dict[str, str]] = []
    keys = sorted(groups)
    while keys and len(selected) < target:
        next_keys: list[tuple[str, ...]] = []
        for key in keys:
            group_rows = groups[key]
            if group_rows and len(selected) < target:
                selected.append(group_rows.pop(0))
            if group_rows:
                next_keys.append(key)
        keys = next_keys
    return selected


def build_control_set(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    positives = [row for row in rows if row["review_role"] == "positive"]
    negatives = [row for row in rows if row["review_role"] == "negative"]
    selected: list[dict[str, str]] = []

    for proxy, target in POSITIVE_PROXY_TARGETS.items():
        bucket = [row for row in positives if row.get("morphology_proxy") == proxy]
        selected.extend(stratified_take(bucket, target, ["country", "province_or_district", "municipality"]))

    for negative_type, target in NEGATIVE_TYPE_TARGETS.items():
        bucket = [row for row in negatives if row.get("negative_type") == negative_type]
        selected.extend(stratified_take(bucket, target, ["country", "province_or_district", "municipality"]))

    seen: set[str] = set()
    unique: list[dict[str, str]] = []
    for row in selected:
        if row["bank_id"] in seen:
            continue
        seen.add(row["bank_id"])
        copied = dict(row)
        copied["control_set_id"] = f"control-v1-{len(unique) + 1:04d}"
        unique.append(copied)
    return unique


def positive_radius_m(row: dict[str, str]) -> float:
    proxy = row.get("morphology_proxy", "")
    if proxy == "large_castrexo_civitas_hint":
        return 180.0
    if proxy == "coastal_promontory_hint":
        return 150.0
    if proxy == "earthwork_or_wall_hint":
        return 130.0
    if proxy == "croa_top_ring_hint":
        return 110.0
    if proxy == "castrel_toponym_hint":
        return 100.0
    return 120.0


def negative_radius_m(row: dict[str, str]) -> float:
    negative_type = row.get("negative_type", "")
    if "megalithic_mound" in negative_type:
        return 45.0
    if "historic_fortification" in negative_type:
        return 100.0
    if "rock_art_surface" in negative_type:
        return 35.0
    if "roman_built_context" in negative_type:
        return 80.0
    if "mining_or_quarry" in negative_type:
        return 120.0
    if "necropolis_or_burial" in negative_type:
        return 50.0
    return 60.0


def radius_m(row: dict[str, str]) -> float:
    if row["review_role"] == "positive":
        return positive_radius_m(row)
    return negative_radius_m(row)


def buffer_polygon(lon: float, lat: float, radius_m_value: float, segments: int = 96) -> list[list[float]]:
    radius_earth = 6378137.0
    lat1 = math.radians(lat)
    lon1 = math.radians(lon)
    angular = radius_m_value / radius_earth
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


def point_feature(lon: float, lat: float, props: dict[str, str]) -> dict:
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": props,
    }


def polygon_feature(ring: list[list[float]], props: dict[str, str]) -> dict:
    return {
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [ring]},
        "properties": props,
    }


def base_props(row: dict[str, str]) -> dict[str, str]:
    return {
        "bank_id": row.get("bank_id", ""),
        "review_seed_id": row.get("review_seed_id", ""),
        "control_set_id": row.get("control_set_id", ""),
        "review_role": row.get("review_role", ""),
        "class_hint": row.get("class_hint", ""),
        "country": row.get("country", ""),
        "region": row.get("region", ""),
        "province_or_district": row.get("province_or_district", ""),
        "municipality": row.get("municipality", ""),
        "parish": row.get("parish", ""),
        "place": row.get("place", ""),
        "name": row.get("name", ""),
        "source": row.get("source", ""),
        "source_quality": row.get("source_quality", ""),
        "source_record_id": row.get("source_record_id", ""),
        "source_code": row.get("source_code", ""),
        "typology": row.get("typology", ""),
        "generic_type": row.get("generic_type", ""),
        "periods": row.get("periods", ""),
        "positive_confidence": row.get("positive_confidence", ""),
        "morphology_proxy": row.get("morphology_proxy", ""),
        "negative_type": row.get("negative_type", ""),
        "review_priority": row.get("review_priority", ""),
        "original_training_use": row.get("training_use", ""),
        "auto_review_status": "auto_seeded_requires_visual_verification",
        "auto_decision": "provisional_geometry_created",
        "training_use": "exclude_until_visual_raster_verification",
        "generated_at": GENERATED_AT,
    }


def build_layers(rows: list[dict[str, str]], control_rows: list[dict[str, str]]) -> dict[str, list[dict]]:
    layers: dict[str, list[dict]] = {
        "p0_points": [],
        "p0_positive_proposed_polygons": [],
        "p0_negative_proposed_polygons": [],
        "control_set_v1_points": [],
        "control_set_v1_positive_polygons": [],
        "control_set_v1_negative_polygons": [],
        "control_set_v1_tile_windows_512m": [],
    }
    control_ids = {row["bank_id"] for row in control_rows}
    for row in rows:
        lon = parse_float(row.get("longitude", ""))
        lat = parse_float(row.get("latitude", ""))
        if lon is None or lat is None:
            continue
        props = base_props(row)
        props["proposed_radius_m"] = f"{radius_m(row):.1f}"
        layers["p0_points"].append(point_feature(lon, lat, props))
        polygon = polygon_feature(buffer_polygon(lon, lat, radius_m(row)), props)
        if row["review_role"] == "positive":
            layers["p0_positive_proposed_polygons"].append(polygon)
        else:
            layers["p0_negative_proposed_polygons"].append(polygon)

        if row["bank_id"] in control_ids:
            control_row = next(item for item in control_rows if item["bank_id"] == row["bank_id"])
            control_props = base_props(control_row)
            control_props["proposed_radius_m"] = f"{radius_m(control_row):.1f}"
            control_props["auto_decision"] = "selected_for_control_set_v1"
            layers["control_set_v1_points"].append(point_feature(lon, lat, control_props))
            control_polygon = polygon_feature(buffer_polygon(lon, lat, radius_m(control_row)), control_props)
            if row["review_role"] == "positive":
                layers["control_set_v1_positive_polygons"].append(control_polygon)
            else:
                layers["control_set_v1_negative_polygons"].append(control_polygon)
            window_props = dict(control_props)
            window_props["tile_side_m"] = "512"
            window_props["tile_status"] = "orthophoto_thumbnail_window"
            layers["control_set_v1_tile_windows_512m"].append(polygon_feature(square_window(lon, lat, 512.0), window_props))
    return layers


def geom_bbox(geometry: dict) -> tuple[float, float, float, float]:
    coords = geometry["coordinates"]
    if geometry["type"] == "Point":
        lon, lat = coords
        return lon, lat, lon, lat
    ring = coords[0]
    xs = [point[0] for point in ring]
    ys = [point[1] for point in ring]
    return min(xs), min(ys), max(xs), max(ys)


def layer_bbox(features: list[dict]) -> tuple[float | None, float | None, float | None, float | None]:
    if not features:
        return None, None, None, None
    boxes = [geom_bbox(feature["geometry"]) for feature in features]
    return min(box[0] for box in boxes), min(box[1] for box in boxes), max(box[2] for box in boxes), max(box[3] for box in boxes)


def gpkg_blob(geometry: dict) -> bytes:
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


def create_gpkg(path: Path, layers: dict[str, list[dict]]) -> None:
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
        geom_type = "POINT" if table_name in POINT_LAYER_NAMES else "POLYGON"
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
                "Castros IA autonomous morphology review layer",
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


def wms_config(country: str) -> tuple[str, str, str]:
    if country == "PT":
        return PT_WMS_BASE, PT_WMS_LAYER, "dgt_ortos2021_rgb"
    return ES_WMS_BASE, ES_WMS_LAYER, "ign_pnoa_rgb"


def wms_bbox_4326(lon: float, lat: float, side_m: float) -> tuple[float, float, float, float]:
    half = side_m / 2
    meters_per_degree_lat = 111_320.0
    meters_per_degree_lon = meters_per_degree_lat * max(math.cos(math.radians(lat)), 0.1)
    dlat = half / meters_per_degree_lat
    dlon = half / meters_per_degree_lon
    return lon - dlon, lat - dlat, lon + dlon, lat + dlat


def build_wms_url(base: str, layer: str, bbox: tuple[float, float, float, float], width: int, height: int) -> str:
    params = {
        "SERVICE": "WMS",
        "VERSION": "1.1.1",
        "REQUEST": "GetMap",
        "LAYERS": layer,
        "STYLES": "",
        "SRS": "EPSG:4326",
        "BBOX": ",".join(f"{value:.8f}" for value in bbox),
        "WIDTH": str(width),
        "HEIGHT": str(height),
        "FORMAT": "image/png",
        "TRANSPARENT": "false",
    }
    return f"{base}?{urlencode(params)}"


def fetch_thumbnail(url: str, path: Path) -> tuple[str, str, int]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        payload = path.read_bytes()
        if payload.startswith(b"\x89PNG"):
            return "exists", "", len(payload)
    for attempt in range(1, 4):
        try:
            req = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(req, timeout=20) as response:
                payload = response.read()
                content_type = response.headers.get("content-type", "")
                if response.status == 200 and payload.startswith(b"\x89PNG"):
                    path.write_bytes(payload)
                    return "exported", "", len(payload)
                return "failed", f"unexpected WMS response status={response.status} content_type={content_type}", len(payload)
        except Exception as exc:
            if attempt == 3:
                return "failed", str(exc), 0
            time.sleep(0.5 * attempt)
    return "failed", "unknown fetch failure", 0


def thumbnail_row(index: int, row: dict[str, str], *, width: int, height: int, semaphores: dict[str, threading.Semaphore]) -> dict[str, str]:
    lon = parse_float(row.get("longitude", ""))
    lat = parse_float(row.get("latitude", ""))
    base, layer, source_name = wms_config(row.get("country", ""))
    thumb_rel = Path("data/morphology-autoreview-v1/thumbnails") / row["review_role"] / f"{row['control_set_id']}-{row['bank_id']}.png"
    thumb_path = PROJECT_ROOT / thumb_rel
    status = "failed"
    error = "missing coordinates"
    size = 0
    bbox = ""
    if lon is not None and lat is not None:
        bbox_values = wms_bbox_4326(lon, lat, 512.0)
        bbox = ",".join(f"{value:.8f}" for value in bbox_values)
        url = build_wms_url(base, layer, bbox_values, width, height)
        semaphore = semaphores[source_name]
        with semaphore:
            status, error, size = fetch_thumbnail(url, thumb_path)
    return {
        "thumbnail_id": f"thumb-v1-{index:04d}",
        "control_set_id": row.get("control_set_id", ""),
        "bank_id": row.get("bank_id", ""),
        "review_role": row.get("review_role", ""),
        "country": row.get("country", ""),
        "name": row.get("name", ""),
        "wms_source": source_name,
        "wms_base": base,
        "wms_layer": layer,
        "bbox_epsg4326": bbox,
        "width_px": str(width),
        "height_px": str(height),
        "thumbnail_path": str(thumb_rel),
        "status": status,
        "bytes": str(size),
        "error": error,
    }


def export_thumbnails(control_rows: list[dict[str, str]], *, width: int = 384, height: int = 384) -> list[dict[str, str]]:
    semaphores = {
        "ign_pnoa_rgb": threading.Semaphore(4),
        "dgt_ortos2021_rgb": threading.Semaphore(2),
    }
    rows: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(thumbnail_row, index, row, width=width, height=height, semaphores=semaphores): index
            for index, row in enumerate(control_rows, start=1)
        }
        for future in as_completed(futures):
            rows.append(future.result())
    return sorted(rows, key=lambda row: row["thumbnail_id"])


def summary_rows(p0: list[dict[str, str]], control_rows: list[dict[str, str]], thumbnails: list[dict[str, str]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for dataset_name, rows in [("p0_all", p0), ("control_set_v1", control_rows)]:
        for field in ["review_role", "country", "province_or_district", "morphology_proxy", "negative_type"]:
            counts = Counter(row.get(field, "") or "(blank)" for row in rows)
            for value, count in sorted(counts.items()):
                if value != "(blank)":
                    out.append({"dataset": dataset_name, "field": field, "value": value, "count": str(count)})
    counts = Counter(row["status"] for row in thumbnails)
    for value, count in sorted(counts.items()):
        out.append({"dataset": "thumbnails", "field": "status", "value": value, "count": str(count)})
    return out


def write_report(p0: list[dict[str, str]], control_rows: list[dict[str, str]], layers: dict[str, list[dict]], thumbnails: list[dict[str, str]]) -> None:
    p0_counts = Counter((row["review_role"], row.get("country", "")) for row in p0)
    control_counts = Counter((row["review_role"], row.get("country", "")) for row in control_rows)
    control_positive_proxy = Counter(row.get("morphology_proxy", "") for row in control_rows if row["review_role"] == "positive")
    control_negative_type = Counter(row.get("negative_type", "") for row in control_rows if row["review_role"] == "negative")
    thumbnail_counts = Counter(row["status"] for row in thumbnails)
    lines = [
        "# Morphology Autoreview v1",
        "",
        f"Generated: {GENERATED_AT}",
        "",
        "## What This Is",
        "",
        "Autonomous first-pass package over the P0 morphology queue. It creates provisional point, polygon and tile-window layers, plus official orthophoto thumbnails for a balanced control set v1.",
        "",
        "This is still not a final archaeological label set. Every generated polygon is an auto-radius proxy around an official catalogue point. The field `training_use` is deliberately set to `exclude_until_visual_raster_verification`.",
        "",
        "## Counts",
        "",
        f"- P0 rows processed: {len(p0)}",
        f"- Control set v1 rows: {len(control_rows)}",
        f"- Orthophoto thumbnails: {len(thumbnails)}",
        f"- Thumbnail status: {dict(thumbnail_counts)}",
        "",
        "### P0 by Role/Country",
        "",
        *[f"- {role}/{country}: {count}" for (role, country), count in sorted(p0_counts.items())],
        "",
        "### Control Set by Role/Country",
        "",
        *[f"- {role}/{country}: {count}" for (role, country), count in sorted(control_counts.items())],
        "",
        "### Control Positive Morphology",
        "",
        *[f"- {key}: {count}" for key, count in control_positive_proxy.most_common()],
        "",
        "### Control Negative Types",
        "",
        *[f"- {key}: {count}" for key, count in control_negative_type.most_common()],
        "",
        "## Layers",
        "",
        *[f"- {name}: {len(features)}" for name, features in layers.items()],
        "",
        "## Files",
        "",
        "- data/morphology-autoreview-v1/morphology_autoreview_v1.gpkg",
        "- data/morphology-autoreview-v1/p0_points.geojson",
        "- data/morphology-autoreview-v1/p0_positive_proposed_polygons.geojson",
        "- data/morphology-autoreview-v1/p0_negative_proposed_polygons.geojson",
        "- data/morphology-autoreview-v1/control_set_v1_points.geojson",
        "- data/morphology-autoreview-v1/control_set_v1_positive_polygons.geojson",
        "- data/morphology-autoreview-v1/control_set_v1_negative_polygons.geojson",
        "- data/morphology-autoreview-v1/control_set_v1_tile_windows_512m.geojson",
        "- data/morphology-autoreview-v1/autoreview_decisions.tsv",
        "- data/morphology-autoreview-v1/orthophoto_thumbnail_manifest.tsv",
        "- data/morphology-autoreview-v1/autoreview_summary.tsv",
        "",
        "## Orthophoto Sources",
        "",
        f"- Galicia/Spain: IGN PNOA WMS `{ES_WMS_BASE}`, layer `{ES_WMS_LAYER}`.",
        f"- Northern Portugal: DGT Ortofotos 2021 WMS `{PT_WMS_BASE}`, layer `{PT_WMS_LAYER}`.",
        "",
        "## Next Step",
        "",
        "Run the radial/LiDAR/orthophoto feature extraction over `control_set_v1_*` first. Do not export these polygons to training manifests until a raster/visual verifier promotes them from `auto_seeded_requires_visual_verification` to `accepted`.",
    ]
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "morphology_autoreview_v1.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    if not SOURCE_SEED.exists():
        raise SystemExit(f"Missing seed bank: {SOURCE_SEED}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = read_tsv(SOURCE_SEED)
    p0 = p0_rows(rows)
    control_rows = build_control_set(p0)
    control_ids = {row["bank_id"]: row for row in control_rows}
    p0_with_control = []
    for row in p0:
        copied = dict(row)
        copied["control_set_id"] = control_ids.get(row["bank_id"], {}).get("control_set_id", "")
        p0_with_control.append(copied)

    layers = build_layers(p0_with_control, control_rows)
    for name, features in layers.items():
        write_geojson(OUT_DIR / f"{name}.geojson", name, features)
    create_gpkg(OUT_DIR / "morphology_autoreview_v1.gpkg", layers)

    decision_fields = [
        "bank_id",
        "review_seed_id",
        "control_set_id",
        "review_role",
        "country",
        "province_or_district",
        "municipality",
        "name",
        "typology",
        "morphology_proxy",
        "negative_type",
        "review_priority",
        "auto_review_status",
        "auto_decision",
        "training_use",
        "proposed_radius_m",
        "source",
        "source_record_id",
        "source_code",
    ]
    decisions: list[dict[str, str]] = []
    for row in p0_with_control:
        decision = base_props(row)
        decision["proposed_radius_m"] = f"{radius_m(row):.1f}"
        if row.get("control_set_id"):
            decision["auto_decision"] = "selected_for_control_set_v1"
        decisions.append(decision)
    write_tsv(OUT_DIR / "autoreview_decisions.tsv", decisions, decision_fields)

    thumbnails = export_thumbnails(control_rows)
    write_tsv(
        OUT_DIR / "orthophoto_thumbnail_manifest.tsv",
        thumbnails,
        [
            "thumbnail_id",
            "control_set_id",
            "bank_id",
            "review_role",
            "country",
            "name",
            "wms_source",
            "wms_base",
            "wms_layer",
            "bbox_epsg4326",
            "width_px",
            "height_px",
            "thumbnail_path",
            "status",
            "bytes",
            "error",
        ],
    )
    write_tsv(OUT_DIR / "autoreview_summary.tsv", summary_rows(p0, control_rows, thumbnails), ["dataset", "field", "value", "count"])
    write_report(p0, control_rows, layers, thumbnails)

    failed_thumbnails = sum(1 for row in thumbnails if row["status"] == "failed")
    print(f"p0_rows={len(p0)}")
    print(f"control_set_v1_rows={len(control_rows)}")
    print(f"thumbnails={len(thumbnails)}")
    print(f"failed_thumbnails={failed_thumbnails}")
    print(f"wrote={OUT_DIR}")
    print(f"report={REPORTS_DIR / 'morphology_autoreview_v1.md'}")


if __name__ == "__main__":
    main()
