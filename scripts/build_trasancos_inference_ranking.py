#!/usr/bin/env python3
"""Score a regular grid over Trasancos with the RGB+relief+MSRM fusion.

Everything before this ran on catalogued points: the model was only ever
asked to rank places somebody had already flagged. This walks a grid over
the comarca instead, so the ranker has to commit on ground nobody selected
for it.

Stages:
  grid   build the tile manifest (reuses the weak-label tile schema, so the
         existing RGB/DEM exporters can consume it unchanged)
  score  extract RGB + relief + MSRM features, apply the saved fusion model,
         flag cells that coincide with catalogued sites, rank the rest

The output is an internal review queue. Cells that rank high and match no
catalogue entry are candidates to look at, not discoveries: coordinates stay
out of anything published until a human and an archaeologist have judged them.
"""

from __future__ import annotations

import argparse
import csv
import os
import json
import math
import statistics
import subprocess
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from evaluate_weak_label_msrm_features import (  # noqa: E402
    DEFAULT_RING_RADII_M,
    DEFAULT_SCALES_M,
    build_multiscale_relief,
    geometry_cache,
    mask_mean as msrm_mask_mean,
    parse_scale_list,
    ring_masks,
    ring_sector_metrics as msrm_ring_sector_metrics,
    scale_tag,
    shannon_entropy,
)
from evaluate_weak_label_relief_score_variants import VARIANT_NAMES  # noqa: E402
from train_weak_label_rgb_baseline import (  # noqa: E402
    FEATURE_NAMES as RGB_FEATURE_NAMES,
    extract_features as extract_rgb_features,
    parse_float,
    read_tsv,
    rel_to_project,
    write_tsv,
)
from train_weak_label_rgb_relief_baseline import (  # noqa: E402
    MSRM_FEATURE_NAMES,
    RELIEF_FEATURE_NAMES,
    fit_variant_scaler,
    variant_scores,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MASTER = PROJECT_ROOT / "data/weak-label-splits-v1/weak_label_master.tsv"
DEFAULT_MODEL = PROJECT_ROOT / "data/weak-label-fusion-v1/weak_label_rgb_relief_msrm_full_model.json"
DEFAULT_TRAIN_RELIEF = PROJECT_ROOT / "data/weak-label-relief-v1/weak_label_relief_features_train.tsv"
DEFAULT_OUT_DIR = PROJECT_ROOT / "data/trasancos-inference-v1"
DEFAULT_CHIP_ROOT = PROJECT_ROOT / "data/external/trasancos-inference-v1"
DEFAULT_REPORT = PROJECT_ROOT / "reports/trasancos_inference_ranking_v1.md"

GENERATED_AT = "2026-08-02T00:00:00Z"
TILE_SIDE_M = 512.0
IGN_WMS_BASE = "https://www.ign.es/wms-inspire/pnoa-ma"
IGN_WMS_LAYER = "OI.OrthoimageCoverage"
WCS_BASE = "https://servicios.idee.es/wcs-inspire/mdt"
COVERAGE_ID = "Elevacion25830_5"

# Trasancos / Ferrolterra working envelope, taken from the holdout rows.
DEFAULT_BBOX = "-8.33,43.42,-7.99,43.65"

GRID_FIELDS = [
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
    "grid_row",
    "grid_col",
    "known_site_id",
    "known_site_name",
    "known_site_class",
    "known_site_distance_m",
]

RANK_FIELDS = [
    "rank",
    "tile_id",
    "longitude",
    "latitude",
    "probability",
    "candidate_class",
    "known_site_name",
    "known_site_class",
    "known_site_distance_m",
    "dominant_scale_m",
    "best_ring_radius_m",
    "dem_prominence_m",
    "sea_or_flat",
    "center_offset_m",
    "center_offset_x_m",
    "center_offset_y_m",
    "status",
    "error",
]


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    radius = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def build_grid(args: argparse.Namespace) -> list[dict[str, str]]:
    min_lon, min_lat, max_lon, max_lat = [float(value) for value in args.bbox.split(",")]
    mid_lat = (min_lat + max_lat) / 2.0
    step_m = args.step_m
    deg_lat = step_m / 111320.0
    deg_lon = step_m / (111320.0 * math.cos(math.radians(mid_lat)))
    half_lat = TILE_SIDE_M / 2.0 / 111320.0
    half_lon = TILE_SIDE_M / 2.0 / (111320.0 * math.cos(math.radians(mid_lat)))

    known = []
    for row in read_tsv(args.master):
        try:
            known.append(
                (
                    float(row["longitude"]),
                    float(row["latitude"]),
                    row.get("sample_id", ""),
                    row.get("name", ""),
                    row.get("label_class", ""),
                    row.get("negative_type", ""),
                )
            )
        except (KeyError, ValueError):
            continue

    rows: list[dict[str, str]] = []
    lat = min_lat
    grid_row = 0
    while lat <= max_lat:
        lon = min_lon
        grid_col = 0
        while lon <= max_lon:
            tile_id = f"{args.tile_prefix}-{grid_row:04d}-{grid_col:04d}"
            nearest = None
            nearest_distance = float("inf")
            for k_lon, k_lat, k_id, k_name, k_class, k_negtype in known:
                if abs(k_lon - lon) > 0.02 or abs(k_lat - lat) > 0.02:
                    continue
                distance = haversine_m(lon, lat, k_lon, k_lat)
                if distance < nearest_distance:
                    nearest_distance = distance
                    nearest = (k_id, k_name, k_class, k_negtype)
            match_radius = args.known_match_m
            has_match = nearest is not None and nearest_distance <= match_radius
            rows.append(
                {
                    "tile_id": tile_id,
                    "sample_id": tile_id,
                    "bank_id": tile_id,
                    "label_class": "",
                    "label_role": "inference_grid",
                    "final_split": args.grid_split,
                    "country": "ES",
                    "name": f"grid {grid_row}/{grid_col}",
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
                    "target_png_path": rel_to_project(
                        args.chip_root / "rgb" / f"{tile_id}.png"
                    ),
                    "training_use": "inference_only_not_training",
                    "grid_row": str(grid_row),
                    "grid_col": str(grid_col),
                    "known_site_id": nearest[0] if has_match else "",
                    "known_site_name": nearest[1] if has_match else "",
                    "known_site_class": (
                        ("positive_castro" if nearest[2] in {"1", "positive"} else (nearest[3] or "negative"))
                        if has_match
                        else ""
                    ),
                    "known_site_distance_m": f"{nearest_distance:.1f}" if has_match else "",
                }
            )
            lon += deg_lon
            grid_col += 1
        lat += deg_lat
        grid_row += 1
    return rows


def dem_path_for(chip_root: Path, tile_id: str, grid_split: str = "trasancos_grid") -> Path:
    """Mirror export_weak_label_relief_wcs.target_dem_path.

    That exporter derives its own output path from final_split/label_class and
    ignores any target_dem_path column, so the reader has to follow the same
    convention or it looks for DEMs that were written elsewhere.
    """
    return (
        PROJECT_ROOT
        / "data/external/weak-label-relief-v1"
        / grid_split
        / "negative"
        / f"{tile_id}-mdt5.tif"
    )


def add_dem_targets(rows: list[dict[str, str]], chip_root: Path, grid_split: str) -> list[dict[str, str]]:
    out = []
    for row in rows:
        item = dict(row)
        item["target_dem_path"] = rel_to_project(dem_path_for(chip_root, row["tile_id"], grid_split))
        out.append(item)
    return out


def offset_distance(shape: tuple[int, int], resolution: float, offset_m: tuple[float, float]):
    """Distance-from-centre grid, but with the centre moved by offset_m.

    All the project's features are concentric around the chip centre. On a
    catalogue point that is where the site is; on a blind grid it is not.
    Moving the centre lets the same features be read off wherever the
    landform actually sits inside the cell.
    """
    import numpy as np

    height, width = shape
    yy, xx = np.indices((height, width))
    cx = (width - 1) / 2.0 + offset_m[0] / max(resolution, 1e-6)
    cy = (height - 1) / 2.0 - offset_m[1] / max(resolution, 1e-6)
    distance = np.hypot(xx - cx, yy - cy)
    angles = (np.arctan2(yy - cy, xx - cx) + 2.0 * math.pi) % (2.0 * math.pi)
    sectors = np.floor(angles / (2.0 * math.pi / RING_SECTORS_LOCAL)).astype("int16")
    return distance, sectors


def search_best_centre(
    dem,
    resolution: float,
    msrm_abs,
    ring_radii_m: list[float],
    search_m: float,
    step_m: float,
) -> tuple[tuple[float, float], float, float]:
    """Find the offset whose ring response is strongest.

    Returns (offset_m, best_radius_m, best_response).
    """
    best_offset = (0.0, 0.0)
    best_radius = ring_radii_m[len(ring_radii_m) // 2]
    best_response = -1.0

    # Searching every candidate radius at every offset is the expensive part
    # and adds little: the offset that wins tends to win at any reasonable
    # ring size. Explore with a coarse ladder, then let the full sweep in
    # msrm_features_for pick the exact radius at the chosen centre.
    if len(ring_radii_m) > 3:
        probe_radii = [
            ring_radii_m[len(ring_radii_m) // 4],
            ring_radii_m[len(ring_radii_m) // 2],
            ring_radii_m[(3 * len(ring_radii_m)) // 4],
        ]
    else:
        probe_radii = ring_radii_m

    steps = int(round(search_m / step_m))
    offsets = [step_m * value for value in range(-steps, steps + 1)]
    for dx in offsets:
        for dy in offsets:
            if math.hypot(dx, dy) > search_m:
                continue
            distance, sectors = offset_distance(dem.shape, resolution, (dx, dy))
            for radius_m in probe_radii:
                _core, annulus, context = ring_masks_at(
                    distance, dem.shape, radius_m, resolution
                )
                if int(annulus.sum()) < 8 or int(context.sum()) < 8:
                    continue
                coverage, balance = msrm_ring_sector_metrics(
                    msrm_abs, annulus, context, sectors
                )
                response = coverage * balance
                if response > best_response:
                    best_response = response
                    best_offset = (dx, dy)
                    best_radius = radius_m
    return best_offset, best_radius, max(best_response, 0.0)


def ring_masks_at(distance, shape: tuple[int, int], radius_m: float, resolution: float):
    """ring_masks, but taking a precomputed (possibly offset) distance grid."""
    height, width = shape
    radius_px = clamp_local(radius_m / max(resolution, 0.1), 3.0, min(width, height) * 0.45)
    annulus_half = clamp_local(radius_px * 0.16, 2.0, 8.0)
    core = distance <= radius_px * 0.62
    annulus = (distance >= radius_px - annulus_half) & (distance <= radius_px + annulus_half)
    context_start = radius_px + annulus_half * 2.0
    context_end = min(min(width, height) * 0.48, max(context_start + annulus_half * 3.0, radius_px * 1.9))
    context = (distance >= context_start) & (distance <= context_end)
    if not context.any():
        context = distance >= min(radius_px * 1.25, min(width, height) * 0.40)
    return core, annulus, context


def clamp_local(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


RING_SECTORS_LOCAL = 36


def relief_features_for(
    dem_path: Path, radius_m: float, offset_m: tuple[float, float] = (0.0, 0.0)
) -> dict[str, float] | None:
    """Fixed-radius relief features, matching the v1 relief baseline."""
    import numpy as np
    import rasterio

    from evaluate_weak_label_relief_baseline import (
        build_masks,
        derive_products,
        mask_mean,
        ring_sector_metrics,
        safe_ratio,
        sobel_edges,
    )

    with rasterio.open(dem_path) as src:
        dem = src.read(1).astype("float32")
        if src.nodata is not None:
            dem[dem == src.nodata] = np.nan
        resolution = abs(float(src.res[0]))
    dem, slope, hillshade, lrm = derive_products(dem, resolution, 50.0)
    hillshade_edge = sobel_edges(hillshade)
    if offset_m == (0.0, 0.0):
        core, annulus, context, sectors = build_masks(dem.shape, radius_m, resolution)
    else:
        distance, sectors = offset_distance(dem.shape, resolution, offset_m)
        core, annulus, context = ring_masks_at(distance, dem.shape, radius_m, resolution)
    coverage, balance = ring_sector_metrics(np.abs(lrm), annulus, context, sectors)
    dem_core = mask_mean(dem[core])
    dem_context = mask_mean(dem[context])
    slope_annulus = mask_mean(slope[annulus])
    slope_context = mask_mean(slope[context])
    lrm_abs_annulus = mask_mean(np.abs(lrm[annulus]))
    lrm_abs_context = mask_mean(np.abs(lrm[context]))
    lrm_core = mask_mean(lrm[core])
    lrm_context = mask_mean(lrm[context])
    edge_annulus = mask_mean(hillshade_edge[annulus])
    edge_context = mask_mean(hillshade_edge[context])
    return {
        "dem_core_mean": dem_core,
        "dem_context_mean": dem_context,
        "dem_prominence_m": dem_core - dem_context,
        "slope_annulus_mean": slope_annulus,
        "slope_context_mean": slope_context,
        "slope_ratio": safe_ratio(slope_annulus, slope_context),
        "lrm_abs_annulus_mean": lrm_abs_annulus,
        "lrm_abs_context_mean": lrm_abs_context,
        "lrm_abs_ratio": safe_ratio(lrm_abs_annulus, lrm_abs_context),
        "lrm_core_mean": lrm_core,
        "lrm_context_mean": lrm_context,
        "lrm_core_delta": lrm_core - lrm_context,
        "hillshade_edge_annulus_mean": edge_annulus,
        "hillshade_edge_context_mean": edge_context,
        "hillshade_edge_ratio": safe_ratio(edge_annulus, edge_context),
        "ring_sector_coverage": coverage,
        "ring_sector_balance": balance,
        "_dem_std": float(np.nanstd(dem)),
    }


def msrm_features_for(
    dem_path: Path,
    scales_m: list[float],
    ring_radii_m: list[float],
    offset_m: tuple[float, float] = (0.0, 0.0),
) -> dict[str, float]:
    import numpy as np
    import rasterio

    from evaluate_weak_label_msrm_features import safe_ratio

    with rasterio.open(dem_path) as src:
        dem = src.read(1).astype("float32")
        if src.nodata is not None:
            dem[dem == src.nodata] = np.nan
        resolution = abs(float(src.res[0]))
    finite = np.isfinite(dem)
    if not finite.all():
        dem = dem.astype("float32", copy=True)
        dem[~finite] = float(np.nanmean(dem)) if finite.any() else 0.0

    layers, msrm = build_multiscale_relief(dem, resolution, scales_m)
    if offset_m == (0.0, 0.0):
        distance_px, sectors = geometry_cache(dem.shape)
    else:
        distance_px, sectors = offset_distance(dem.shape, resolution, offset_m)
    msrm_abs = np.abs(msrm)
    features: dict[str, float] = {}

    scale_ratios = []
    for radius_m, layer in zip(scales_m, layers):
        core, annulus, context = ring_masks_at(distance_px, dem.shape, 120.0, resolution)
        layer_abs = np.abs(layer)
        ratio = safe_ratio(msrm_mask_mean(layer_abs[annulus]), msrm_mask_mean(layer_abs[context]))
        features[f"lrm{scale_tag(radius_m)}_abs_ratio"] = ratio
        features[f"lrm{scale_tag(radius_m)}_core_delta"] = (
            msrm_mask_mean(layer[core]) - msrm_mask_mean(layer[context])
        )
        scale_ratios.append(ratio)

    best_index = max(range(len(scale_ratios)), key=lambda idx: scale_ratios[idx])
    features["dominant_scale_m"] = float(scales_m[best_index])
    features["dominant_scale_ratio"] = scale_ratios[best_index]
    features["scale_ratio_spread"] = float(max(scale_ratios) - min(scale_ratios))
    features["scale_response_entropy"] = shannon_entropy(scale_ratios)

    sweep = []
    for radius_m in ring_radii_m:
        core, annulus, context = ring_masks_at(distance_px, dem.shape, radius_m, resolution)
        coverage, balance = msrm_ring_sector_metrics(msrm_abs, annulus, context, sectors)
        sweep.append(
            {
                "radius_m": radius_m,
                "coverage": coverage,
                "balance": balance,
                "abs_ratio": safe_ratio(
                    msrm_mask_mean(msrm_abs[annulus]), msrm_mask_mean(msrm_abs[context])
                ),
            }
        )
    best = max(sweep, key=lambda item: item["coverage"] * item["balance"])
    coverages = [item["coverage"] for item in sweep]
    features["best_ring_radius_m"] = float(best["radius_m"])
    features["best_ring_coverage"] = float(best["coverage"])
    features["best_ring_balance"] = float(best["balance"])
    features["best_ring_abs_ratio"] = float(best["abs_ratio"])
    features["ring_radius_sharpness"] = float(max(coverages) - statistics.mean(coverages))

    core, annulus, context = ring_masks_at(distance_px, dem.shape, 120.0, resolution)
    coverage, balance = msrm_ring_sector_metrics(msrm_abs, annulus, context, sectors)
    features["msrm_abs_annulus_mean"] = msrm_mask_mean(msrm_abs[annulus])
    features["msrm_abs_context_mean"] = msrm_mask_mean(msrm_abs[context])
    features["msrm_abs_ratio"] = safe_ratio(
        features["msrm_abs_annulus_mean"], features["msrm_abs_context_mean"]
    )
    features["msrm_core_mean"] = msrm_mask_mean(msrm[core])
    features["msrm_context_mean"] = msrm_mask_mean(msrm[context])
    features["msrm_core_delta"] = features["msrm_core_mean"] - features["msrm_context_mean"]
    features["msrm_ring_coverage"] = coverage
    features["msrm_ring_balance"] = balance
    return features


def rgb_features_at(
    image_path: Path, radius_m: float, image_size: int, offset_m: tuple[float, float]
) -> dict[str, float]:
    """RGB features read around a moved centre.

    Mirrors train_weak_label_rgb_baseline.extract_features but rebuilds the
    concentric masks about offset_m instead of the chip centre.
    """
    import numpy as np

    from train_weak_label_rgb_baseline import (
        SECTOR_COUNT,
        gray_entropy,
        load_rgb,
        mask_mean,
        mask_std,
        radial_peak_metrics,
        ring_sector_metrics as rgb_ring_sector_metrics,
        safe_ratio,
        sobel_edges as rgb_sobel_edges,
    )

    rgb = load_rgb(image_path, image_size)
    gray = 0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]
    green = rgb[:, :, 1]
    excess_green = 2.0 * rgb[:, :, 1] - rgb[:, :, 0] - rgb[:, :, 2]
    edges = rgb_sobel_edges(gray)

    height, width = gray.shape
    resolution = TILE_SIDE_M / float(min(height, width))
    yy, xx = np.indices((height, width))
    cx = (width - 1) / 2.0 + offset_m[0] / resolution
    cy = (height - 1) / 2.0 - offset_m[1] / resolution
    distance = np.hypot(xx - cx, yy - cy)

    max_radius = min(width, height) * 0.47
    radius_px = clamp_local(radius_m * min(width, height) / TILE_SIDE_M, 10.0, max_radius)
    annulus_half = clamp_local(radius_px * 0.16, 5.0, 14.0)
    inner = distance <= radius_px * 0.62
    annulus = (distance >= radius_px - annulus_half) & (distance <= radius_px + annulus_half)
    outer_start = radius_px + annulus_half * 2.0
    outer_end = min(max_radius, max(outer_start + annulus_half * 3.0, radius_px * 1.95))
    outer = (distance >= outer_start) & (distance <= outer_end)
    if not outer.any():
        outer = distance >= min(max(radius_px * 1.3, 24.0), max_radius * 0.8)
    angles = (np.arctan2(yy - cy, xx - cx) + 2.0 * math.pi) % (2.0 * math.pi)
    sector_ids = np.floor(angles / (2.0 * math.pi / SECTOR_COUNT)).astype("int16")

    coverage, balance = rgb_ring_sector_metrics(edges, annulus, outer, sector_ids)
    inverse_rank, peak_count = radial_peak_metrics(edges, radius_px)

    edge_inner = mask_mean(edges[inner])
    edge_annulus = mask_mean(edges[annulus])
    edge_outer = mask_mean(edges[outer])
    texture_annulus = mask_std(gray[annulus])
    texture_outer = mask_std(gray[outer])
    lum_inner = mask_mean(gray[inner])
    lum_outer = mask_mean(gray[outer])
    green_inner = mask_mean(green[inner])
    green_outer = mask_mean(green[outer])

    return {
        "gray_mean": float(gray.mean()),
        "gray_std": float(gray.std()),
        "gray_entropy": gray_entropy(gray),
        "dark_fraction": float((gray < 0.08).mean()),
        "bright_fraction": float((gray > 0.92).mean()),
        "green_mean": float(green.mean()),
        "excess_green_mean": float(excess_green.mean()),
        "green_std": float(green.std()),
        "edge_global_mean": float(edges.mean()),
        "edge_global_std": float(edges.std()),
        "edge_inner_mean": edge_inner,
        "edge_annulus_mean": edge_annulus,
        "edge_outer_mean": edge_outer,
        "edge_annulus_to_outer_ratio": safe_ratio(edge_annulus, edge_outer),
        "edge_annulus_to_inner_ratio": safe_ratio(edge_annulus, edge_inner),
        "texture_inner_std": mask_std(gray[inner]),
        "texture_annulus_std": texture_annulus,
        "texture_outer_std": texture_outer,
        "texture_annulus_to_outer_ratio": safe_ratio(texture_annulus, texture_outer),
        "luminance_inner_mean": lum_inner,
        "luminance_annulus_mean": mask_mean(gray[annulus]),
        "luminance_outer_mean": lum_outer,
        "luminance_delta_inner_outer": lum_inner - lum_outer,
        "green_delta_inner_outer": green_inner - green_outer,
        "ring_sector_coverage": coverage,
        "ring_sector_balance": balance,
        "radial_peak_inverse_rank": inverse_rank,
        "radial_peak_count": float(peak_count),
    }


def msrm_raster_for(dem_path: Path, scales_m: list[float]):
    """DEM, resolution and |MSRM|, for the centre search."""
    import numpy as np
    import rasterio

    with rasterio.open(dem_path) as src:
        dem = src.read(1).astype("float32")
        if src.nodata is not None:
            dem[dem == src.nodata] = np.nan
        resolution = abs(float(src.res[0]))
    finite = np.isfinite(dem)
    if not finite.all():
        dem = dem.astype("float32", copy=True)
        dem[~finite] = float(np.nanmean(dem)) if finite.any() else 0.0
    _layers, msrm = build_multiscale_relief(dem, resolution, scales_m)
    return dem, resolution, np.abs(msrm)


_SCORE_STATE: dict[str, object] = {}


def _score_init(model: dict, scaler: dict, scales_m: list[float], ring_radii_m: list[float], args_dict: dict) -> None:
    import numpy as np

    _SCORE_STATE["feature_names"] = model["feature_names"]
    _SCORE_STATE["weights"] = np.array(model["weights"], dtype="float64")
    _SCORE_STATE["mean"] = np.array(model["feature_mean"], dtype="float64")
    _SCORE_STATE["std"] = np.array(model["feature_std"], dtype="float64")
    _SCORE_STATE["scaler"] = scaler
    _SCORE_STATE["scales_m"] = scales_m
    _SCORE_STATE["ring_radii_m"] = ring_radii_m
    _SCORE_STATE["args"] = argparse.Namespace(**args_dict)


def _score_one(row: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    args = _SCORE_STATE["args"]
    return score_row(
        row,
        _SCORE_STATE["feature_names"],  # type: ignore[arg-type]
        _SCORE_STATE["weights"],
        _SCORE_STATE["mean"],
        _SCORE_STATE["std"],
        _SCORE_STATE["scaler"],  # type: ignore[arg-type]
        _SCORE_STATE["scales_m"],  # type: ignore[arg-type]
        _SCORE_STATE["ring_radii_m"],  # type: ignore[arg-type]
        args,
    )


def score_row(
    row: dict[str, str],
    feature_names: list[str],
    weights,
    mean,
    std,
    scaler: dict,
    scales_m: list[float],
    ring_radii_m: list[float],
    args: argparse.Namespace,
) -> tuple[dict[str, str], list[str]]:
    """Score one grid cell. Returns (row, count_tags)."""
    import numpy as np

    tags: list[str] = []
    tile_id = row["tile_id"]
    png_path = PROJECT_ROOT / row["target_png_path"]
    dem_path = dem_path_for(args.chip_root, tile_id, args.grid_split)
    result = {
        "tile_id": tile_id,
        "longitude": row["longitude"],
        "latitude": row["latitude"],
        "known_site_name": row.get("known_site_name", ""),
        "known_site_class": row.get("known_site_class", ""),
        "known_site_distance_m": row.get("known_site_distance_m", ""),
        "status": "failed",
        "error": "",
        "probability": "",
        "candidate_class": "",
        "dominant_scale_m": "",
        "best_ring_radius_m": "",
        "dem_prominence_m": "",
        "sea_or_flat": "no",
        "center_offset_m": "",
        "center_offset_x_m": "",
        "center_offset_y_m": "",
    }
    if not png_path.exists():
        result["error"] = "missing_rgb"
        return result, ["missing_rgb"]
    if not dem_path.exists():
        result["error"] = "missing_dem"
        return result, ["missing_dem"]
    try:
        offset_m = (0.0, 0.0)
        if args.center_search_m > 0:
            dem_raster, resolution, msrm_abs = msrm_raster_for(dem_path, scales_m)
            offset_m, _best_radius, _response = search_best_centre(
                dem_raster,
                resolution,
                msrm_abs,
                ring_radii_m,
                args.center_search_m,
                args.center_search_step_m,
            )
        if offset_m == (0.0, 0.0):
            rgb = extract_rgb_features(png_path, args.fixed_radius_m, args.image_size)
        else:
            rgb = rgb_features_at(png_path, args.fixed_radius_m, args.image_size, offset_m)
        relief = relief_features_for(dem_path, args.fixed_radius_m, offset_m)
        # A flat, near-zero DEM is sea or estuary: no landform to rank.
        if relief["_dem_std"] < args.flat_dem_std_m:
            result["sea_or_flat"] = "yes"
            tags.append("sea_or_flat")
        msrm = msrm_features_for(dem_path, scales_m, ring_radii_m, offset_m)
        variants = variant_scores({k: f"{v:.8f}" for k, v in relief.items()}, scaler)
        result["center_offset_m"] = f"{math.hypot(*offset_m):.1f}"
        result["center_offset_x_m"] = f"{offset_m[0]:.1f}"
        result["center_offset_y_m"] = f"{offset_m[1]:.1f}"

        merged: dict[str, float] = {}
        for name in RGB_FEATURE_NAMES:
            merged[f"rgb__{name}"] = float(rgb.get(name, 0.0))
        for name in RELIEF_FEATURE_NAMES:
            merged[f"relief__{name}"] = float(relief.get(name, 0.0))
        for name in VARIANT_NAMES:
            merged[f"relief_variant__{name}"] = float(variants.get(name, 0.0))
        for name in MSRM_FEATURE_NAMES:
            merged[f"msrm__{name}"] = float(msrm.get(name, 0.0))

        vector = np.array([merged.get(name, 0.0) for name in feature_names], dtype="float64")
        safe_std = np.where(std < 1e-9, 1.0, std)
        scaled = (vector - mean) / safe_std
        logit = float(weights[0] + float(np.dot(weights[1:], scaled)))
        probability = 1.0 / (1.0 + math.exp(-max(-60.0, min(60.0, logit))))

        result["probability"] = f"{probability:.8f}"
        result["dominant_scale_m"] = f"{msrm['dominant_scale_m']:.1f}"
        result["best_ring_radius_m"] = f"{msrm['best_ring_radius_m']:.1f}"
        result["dem_prominence_m"] = f"{relief['dem_prominence_m']:.3f}"
        result["status"] = "ok"
        tags.append("ok")
    except Exception as exc:
        result["error"] = str(exc)[:200]
        tags.append("error")
    return result, tags


def score_grid(args: argparse.Namespace) -> tuple[list[dict[str, str]], dict[str, int]]:
    """Score every grid cell, in parallel across cores."""
    import numpy as np

    model = json.loads(args.model.read_text(encoding="utf-8"))
    scaler = fit_variant_scaler(
        [row for row in read_tsv(args.train_relief) if row.get("status") == "ok"]
    )
    scales_m = parse_scale_list(args.scales_m)
    ring_radii_m = parse_scale_list(args.ring_radii_m)

    grid_rows = read_tsv(args.grid_manifest)
    if args.limit:
        grid_rows = grid_rows[: args.limit]
    counts: Counter = Counter()
    out_rows: list[dict[str, str]] = []

    workers = max(1, int(args.score_workers))
    total = len(grid_rows)
    # Paths in args must survive pickling to the workers.
    args_dict = {key: value for key, value in vars(args).items()}

    if workers == 1:
        _score_init(model, scaler, scales_m, ring_radii_m, args_dict)
        for index, row in enumerate(grid_rows, start=1):
            result, tags = _score_one(row)
            out_rows.append(result)
            counts.update(tags)
            if index % args.progress_every == 0 or index == total:
                print(f"scored {index}/{total}", flush=True)
    else:
        with ProcessPoolExecutor(
            max_workers=workers,
            initializer=_score_init,
            initargs=(model, scaler, scales_m, ring_radii_m, args_dict),
        ) as pool:
            done = 0
            for result, tags in pool.map(_score_one, grid_rows, chunksize=8):
                out_rows.append(result)
                counts.update(tags)
                done += 1
                if done % args.progress_every == 0 or done == total:
                    print(f"scored {done}/{total}", flush=True)

    ok_rows = [row for row in out_rows if row["status"] == "ok"]
    ok_rows.sort(key=lambda row: float(row["probability"]), reverse=True)
    for position, row in enumerate(ok_rows, start=1):
        row["rank"] = str(position)
        if row["sea_or_flat"] == "yes":
            row["candidate_class"] = "sea_or_flat_excluded"
        elif row["known_site_class"] == "positive_castro":
            row["candidate_class"] = "known_castro_recovered"
        elif row["known_site_class"]:
            row["candidate_class"] = f"known_{row['known_site_class']}"
        else:
            row["candidate_class"] = "uncatalogued_candidate"
        counts[row["candidate_class"]] += 1
    for row in out_rows:
        row.setdefault("rank", "")
    return ok_rows + [row for row in out_rows if row["status"] != "ok"], counts



def write_geojson(path: Path, rows: list[dict[str, str]], limit: int) -> None:
    features = []
    for row in rows[:limit]:
        if row["status"] != "ok":
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(row["longitude"]), float(row["latitude"])],
                },
                "properties": {key: row.get(key, "") for key in RANK_FIELDS},
            }
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )


def write_report(path: Path, args: argparse.Namespace, rows: list[dict[str, str]], counts: Counter) -> None:
    ok_rows = [row for row in rows if row["status"] == "ok"]
    land_rows = [row for row in ok_rows if row["sea_or_flat"] == "no"]
    recovered = [row for row in land_rows if row["candidate_class"] == "known_castro_recovered"]
    candidates = [row for row in land_rows if row["candidate_class"] == "uncatalogued_candidate"]
    top_candidates = candidates[: args.report_top]

    known_total = sum(1 for row in ok_rows if row["known_site_class"] == "positive_castro")
    recovered_top = [row for row in recovered if int(row["rank"]) <= max(1, len(land_rows) // 10)]

    lines = [
        "# Trasancos inference ranking v1",
        "",
        f"Generated at: `{GENERATED_AT}`",
        f"Grid step: `{args.step_m:.0f} m` · tile side: `{int(TILE_SIDE_M)} m` · bbox: `{args.bbox}`",
        f"Model: `{rel_to_project(args.model)}`",
        "",
        "## What this is",
        "",
        "Every earlier metric ranked catalogued points. This ranks a blind grid",
        "over the comarca, so the model has to commit on ground nobody pre-selected.",
        "A high rank here is a place worth opening in QGIS, nothing more.",
        "",
        "## Coverage",
        "",
        f"- grid cells: `{len(rows)}`",
        f"- scored ok: `{len(ok_rows)}`",
        f"- sea/flat excluded: `{counts.get('sea_or_flat', 0)}`",
        f"- missing RGB: `{counts.get('missing_rgb', 0)}`",
        f"- missing DEM: `{counts.get('missing_dem', 0)}`",
        f"- errors: `{counts.get('error', 0)}`",
        "",
        "## Sanity check: does it find what we already know?",
        "",
        f"- catalogued castros inside the grid: `{known_total}`",
        f"- of those, ranked in the top decile of land cells: `{len(recovered_top)}`",
        "",
        "If the model cannot re-find catalogued castros on a blind grid, its",
        "uncatalogued candidates carry no weight. Read this number first.",
        "",
        "## Candidate classes",
        "",
        "| class | cells |",
        "|---|---:|",
    ]
    for name, count in counts.most_common():
        if name in {"ok", "error", "missing_rgb", "missing_dem", "sea_or_flat"}:
            continue
        lines.append(f"| `{name}` | `{count}` |")

    lines += [
        "",
        f"## Top `{len(top_candidates)}` uncatalogued cells",
        "",
        "Coordinates are rounded here on purpose. Precise positions live in the",
        "TSV/GeoJSON, which stay internal.",
        "",
        "| rank | probability | approx lon | approx lat | dominant scale (m) | best ring (m) | prominence (m) |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in top_candidates:
        lines.append(
            f"| `{row['rank']}` | `{row['probability']}` | `{float(row['longitude']):.2f}` | "
            f"`{float(row['latitude']):.2f}` | `{row['dominant_scale_m']}` | "
            f"`{row['best_ring_radius_m']}` | `{row['dem_prominence_m']}` |"
        )

    lines += [
        "",
        "## Cautions",
        "",
        "- Weak labels trained this model. A high score is a shape prior, not a site.",
        "- The dominant false positive in every evaluation so far is the mámoa;",
        "  expect burial mounds near the top and check `negative_type` history.",
        "- Nothing here is a discovery claim. No precise coordinate of an",
        "  uncatalogued cell goes into any public artefact, repo README, web map",
        "  or wiki page before archaeological review.",
        "- Sea and estuary cells are flagged, not deleted, so the exclusion stays",
        "  auditable.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_exporters(args: argparse.Namespace, grid_path: Path) -> None:
    geo_python = sys.executable
    rgb_cmd = [
        geo_python,
        str(PROJECT_ROOT / "scripts/export_weak_label_chips.py"),
        "--input", str(grid_path),
        "--out-manifest", str(args.out_dir / "trasancos_grid_rgb_manifest.tsv"),
        "--report", str(PROJECT_ROOT / "reports/trasancos_grid_rgb_export.md"),
        "--workers", str(args.workers),
    ]
    dem_cmd = [
        geo_python,
        str(PROJECT_ROOT / "scripts/export_weak_label_relief_wcs.py"),
        "--input", str(grid_path),
        "--out-manifest", str(args.out_dir / "trasancos_grid_dem_manifest.tsv"),
        "--report", str(PROJECT_ROOT / "reports/trasancos_grid_dem_export.md"),
        "--workers", str(args.workers),
    ]
    for label, cmd in (("rgb", rgb_cmd), ("dem", dem_cmd)):
        print(f"[fetch:{label}] {' '.join(cmd[:4])} ...", flush=True)
        subprocess.run(cmd, check=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=["grid", "fetch", "score", "all"], default="all")
    parser.add_argument("--bbox", default=DEFAULT_BBOX)
    parser.add_argument("--step-m", type=float, default=512.0)
    parser.add_argument("--tile-prefix", default="tr-grid-v1")
    parser.add_argument("--grid-split", default="trasancos_grid")
    parser.add_argument("--known-match-m", type=float, default=256.0)
    parser.add_argument("--master", type=Path, default=DEFAULT_MASTER)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--train-relief", type=Path, default=DEFAULT_TRAIN_RELIEF)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--chip-root", type=Path, default=DEFAULT_CHIP_ROOT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--grid-manifest", type=Path, default=None)
    parser.add_argument("--scales-m", default=DEFAULT_SCALES_M)
    parser.add_argument("--ring-radii-m", default=DEFAULT_RING_RADII_M)
    parser.add_argument("--fixed-radius-m", type=float, default=120.0)
    parser.add_argument("--image-size", type=int, default=256)
    parser.add_argument("--flat-dem-std-m", type=float, default=1.5)
    parser.add_argument(
        "--center-search-m",
        type=float,
        default=0.0,
        help="Search radius for the best ring centre inside each cell. 0 keeps the chip centre.",
    )
    parser.add_argument("--center-search-step-m", type=float, default=32.0)
    parser.add_argument(
        "--score-workers",
        type=int,
        default=max(1, (os.cpu_count() or 2) - 1),
        help="Processes used to score cells. Scoring is CPU-bound and embarrassingly parallel.",
    )
    parser.add_argument("--progress-every", type=int, default=100)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--report-top", type=int, default=40)
    parser.add_argument("--geojson-top", type=int, default=400)
    return parser.parse_args()


def resolve_args(args: argparse.Namespace) -> argparse.Namespace:
    for attr in ("master", "model", "train_relief", "out_dir", "chip_root", "report"):
        value = getattr(args, attr)
        setattr(args, attr, value if value.is_absolute() else PROJECT_ROOT / value)
    if args.grid_manifest is None:
        args.grid_manifest = args.out_dir / "trasancos_grid_manifest.tsv"
    elif not args.grid_manifest.is_absolute():
        args.grid_manifest = PROJECT_ROOT / args.grid_manifest
    return args


def main() -> None:
    args = resolve_args(parse_args())
    args.out_dir.mkdir(parents=True, exist_ok=True)

    if args.stage in {"grid", "all"}:
        rows = build_grid(args)
        if args.limit:
            rows = rows[: args.limit]
        rows = add_dem_targets(rows, args.chip_root, args.grid_split)
        write_tsv(args.grid_manifest, rows, GRID_FIELDS + ["target_dem_path"])
        known = sum(1 for row in rows if row["known_site_id"])
        print(f"grid_cells={len(rows)} known_matches={known} manifest={rel_to_project(args.grid_manifest)}")

    if args.stage in {"fetch", "all"}:
        run_exporters(args, args.grid_manifest)

    if args.stage in {"score", "all"}:
        rows, counts = score_grid(args)
        ranked_path = args.out_dir / "trasancos_inference_ranking.tsv"
        write_tsv(ranked_path, rows, RANK_FIELDS)
        geojson_path = args.out_dir / "trasancos_inference_ranking.geojson"
        write_geojson(geojson_path, rows, args.geojson_top)
        write_report(args.report, args, rows, counts)
        print(f"scored_ok={counts.get('ok', 0)} sea_or_flat={counts.get('sea_or_flat', 0)}")
        print(f"uncatalogued_candidates={counts.get('uncatalogued_candidate', 0)}")
        print(f"known_castro_recovered={counts.get('known_castro_recovered', 0)}")
        print(f"ranking={rel_to_project(ranked_path)}")
        print(f"geojson={rel_to_project(geojson_path)}")
        print(f"report={rel_to_project(args.report)}")


if __name__ == "__main__":
    main()
