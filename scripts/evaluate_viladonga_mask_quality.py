#!/usr/bin/env python3
"""Evaluate Viladonga PNOA chip and segmentation mask quality."""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = PROJECT_ROOT / "data/viladonga-pilot/pnoa_chip_manifest.tsv"
DEFAULT_OUT = PROJECT_ROOT / "data/viladonga-pilot/mask_quality.tsv"
DEFAULT_REPORT = PROJECT_ROOT / "reports/viladonga_mask_quality.md"
DEFAULT_OVERLAY_DIR = PROJECT_ROOT / "data/viladonga-pilot/chips/pnoa/qa"
GENERATED_AT = "2026-08-01"

FIELDS = [
    "chip_id",
    "feature_id",
    "label_class",
    "label_kind",
    "image_path",
    "mask_path",
    "image_exists",
    "mask_exists",
    "width_px",
    "height_px",
    "unique_values",
    "positive_pixels",
    "mask_area_pct",
    "bbox_px",
    "centroid_x",
    "centroid_y",
    "center_offset_px",
    "area_m2",
    "perimeter_m",
    "circularity",
    "equivalent_diameter_m",
    "overlay_path",
    "status",
    "error",
]


def require_runtime() -> None:
    missing = []
    for module in ("numpy", "PIL"):
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


def load_mask_array(path: Path):
    import numpy as np
    from PIL import Image

    with Image.open(path) as image:
        array = np.array(image)
    if array.ndim == 3:
        array = array[:, :, 0]
    return array


def mask_metrics(mask, tile_side_m: float) -> dict[str, str]:
    import numpy as np

    height, width = mask.shape
    binary = mask > 0
    positive_pixels = int(binary.sum())
    unique_values = ",".join(str(int(value)) for value in sorted(np.unique(mask).tolist()))
    pixel_size_m = tile_side_m / float(width) if width else 0.0

    metrics = {
        "width_px": str(width),
        "height_px": str(height),
        "unique_values": unique_values,
        "positive_pixels": str(positive_pixels),
        "mask_area_pct": "0.0000",
        "bbox_px": "",
        "centroid_x": "",
        "centroid_y": "",
        "center_offset_px": "",
        "area_m2": "",
        "perimeter_m": "",
        "circularity": "",
        "equivalent_diameter_m": "",
    }
    if positive_pixels == 0:
        return metrics

    ys, xs = np.nonzero(binary)
    min_x = int(xs.min())
    max_x = int(xs.max())
    min_y = int(ys.min())
    max_y = int(ys.max())
    centroid_x = float(xs.mean())
    centroid_y = float(ys.mean())
    center_offset = math.hypot(centroid_x - ((width - 1) / 2.0), centroid_y - ((height - 1) / 2.0))
    area_m2 = positive_pixels * pixel_size_m * pixel_size_m

    padded = np.pad(binary, 1, mode="constant", constant_values=False)
    vertical_edges = np.count_nonzero(padded[1:, :] != padded[:-1, :])
    horizontal_edges = np.count_nonzero(padded[:, 1:] != padded[:, :-1])
    perimeter_m = float(vertical_edges + horizontal_edges) * pixel_size_m
    circularity = (4.0 * math.pi * area_m2 / (perimeter_m * perimeter_m)) if perimeter_m else 0.0
    equivalent_diameter_m = 2.0 * math.sqrt(area_m2 / math.pi) if area_m2 else 0.0

    metrics.update(
        {
            "mask_area_pct": f"{positive_pixels * 100.0 / float(width * height):.4f}",
            "bbox_px": f"{min_x},{min_y},{max_x},{max_y}",
            "centroid_x": f"{centroid_x:.2f}",
            "centroid_y": f"{centroid_y:.2f}",
            "center_offset_px": f"{center_offset:.2f}",
            "area_m2": f"{area_m2:.2f}",
            "perimeter_m": f"{perimeter_m:.2f}",
            "circularity": f"{circularity:.4f}",
            "equivalent_diameter_m": f"{equivalent_diameter_m:.2f}",
        }
    )
    return metrics


