#!/usr/bin/env python3
"""Build a small DEM and relief derivatives for the Viladonga morphology pilot."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "configs/viladonga_pilot.json"
DEFAULT_OUT_DIR = PROJECT_ROOT / "data/viladonga-pilot/lidar"
DEFAULT_REPORT = PROJECT_ROOT / "reports/viladonga_lidar_derivatives.md"
DEFAULT_MANIFEST = PROJECT_ROOT / "data/viladonga-pilot/lidar_derivatives_manifest.tsv"
GENERATED_AT = "2026-08-01"


FIELDS = ["product", "path", "width", "height", "resolution_m", "crs", "status", "notes"]


def require_runtime(build_from_laz: bool) -> None:
    missing = []
    for module in ("numpy", "pyproj", "rasterio", "shapely"):
        try:
            __import__(module)
        except Exception:
            missing.append(module)
    if build_from_laz:
        for module in ("laspy", "lazrs"):
            try:
                __import__(module)
            except Exception:
                missing.append(module)
    if missing:
        raise SystemExit(f"Missing Python modules: {', '.join(missing)}")


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


def rel_to_project(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def load_label_geometries(path: Path):
    from shapely.geometry import shape

    payload = json.loads(path.read_text(encoding="utf-8"))
    return [shape(feature["geometry"]) for feature in payload.get("features", []) if feature.get("geometry")]


def transformed_total_bounds(geometries, source_crs: str, target_crs: str) -> tuple[float, float, float, float]:
    from pyproj import Transformer
    from shapely.ops import transform as transform_geom

    transformer = Transformer.from_crs(source_crs, target_crs, always_xy=True)
    transformed = [transform_geom(transformer.transform, geom) for geom in geometries]
    minx = min(geom.bounds[0] for geom in transformed)
    miny = min(geom.bounds[1] for geom in transformed)
    maxx = max(geom.bounds[2] for geom in transformed)
    maxy = max(geom.bounds[3] for geom in transformed)
    return minx, miny, maxx, maxy


def fill_nodata_neighbour_mean(grid, max_iter: int = 80):
    import numpy as np

    filled = grid.astype("float32", copy=True)
    for _ in range(max_iter):
        missing = ~np.isfinite(filled)
        if not missing.any():
            break
        acc = np.zeros_like(filled, dtype="float32")
        count = np.zeros_like(filled, dtype="float32")
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                src_y = slice(max(0, -dy), filled.shape[0] - max(0, dy))
                dst_y = slice(max(0, dy), filled.shape[0] - max(0, -dy))
                src_x = slice(max(0, -dx), filled.shape[1] - max(0, dx))
                dst_x = slice(max(0, dx), filled.shape[1] - max(0, -dx))
                neighbour = filled[src_y, src_x]
                valid = np.isfinite(neighbour)
                acc_view = acc[dst_y, dst_x]
                count_view = count[dst_y, dst_x]
                acc_view[valid] += neighbour[valid]
                count_view[valid] += 1
        can_fill = missing & (count > 0)
        if not can_fill.any():
            break
        filled[can_fill] = acc[can_fill] / count[can_fill]
    if (~np.isfinite(filled)).any():
        mean_value = float(np.nanmean(filled))
        filled[~np.isfinite(filled)] = mean_value
    return filled


def build_dem_from_laz(laz_paths: list[Path], bounds: tuple[float, float, float, float], resolution: float):
    import laspy
    import numpy as np

    minx, miny, maxx, maxy = bounds
    width = int(math.ceil((maxx - minx) / resolution))
    height = int(math.ceil((maxy - miny) / resolution))
    grid = np.full((height, width), np.inf, dtype="float32")
    total_points = 0
    used_points = 0
    for laz_path in laz_paths:
        las = laspy.read(laz_path)
        x = np.asarray(las.x)
        y = np.asarray(las.y)
        z = np.asarray(las.z)
        keep = (x >= minx) & (x < maxx) & (y >= miny) & (y < maxy)
        total_points += int(keep.sum())
        if hasattr(las, "classification"):
            ground = keep & (las.classification == 2)
            if int(ground.sum()) > 100:
                keep = ground
        used_points += int(keep.sum())
        if not int(keep.sum()):
            continue
        cols = ((x[keep] - minx) / resolution).astype("int64")
        rows = ((maxy - y[keep]) / resolution).astype("int64")
        valid = (cols >= 0) & (cols < width) & (rows >= 0) & (rows < height)
        if int(valid.sum()):
            np.minimum.at(grid, (rows[valid], cols[valid]), z[keep][valid].astype("float32"))
    grid[grid == np.inf] = np.nan
    if not np.isfinite(grid).any():
        tile_bounds = []
        for laz_path in laz_paths:
            las = laspy.read(laz_path)
            header = las.header
            tile_bounds.append(f"{laz_path.name}: {header.mins[0]:.2f},{header.mins[1]:.2f},{header.maxs[0]:.2f},{header.maxs[1]:.2f}")
        raise RuntimeError(
            "No LiDAR points fell inside the pilot bounds. "
            f"Pilot bounds={minx:.2f},{miny:.2f},{maxx:.2f},{maxy:.2f}. "
            f"LAZ bounds={' | '.join(tile_bounds)}"
        )
    return fill_nodata_neighbour_mean(grid), total_points, used_points


def box_mean(array, radius: int):
    import numpy as np

    radius = max(1, int(radius))
    kernel = 2 * radius + 1
    padded = np.pad(array, radius, mode="edge")
    padded_integral = np.pad(padded, ((1, 0), (1, 0)), mode="constant", constant_values=0).cumsum(axis=0).cumsum(axis=1)
    summed = (
        padded_integral[kernel:, kernel:]
        - padded_integral[:-kernel, kernel:]
        - padded_integral[kernel:, :-kernel]
        + padded_integral[:-kernel, :-kernel]
    )
    return (summed / float(kernel * kernel)).astype("float32")


def derive_products(dem, resolution: float, lrm_radius_m: float) -> dict[str, Any]:
    import numpy as np

    dz_dy, dz_dx = np.gradient(dem, resolution, resolution)
    slope = np.degrees(np.arctan(np.hypot(dz_dx, dz_dy))).astype("float32")

    azimuth = math.radians(315.0)
    altitude = math.radians(45.0)
    slope_rad = np.arctan(np.hypot(dz_dx, dz_dy))
    aspect = np.arctan2(-dz_dx, dz_dy)
    hillshade = 255.0 * (
        math.sin(altitude) * np.cos(slope_rad)
        + math.cos(altitude) * np.sin(slope_rad) * np.cos(azimuth - aspect)
    )
    hillshade = np.clip(hillshade, 0, 255).astype("uint8")

    radius_px = max(1, int(round(lrm_radius_m / resolution)))
    lrm = (dem - box_mean(dem, radius_px)).astype("float32")
    return {"dem": dem.astype("float32"), "slope_degrees": slope, "hillshade_315_45": hillshade, "lrm": lrm}


def write_geotiff(path: Path, array, transform, crs: str, dtype: str, nodata=None) -> None:
    import rasterio

    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=array.shape[0],
        width=array.shape[1],
        count=1,
        dtype=dtype,
        crs=crs,
        transform=transform,
        nodata=nodata,
        compress="deflate",
    ) as dst:
        dst.write(array, 1)


def write_tsv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, dialect="excel-tab")
        writer.writeheader()
        writer.writerows(rows)


def write_report(path: Path, rows: list[dict[str, str]], notes: list[str], source_root: Path) -> None:
    ready = bool(rows) and all(row["status"] in {"written", "exists"} for row in rows)
    lines = [
        "# Viladonga LiDAR derivatives",
        "",
        f"Generated: {GENERATED_AT}",
        "",
        f"- Source root: `{source_root}`",
        f"- Products: {len(rows)}",
        f"- Status: `{'ready' if ready else 'blocked_or_partial'}`",
        "",
        "## Products",
        "",
    ]
    if rows:
        lines.append("| Product | Path | Size | Resolution m | Status |")
        lines.append("|---|---|---:|---:|---|")
        for row in rows:
            lines.append(f"| {row['product']} | `{row['path']}` | {row['width']}x{row['height']} | {row['resolution_m']} | {row['status']} |")
    else:
        lines.append("- No products written.")
    if notes:
        lines.extend(["", "## Notes", ""])
        lines.extend(f"- {note}" for note in notes)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Viladonga LiDAR DEM and derivatives.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--source-root")
    parser.add_argument("--laz", action="append", type=Path, help="Explicit LAZ file to use instead of config lidar_laz. Repeatable.")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--dem", type=Path, help="Use an existing DEM/DTM instead of gridding LAZ files.")
    parser.add_argument("--resolution-m", type=float)
    parser.add_argument("--buffer-m", type=float)
    parser.add_argument("--lrm-radius-m", type=float)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    source_root = resolve_source_root(config, args.source_root)
    out_dir = args.out_dir if args.out_dir.is_absolute() else PROJECT_ROOT / args.out_dir
    resolution = float(args.resolution_m or config["dem_resolution_m"])
    buffer_m = float(args.buffer_m or config["dem_buffer_m"])
    lrm_radius_m = float(args.lrm_radius_m or config["lrm_radius_m"])
    build_from_laz = args.dem is None
    require_runtime(build_from_laz)

    import rasterio
    from rasterio.transform import from_origin

    rows: list[dict[str, str]] = []
    notes: list[str] = []
    crs = config["lidar_crs"]

    try:
        if args.dem:
            dem_path = args.dem.expanduser()
            if not dem_path.exists():
                raise RuntimeError(f"Missing DEM: {dem_path}")
            with rasterio.open(dem_path) as src:
                dem = src.read(1, masked=True).filled(float("nan")).astype("float32")
                transform = src.transform
                crs = str(src.crs)
                resolution = float(abs(src.res[0]))
            notes.append(f"Loaded existing DEM: {dem_path}")
        else:
            label_path = source_root / config["label_geojson"]
            if args.laz:
                laz_paths = [path.expanduser() if path.is_absolute() else PROJECT_ROOT / path for path in args.laz]
            else:
                laz_paths = [source_root / rel_path for rel_path in config["lidar_laz"]]
            missing_laz = [path for path in laz_paths if not path.exists()]
            if missing_laz:
                raise RuntimeError("Missing LiDAR LAZ files: " + ", ".join(str(path) for path in missing_laz))
            geometries = load_label_geometries(label_path)
            minx, miny, maxx, maxy = transformed_total_bounds(geometries, config["label_crs"], crs)
            minx -= buffer_m
            miny -= buffer_m
            maxx += buffer_m
            maxy += buffer_m
            dem, total_points, used_points = build_dem_from_laz(laz_paths, (minx, miny, maxx, maxy), resolution)
            transform = from_origin(minx, maxy, resolution, resolution)
            notes.append(f"LiDAR points in pilot bounds: total={total_points}, used={used_points}")
    except Exception as exc:
        notes.append(str(exc))
        write_tsv(args.manifest, [], FIELDS)
        write_report(args.report, [], notes, source_root)
        print(f"source_root={source_root}")
        print("products=0")
        print(f"blocked={exc}")
        return 1

    products = derive_products(dem, resolution, lrm_radius_m)
    product_specs = {
        "dem": ("viladonga_dem.tif", "float32", -9999.0),
        "slope_degrees": ("viladonga_slope_degrees.tif", "float32", -9999.0),
        "hillshade_315_45": ("viladonga_hillshade_315_45.tif", "uint8", 0),
        "lrm": ("viladonga_lrm.tif", "float32", -9999.0),
    }
    for product, array in products.items():
        filename, dtype, nodata = product_specs[product]
        out_path = out_dir / filename
        if out_path.exists() and not args.force:
            status = "exists"
        else:
            write_geotiff(out_path, array, transform, crs, dtype, nodata)
            status = "written"
        rows.append(
            {
                "product": product,
                "path": rel_to_project(out_path),
                "width": str(array.shape[1]),
                "height": str(array.shape[0]),
                "resolution_m": f"{resolution:.2f}",
                "crs": crs,
                "status": status,
                "notes": "",
            }
        )

    write_tsv(args.manifest, rows, FIELDS)
    write_report(args.report, rows, notes, source_root)
    print(f"source_root={source_root}")
    print(f"products={len(rows)}")
    print(f"manifest={args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
