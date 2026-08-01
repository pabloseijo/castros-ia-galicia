#!/usr/bin/env python3
"""Build rough, non-final relief boundary proposals for P0 castro positives."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from evaluate_weak_label_relief_baseline import derive_products
from train_weak_label_rgb_baseline import parse_float, read_tsv, rel_to_project


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DECISION_SEED = PROJECT_ROOT / "data/weak-label-error-review-workspace-v1/p0_decision_seed.tsv"
DEFAULT_RELIEF_MANIFEST = PROJECT_ROOT / "data/weak-label-relief-v1/weak_label_relief_wcs_holdouts.tsv"
DEFAULT_OUT_TSV = PROJECT_ROOT / "data/weak-label-error-review-workspace-v1/p0_positive_boundary_proposals.tsv"
DEFAULT_OUT_GEOJSON = PROJECT_ROOT / "data/weak-label-error-review-workspace-v1/p0_positive_boundary_proposals.geojson"
DEFAULT_OUT_GPKG = PROJECT_ROOT / "data/weak-label-error-review-workspace-v1/p0_positive_boundary_proposals_v1.gpkg"
DEFAULT_REPORT = PROJECT_ROOT / "reports/weak_label_p0_positive_boundary_proposals_v1.md"

GENERATED_AT = "2026-08-01T00:00:00Z"
SEARCH_RADIUS_M = 120.0
MIN_AREA_M2 = 800.0
MAX_AREA_M2 = 60000.0

PROPOSAL_FIELDS = [
    "proposal_id",
    "decision_seed_id",
    "dossier_order",
    "sample_id",
    "name",
    "municipality",
    "parish",
    "final_split",
    "morphology_proxy",
    "proposal_status",
    "accepted_label_status",
    "can_enter_training_now",
    "needs_review",
    "method",
    "proposal_area_m2",
    "search_radius_m",
    "dem_path",
    "dem_status",
    "resolution_m",
    "mask_pixels",
    "geometry_note",
    "visual_card",
    "rationale",
]


def require_runtime() -> None:
    missing = []
    for module in ("geopandas", "numpy", "rasterio", "shapely", "skimage"):
        try:
            __import__(module)
        except Exception:
            missing.append(module)
    if missing:
        raise SystemExit(f"Missing Python modules: {', '.join(missing)}")


def write_tsv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            dialect="excel-tab",
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def project_path(raw_path: str) -> Path:
    path = Path(raw_path)
    return path if path.is_absolute() else PROJECT_ROOT / path


def by_sample(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    return {row["sample_id"]: row for row in rows}


def center_masks(shape: tuple[int, int], resolution: float):
    import numpy as np

    height, width = shape
    yy, xx = np.indices((height, width))
    cx = (width - 1) / 2.0
    cy = (height - 1) / 2.0
    distance_m = np.hypot(xx - cx, yy - cy) * resolution
    search = distance_m <= SEARCH_RADIUS_M
    core = distance_m <= 45.0
    inner = distance_m <= 80.0
    return search, core, inner


def adaptive_mask(dem, slope, lrm, morphology: str, resolution: float):
    import numpy as np
    from skimage import measure, morphology as sk_morph

    search, core, inner = center_masks(dem.shape, resolution)
    if not search.any():
        return search, "empty_search_mask"

    dem_values = dem[search]
    slope_values = slope[search]
    lrm_abs = np.abs(lrm)
    lrm_values = lrm_abs[search]

    if "promontory" in morphology:
        slope_cut = float(np.nanpercentile(slope_values, 62))
        lrm_cut = float(np.nanpercentile(lrm_values, 62))
        raw = search & ((slope >= slope_cut) | (lrm_abs >= lrm_cut) | ((dem >= np.nanpercentile(dem_values, 55)) & inner))
        method = "promontory_slope_lrm_component"
    elif "hilltop" in morphology:
        dem_cut = float(np.nanpercentile(dem_values, 58))
        lrm_cut = float(np.nanpercentile(lrm_values, 55))
        raw = search & ((dem >= dem_cut) | (lrm >= np.nanpercentile(lrm[search], 55)) | (lrm_abs >= lrm_cut))
        method = "hilltop_dem_lrm_component"
    else:
        slope_cut = float(np.nanpercentile(slope_values, 58))
        lrm_cut = float(np.nanpercentile(lrm_values, 58))
        raw = search & ((slope >= slope_cut) | (lrm_abs >= lrm_cut))
        method = "generic_relief_component"

    raw = sk_morph.binary_closing(raw, sk_morph.disk(2))
    raw = sk_morph.remove_small_objects(raw.astype(bool), min_size=8)
    labels = measure.label(raw, connectivity=2)
    if labels.max() == 0:
        return core, f"{method}_fallback_core"

    core_labels = labels[core & (labels > 0)]
    if core_labels.size:
        values, counts = np.unique(core_labels, return_counts=True)
        keep = int(values[counts.argmax()])
    else:
        values, counts = np.unique(labels[labels > 0], return_counts=True)
        keep = int(values[counts.argmax()])
    mask = labels == keep
    mask = sk_morph.binary_closing(mask, sk_morph.disk(2))
    return mask, method


def mask_to_polygon(mask, transform, crs):
    import geopandas as gpd
    import numpy as np
    from rasterio import features
    from shapely.geometry import shape
    from shapely.ops import unary_union

    geometries = [
        shape(geom)
        for geom, value in features.shapes(mask.astype("uint8"), mask=mask.astype(bool), transform=transform)
        if value == 1
    ]
    if not geometries:
        return None
    geom = unary_union(geometries).buffer(0)
    if geom.is_empty:
        return None
    return gpd.GeoSeries([geom], crs=crs)


def search_buffer_polygon(src, search_radius_m: float):
    import geopandas as gpd
    from shapely.geometry import Point

    cx = (src.bounds.left + src.bounds.right) / 2.0
    cy = (src.bounds.bottom + src.bounds.top) / 2.0
    return gpd.GeoSeries([Point(cx, cy).buffer(search_radius_m)], crs=src.crs)


def proposal_for_row(row: dict[str, str], relief_row: dict[str, str] | None):
    import rasterio

    if not relief_row or relief_row.get("dem_status") != "valid":
        return None, {
            "method": "missing_dem",
            "proposal_area_m2": "0",
            "dem_path": "",
            "dem_status": (relief_row or {}).get("dem_status", "missing"),
            "resolution_m": "",
            "mask_pixels": "0",
            "geometry_note": "No DEM available; no proposal geometry generated.",
        }

    dem_path = project_path(relief_row["target_dem_path"])
    with rasterio.open(dem_path) as src:
        dem = src.read(1).astype("float32")
        if src.nodata is not None:
            dem[dem == src.nodata] = float("nan")
        resolution = abs(float(src.res[0]))
        _dem, slope, _hillshade, lrm = derive_products(dem, resolution, 50.0)
        mask, method = adaptive_mask(_dem, slope, lrm, row.get("morphology_proxy", ""), resolution)
        series = mask_to_polygon(mask, src.transform, src.crs)
        if series is None:
            series = search_buffer_polygon(src, min(80.0, SEARCH_RADIUS_M))
            method = f"{method}_fallback_buffer"
        search = search_buffer_polygon(src, SEARCH_RADIUS_M)
        geom = series.iloc[0].intersection(search.iloc[0]).buffer(0)
        area_m2 = float(geom.area)
        if area_m2 < MIN_AREA_M2 or area_m2 > MAX_AREA_M2 or geom.is_empty:
            geom = search_buffer_polygon(src, 80.0).iloc[0]
            area_m2 = float(geom.area)
            method = f"{method}_area_fallback_buffer"
        note = "Rough relief-derived proposal; use only as a tracing aid, not as an accepted boundary."
        return geom, {
            "method": method,
            "proposal_area_m2": f"{area_m2:.1f}",
            "dem_path": rel_to_project(dem_path),
            "dem_status": relief_row.get("dem_status", ""),
            "resolution_m": f"{resolution:.2f}",
            "mask_pixels": str(int(mask.sum())),
            "geometry_note": note,
        }


def build_proposals(seed_rows: list[dict[str, str]], relief_rows: dict[str, dict[str, str]]):
    import geopandas as gpd

    out_rows = []
    geometries = []
    for idx, row in enumerate([item for item in seed_rows if item.get("suggested_taxonomy") == "castro"], start=1):
        geom, info = proposal_for_row(row, relief_rows.get(row["sample_id"]))
        proposal = {field: "" for field in PROPOSAL_FIELDS}
        proposal.update(row)
        proposal.update(info)
        proposal["proposal_id"] = f"p0-boundary-proposal-{idx:03d}"
        proposal["proposal_status"] = "rough_relief_proposal_not_label"
        proposal["accepted_label_status"] = "not_accepted"
        proposal["can_enter_training_now"] = "no"
        proposal["needs_review"] = "yes"
        proposal["search_radius_m"] = f"{SEARCH_RADIUS_M:.0f}"
        proposal["rationale"] = (
            "Autonomous relief proposal for QGIS tracing. The geometry may approximate a visible terrain unit, "
            "but it is not a validated castro boundary and must not enter training until reviewed."
        )
        if geom is not None:
            out_rows.append(proposal)
            geometries.append(geom)
    gdf = gpd.GeoDataFrame(out_rows, geometry=geometries, crs="EPSG:25830").to_crs("EPSG:4326")
    return out_rows, gdf


def write_geodata(gdf, out_geojson: Path, out_gpkg: Path) -> None:
    out_geojson.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(out_geojson, driver="GeoJSON")
    if out_gpkg.exists():
        out_gpkg.unlink()
    gdf.to_file(out_gpkg, layer="p0_positive_boundary_proposals", driver="GPKG")


def write_report(path: Path, rows: list[dict[str, str]], out_tsv: Path, out_geojson: Path, out_gpkg: Path) -> None:
    lines = [
        "# Weak-label P0 positive boundary proposals v1",
        "",
        f"Generated: {GENERATED_AT}",
        "",
        "## What This Is",
        "",
        "Rough relief-derived geometry proposals for the six P0 positive castros.",
        "These are QGIS tracing aids, not accepted archaeological boundaries and not training labels.",
        "Every row keeps `proposal_status=rough_relief_proposal_not_label`, `accepted_label_status=not_accepted` and `can_enter_training_now=no`.",
        "",
        "## Outputs",
        "",
        f"- TSV: `{rel_to_project(out_tsv)}`",
        f"- GeoJSON: `{rel_to_project(out_geojson)}`",
        f"- GeoPackage: `{rel_to_project(out_gpkg)}`",
        f"- GPKG layer: `p0_positive_boundary_proposals`",
        "",
        "## Counts",
        "",
        f"- proposals: `{len(rows)}`",
        "",
        "## Proposal Table",
        "",
        "| Order | Name | Method | Area m2 | Card |",
        "|---:|---|---|---:|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['dossier_order']} | `{row['name']}` | `{row['method']}` | {row['proposal_area_m2']} | `{row['visual_card']}` |"
        )
    lines.extend(
        [
            "",
            "## Use In QGIS",
            "",
            "1. Open this GPKG together with `p0_decision_seed_v1.gpkg` and the visual dossier.",
            "2. Treat every polygon as a sketch/tracing aid.",
            "3. If a boundary is defensible, redraw it into the editable annotation workspace; do not copy it blindly.",
            "4. If the proposal follows a cliff, beach, vegetation edge or terrain artifact instead of a castro boundary, mark the case as `needs_followup`.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decision-seed", type=Path, default=DEFAULT_DECISION_SEED)
    parser.add_argument("--relief-manifest", type=Path, default=DEFAULT_RELIEF_MANIFEST)
    parser.add_argument("--out-tsv", type=Path, default=DEFAULT_OUT_TSV)
    parser.add_argument("--out-geojson", type=Path, default=DEFAULT_OUT_GEOJSON)
    parser.add_argument("--out-gpkg", type=Path, default=DEFAULT_OUT_GPKG)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_ROOT / path


def main() -> None:
    require_runtime()
    args = parse_args()
    seed_path = resolve_path(args.decision_seed)
    relief_path = resolve_path(args.relief_manifest)
    out_tsv = resolve_path(args.out_tsv)
    out_geojson = resolve_path(args.out_geojson)
    out_gpkg = resolve_path(args.out_gpkg)
    report = resolve_path(args.report)

    rows, gdf = build_proposals(read_tsv(seed_path), by_sample(read_tsv(relief_path)))
    write_tsv(out_tsv, rows, PROPOSAL_FIELDS)
    write_geodata(gdf, out_geojson, out_gpkg)
    write_report(report, rows, out_tsv, out_geojson, out_gpkg)

    print(f"boundary_proposals={len(rows)}")
    print(f"wrote={rel_to_project(out_tsv)}")
    print(f"geojson={rel_to_project(out_geojson)}")
    print(f"gpkg={rel_to_project(out_gpkg)}")
    print(f"report={rel_to_project(report)}")


if __name__ == "__main__":
    main()