def write_overlay(image_path: Path, mask, overlay_path: Path) -> None:
    import numpy as np
    from PIL import Image

    with Image.open(image_path) as image:
        base = image.convert("RGBA")
    alpha = np.where(mask > 0, 120, 0).astype("uint8")
    red = np.full(mask.shape, 220, dtype="uint8")
    green = np.full(mask.shape, 35, dtype="uint8")
    blue = np.full(mask.shape, 30, dtype="uint8")
    rgba = np.stack([red, green, blue, alpha], axis=2)
    mask_layer = Image.fromarray(rgba, mode="RGBA")
    out = Image.alpha_composite(base, mask_layer).convert("RGB")
    overlay_path.parent.mkdir(parents=True, exist_ok=True)
    out.save(overlay_path)


def row_status(
    row: dict[str, str],
    image_path: Path,
    mask,
    metrics: dict[str, str],
) -> tuple[str, str]:
    import numpy as np
    from PIL import Image

    errors: list[str] = []
    label_class = row.get("label_class", "")
    unique = set(int(value) for value in np.unique(mask).tolist())
    if not unique.issubset({0, 1}):
        errors.append(f"mask_not_binary:{','.join(str(value) for value in sorted(unique))}")
    if label_class == "1" and int(metrics["positive_pixels"]) == 0:
        errors.append("positive_mask_empty")
    if label_class == "0" and int(metrics["positive_pixels"]) != 0:
        errors.append("negative_mask_has_pixels")
    try:
        expected_width = int(float(row.get("width_px", "0")))
        expected_height = int(float(row.get("height_px", "0")))
    except ValueError:
        expected_width = 0
        expected_height = 0
    if expected_width and int(metrics["width_px"]) != expected_width:
        errors.append(f"mask_width_mismatch:{metrics['width_px']}!={expected_width}")
    if expected_height and int(metrics["height_px"]) != expected_height:
        errors.append(f"mask_height_mismatch:{metrics['height_px']}!={expected_height}")
    with Image.open(image_path) as image:
        if expected_width and image.width != expected_width:
            errors.append(f"image_width_mismatch:{image.width}!={expected_width}")
        if expected_height and image.height != expected_height:
            errors.append(f"image_height_mismatch:{image.height}!={expected_height}")
    return ("ok", "") if not errors else ("failed", "; ".join(errors))


def write_report(path: Path, rows: list[dict[str, str]], manifest_path: Path, out_path: Path) -> None:
    total = len(rows)
    ok = sum(1 for row in rows if row["status"] == "ok")
    failed = total - ok
    positives = [row for row in rows if row["label_class"] == "1"]
    negatives = [row for row in rows if row["label_class"] == "0"]
    missing_images = sum(1 for row in rows if row["image_exists"] != "yes")
    missing_masks = sum(1 for row in rows if row["mask_exists"] != "yes")
    negative_masks_with_pixels = sum(1 for row in negatives if int(row["positive_pixels"] or "0") > 0)
    positive_masks_empty = sum(1 for row in positives if int(row["positive_pixels"] or "0") == 0)
    status = "ready_for_shape_baseline" if failed == 0 and positives and positive_masks_empty == 0 else "blocked"

    lines = [
        "# Viladonga mask quality",
        "",
        f"Generated: {GENERATED_AT}",
        "",
        f"- Manifest: `{rel_to_project(manifest_path)}`",
        f"- Output TSV: `{rel_to_project(out_path)}`",
        f"- Rows checked: {total}",
        f"- OK rows: {ok}",
        f"- Failed rows: {failed}",
        f"- Positive rows: {len(positives)}",
        f"- Negative rows: {len(negatives)}",
        f"- Missing images: {missing_images}",
        f"- Missing masks: {missing_masks}",
        f"- Negative masks with positive pixels: {negative_masks_with_pixels}",
        f"- Positive masks empty: {positive_masks_empty}",
        f"- Status: `{status}`",
        "",
        "## Positive Mask",
        "",
    ]
    if positives:
        positive = positives[0]
        lines.extend(
            [
                f"- Chip: `{positive['chip_id']}`",
                f"- Positive pixels: {positive['positive_pixels']}",
                f"- Mask area: {positive['mask_area_pct']}% of chip",
                f"- BBOX px: `{positive['bbox_px']}`",
                f"- Centroid px: `{positive['centroid_x']},{positive['centroid_y']}`",
                f"- Center offset px: {positive['center_offset_px']}",
                f"- Area m2 from raster mask: {positive['area_m2']}",
                f"- Perimeter m from raster mask: {positive['perimeter_m']}",
                f"- Circularity from raster mask: {positive['circularity']}",
                f"- Equivalent diameter m from raster mask: {positive['equivalent_diameter_m']}",
                f"- QA overlay: `{positive['overlay_path']}`",
            ]
        )
    else:
        lines.append("- none")

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "The exported PNOA chips and masks are technically usable for a controlled morphology smoke test if status is `ready_for_shape_baseline`. This only validates the export and mask geometry; it does not prove automatic archaeological discovery and it is not enough data for serious model training.",
            "",
            "The raster circularity is computed from pixel-edge perimeter, so it is deliberately conservative and not directly comparable to vector circularity from `reports/viladonga_pilot_readiness.md`. Use it as a mask QA signal, not as the archaeological morphology estimate.",
            "",
            "The next defensible step is to compare image and relief features against this verified mask, while the fine LiDAR branch waits for the correct LAZ tiles `630-4780` and `630-4782`.",
        ]
    )
    if failed:
        lines.extend(["", "## Errors", ""])
        for row in rows:
            if row["status"] != "ok":
                lines.append(f"- `{row['chip_id']}`: {row['error']}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate Viladonga chip and mask quality.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--overlay-dir", type=Path, default=DEFAULT_OVERLAY_DIR)
    parser.add_argument("--no-overlays", action="store_true")
    return parser.parse_args()


