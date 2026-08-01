#!/usr/bin/env python3
"""Evaluate a small PNOA shape-signal baseline for the Viladonga pilot."""

from __future__ import annotations

import argparse
import csv
import statistics
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = PROJECT_ROOT / "data/viladonga-pilot/pnoa_chip_manifest.tsv"
DEFAULT_OUT = PROJECT_ROOT / "data/viladonga-pilot/pnoa_shape_baseline.tsv"
DEFAULT_REPORT = PROJECT_ROOT / "reports/viladonga_pnoa_shape_baseline.md"
GENERATED_AT = "2026-08-01"

FIELDS = [
    "chip_id",
    "label_class",
    "label_kind",
    "template_source",
    "boundary_pixels",
    "context_pixels",
    "edge_boundary_mean",
    "edge_context_mean",
    "edge_ratio",
    "texture_boundary_std",
    "texture_context_std",
    "texture_ratio",
    "luminance_inside_mean",
    "luminance_context_mean",
    "luminance_delta",
    "edge_ratio_rank_desc",
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


def load_gray(path: Path):
    import numpy as np
    from PIL import Image

    with Image.open(path) as image:
        rgb = np.array(image.convert("RGB"), dtype="float32")
    return (0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]) / 255.0


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
    for _ in range(iterations):
        padded = np.pad(out, 1, mode="constant", constant_values=False)
        grown = np.zeros_like(out, dtype=bool)
        for y_offset in range(3):
            for x_offset in range(3):
                grown |= padded[y_offset : y_offset + out.shape[0], x_offset : x_offset + out.shape[1]]
        out = grown
    return out


def erode(mask, iterations: int = 1):
    return ~dilate(~mask, iterations=iterations)


def sobel_edges(gray):
    import numpy as np

    padded = np.pad(gray, 1, mode="edge")
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


def mean_or_zero(values) -> float:
    return float(values.mean()) if values.size else 0.0


def std_or_zero(values) -> float:
    return float(values.std()) if values.size else 0.0


def build_regions(template):
    inner_edge = template & ~erode(template, iterations=8)
    outer_edge = dilate(template, iterations=8) & ~template
    boundary = inner_edge | outer_edge
    near_context = dilate(template, iterations=72) & ~dilate(template, iterations=20)
    if not near_context.any():
        near_context = ~dilate(template, iterations=20)
    inside = erode(template, iterations=16)
    if not inside.any():
        inside = template
    return boundary, near_context, inside


def evaluate_row(row: dict[str, str], positive_template) -> dict[str, str]:
    image_path = project_path(row.get("image_path", ""))
    mask_path = project_path(row.get("mask_path", ""))
    result = {field: "" for field in FIELDS}
    result.update(
        {
            "chip_id": row.get("chip_id", ""),
            "label_class": row.get("label_class", ""),
            "label_kind": row.get("label_kind", ""),
        }
    )
    if not image_path.exists():
        result["status"] = "failed"
        result["error"] = f"missing_image:{rel_to_project(image_path)}"
        return result
    if not mask_path.exists():
        result["status"] = "failed"
        result["error"] = f"missing_mask:{rel_to_project(mask_path)}"
        return result

    try:
        gray = load_gray(image_path)
        if row.get("label_class") == "1":
            template = load_mask(mask_path)
            result["template_source"] = "actual_positive_mask"
        else:
            template = positive_template
            result["template_source"] = "centered_positive_template"
        if gray.shape != template.shape:
            result["status"] = "failed"
            result["error"] = f"shape_mismatch:image={gray.shape},template={template.shape}"
            return result

        edges = sobel_edges(gray)
        boundary, context, inside = build_regions(template)
        boundary_edges = edges[boundary]
        context_edges = edges[context]
        boundary_gray = gray[boundary]
        context_gray = gray[context]
        inside_gray = gray[inside]
        edge_boundary = mean_or_zero(boundary_edges)
        edge_context = mean_or_zero(context_edges)
        texture_boundary = std_or_zero(boundary_gray)
        texture_context = std_or_zero(context_gray)
        luminance_inside = mean_or_zero(inside_gray)
        luminance_context = mean_or_zero(context_gray)
        result.update(
            {
                "boundary_pixels": str(int(boundary.sum())),
                "context_pixels": str(int(context.sum())),
                "edge_boundary_mean": f"{edge_boundary:.6f}",
                "edge_context_mean": f"{edge_context:.6f}",
                "edge_ratio": f"{(edge_boundary / edge_context) if edge_context else 0.0:.6f}",
                "texture_boundary_std": f"{texture_boundary:.6f}",
                "texture_context_std": f"{texture_context:.6f}",
                "texture_ratio": f"{(texture_boundary / texture_context) if texture_context else 0.0:.6f}",
                "luminance_inside_mean": f"{luminance_inside:.6f}",
                "luminance_context_mean": f"{luminance_context:.6f}",
                "luminance_delta": f"{(luminance_inside - luminance_context):.6f}",
                "status": "ok",
            }
        )
    except Exception as exc:
        result["status"] = "failed"
        result["error"] = str(exc)
    return result


def classify_signal(positive_row: dict[str, str], all_rows: list[dict[str, str]]) -> str:
    ok_rows = [row for row in all_rows if row["status"] == "ok"]
    if not positive_row or positive_row["status"] != "ok" or len(ok_rows) < 3:
        return "blocked"
    edge_ratio = float(positive_row["edge_ratio"])
    rank = int(positive_row["edge_ratio_rank_desc"])
    ratios = [float(row["edge_ratio"]) for row in ok_rows if row.get("label_class") == "0"]
    negative_median = statistics.median(ratios) if ratios else 0.0
    if rank <= 3 and edge_ratio >= 1.05 and edge_ratio >= negative_median:
        return "pnoa_shape_signal_present_in_controlled_chip"
    if rank <= 5 and edge_ratio >= negative_median:
        return "pnoa_shape_signal_ambiguous"
    return "pnoa_shape_signal_weak"


