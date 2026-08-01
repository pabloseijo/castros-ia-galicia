#!/usr/bin/env python3
"""Build visual contact sheets for the weak-label error review queue."""

from __future__ import annotations

import argparse
import csv
import math
import textwrap
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from evaluate_weak_label_relief_baseline import derive_products
from train_weak_label_rgb_baseline import parse_float, read_tsv, rel_to_project, write_tsv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QUEUE = PROJECT_ROOT / "data/weak-label-fusion-v1/weak_label_error_review_queue.tsv"
DEFAULT_CHIP_MANIFESTS = [
    PROJECT_ROOT / "data/weak-label-splits-v1/weak_label_chip_export_holdouts.tsv",
    PROJECT_ROOT / "data/weak-label-splits-v1/weak_label_chip_export_val.tsv",
]
DEFAULT_RELIEF_MANIFESTS = [
    PROJECT_ROOT / "data/weak-label-relief-v1/weak_label_relief_wcs_holdouts.tsv",
    PROJECT_ROOT / "data/weak-label-relief-v1/weak_label_relief_wcs_val.tsv",
]
DEFAULT_OUT_DIR = PROJECT_ROOT / "reports/figures/weak_label_error_review_v1"
DEFAULT_OUT_TSV = PROJECT_ROOT / "data/weak-label-fusion-v1/weak_label_error_review_visual_batch.tsv"
DEFAULT_REPORT = PROJECT_ROOT / "reports/weak_label_error_review_visual_batch_v1.md"

GENERATED_AT = "2026-08-01T00:00:00Z"
PANEL_SIZE = 180
TITLE_HEIGHT = 22
ROW_HEADER_HEIGHT = 92
RADIUS_M = 120.0

QUEUE_LIMITS = {
    "holdout_top_false_positives": 25,
    "holdout_low_rank_positives": 25,
    "holdout_morphology_rescues": 13,
    "val_top_weak_negatives": 12,
    "val_low_rank_weak_positives": 12,
    "val_morphology_rescues": 12,
}

VISUAL_FIELDS = [
    "queue",
    "priority_order",
    "dataset",
    "final_split",
    "sample_id",
    "label_class",
    "name",
    "municipality",
    "parish",
    "country",
    "fusion_probability",
    "fusion_rank",
    "max_safety_rank",
    "archetype_only_rank",
    "rank_delta_fusion_to_max",
    "negative_type",
    "morphology_proxy",
    "rgb_status",
    "relief_status",
    "visual_sheet",
    "review_focus",
]


def require_runtime() -> None:
    missing = []
    for module in ("numpy", "PIL", "rasterio"):
        try:
            __import__(module)
        except Exception:
            missing.append(module)
    if missing:
        raise SystemExit(f"Missing Python modules: {', '.join(missing)}")


def load_font(size: int, *, bold: bool = False):
    from PIL import ImageFont

    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except Exception:
            continue
    return ImageFont.load_default()


def project_path(raw_path: str) -> Path:
    path = Path(raw_path)
    return path if path.is_absolute() else PROJECT_ROOT / path


def by_sample(paths: list[Path]) -> dict[str, dict[str, str]]:
    rows = {}
    for path in paths:
        if path.exists():
            for row in read_tsv(path):
                rows[row["sample_id"]] = row
    return rows


def resolve_paths(paths: list[Path]) -> list[Path]:
    return [path if path.is_absolute() else PROJECT_ROOT / path for path in paths]


