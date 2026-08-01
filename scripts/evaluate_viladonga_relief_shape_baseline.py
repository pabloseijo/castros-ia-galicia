#!/usr/bin/env python3
"""Evaluate a small relief-based shape baseline for the Viladonga pilot."""

from __future__ import annotations

import argparse
import csv
import math
import statistics
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHIP_MANIFEST = PROJECT_ROOT / "data/viladonga-pilot/pnoa_chip_manifest.tsv"
DEFAULT_RELIEF_MANIFEST = PROJECT_ROOT / "data/viladonga-pilot/lidar_derivatives_manifest.tsv"
DEFAULT_OUT = PROJECT_ROOT / "data/viladonga-pilot/relief_shape_baseline.tsv"
DEFAULT_REPORT = PROJECT_ROOT / "reports/viladonga_relief_shape_baseline.md"
GENERATED_AT = "2026-08-01"

FIELDS = [
    "chip_id",
    "label_class",
    "label_kind",
    "template_source",
    "template_pixels",
    "boundary_pixels",
    "context_pixels",
    "inside_pixels",
    "slope_boundary_mean",
    "slope_context_mean",
    "slope_ratio",
    "lrm_boundary_abs_mean",
    "lrm_context_abs_mean",
    "lrm_abs_ratio",
    "hillshade_edge_boundary_mean",
    "hillshade_edge_context_mean",
    "hillshade_edge_ratio",
    "dem_inside_mean",
    "dem_context_mean",
    "dem_inside_delta",
    "lrm_inside_mean",
    "lrm_context_mean",
    "lrm_inside_delta",
    "relief_score",
    "relief_rank_desc",
    "status",
    "error",
]

REQUIRED_PRODUCTS = {
    "dem": "viladonga_dem.tif",
    "slope_degrees": "viladonga_slope_degrees.tif",
    "hillshade_315_45": "viladonga_hillshade_315_45.tif",
    "lrm": "viladonga_lrm.tif",
}


def require_runtime() -> None:
    missing = []
    for module in ("numpy", "PIL", "pyproj", "rasterio"):
        try:
            __import__(module)
        except Exception:
            missing.append(module)
    if missing:
        raise SystemExit(f"Missing Python modules: {', '.join(missing)}")


def project_path(raw_path: str) -> Path:
    path = Path(raw_path)
    return path if path.is_absolute() else PROJECT_ROOT / path


def rel_to_project(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, dialect="excel-tab"))


def write_tsv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS, dialect="excel-tab")
        writer.writeheader()
        writer.writerows(rows)


def load_mask(path: Path):
    import numpy as np
    from PIL import Image

    with Image.open(path) as image:
        array = np.array(image)
    if array.ndim == 3:
        array = array[:, :, 0]
    return array > 0


def dilate(mask, iterations: int = 1):
    import numpy as np

    out = mask.copy()
    for _ in range(max(1, iterations)):
        padded = np.pad(out, 1, mode="constant", constant_values=False)
        grown = np.zeros_like(out, dtype=bool)
        for y_offset in range(3):
            for x_offset in range(3):
                grown |= padded[y_offset : y_offset + out.shape[0], x_offset : x_offset + out.shape[1]]
        out = grown
    return out


def erode(mask, iterations: int = 1):
    return ~dilate(~mask, iterations=iterations)


def sobel_edges(array):
    import numpy as np

    arr = array.astype("float32")
    finite = np.isfinite(arr)
    if not finite.all():
        mean_value = float(np.nanmean(arr))
        arr = arr.copy()
        arr[~finite] = mean_value
    min_value = float(np.nanmin(arr))
    max_value = float(np.nanmax(arr))
    if max_value > min_value:
        arr = (arr - min_value) / (max_value - min_value)
    padded = np.pad(arr, 1, mode="edge")
    gx = (
        -padded[:-2, :-2]
        + padded[:-2, 2:]
        - 2.0 * padded[1:-1, :-2]
        + 2.0 * padded[1:-1, 2:]
        - padded[2:, :-2]
        + padded[2:, 2:]
    )
    gy = (
        padded[:-2, :-2]
        + 2.0 * padded[:-2, 1:-1]
        + padded[:-2, 2:]
        - padded[2:, :-2]
        - 2.0 * padded[2:, 1:-1]
        - padded[2:, 2:]
    )
    return np.hypot(gx, gy)


def parse_bbox(raw_value: str) -> tuple[float, float, float, float]:
    values = [float(value) for value in raw_value.split(",")]
    if len(values) != 4:
        raise ValueError(f"invalid bbox: {raw_value}")
    return values[0], values[1], values[2], values[3]


