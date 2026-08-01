#!/usr/bin/env python3
"""Evaluate radial relief rings around the Viladonga pilot shape."""

from __future__ import annotations

import argparse
import csv
import math
import statistics
from pathlib import Path

from evaluate_viladonga_relief_shape_baseline import (
    DEFAULT_CHIP_MANIFEST,
    DEFAULT_RELIEF_MANIFEST,
    PROJECT_ROOT,
    load_mask,
    load_relief_products,
    mean_or_zero,
    project_path,
    read_tsv,
    relief_pixel_centers,
    rel_to_project,
    sobel_edges,
    template_on_relief_grid,
)


DEFAULT_SUMMARY = PROJECT_ROOT / "data/viladonga-pilot/radial_relief_summary.tsv"
DEFAULT_RINGS = PROJECT_ROOT / "data/viladonga-pilot/radial_relief_rings.tsv"
DEFAULT_REPORT = PROJECT_ROOT / "reports/viladonga_radial_relief_profile.md"
GENERATED_AT = "2026-08-01"

RING_SPECS = [
    ("core", 0.00, 0.60),
    ("inner_plateau", 0.60, 0.85),
    ("expected_wall_inner", 0.85, 1.05),
    ("expected_wall_outer", 1.05, 1.30),
    ("near_exterior", 1.30, 1.70),
    ("far_context", 1.70, 2.50),
]

EDGE_RINGS = {"expected_wall_inner", "expected_wall_outer"}
CONTEXT_RINGS = {"near_exterior", "far_context"}

SUMMARY_FIELDS = [
    "chip_id",
    "label_class",
    "label_kind",
    "template_source",
    "template_pixels",
    "centroid_row",
    "centroid_col",
    "equivalent_radius_px",
    "equivalent_radius_m",
    "edge_slope_ring",
    "edge_slope_mean",
    "context_slope_mean",
    "edge_slope_ratio",
    "edge_lrm_abs_ring",
    "edge_lrm_abs_mean",
    "context_lrm_abs_mean",
    "edge_lrm_abs_ratio",
    "edge_hillshade_ring",
    "edge_hillshade_mean",
    "context_hillshade_mean",
    "edge_hillshade_ratio",
    "core_dem_mean",
    "far_context_dem_mean",
    "dem_prominence_m",
    "edge_talud_score",
    "edge_talud_rank_desc",
    "topographic_prominence_rank_desc",
    "status",
    "error",
]

RING_FIELDS = [
    "chip_id",
    "label_class",
    "ring",
    "r_min",
    "r_max",
    "pixels",
    "dem_mean",
    "slope_mean",
    "lrm_mean",
    "lrm_abs_mean",
    "hillshade_edge_mean",
]


def require_runtime() -> None:
    missing = []
    for module in ("numpy", "PIL", "pyproj", "rasterio"):
        try:
            __import__(module)
        except Exception:
            missing.append(module)
    if missing:
        raise SystemExit(f"Missing Python modules: {', '.join(missing)}")


def write_tsv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, dialect="excel-tab")
        writer.writeheader()
        writer.writerows(rows)


def finite_values(values):
    import numpy as np

    return values[np.isfinite(values)]


def mean(values) -> float:
    return mean_or_zero(finite_values(values))


def template_centroid_and_radius(template):
    import numpy as np

    rows, cols = np.nonzero(template)
    if rows.size == 0:
        raise ValueError("empty template")
    centroid_row = float(rows.mean())
    centroid_col = float(cols.mean())
    equivalent_radius_px = math.sqrt(float(rows.size) / math.pi)
    return centroid_row, centroid_col, equivalent_radius_px


def radial_rings(template, finite_mask):
    import numpy as np

    centroid_row, centroid_col, radius_px = template_centroid_and_radius(template)
    rows, cols = np.indices(template.shape, dtype="float64")
    norm_radius = np.hypot(rows - centroid_row, cols - centroid_col) / radius_px
    rings = {
        name: (norm_radius >= r_min) & (norm_radius < r_max) & finite_mask
        for name, r_min, r_max in RING_SPECS
    }
    return rings, centroid_row, centroid_col, radius_px


