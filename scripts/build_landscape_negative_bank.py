#!/usr/bin/env python3
"""Sample generic landscape negatives across Galicia.

The v1 negative bank is 69.3% megalithic mounds and 25% rock art: the model
never learned "castro vs world", it learned "castro vs mámoa". On a blind
grid the terrain is quarries, farm enclosures, roundabouts, reservoirs and
buildings — none of which it was ever shown as a negative.

This draws a spatially spread random sample of Galician land, excluding a
buffer around every catalogued site, so the bank gains ordinary terrain.

These are positive-unlabeled negatives, not verified absences: a sampled
cell could hide an uncatalogued castro. The exclusion buffer and the low
prior make that rare, and the point is to teach the model what ordinary
ground looks like, not to assert emptiness.
"""

from __future__ import annotations

import argparse
import csv
import math
import random
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MASTER = PROJECT_ROOT / "data/weak-label-splits-v1/weak_label_master.tsv"
DEFAULT_OUT_DIR = PROJECT_ROOT / "data/landscape-negatives-v1"
DEFAULT_CHIP_ROOT = PROJECT_ROOT / "data/external/landscape-negatives-v1"
DEFAULT_REPORT = PROJECT_ROOT / "reports/landscape_negative_bank_v1.md"

GENERATED_AT = "2026-08-03T00:00:00Z"
TILE_SIDE_M = 512.0
IGN_WMS_BASE = "https://www.ign.es/wms-inspire/pnoa-ma"
IGN_WMS_LAYER = "OI.OrthoimageCoverage"

# Galicia mainland envelope.
DEFAULT_BBOX = "-9.30,41.80,-6.73,43.79"

FIELDS = [
    "tile_id",
    "sample_id",
    "bank_id",
    "label_class",
    "label_role",
    "final_split",
    "country",
    "name",
    "longitude",
    "latitude",
    "bbox_epsg4326",
    "tile_side_m",
    "wms_source",
    "wms_base",
    "wms_layer",
    "target_png_path",
    "training_use",
    "negative_type",
    "province_or_district",
    "municipality",
    "spatial_block_id",
    "nearest_site_m",
]


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    radius = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, dialect="excel-tab"))