def load_relief_products(manifest_path: Path):
    import numpy as np
    import rasterio

    products: dict[str, dict[str, object]] = {}
    manifest_rows = {row["product"]: row for row in read_tsv(manifest_path)}
    for product in REQUIRED_PRODUCTS:
        if product not in manifest_rows:
            raise SystemExit(f"Missing relief product in manifest: {product}")
        path = project_path(manifest_rows[product]["path"])
        if not path.exists():
            raise SystemExit(f"Missing relief raster: {path}")
        with rasterio.open(path) as src:
            array = src.read(1).astype("float32")
            if src.nodata is not None:
                array[array == src.nodata] = np.nan
            products[product] = {
                "path": path,
                "array": array,
                "transform": src.transform,
                "crs": str(src.crs),
                "shape": array.shape,
            }
    shapes = {tuple(product["shape"]) for product in products.values()}
    if len(shapes) != 1:
        raise SystemExit(f"Relief rasters do not share a shape: {sorted(shapes)}")
    crs_values = {str(product["crs"]) for product in products.values()}
    if len(crs_values) != 1:
        raise SystemExit(f"Relief rasters do not share a CRS: {sorted(crs_values)}")
    return products


def relief_pixel_centers(transform, shape):
    import numpy as np

    rows, cols = np.indices(shape, dtype="float64")
    xs = transform.c + (cols + 0.5) * transform.a + (rows + 0.5) * transform.b
    ys = transform.f + (cols + 0.5) * transform.d + (rows + 0.5) * transform.e
    return xs, ys


def template_on_relief_grid(row: dict[str, str], positive_template, x_chip_crs, y_chip_crs):
    import numpy as np

    minx, miny, maxx, maxy = parse_bbox(row["bbox_raster_crs"])
    width = int(float(row["width_px"]))
    height = int(float(row["height_px"]))
    px = ((x_chip_crs - minx) * width / (maxx - minx)).astype("int64")
    py = ((maxy - y_chip_crs) * height / (maxy - miny)).astype("int64")
    valid = (px >= 0) & (px < width) & (py >= 0) & (py < height)
    template = np.zeros(x_chip_crs.shape, dtype=bool)
    template[valid] = positive_template[py[valid], px[valid]]
    return template


def build_regions(template, finite_mask):
    outside_3 = dilate(template, iterations=3)
    boundary = (dilate(template, iterations=1) & ~erode(template, iterations=1)) & finite_mask
    context = (dilate(template, iterations=12) & ~outside_3) & finite_mask
    inside = erode(template, iterations=2) & finite_mask
    if not inside.any():
        inside = template & finite_mask
    return boundary, context, inside


def mean_or_zero(values) -> float:
    import numpy as np

    values = values[np.isfinite(values)]
    return float(values.mean()) if values.size else 0.0


def evaluate_row(row: dict[str, str], template, products: dict[str, dict[str, object]]) -> dict[str, str]:
    import numpy as np

    result = {field: "" for field in FIELDS}
    result.update(
        {
            "chip_id": row.get("chip_id", ""),
            "label_class": row.get("label_class", ""),
            "label_kind": row.get("label_kind", ""),
            "template_source": "actual_positive_mask" if row.get("label_class") == "1" else "centered_positive_template",
        }
    )
    finite_mask = np.isfinite(products["dem"]["array"]) & np.isfinite(products["slope_degrees"]["array"]) & np.isfinite(products["lrm"]["array"])
    template = template & finite_mask
    if int(template.sum()) < 10:
        result["status"] = "failed"
        result["error"] = "template_not_covered_by_relief_grid"
        return result

    boundary, context, inside = build_regions(template, finite_mask)
    if int(boundary.sum()) < 5 or int(context.sum()) < 5 or int(inside.sum()) < 5:
        result["status"] = "failed"
        result["error"] = "insufficient_region_pixels"
        return result

    dem = products["dem"]["array"]
    slope = products["slope_degrees"]["array"]
    lrm = products["lrm"]["array"]
    hillshade_edges = sobel_edges(products["hillshade_315_45"]["array"])

    slope_boundary = mean_or_zero(slope[boundary])
    slope_context = mean_or_zero(slope[context])
    lrm_boundary_abs = mean_or_zero(np.abs(lrm[boundary]))
    lrm_context_abs = mean_or_zero(np.abs(lrm[context]))
    hillshade_edge_boundary = mean_or_zero(hillshade_edges[boundary])
    hillshade_edge_context = mean_or_zero(hillshade_edges[context])
    dem_inside = mean_or_zero(dem[inside])
    dem_context = mean_or_zero(dem[context])
    lrm_inside = mean_or_zero(lrm[inside])
    lrm_context = mean_or_zero(lrm[context])

    result.update(
        {
            "template_pixels": str(int(template.sum())),
            "boundary_pixels": str(int(boundary.sum())),
            "context_pixels": str(int(context.sum())),
            "inside_pixels": str(int(inside.sum())),
            "slope_boundary_mean": f"{slope_boundary:.6f}",
            "slope_context_mean": f"{slope_context:.6f}",
            "slope_ratio": f"{(slope_boundary / slope_context) if slope_context else 0.0:.6f}",
            "lrm_boundary_abs_mean": f"{lrm_boundary_abs:.6f}",
            "lrm_context_abs_mean": f"{lrm_context_abs:.6f}",
            "lrm_abs_ratio": f"{(lrm_boundary_abs / lrm_context_abs) if lrm_context_abs else 0.0:.6f}",
            "hillshade_edge_boundary_mean": f"{hillshade_edge_boundary:.6f}",
            "hillshade_edge_context_mean": f"{hillshade_edge_context:.6f}",
            "hillshade_edge_ratio": f"{(hillshade_edge_boundary / hillshade_edge_context) if hillshade_edge_context else 0.0:.6f}",
            "dem_inside_mean": f"{dem_inside:.6f}",
            "dem_context_mean": f"{dem_context:.6f}",
            "dem_inside_delta": f"{(dem_inside - dem_context):.6f}",
            "lrm_inside_mean": f"{lrm_inside:.6f}",
            "lrm_context_mean": f"{lrm_context:.6f}",
            "lrm_inside_delta": f"{(lrm_inside - lrm_context):.6f}",
            "status": "ok",
        }
    )
    return result