def best_ring(ring_stats: dict[str, dict[str, float]], names: set[str], metric: str) -> tuple[str, float]:
    candidates = [(name, ring_stats[name][metric]) for name in names if name in ring_stats and ring_stats[name]["pixels"] > 0]
    if not candidates:
        return "", 0.0
    return max(candidates, key=lambda item: item[1])


def ring_average(ring_stats: dict[str, dict[str, float]], names: set[str], metric: str) -> float:
    values = [ring_stats[name][metric] for name in names if name in ring_stats and ring_stats[name]["pixels"] > 0]
    return float(sum(values) / len(values)) if values else 0.0


def robust_scale(values: list[float]) -> float:
    if len(values) < 2:
        return 1.0
    median = statistics.median(values)
    mad = statistics.median(abs(value - median) for value in values)
    if mad > 0:
        return 1.4826 * mad
    stdev = statistics.pstdev(values)
    return stdev if stdev > 0 else 1.0


def evaluate_chip(chip_row: dict[str, str], template, products, pixel_size_m: float) -> tuple[dict[str, str], list[dict[str, str]]]:
    import numpy as np

    summary = {field: "" for field in SUMMARY_FIELDS}
    summary.update(
        {
            "chip_id": chip_row.get("chip_id", ""),
            "label_class": chip_row.get("label_class", ""),
            "label_kind": chip_row.get("label_kind", ""),
            "template_source": "actual_positive_mask" if chip_row.get("label_class") == "1" else "centered_positive_template",
        }
    )
    finite_mask = (
        np.isfinite(products["dem"]["array"])
        & np.isfinite(products["slope_degrees"]["array"])
        & np.isfinite(products["lrm"]["array"])
        & np.isfinite(products["hillshade_315_45"]["array"])
    )
    template = template & finite_mask
    if int(template.sum()) < 10:
        summary["status"] = "failed"
        summary["error"] = "template_not_covered_by_relief_grid"
        return summary, []

    try:
        rings, centroid_row, centroid_col, radius_px = radial_rings(template, finite_mask)
    except Exception as exc:
        summary["status"] = "failed"
        summary["error"] = str(exc)
        return summary, []

    dem = products["dem"]["array"]
    slope = products["slope_degrees"]["array"]
    lrm = products["lrm"]["array"]
    hillshade_edge = sobel_edges(products["hillshade_315_45"]["array"])
    ring_rows: list[dict[str, str]] = []
    ring_stats: dict[str, dict[str, float]] = {}

    for name, r_min, r_max in RING_SPECS:
        mask = rings[name]
        pixels = int(mask.sum())
        stats = {
            "pixels": float(pixels),
            "dem_mean": mean(dem[mask]),
            "slope_mean": mean(slope[mask]),
            "lrm_mean": mean(lrm[mask]),
            "lrm_abs_mean": mean(np.abs(lrm[mask])),
            "hillshade_edge_mean": mean(hillshade_edge[mask]),
        }
        ring_stats[name] = stats
        ring_rows.append(
            {
                "chip_id": chip_row.get("chip_id", ""),
                "label_class": chip_row.get("label_class", ""),
                "ring": name,
                "r_min": f"{r_min:.2f}",
                "r_max": f"{r_max:.2f}",
                "pixels": str(pixels),
                "dem_mean": f"{stats['dem_mean']:.6f}",
                "slope_mean": f"{stats['slope_mean']:.6f}",
                "lrm_mean": f"{stats['lrm_mean']:.6f}",
                "lrm_abs_mean": f"{stats['lrm_abs_mean']:.6f}",
                "hillshade_edge_mean": f"{stats['hillshade_edge_mean']:.6f}",
            }
        )

    edge_slope_ring, edge_slope = best_ring(ring_stats, EDGE_RINGS, "slope_mean")
    edge_lrm_ring, edge_lrm = best_ring(ring_stats, EDGE_RINGS, "lrm_abs_mean")
    edge_hillshade_ring, edge_hillshade = best_ring(ring_stats, EDGE_RINGS, "hillshade_edge_mean")
    context_slope = ring_average(ring_stats, CONTEXT_RINGS, "slope_mean")
    context_lrm = ring_average(ring_stats, CONTEXT_RINGS, "lrm_abs_mean")
    context_hillshade = ring_average(ring_stats, CONTEXT_RINGS, "hillshade_edge_mean")
    core_dem = ring_stats["core"]["dem_mean"]
    far_context_dem = ring_stats["far_context"]["dem_mean"]
    dem_prominence = core_dem - far_context_dem

    summary.update(
        {
            "template_pixels": str(int(template.sum())),
            "centroid_row": f"{centroid_row:.2f}",
            "centroid_col": f"{centroid_col:.2f}",
            "equivalent_radius_px": f"{radius_px:.2f}",
            "equivalent_radius_m": f"{radius_px * pixel_size_m:.2f}",
            "edge_slope_ring": edge_slope_ring,
            "edge_slope_mean": f"{edge_slope:.6f}",
            "context_slope_mean": f"{context_slope:.6f}",
            "edge_slope_ratio": f"{(edge_slope / context_slope) if context_slope else 0.0:.6f}",
            "edge_lrm_abs_ring": edge_lrm_ring,
            "edge_lrm_abs_mean": f"{edge_lrm:.6f}",
            "context_lrm_abs_mean": f"{context_lrm:.6f}",
            "edge_lrm_abs_ratio": f"{(edge_lrm / context_lrm) if context_lrm else 0.0:.6f}",
            "edge_hillshade_ring": edge_hillshade_ring,
            "edge_hillshade_mean": f"{edge_hillshade:.6f}",
            "context_hillshade_mean": f"{context_hillshade:.6f}",
            "edge_hillshade_ratio": f"{(edge_hillshade / context_hillshade) if context_hillshade else 0.0:.6f}",
            "core_dem_mean": f"{core_dem:.6f}",
            "far_context_dem_mean": f"{far_context_dem:.6f}",
            "dem_prominence_m": f"{dem_prominence:.6f}",
            "status": "ok",
        }
    )
    return summary, ring_rows