def main() -> int:
    require_runtime()
    args = parse_args()
    manifest_path = args.manifest if args.manifest.is_absolute() else PROJECT_ROOT / args.manifest
    out_path = args.out if args.out.is_absolute() else PROJECT_ROOT / args.out
    report_path = args.report if args.report.is_absolute() else PROJECT_ROOT / args.report
    overlay_dir = args.overlay_dir if args.overlay_dir.is_absolute() else PROJECT_ROOT / args.overlay_dir
    if not manifest_path.exists():
        raise SystemExit(f"Missing manifest: {manifest_path}")

    rows: list[dict[str, str]] = []
    for source_row in read_tsv(manifest_path):
        image_path = project_path(source_row.get("image_path", ""))
        mask_path = project_path(source_row.get("mask_path", ""))
        result = {field: "" for field in FIELDS}
        result.update(
            {
                "chip_id": source_row.get("chip_id", ""),
                "feature_id": source_row.get("feature_id", ""),
                "label_class": source_row.get("label_class", ""),
                "label_kind": source_row.get("label_kind", ""),
                "image_path": source_row.get("image_path", ""),
                "mask_path": source_row.get("mask_path", ""),
                "image_exists": "yes" if image_path.exists() else "no",
                "mask_exists": "yes" if mask_path.exists() else "no",
            }
        )
        if not image_path.exists() or not mask_path.exists():
            missing = []
            if not image_path.exists():
                missing.append("missing_image")
            if not mask_path.exists():
                missing.append("missing_mask")
            result["status"] = "failed"
            result["error"] = "; ".join(missing)
            rows.append(result)
            continue

        try:
            mask = load_mask_array(mask_path)
            tile_side_m = float(source_row.get("tile_side_m", "512") or "512")
            metrics = mask_metrics(mask, tile_side_m)
            result.update(metrics)
            if int(result["positive_pixels"]) > 0 and not args.no_overlays:
                overlay_path = overlay_dir / f"{result['chip_id']}-overlay.png"
                write_overlay(image_path, mask, overlay_path)
                result["overlay_path"] = rel_to_project(overlay_path)
            status, error = row_status(source_row, image_path, mask, metrics)
            result["status"] = status
            result["error"] = error
        except Exception as exc:
            result["status"] = "failed"
            result["error"] = str(exc)
        rows.append(result)

    write_tsv(out_path, rows)
    write_report(report_path, rows, manifest_path, out_path)
    failed = sum(1 for row in rows if row["status"] != "ok")
    print(f"rows_checked={len(rows)}")
    print(f"failed_rows={failed}")
    print(f"report={report_path}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