def robust_scale(values: list[float]) -> float:
    if len(values) < 2:
        return 1.0
    median = statistics.median(values)
    mad = statistics.median(abs(value - median) for value in values)
    if mad > 0:
        return 1.4826 * mad
    stdev = statistics.pstdev(values)
    return stdev if stdev > 0 else 1.0


def add_scores(rows: list[dict[str, str]]) -> None:
    metrics = ["slope_ratio", "lrm_abs_ratio", "hillshade_edge_ratio", "dem_inside_delta", "lrm_inside_delta"]
    ok_rows = [row for row in rows if row["status"] == "ok"]
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
        row["relief_score"] = f"{score:.6f}"
    ranked = sorted(ok_rows, key=lambda item: float(item["relief_score"]), reverse=True)
    for rank, row in enumerate(ranked, start=1):
        row["relief_rank_desc"] = str(rank)


def classify_signal(rows: list[dict[str, str]]) -> str:
    ok_rows = [row for row in rows if row["status"] == "ok"]
    positive = next((row for row in ok_rows if row.get("label_class") == "1"), None)
    if not positive or len(ok_rows) < 3:
        return "blocked"
    rank = int(positive["relief_rank_desc"])
    score = float(positive["relief_score"])
    negative_scores = [float(row["relief_score"]) for row in ok_rows if row.get("label_class") == "0"]
    negative_median = statistics.median(negative_scores) if negative_scores else 0.0
    if rank == 1 and score > negative_median:
        return "relief_shape_signal_present_in_controlled_chip"
    if rank <= 3 and score > negative_median:
        return "relief_shape_signal_ambiguous"
    return "relief_shape_signal_weak"