def add_scores(summary_rows: list[dict[str, str]]) -> None:
    metrics = ["edge_slope_ratio", "edge_lrm_abs_ratio", "edge_hillshade_ratio"]
    ok_rows = [row for row in summary_rows if row["status"] == "ok"]
    negatives = [row for row in ok_rows if row.get("label_class") == "0"]
    centers: dict[str, float] = {}
    scales: dict[str, float] = {}
    for metric in metrics:
        values = [float(row[metric]) for row in negatives]
        centers[metric] = statistics.median(values) if values else 0.0
        scales[metric] = robust_scale(values)
    for row in ok_rows:
        score = 0.0
        for metric in metrics:
            contribution = (float(row[metric]) - centers[metric]) / scales[metric]
            score += max(-5.0, min(5.0, contribution))
        row["edge_talud_score"] = f"{score:.6f}"
    edge_ranked = sorted(ok_rows, key=lambda item: float(item["edge_talud_score"]), reverse=True)
    for rank, row in enumerate(edge_ranked, start=1):
        row["edge_talud_rank_desc"] = str(rank)
    topo_ranked = sorted(ok_rows, key=lambda item: float(item["dem_prominence_m"]), reverse=True)
    for rank, row in enumerate(topo_ranked, start=1):
        row["topographic_prominence_rank_desc"] = str(rank)


def classify_signal(summary_rows: list[dict[str, str]]) -> str:
    ok_rows = [row for row in summary_rows if row["status"] == "ok"]
    positive = next((row for row in ok_rows if row.get("label_class") == "1"), None)
    if not positive or len(ok_rows) < 3:
        return "blocked"
    edge_rank = int(positive["edge_talud_rank_desc"])
    topo_rank = int(positive["topographic_prominence_rank_desc"])
    if edge_rank == 1 and topo_rank == 1:
        return "radial_edge_and_topography_signal_present"
    if edge_rank == 1:
        return "radial_edge_signal_present"
    if edge_rank <= 3:
        return "radial_edge_signal_ambiguous"
    if topo_rank == 1:
        return "topographic_signal_without_clean_radial_edge"
    return "radial_edge_signal_weak"