def write_report(path: Path, rows: list[dict[str, str]], manifest_path: Path, out_path: Path) -> None:
    ok_rows = [row for row in rows if row["status"] == "ok"]
    failed_rows = [row for row in rows if row["status"] != "ok"]
    positive_row = next((row for row in rows if row.get("label_class") == "1"), {})
    signal = classify_signal(positive_row, rows)
    negative_ratios = [float(row["edge_ratio"]) for row in ok_rows if row.get("label_class") == "0"]
    negative_median = statistics.median(negative_ratios) if negative_ratios else 0.0
    top_rows = sorted(ok_rows, key=lambda item: float(item["edge_ratio"]), reverse=True)[:5]

    lines = [
        "# Viladonga PNOA shape baseline",
        "",
        f"Generated: {GENERATED_AT}",
        "",
        f"- Manifest: `{rel_to_project(manifest_path)}`",
        f"- Output TSV: `{rel_to_project(out_path)}`",
        "- Baseline: `centered_positive_shape_template`",
        f"- Rows checked: {len(rows)}",
        f"- OK rows: {len(ok_rows)}",
        f"- Failed rows: {len(failed_rows)}",
        f"- Signal status: `{signal}`",
        "",
        "## Positive Row",
        "",
    ]
    if positive_row:
        lines.extend(
            [
                f"- Chip: `{positive_row['chip_id']}`",
                f"- Edge ratio: {positive_row['edge_ratio']}",
                f"- Edge-ratio rank: {positive_row['edge_ratio_rank_desc']} of {len(ok_rows)}",
                f"- Negative median edge ratio: {negative_median:.6f}",
                f"- Texture ratio: {positive_row['texture_ratio']}",
                f"- Luminance delta: {positive_row['luminance_delta']}",
            ]
        )
    else:
        lines.append("- none")

    lines.extend(["", "## Signal Reading", ""])
    if signal == "pnoa_shape_signal_present_in_controlled_chip":
        lines.append(
            "PNOA shows a usable controlled-chip signal: the positive contour ranks near the top and its boundary edge ratio is above nearby context. This is still only a baseline, but it is worth extending with relief products."
        )
    elif signal == "pnoa_shape_signal_ambiguous":
        lines.append(
            "PNOA is visually useful but not decisive as a shape detector. The positive chip ranks above the negative median, yet the result is not clean enough to treat PNOA-only edges as a reliable morphology signal. Relief products should carry the next baseline."
        )
    elif signal == "pnoa_shape_signal_weak":
        lines.append(
            "PNOA-only shape signal is weak in this test. Keep PNOA as inspection context and prioritize LiDAR/DTM-derived relief for morphology."
        )
    else:
        lines.append("The baseline could not produce a usable signal classification.")

    lines.extend(["", "## Top Edge Ratios", ""])
    lines.append("| Rank | Chip | Class | Edge ratio | Texture ratio |")
    lines.append("|---:|---|---:|---:|---:|")
    for row in top_rows:
        lines.append(
            f"| {row['edge_ratio_rank_desc']} | `{row['chip_id']}` | {row['label_class']} | {row['edge_ratio']} | {row['texture_ratio']} |"
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "This is a smoke-test baseline, not a detector. The positive mask is used as the real contour for Viladonga and as a centered template for the negative chips. The score asks a narrow question: does a castro-sized boundary ring show more PNOA edge signal than nearby context, and does the positive chip rank above the negatives?",
            "",
            "A strong result here would justify spending time on a relief-aware baseline and on the correct LAZ tiles. A weak or ambiguous result means PNOA alone should stay as visual support while LiDAR/DTM remains the main morphology signal.",
        ]
    )
    if failed_rows:
        lines.extend(["", "## Errors", ""])
        for row in failed_rows:
            lines.append(f"- `{row['chip_id']}`: {row['error']}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate a PNOA shape-signal baseline for Viladonga.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def main() -> int:
    require_runtime()
    args = parse_args()
    manifest_path = args.manifest if args.manifest.is_absolute() else PROJECT_ROOT / args.manifest
    out_path = args.out if args.out.is_absolute() else PROJECT_ROOT / args.out
    report_path = args.report if args.report.is_absolute() else PROJECT_ROOT / args.report
    if not manifest_path.exists():
        raise SystemExit(f"Missing manifest: {manifest_path}")

    manifest_rows = read_tsv(manifest_path)
    positive_manifest = next((row for row in manifest_rows if row.get("label_class") == "1"), None)
    if not positive_manifest:
        raise SystemExit("Missing positive row in manifest")
    positive_mask_path = project_path(positive_manifest.get("mask_path", ""))
    if not positive_mask_path.exists():
        raise SystemExit(f"Missing positive mask: {positive_mask_path}")
    positive_template = load_mask(positive_mask_path)

    rows = [evaluate_row(row, positive_template) for row in manifest_rows]
    ok_rows = [row for row in rows if row["status"] == "ok"]
    ranked = sorted(ok_rows, key=lambda item: float(item["edge_ratio"]), reverse=True)
    for rank, row in enumerate(ranked, start=1):
        row["edge_ratio_rank_desc"] = str(rank)

    write_tsv(out_path, rows)
    write_report(report_path, rows, manifest_path, out_path)
    failed = sum(1 for row in rows if row["status"] != "ok")
    print(f"rows_checked={len(rows)}")
    print(f"failed_rows={failed}")
    print(f"report={report_path}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