def write_report(path: Path, rows: list[dict[str, str]], chip_manifest: Path, relief_manifest: Path, out_path: Path) -> None:
    ok_rows = [row for row in rows if row["status"] == "ok"]
    failed_rows = [row for row in rows if row["status"] != "ok"]
    positive = next((row for row in ok_rows if row.get("label_class") == "1"), {})
    signal = classify_signal(rows)
    top_rows = sorted(ok_rows, key=lambda item: float(item["relief_score"]), reverse=True)[:5]
    negative_scores = [float(row["relief_score"]) for row in ok_rows if row.get("label_class") == "0"]
    negative_median = statistics.median(negative_scores) if negative_scores else 0.0

    lines = [
        "# Viladonga relief shape baseline",
        "",
        f"Generated: {GENERATED_AT}",
        "",
        f"- Chip manifest: `{rel_to_project(chip_manifest)}`",
        f"- Relief manifest: `{rel_to_project(relief_manifest)}`",
        f"- Output TSV: `{rel_to_project(out_path)}`",
        "- Baseline: `centered_positive_shape_template_on_relief_grid`",
        f"- Rows checked: {len(rows)}",
        f"- OK rows: {len(ok_rows)}",
        f"- Failed rows: {len(failed_rows)}",
        f"- Signal status: `{signal}`",
        "",
        "## Positive Row",
        "",
    ]
    if positive:
        lines.extend(
            [
                f"- Chip: `{positive['chip_id']}`",
                f"- Relief score: {positive['relief_score']}",
                f"- Relief-rank: {positive['relief_rank_desc']} of {len(ok_rows)}",
                f"- Negative median relief score: {negative_median:.6f}",
                f"- Slope ratio: {positive['slope_ratio']}",
                f"- LRM abs ratio: {positive['lrm_abs_ratio']}",
                f"- Hillshade edge ratio: {positive['hillshade_edge_ratio']}",
                f"- DEM inside delta: {positive['dem_inside_delta']} m",
                f"- LRM inside delta: {positive['lrm_inside_delta']} m",
            ]
        )
    else:
        lines.append("- none")

    lines.extend(["", "## Signal Reading", ""])
    if signal == "relief_shape_signal_present_in_controlled_chip":
        lines.append(
            "Relief shows the strongest controlled-chip signal so far: the known castro ranks first against the eight negatives. This supports moving from PNOA-only inspection toward a relief-led morphology baseline."
        )
    elif signal == "relief_shape_signal_ambiguous":
        lines.append(
            "Relief improves the morphology test but remains ambiguous. Keep the baseline, but do not claim automatic detection until the correct LAZ tiles or more controlled castros are added."
        )
    elif signal == "relief_shape_signal_weak":
        lines.append(
            "The MDT5 relief signal is weak in this controlled test. This does not kill the project, but it makes the fine LAZ tiles more important before any serious detector claim."
        )
    else:
        lines.append("The baseline could not produce a usable signal classification.")

    lines.extend(["", "## Top Relief Scores", ""])
    lines.append("| Rank | Chip | Class | Score | Slope ratio | LRM abs ratio | DEM delta m |")
    lines.append("|---:|---|---:|---:|---:|---:|---:|")
    for row in top_rows:
        lines.append(
            f"| {row['relief_rank_desc']} | `{row['chip_id']}` | {row['label_class']} | {row['relief_score']} | {row['slope_ratio']} | {row['lrm_abs_ratio']} | {row['dem_inside_delta']} |"
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "This is a controlled baseline, not a detector. The positive mask is projected onto the relief grid for Viladonga and reused as a centered template for the negative chips. The score compares slope, absolute LRM, hillshade-edge texture, DEM inside-vs-context elevation and LRM inside-vs-context elevation against the negative median.",
            "",
            "The DEM inside-vs-context signal can capture the fact that the known hillfort sits on a topographic high; that is useful hillfort morphology, but not by itself proof of walls or ditches. The wall/ditch question needs finer LiDAR or a richer relief baseline.",
            "",
            "Because the input is a 5 m MDT WCS product, a positive result is only a coarse morphology signal. The fine archaeological test still depends on getting the correct LAZ tiles or an equivalent high-resolution LiDAR/DTM covering Viladonga.",
        ]
    )
    if failed_rows:
        lines.extend(["", "## Errors", ""])
        for row in failed_rows:
            lines.append(f"- `{row['chip_id']}`: {row['error']}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate a relief shape baseline for Viladonga.")
    parser.add_argument("--chip-manifest", type=Path, default=DEFAULT_CHIP_MANIFEST)
    parser.add_argument("--relief-manifest", type=Path, default=DEFAULT_RELIEF_MANIFEST)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def main() -> int:
    require_runtime()
    args = parse_args()
    chip_manifest = args.chip_manifest if args.chip_manifest.is_absolute() else PROJECT_ROOT / args.chip_manifest
    relief_manifest = args.relief_manifest if args.relief_manifest.is_absolute() else PROJECT_ROOT / args.relief_manifest
    out_path = args.out if args.out.is_absolute() else PROJECT_ROOT / args.out
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
    x_relief, y_relief = relief_pixel_centers(dem_product["transform"], dem_product["shape"])
    transformer = Transformer.from_crs(str(dem_product["crs"]), "EPSG:25829", always_xy=True)
    x_chip_crs, y_chip_crs = transformer.transform(x_relief, y_relief)
    x_chip_crs = np.asarray(x_chip_crs)
    y_chip_crs = np.asarray(y_chip_crs)

    rows = []
    for chip_row in chip_rows:
        template = template_on_relief_grid(chip_row, positive_template, x_chip_crs, y_chip_crs)
        rows.append(evaluate_row(chip_row, template, products))
    add_scores(rows)
    write_tsv(out_path, rows)
    write_report(report_path, rows, chip_manifest, relief_manifest, out_path)
    failed = sum(1 for row in rows if row["status"] != "ok")
    print(f"rows_checked={len(rows)}")
    print(f"failed_rows={failed}")
    print(f"report={report_path}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