def write_report(
    path: Path,
    summary_rows: list[dict[str, str]],
    ring_rows: list[dict[str, str]],
    chip_manifest: Path,
    relief_manifest: Path,
    summary_path: Path,
    rings_path: Path,
) -> None:
    ok_rows = [row for row in summary_rows if row["status"] == "ok"]
    failed_rows = [row for row in summary_rows if row["status"] != "ok"]
    positive = next((row for row in ok_rows if row.get("label_class") == "1"), {})
    signal = classify_signal(summary_rows)
    edge_top = sorted(ok_rows, key=lambda item: float(item["edge_talud_score"]), reverse=True)[:5]
    topo_top = sorted(ok_rows, key=lambda item: float(item["dem_prominence_m"]), reverse=True)[:5]
    positive_rings = [row for row in ring_rows if row["chip_id"] == positive.get("chip_id")]

    lines = [
        "# Viladonga radial relief profile",
        "",
        f"Generated: {GENERATED_AT}",
        "",
        f"- Chip manifest: `{rel_to_project(chip_manifest)}`",
        f"- Relief manifest: `{rel_to_project(relief_manifest)}`",
        f"- Summary TSV: `{rel_to_project(summary_path)}`",
        f"- Rings TSV: `{rel_to_project(rings_path)}`",
        "- Baseline: `normalized_radial_rings_on_relief_grid`",
        f"- Rows checked: {len(summary_rows)}",
        f"- OK rows: {len(ok_rows)}",
        f"- Failed rows: {len(failed_rows)}",
        f"- Signal status: `{signal}`",
        "",
        "## Positive Summary",
        "",
    ]
    if positive:
        lines.extend(
            [
                f"- Chip: `{positive['chip_id']}`",
                f"- Edge/talud score: {positive['edge_talud_score']}",
                f"- Edge/talud rank: {positive['edge_talud_rank_desc']} of {len(ok_rows)}",
                f"- Topographic prominence rank: {positive['topographic_prominence_rank_desc']} of {len(ok_rows)}",
                f"- Edge slope ring: `{positive['edge_slope_ring']}` ({positive['edge_slope_mean']} vs context {positive['context_slope_mean']}, ratio {positive['edge_slope_ratio']})",
                f"- Edge LRM ring: `{positive['edge_lrm_abs_ring']}` ({positive['edge_lrm_abs_mean']} vs context {positive['context_lrm_abs_mean']}, ratio {positive['edge_lrm_abs_ratio']})",
                f"- Edge hillshade ring: `{positive['edge_hillshade_ring']}` ({positive['edge_hillshade_mean']} vs context {positive['context_hillshade_mean']}, ratio {positive['edge_hillshade_ratio']})",
                f"- DEM prominence core-vs-far-context: {positive['dem_prominence_m']} m",
                f"- Equivalent radius: {positive['equivalent_radius_m']} m",
            ]
        )
    else:
        lines.append("- none")

    lines.extend(["", "## Positive Rings", ""])
    lines.append("| Ring | Pixels | DEM | Slope | LRM abs | Hillshade edge |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for row in positive_rings:
        lines.append(
            f"| `{row['ring']}` | {row['pixels']} | {row['dem_mean']} | {row['slope_mean']} | {row['lrm_abs_mean']} | {row['hillshade_edge_mean']} |"
        )

    lines.extend(["", "## Edge/Talud Ranking", ""])
    lines.append("| Rank | Chip | Class | Score | Slope ratio | LRM abs ratio | Hillshade ratio |")
    lines.append("|---:|---|---:|---:|---:|---:|---:|")
    for row in edge_top:
        lines.append(
            f"| {row['edge_talud_rank_desc']} | `{row['chip_id']}` | {row['label_class']} | {row['edge_talud_score']} | {row['edge_slope_ratio']} | {row['edge_lrm_abs_ratio']} | {row['edge_hillshade_ratio']} |"
        )

    lines.extend(["", "## Topographic Prominence Ranking", ""])
    lines.append("| Rank | Chip | Class | DEM prominence m |")
    lines.append("|---:|---|---:|---:|")
    for row in topo_top:
        lines.append(
            f"| {row['topographic_prominence_rank_desc']} | `{row['chip_id']}` | {row['label_class']} | {row['dem_prominence_m']} |"
        )

    lines.extend(["", "## Interpretation", ""])
    if signal == "radial_edge_and_topography_signal_present":
        lines.append(
            "The known castro ranks first both in topographic prominence and in the radial edge/talud score. This is the strongest current evidence that the relief signal is not only generic elevation: there is also ring-local contrast around the expected boundary."
        )
    elif signal == "radial_edge_signal_present":
        lines.append(
            "The known castro ranks first in radial edge/talud score even if it is not the strongest topographic high. This is a useful wall/edge-oriented signal."
        )
    elif signal == "radial_edge_signal_ambiguous":
        lines.append(
            "The known castro is near the top but not first in edge/talud score. The profile is suggestive but should not be treated as a clean wall/foso signal."
        )
    elif signal == "topographic_signal_without_clean_radial_edge":
        lines.append(
            "The known castro ranks first as a topographic high but not as a radial edge/talud feature. This supports hillfort siting, not yet wall/foso detection."
        )
    else:
        lines.append("The radial profile does not isolate a strong edge/talud signal in this coarse MDT5 test.")
    lines.extend(
        [
            "",
            "This is still a controlled smoke test over a 5 m MDT WCS product. The result should guide the next measurement, not serve as a claim of automatic archaeological detection. Fine LiDAR and more known castros are still required.",
        ]
    )
    if failed_rows:
        lines.extend(["", "## Errors", ""])
        for row in failed_rows:
            lines.append(f"- `{row['chip_id']}`: {row['error']}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate normalized radial relief rings for Viladonga.")
    parser.add_argument("--chip-manifest", type=Path, default=DEFAULT_CHIP_MANIFEST)
    parser.add_argument("--relief-manifest", type=Path, default=DEFAULT_RELIEF_MANIFEST)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--rings", type=Path, default=DEFAULT_RINGS)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def main() -> int:
    require_runtime()
    args = parse_args()
    chip_manifest = args.chip_manifest if args.chip_manifest.is_absolute() else PROJECT_ROOT / args.chip_manifest
    relief_manifest = args.relief_manifest if args.relief_manifest.is_absolute() else PROJECT_ROOT / args.relief_manifest
    summary_path = args.summary if args.summary.is_absolute() else PROJECT_ROOT / args.summary
    rings_path = args.rings if args.rings.is_absolute() else PROJECT_ROOT / args.rings
    report_path = args.report if args.report.is_absolute() else PROJECT_ROOT / args.report
    if not chip_manifest.exists():
        raise SystemExit(f"Missing chip manifest: {chip_manifest}")
    if not relief_manifest.exists():
        raise SystemExit(f"Missing relief manifest: {relief_manifest}")

    import numpy as np
    from pyproj import Transformer

    chip_rows = read_tsv(chip_manifest)
    positive_row = next((row for row in chip_rows if row.get("label_class") == "1"), None)
    if not positive_row:
        raise SystemExit("Missing positive row in chip manifest")
    positive_template = load_mask(project_path(positive_row["mask_path"]))
    products = load_relief_products(relief_manifest)
    dem_product = products["dem"]
    pixel_size_m = abs(float(dem_product["transform"].a))
    x_relief, y_relief = relief_pixel_centers(dem_product["transform"], dem_product["shape"])
    transformer = Transformer.from_crs(str(dem_product["crs"]), "EPSG:25829", always_xy=True)
    x_chip_crs, y_chip_crs = transformer.transform(x_relief, y_relief)
    x_chip_crs = np.asarray(x_chip_crs)
    y_chip_crs = np.asarray(y_chip_crs)

    summary_rows: list[dict[str, str]] = []
    ring_rows: list[dict[str, str]] = []
    for chip_row in chip_rows:
        template = template_on_relief_grid(chip_row, positive_template, x_chip_crs, y_chip_crs)
        summary, rings = evaluate_chip(chip_row, template, products, pixel_size_m)
        summary_rows.append(summary)
        ring_rows.extend(rings)
    add_scores(summary_rows)
    write_tsv(summary_path, summary_rows, SUMMARY_FIELDS)
    write_tsv(rings_path, ring_rows, RING_FIELDS)
    write_report(report_path, summary_rows, ring_rows, chip_manifest, relief_manifest, summary_path, rings_path)
    failed = sum(1 for row in summary_rows if row["status"] != "ok")
    print(f"rows_checked={len(summary_rows)}")
    print(f"failed_rows={failed}")
    print(f"report={report_path}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