def write_tsv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=fields, dialect="excel-tab", extrasaction="ignore", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def rel_to_project(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def build_cell_index(sites: list[tuple[float, float]], cell_deg: float) -> dict:
    index: dict[tuple[int, int], list[tuple[float, float]]] = {}
    for lon, lat in sites:
        key = (int(lon / cell_deg), int(lat / cell_deg))
        index.setdefault(key, []).append((lon, lat))
    return index


def nearest_site_m(index: dict, cell_deg: float, lon: float, lat: float, cap_m: float) -> float:
    """Nearest catalogued site, searching only neighbouring grid cells."""
    key_x, key_y = int(lon / cell_deg), int(lat / cell_deg)
    best = float("inf")
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for s_lon, s_lat in index.get((key_x + dx, key_y + dy), ()):
                distance = haversine_m(lon, lat, s_lon, s_lat)
                if distance < best:
                    best = distance
                    if best < cap_m * 0.25:
                        return best
    return best


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--master", type=Path, default=DEFAULT_MASTER)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--chip-root", type=Path, default=DEFAULT_CHIP_ROOT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--bbox", default=DEFAULT_BBOX)
    parser.add_argument("--samples", type=int, default=6000)
    parser.add_argument("--exclusion-m", type=float, default=400.0)
    parser.add_argument("--min-separation-m", type=float, default=600.0)
    parser.add_argument("--seed", type=int, default=20260803)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    for attr in ("master", "out_dir", "chip_root", "report"):
        value = getattr(args, attr)
        setattr(args, attr, value if value.is_absolute() else PROJECT_ROOT / value)

    min_lon, min_lat, max_lon, max_lat = [float(v) for v in args.bbox.split(",")]
    master = read_tsv(args.master)

    sites: list[tuple[float, float]] = []
    for row in master:
        try:
            sites.append((float(row["longitude"]), float(row["latitude"])))
        except (KeyError, ValueError):
            continue

    cell_deg = 0.01
    site_index = build_cell_index(sites, cell_deg)

    rng = random.Random(args.seed)
    accepted: list[dict[str, str]] = []
    accepted_points: list[tuple[float, float]] = []
    accepted_index: dict[tuple[int, int], list[tuple[float, float]]] = {}

    attempts = 0
    max_attempts = args.samples * 60
    while len(accepted) < args.samples and attempts < max_attempts:
        attempts += 1
        lon = rng.uniform(min_lon, max_lon)
        lat = rng.uniform(min_lat, max_lat)

        distance = nearest_site_m(site_index, cell_deg, lon, lat, args.exclusion_m)
        if distance < args.exclusion_m:
            continue
        own = nearest_site_m(accepted_index, cell_deg, lon, lat, args.min_separation_m)
        if own < args.min_separation_m:
            continue

        index = len(accepted)
        tile_id = f"lsneg-v1-{index:05d}"
        half_lat = TILE_SIDE_M / 2.0 / 111320.0
        half_lon = TILE_SIDE_M / 2.0 / (111320.0 * math.cos(math.radians(lat)))
        accepted.append(
            {
                "tile_id": tile_id,
                "sample_id": f"wl-neg-{tile_id}",
                "bank_id": tile_id,
                "label_class": "0",
                "label_role": "hard_negative",
                "final_split": "train",
                "country": "ES",
                "name": f"landscape sample {index}",
                "longitude": f"{lon:.8f}",
                "latitude": f"{lat:.8f}",
                "bbox_epsg4326": (
                    f"{lon - half_lon:.8f},{lat - half_lat:.8f},"
                    f"{lon + half_lon:.8f},{lat + half_lat:.8f}"
                ),
                "tile_side_m": f"{int(TILE_SIDE_M)}",
                "wms_source": "ign_pnoa_rgb",
                "wms_base": IGN_WMS_BASE,
                "wms_layer": IGN_WMS_LAYER,
                "target_png_path": rel_to_project(args.chip_root / "rgb" / f"{tile_id}.png"),
                "training_use": "landscape_negative_v1",
                "negative_type": "generic_landscape",
                "province_or_district": "",
                "municipality": "",
                "spatial_block_id": f"ES|landscape|{int(lon * 20)}_{int(lat * 20)}",
                "nearest_site_m": f"{distance:.0f}" if math.isfinite(distance) else "",
            }
        )
        accepted_points.append((lon, lat))
        key = (int(lon / cell_deg), int(lat / cell_deg))
        accepted_index.setdefault(key, []).append((lon, lat))

    manifest = args.out_dir / "landscape_negative_manifest.tsv"
    write_tsv(manifest, accepted, FIELDS)

    distances = [float(r["nearest_site_m"]) for r in accepted if r["nearest_site_m"]]
    distances.sort()
    median = distances[len(distances) // 2] if distances else 0.0
    blocks = len({r["spatial_block_id"] for r in accepted})

    lines = [
        "# Landscape negative bank v1",
        "",
        f"Generated at: `{GENERATED_AT}`",
        "",
        "## Why",
        "",
        "The v1 negative bank is `69.3%` megalithic mounds and `25%` rock art.",
        "That taught the model to separate castros from mámoas, not from ordinary",
        "ground. On a blind grid it meets quarries, field enclosures, reservoirs",
        "and buildings it has never been shown as negatives.",
        "",
        "## Sample",
        "",
        f"- requested: `{args.samples}`",
        f"- accepted: `{len(accepted)}`",
        f"- draw attempts: `{attempts}`",
        f"- exclusion buffer around catalogued sites: `{args.exclusion_m:.0f} m`",
        f"- minimum separation between samples: `{args.min_separation_m:.0f} m`",
        f"- distinct spatial blocks covered: `{blocks}`",
        f"- median distance to nearest catalogued site: `{median:.0f} m`",
        "",
        "## Caution",
        "",
        "These are positive-unlabeled negatives. A sampled cell can hide an",
        "uncatalogued castro; the exclusion buffer and the low base rate make it",
        "rare but not impossible. They are here to teach the model what ordinary",
        "terrain looks like, never to assert archaeological absence.",
        "",
        "Sea and water cells are not filtered here: the relief stage flags them",
        "by DEM flatness downstream, which keeps the exclusion auditable.",
        "",
    ]
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"accepted={len(accepted)} attempts={attempts} blocks={blocks}")
    print(f"manifest={rel_to_project(manifest)}")
    print(f"report={rel_to_project(args.report)}")


if __name__ == "__main__":
    main()
