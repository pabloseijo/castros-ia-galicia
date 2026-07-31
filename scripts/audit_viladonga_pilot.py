#!/usr/bin/env python3
"""Audit the controlled Viladonga morphology pilot inputs."""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import shutil
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "configs/viladonga_pilot.json"
DEFAULT_REPORT = PROJECT_ROOT / "reports/viladonga_pilot_readiness.md"
DEFAULT_MANIFEST = PROJECT_ROOT / "data/viladonga-pilot/labels_manifest.tsv"
GENERATED_AT = "2026-07-31"


LABEL_FIELDS = [
    "feature_id",
    "label_class",
    "label_kind",
    "area_m2",
    "perimeter_m",
    "circularity",
    "equivalent_diameter_m",
    "centroid_x",
    "centroid_y",
    "bbox_utm29",
]


def load_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_source_root(config: dict[str, Any], override: str | None) -> Path:
    if override:
        return Path(override).expanduser()
    for key in ("source_root_local", "source_root_raspberry"):
        candidate = Path(config[key]).expanduser()
        if candidate.exists():
            return candidate
    return Path(config["source_root_local"]).expanduser()


def module_status(module: str) -> str:
    return "ok" if importlib.util.find_spec(module) else "missing"


def command_status(command: str) -> str:
    return "ok" if shutil.which(command) else "missing"


def file_status(root: Path, rel_path: str) -> dict[str, str]:
    path = root / rel_path
    if path.exists():
        return {
            "path": str(path),
            "relative_path": rel_path,
            "exists": "yes",
            "size_mb": f"{path.stat().st_size / 1024 / 1024:.2f}",
        }
    return {"path": str(path), "relative_path": rel_path, "exists": "no", "size_mb": "0.00"}


def ring_area(coords: list[list[float]]) -> float:
    total = 0.0
    for (x1, y1), (x2, y2) in zip(coords, coords[1:] + coords[:1]):
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


def ring_perimeter(coords: list[list[float]]) -> float:
    total = 0.0
    for (x1, y1), (x2, y2) in zip(coords, coords[1:] + coords[:1]):
        total += math.hypot(x2 - x1, y2 - y1)
    return total


def ring_centroid(coords: list[list[float]]) -> tuple[float, float]:
    signed_twice_area = 0.0
    cx = 0.0
    cy = 0.0
    for (x1, y1), (x2, y2) in zip(coords, coords[1:] + coords[:1]):
        cross = x1 * y2 - x2 * y1
        signed_twice_area += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    if abs(signed_twice_area) < 1e-9:
        xs = [point[0] for point in coords]
        ys = [point[1] for point in coords]
        return sum(xs) / len(xs), sum(ys) / len(ys)
    return cx / (3.0 * signed_twice_area), cy / (3.0 * signed_twice_area)