def slugify(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    out = []
    for char in ascii_value.lower():
        out.append(char if char.isalnum() else "-")
    slug = "".join(out).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "queue"


def normalize_gray(array):
    import numpy as np

    arr = array.astype("float32", copy=True)
    finite = np.isfinite(arr)
    if not finite.any():
        return np.zeros(arr.shape, dtype="uint8")
    lo, hi = np.nanpercentile(arr[finite], [2, 98])
    if abs(float(hi) - float(lo)) < 1e-9:
        lo, hi = float(np.nanmin(arr[finite])), float(np.nanmax(arr[finite]))
    if abs(float(hi) - float(lo)) < 1e-9:
        return np.zeros(arr.shape, dtype="uint8")
    scaled = (np.clip(arr, lo, hi) - lo) / (hi - lo)
    scaled[~finite] = 0.0
    return (scaled * 255.0).astype("uint8")


def diverging_lrm(array):
    import numpy as np

    arr = array.astype("float32", copy=True)
    finite = np.isfinite(arr)
    if not finite.any():
        return np.zeros((*arr.shape, 3), dtype="uint8")
    scale = float(np.nanpercentile(np.abs(arr[finite]), 98))
    if scale <= 1e-9:
        scale = 1.0
    norm = np.clip(arr / scale, -1.0, 1.0)
    red = np.where(norm >= 0, 255.0, 255.0 * (1.0 + norm))
    green = 255.0 * (1.0 - np.abs(norm) * 0.70)
    blue = np.where(norm <= 0, 255.0, 255.0 * (1.0 - norm))
    rgb = np.stack([red, green, blue], axis=-1)
    rgb[~finite] = 0.0
    return np.clip(rgb, 0, 255).astype("uint8")


def draw_radius(draw, source_width: int, source_height: int, radius_px: float, scale: float, y_offset: int = TITLE_HEIGHT) -> None:
    cx = (source_width - 1) * scale / 2.0
    cy = y_offset + (source_height - 1) * scale / 2.0
    rr = radius_px * scale
    bbox = [cx - rr, cy - rr, cx + rr, cy + rr]
    draw.ellipse(bbox, outline=(0, 0, 0), width=4)
    draw.ellipse(bbox, outline=(255, 230, 60), width=2)
    tick = 5
    draw.line([cx - tick, cy, cx + tick, cy], fill=(255, 230, 60), width=2)
    draw.line([cx, cy - tick, cx, cy + tick], fill=(255, 230, 60), width=2)


def panel(title: str, image, radius_px: float | None):
    from PIL import Image, ImageDraw

    title_font = load_font(12, bold=True)
    source_width, source_height = image.size
    scale = PANEL_SIZE / max(source_width, source_height, 1)
    image = image.resize((PANEL_SIZE, PANEL_SIZE), Image.Resampling.BILINEAR)
    canvas = Image.new("RGB", (PANEL_SIZE, PANEL_SIZE + TITLE_HEIGHT), (245, 245, 242))
    canvas.paste(image, (0, TITLE_HEIGHT))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle([0, 0, PANEL_SIZE, TITLE_HEIGHT], fill=(24, 26, 28))
    draw.text((7, 5), title, fill=(245, 245, 242), font=title_font)
    if radius_px is not None:
        draw_radius(draw, source_width, source_height, radius_px, scale)
    return canvas


def placeholder_panel(title: str, message: str):
    from PIL import Image, ImageDraw

    body_font = load_font(13)
    image = Image.new("RGB", (PANEL_SIZE, PANEL_SIZE), (226, 226, 220))
    draw = ImageDraw.Draw(image)
    y = 58
    for line in textwrap.wrap(message, width=22):
        draw.text((14, y), line, fill=(72, 72, 68), font=body_font)
        y += 17
    return panel(title, image, None)


def rgb_panel(chip_row: dict[str, str] | None):
    from PIL import Image

    if not chip_row or chip_row.get("image_status") != "valid":
        return placeholder_panel("RGB", "missing or invalid chip")
    rgb_path = project_path(chip_row["target_png_path"])
    if not rgb_path.exists():
        return placeholder_panel("RGB", "chip file missing")
    image = Image.open(rgb_path).convert("RGB")
    tile_side_m = parse_float(chip_row.get("tile_side_m", "512"), 512.0)
    radius_px = RADIUS_M / max(tile_side_m, 1.0) * image.width
    return panel("RGB", image, radius_px)


def relief_panels(relief_row: dict[str, str] | None):
    from PIL import Image
    import rasterio

    if not relief_row or relief_row.get("dem_status") != "valid":
        reason = (relief_row or {}).get("dem_status") or "missing DEM"
        return [
            placeholder_panel("DEM", reason),
            placeholder_panel("Slope", reason),
            placeholder_panel("LRM", reason),
        ]
    dem_path = project_path(relief_row["target_dem_path"])
    if not dem_path.exists():
        return [
            placeholder_panel("DEM", "DEM file missing"),
            placeholder_panel("Slope", "DEM file missing"),
            placeholder_panel("LRM", "DEM file missing"),
        ]
    with rasterio.open(dem_path) as src:
        dem = src.read(1).astype("float32")
        if src.nodata is not None:
            dem[dem == src.nodata] = math.nan
        resolution = abs(float(src.res[0]))
    dem, slope, _hillshade, lrm = derive_products(dem, resolution, 50.0)
    radius_px = RADIUS_M / max(resolution, 0.1)
    return [
        panel("DEM", Image.fromarray(normalize_gray(dem)).convert("RGB"), radius_px),
        panel("Slope", Image.fromarray(normalize_gray(slope)).convert("RGB"), radius_px),
        panel("LRM", Image.fromarray(diverging_lrm(lrm)), radius_px),
    ]


def draw_wrapped(draw, xy: tuple[int, int], text: str, *, font, fill, width_chars: int, line_spacing: int = 3) -> None:
    y = xy[1]
    for line in textwrap.wrap(text, width=width_chars):
        draw.text((xy[0], y), line, fill=fill, font=font)
        bbox = draw.textbbox((xy[0], y), line, font=font)
        y += (bbox[3] - bbox[1]) + line_spacing


def review_focus(row: dict[str, str]) -> str:
    queue = row["queue"]
    if queue.endswith("top_false_positives") or queue.endswith("top_weak_negatives"):
        return "negative high in fusion; inspect recurring distractor type"
    if queue.endswith("low_rank_positives"):
        return "positive low in fusion; inspect visibility, centering and morphology"
    if queue.endswith("morphology_rescues"):
        return "positive rescued by morphology channel; inspect archetype pattern"
    return "inspect"


def row_plate(row: dict[str, str], chip_by_sample: dict[str, dict[str, str]], relief_by_sample: dict[str, dict[str, str]]):
    from PIL import Image, ImageDraw

    title_font = load_font(16, bold=True)
    body_font = load_font(12)
    panels = [rgb_panel(chip_by_sample.get(row["sample_id"])), *relief_panels(relief_by_sample.get(row["sample_id"]))]
    width = len(panels) * PANEL_SIZE
    height = ROW_HEADER_HEIGHT + PANEL_SIZE + TITLE_HEIGHT
    canvas = Image.new("RGB", (width, height), (250, 249, 246))
    draw = ImageDraw.Draw(canvas)
    title = f"{row['queue']} #{row['priority_order']} | {row['name']} ({row['municipality']})"
    metrics = (
        f"class={row['label_class']} fusion_rank={row['fusion_rank']} max_rank={row['max_safety_rank']} "
        f"delta={row['rank_delta_fusion_to_max']} p={row['fusion_probability']} "
        f"neg={row['negative_type'] or '-'} morph={row['morphology_proxy'] or '-'}"
    )
    draw.text((10, 8), title[:110], fill=(20, 22, 24), font=title_font)
    draw_wrapped(draw, (10, 34), metrics, font=body_font, fill=(55, 58, 60), width_chars=116)
    draw_wrapped(draw, (10, 62), review_focus(row), font=body_font, fill=(88, 66, 30), width_chars=116)
    for index, image in enumerate(panels):
        canvas.paste(image, (index * PANEL_SIZE, ROW_HEADER_HEIGHT))
    return canvas


def selected_rows(queue_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    out = []
    seen = set()
    for queue, limit in QUEUE_LIMITS.items():
        rows = [row for row in queue_rows if row["queue"] == queue]
        rows.sort(key=lambda row: int(row.get("priority_order") or 999999))
        for row in rows[:limit]:
            key = (queue, row["sample_id"])
            if key in seen:
                continue
            seen.add(key)
            out.append(row)
    return out


def contact_sheet(path: Path, plates: list[object]) -> None:
    from PIL import Image

    if not plates:
        return
    width = max(image.width for image in plates)
    height = sum(image.height for image in plates)
    sheet = Image.new("RGB", (width, height), (250, 249, 246))
    y = 0
    for image in plates:
        sheet.paste(image, (0, y))
        y += image.height
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path, optimize=True)


def visual_rows(
    rows: list[dict[str, str]],
    sheet_by_queue: dict[str, Path],
    chip_by_sample: dict[str, dict[str, str]],
    relief_by_sample: dict[str, dict[str, str]],
) -> list[dict[str, str]]:
    out = []
    for row in rows:
        chip = chip_by_sample.get(row["sample_id"], {})
        relief = relief_by_sample.get(row["sample_id"], {})
        out.append(
            {
                "queue": row["queue"],
                "priority_order": row["priority_order"],
                "dataset": row["dataset"],
                "final_split": row["final_split"],
                "sample_id": row["sample_id"],
                "label_class": row["label_class"],
                "name": row["name"],
                "municipality": row["municipality"],
                "parish": row["parish"],
                "country": row["country"],
                "fusion_probability": row["fusion_probability"],
                "fusion_rank": row["fusion_rank"],
                "max_safety_rank": row["max_safety_rank"],
                "archetype_only_rank": row["archetype_only_rank"],
                "rank_delta_fusion_to_max": row["rank_delta_fusion_to_max"],
                "negative_type": row["negative_type"],
                "morphology_proxy": row["morphology_proxy"],
                "rgb_status": chip.get("image_status", "missing"),
                "relief_status": relief.get("dem_status", "missing"),
                "visual_sheet": rel_to_project(sheet_by_queue[row["queue"]]),
                "review_focus": review_focus(row),
            }
        )
    return out


def count_by(rows: list[dict[str, str]], field: str) -> Counter:
    return Counter(row.get(field, "") or "-" for row in rows)


def o_val_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in rows if row["final_split"] == "test_o_val"]


def write_report(path: Path, rows: list[dict[str, str]], sheet_by_queue: dict[str, Path]) -> None:
    by_queue: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_queue[row["queue"]].append(row)

    lines = [
        "# Weak-label error review visual batch v1",
        "",
        f"Generated: {GENERATED_AT}",
        "",
        "## What This Is",
        "",
        "Visual contact sheets for the first error-review batch. Each row combines RGB, DEM, slope and local relief with the same 120 m reference radius.",
        "This is inspection material for deciding what the model confuses; it is not a discovery report.",
        "",
        "## Sheets",
        "",
    ]
    for queue, sheet in sorted(sheet_by_queue.items()):
        queue_rows = by_queue.get(queue, [])
        lines.append(f"### {queue}")
        lines.append("")
        lines.append(f"- rows: `{len(queue_rows)}`")
        lines.append(f"- image: `{rel_to_project(sheet)}`")
        if queue_rows:
            neg_counts = ", ".join(f"{key}={value}" for key, value in count_by(queue_rows, "negative_type").most_common(5))
            morph_counts = ", ".join(f"{key}={value}" for key, value in count_by(queue_rows, "morphology_proxy").most_common(5))
            relief_counts = ", ".join(f"{key}={value}" for key, value in count_by(queue_rows, "relief_status").most_common(5))
            lines.append(f"- negative types: {neg_counts}")
            lines.append(f"- morphology proxies: {morph_counts}")
            lines.append(f"- relief status: {relief_counts}")
        lines.append("")
        lines.append(f"![{queue}]({rel_to_project(sheet)})")
        lines.append("")

    lines.extend(
        [
            "## O Val Focus",
            "",
            "| Queue | Rank fusion | Rank max | Delta | Class | Name | Focus |",
            "|---|---:|---:|---:|---:|---|---|",
        ]
    )
    for row in o_val_rows(rows):
        lines.append(
            f"| `{row['queue']}` | {row['fusion_rank']} | {row['max_safety_rank']} | {row['rank_delta_fusion_to_max']} | {row['label_class']} | `{row['name']}` | {row['review_focus']} |"
        )

    holdout_false = by_queue.get("holdout_top_false_positives", [])
    holdout_positive = by_queue.get("holdout_low_rank_positives", [])
    lines.extend(["", "## Reading", ""])
    if holdout_false:
        false_types = count_by(holdout_false, "negative_type")
        lines.append(
            f"- Holdout false positives are dominated by `{false_types.most_common(1)[0][0]}` (`{false_types.most_common(1)[0][1]}`/{len(holdout_false)} in this visual batch), so the model is mainly confusing castros with archaeological relief distractors rather than random modern noise."
        )
    if holdout_positive:
        morph = count_by(holdout_positive, "morphology_proxy")
        lines.append(
            f"- Low-ranked positives are mixed morphology cases; top proxy in this batch is `{morph.most_common(1)[0][0]}` (`{morph.most_common(1)[0][1]}`/{len(holdout_positive)}). These are the best candidates for hard-positive review."
        )
    lines.extend(
        [
            "- Use the holdout sheets before validation sheets. Holdouts explain local target behavior; validation sheets are weak-label stress tests.",
            "- If a high-ranked negative visually looks like a plausible castro-like enclosure, keep it as `needs_review` rather than calling it a false positive.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    parser.add_argument("--chip-manifest", type=Path, action="append", default=None)
    parser.add_argument("--relief-manifest", type=Path, action="append", default=None)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--out-tsv", type=Path, default=DEFAULT_OUT_TSV)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def resolve_args(args: argparse.Namespace) -> argparse.Namespace:
    args.queue = args.queue if args.queue.is_absolute() else PROJECT_ROOT / args.queue
    args.chip_manifest = resolve_paths(args.chip_manifest or DEFAULT_CHIP_MANIFESTS)
    args.relief_manifest = resolve_paths(args.relief_manifest or DEFAULT_RELIEF_MANIFESTS)
    args.out_dir = args.out_dir if args.out_dir.is_absolute() else PROJECT_ROOT / args.out_dir
    args.out_tsv = args.out_tsv if args.out_tsv.is_absolute() else PROJECT_ROOT / args.out_tsv
    args.report = args.report if args.report.is_absolute() else PROJECT_ROOT / args.report
    return args


def main() -> None:
    require_runtime()
    args = resolve_args(parse_args())
    queue_rows = selected_rows(read_tsv(args.queue))
    chip_by_sample = by_sample(args.chip_manifest)
    relief_by_sample = by_sample(args.relief_manifest)

    sheet_by_queue = {}
    rows_by_queue: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in queue_rows:
        rows_by_queue[row["queue"]].append(row)

    for queue, rows in sorted(rows_by_queue.items()):
        rows.sort(key=lambda row: int(row.get("priority_order") or 999999))
        plates = [row_plate(row, chip_by_sample, relief_by_sample) for row in rows]
        sheet_path = args.out_dir / f"{slugify(queue)}.png"
        contact_sheet(sheet_path, plates)
        sheet_by_queue[queue] = sheet_path

    rows = visual_rows(queue_rows, sheet_by_queue, chip_by_sample, relief_by_sample)
    write_tsv(args.out_tsv, rows, VISUAL_FIELDS)
    write_report(args.report, rows, sheet_by_queue)

    print(f"visual_rows={len(rows)}")
    print(f"sheets={len(sheet_by_queue)}")
    print(f"wrote={rel_to_project(args.out_tsv)}")
    print(f"report={rel_to_project(args.report)}")


if __name__ == "__main__":
    main()