def load_label_rows(path: Path) -> list[dict[str, str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows: list[dict[str, str]] = []
    for feature in payload.get("features", []):
        properties = feature.get("properties", {})
        geometry = feature.get("geometry", {})
        if geometry.get("type") != "Polygon":
            continue
        rings = geometry.get("coordinates") or []
        if not rings:
            continue
        outer = rings[0]
        coords = [[float(x), float(y)] for x, y, *_rest in outer]
        if len(coords) > 1 and coords[0] == coords[-1]:
            coords = coords[:-1]
        if len(coords) < 3:
            continue
        area = ring_area(coords)
        perimeter = ring_perimeter(coords)
        centroid_x, centroid_y = ring_centroid(coords)
        xs = [point[0] for point in coords]
        ys = [point[1] for point in coords]
        label_class = str(properties.get("class", ""))
        rows.append(
            {
                "feature_id": str(properties.get("fid", len(rows) + 1)),
                "label_class": label_class,
                "label_kind": "positive" if label_class == "1" else "negative",
                "area_m2": f"{area:.2f}",
                "perimeter_m": f"{perimeter:.2f}",
                "circularity": f"{(4.0 * math.pi * area / (perimeter * perimeter)) if perimeter else 0.0:.4f}",
                "equivalent_diameter_m": f"{math.sqrt(4.0 * area / math.pi):.2f}",
                "centroid_x": f"{centroid_x:.2f}",
                "centroid_y": f"{centroid_y:.2f}",
                "bbox_utm29": ",".join(f"{value:.2f}" for value in (min(xs), min(ys), max(xs), max(ys))),
            }
        )
    return rows


def raster_metadata(path: Path) -> dict[str, str]:
    try:
        import rasterio
    except Exception:
        return {"status": "skipped_missing_rasterio"}
    try:
        with rasterio.open(path) as src:
            return {
                "status": "ok",
                "crs": str(src.crs),
                "size": f"{src.width}x{src.height}",
                "bands": str(src.count),
                "resolution": ",".join(f"{value:.4f}" for value in src.res),
                "bounds": ",".join(f"{value:.2f}" for value in src.bounds),
            }
    except Exception as exc:
        return {"status": f"error: {exc}"}


def write_tsv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, dialect="excel-tab")
        writer.writeheader()
        writer.writerows(rows)


def write_report(
    path: Path,
    config: dict[str, Any],
    root: Path,
    labels: list[dict[str, str]],
    file_checks: list[dict[str, str]],
    raster_checks: list[tuple[str, dict[str, str]]],
) -> None:
    positives = [row for row in labels if row["label_class"] == "1"]
    negatives = [row for row in labels if row["label_class"] == "0"]
    missing_files = [item for item in file_checks if item["exists"] != "yes"]
    pnoa_ok = (root / config["pnoa_ortho"]).exists()
    lidar_ok = all((root / rel_path).exists() for rel_path in config["lidar_laz"])
    labels_ok = bool(positives) and bool(negatives)
    status = "ready_for_first_pilot" if labels_ok and (pnoa_ok or lidar_ok) else "blocked"

    lines = [
        "# Viladonga pilot readiness",
        "",
        f"Generated: {GENERATED_AT}",
        "",
        f"- Source root: `{root}`",
        f"- Label CRS: `{config['label_crs']}`",
        f"- Target CRS: `{config['target_crs']}`",
        f"- Positive polygons: {len(positives)}",
        f"- Negative polygons: {len(negatives)}",
        f"- Status: `{status}`",
        "",
        "## Interpretation",
        "",
        "Viladonga is a controlled smoke test for the original TFG idea: learn whether the pipeline can export imagery, masks and relief products around a known castro shape. It is not enough for model training by itself.",
        "",
        "## Labels",
        "",
    ]
    if labels:
        lines.append("| Feature | Class | Kind | Area m2 | Perimeter m | Circularity | Equivalent diameter m |")
        lines.append("|---:|---:|---|---:|---:|---:|---:|")
        for row in labels:
            lines.append(
                f"| {row['feature_id']} | {row['label_class']} | {row['label_kind']} | {row['area_m2']} | {row['perimeter_m']} | {row['circularity']} | {row['equivalent_diameter_m']} |"
            )
    else:
        lines.append("- No valid polygon labels found.")

    lines.extend(["", "## Source Files", ""])
    for item in file_checks:
        lines.append(f"- `{item['relative_path']}`: {item['exists']} ({item['size_mb']} MB)")

    lines.extend(["", "## Runtime", ""])
    for module in ("numpy", "rasterio", "geopandas", "shapely", "pyproj", "laspy", "lazrs"):
        lines.append(f"- Python module `{module}`: {module_status(module)}")
    for command in ("gdalinfo", "gdaldem", "pdal"):
        lines.append(f"- Command `{command}`: {command_status(command)}")

    lines.extend(["", "## Raster Metadata", ""])
    if raster_checks:
        for name, meta in raster_checks:
            details = ", ".join(f"{key}={value}" for key, value in meta.items())
            lines.append(f"- `{name}`: {details}")
    else:
        lines.append("- Raster metadata unavailable.")

    lines.extend(["", "## Next Commands", ""])
    lines.append("```bash")
    lines.append("make viladonga-pnoa-chips")
    lines.append("make viladonga-lidar-derivatives")
    lines.append("```")

    if missing_files:
        lines.extend(["", "## Missing Files", ""])
        for item in missing_files:
            lines.append(f"- `{item['relative_path']}`")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit the Viladonga pilot inputs.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--source-root")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    root = resolve_source_root(config, args.source_root)
    label_path = root / config["label_geojson"]

    rel_paths = [config["label_geojson"], config["label_gpkg"], config["pnoa_ortho"]]
    rel_paths.extend(config["lidar_laz"])
    rel_paths.extend(config["sentinel_products"].values())
    file_checks = [file_status(root, rel_path) for rel_path in rel_paths]

    labels = load_label_rows(label_path) if label_path.exists() else []
    write_tsv(args.manifest, labels, LABEL_FIELDS)

    raster_rel_paths = [config["pnoa_ortho"], *config["sentinel_products"].values()]
    raster_checks = [(rel_path, raster_metadata(root / rel_path)) for rel_path in raster_rel_paths if (root / rel_path).exists()]
    write_report(args.report, config, root, labels, file_checks, raster_checks)

    positives = sum(1 for row in labels if row["label_class"] == "1")
    negatives = sum(1 for row in labels if row["label_class"] == "0")
    missing = sum(1 for item in file_checks if item["exists"] != "yes")
    print(f"source_root={root}")
    print(f"positive_polygons={positives}")
    print(f"negative_polygons={negatives}")
    print(f"missing_files={missing}")
    print(f"report={args.report}")
    return 1 if missing or not positives or not negatives else 0


if __name__ == "__main__":
    raise SystemExit(main())
