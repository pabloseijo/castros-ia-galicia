#!/usr/bin/env python3
"""Build O Val RGB/relief diagnostic plates for the holdout set."""

from __future__ import annotations

import argparse
import csv
import math
import textwrap
import unicodedata
from pathlib import Path

from evaluate_weak_label_relief_baseline import derive_products, parse_float


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHIP_MANIFEST = PROJECT_ROOT / "data/weak-label-splits-v1/weak_label_chip_export_holdouts.tsv"
DEFAULT_RELIEF_MANIFEST = PROJECT_ROOT / "data/weak-label-relief-v1/weak_label_relief_wcs_holdouts.tsv"
DEFAULT_FEATURES = PROJECT_ROOT / "data/weak-label-relief-v1/weak_label_relief_features_holdouts.tsv"
DEFAULT_RELIEF_SCORES = PROJECT_ROOT / "data/weak-label-relief-v1/weak_label_relief_scores_holdouts.tsv"
DEFAULT_RGB_SCORES = PROJECT_ROOT / "data/weak-label-baseline-v1/weak_label_rgb_baseline_scores.tsv"
DEFAULT_OUT_DIR = PROJECT_ROOT / "reports/figures/o_val_relief_diagnostics"
DEFAULT_OUT_TSV = PROJECT_ROOT / "data/weak-label-relief-v1/o_val_relief_diagnostics.tsv"
DEFAULT_REPORT = PROJECT_ROOT / "reports/o_val_relief_diagnostics.md"

GENERATED_AT = "2026-08-01T00:00:00Z"
PANEL_SIZE = 256
TITLE_HEIGHT = 28
ROW_HEADER_HEIGHT = 76
RADIUS_M = 120.0

FIELDS = [
    "sample_id",
    "tile_id",
    "label_class",
    "label_role",
    "name",
    "municipality",
    "parish",
    "rgb_probability",
    "rgb_rank",
    "relief_score",
    "relief_rank",
    "dem_prominence_m",
    "slope_ratio",
    "lrm_abs_ratio",
    "ring_sector_coverage",
    "diagnostic_png",
    "watchlist_reason",
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


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, dialect="excel-tab"))


def write_tsv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, dialect="excel-tab", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def rel_to_project(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def project_path(raw_path: str) -> Path:
    path = Path(raw_path)
    return path if path.is_absolute() else PROJECT_ROOT / path


def by_sample(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    return {row["sample_id"]: row for row in rows if row.get("sample_id")}


def slugify(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    out = []
    for char in ascii_value.lower():
        out.append(char if char.isalnum() else "-")
    slug = "".join(out).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "site"


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


def resize_image(image, size: int = PANEL_SIZE):
    from PIL import Image

    return image.resize((size, size), Image.Resampling.BILINEAR)


def draw_radius(draw, source_width: int, source_height: int, radius_px: float, scale: float, y_offset: int = TITLE_HEIGHT) -> None:
    cx = (source_width - 1) * scale / 2.0
    cy = y_offset + (source_height - 1) * scale / 2.0
    rr = radius_px * scale
    bbox = [cx - rr, cy - rr, cx + rr, cy + rr]
    draw.ellipse(bbox, outline=(0, 0, 0), width=4)
    draw.ellipse(bbox, outline=(255, 230, 60), width=2)
    tick = 6
    draw.line([cx - tick, cy, cx + tick, cy], fill=(255, 230, 60), width=2)
    draw.line([cx, cy - tick, cx, cy + tick], fill=(255, 230, 60), width=2)


def panel(title: str, image, radius_px: float) -> object:
    from PIL import Image, ImageDraw

    title_font = load_font(14, bold=True)
    source_width, source_height = image.size
    scale = PANEL_SIZE / max(source_width, source_height, 1)
    image = resize_image(image)
    canvas = Image.new("RGB", (PANEL_SIZE, PANEL_SIZE + TITLE_HEIGHT), (245, 245, 242))
    canvas.paste(image, (0, TITLE_HEIGHT))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle([0, 0, PANEL_SIZE, TITLE_HEIGHT], fill=(24, 26, 28))
    draw.text((8, 7), title, fill=(245, 245, 242), font=title_font)
    draw_radius(draw, source_width, source_height, radius_px, scale)
    return canvas


def rgb_panel(chip_row: dict[str, str]) -> object:
    from PIL import Image

    rgb_path = project_path(chip_row["target_png_path"])
    image = Image.open(rgb_path).convert("RGB")
    tile_side_m = parse_float(chip_row.get("tile_side_m", "512"), 512.0)
    radius_px = RADIUS_M / max(tile_side_m, 1.0) * image.width
    return panel("PNOA RGB", image, radius_px)


def relief_panels(relief_row: dict[str, str]) -> list[object]:
    from PIL import Image
    import rasterio

    dem_path = project_path(relief_row["target_dem_path"])
    with rasterio.open(dem_path) as src:
        dem = src.read(1).astype("float32")
        if src.nodata is not None:
            dem[dem == src.nodata] = math.nan
        resolution = abs(float(src.res[0]))
    dem, slope, _hillshade, lrm = derive_products(dem, resolution, 50.0)
    radius_px = RADIUS_M / max(resolution, 0.1)
    return [
        panel("MDT5 DEM", Image.fromarray(normalize_gray(dem)).convert("RGB"), radius_px),
        panel("Slope", Image.fromarray(normalize_gray(slope)).convert("RGB"), radius_px),
        panel("Local relief", Image.fromarray(diverging_lrm(lrm)), radius_px),
    ]


def metric_text(score_row: dict[str, str], rgb_row: dict[str, str], feature_row: dict[str, str]) -> str:
    label = "positive" if score_row["label_class"] == "1" else "hard negative"
    return (
        f"{label} | RGB rank {rgb_row.get('rank_desc_in_dataset', 'n/a')} p={rgb_row.get('probability', 'n/a')} | "
        f"relief rank {score_row.get('rank_desc', 'n/a')} score={score_row.get('relief_score', 'n/a')} | "
        f"prom={feature_row.get('dem_prominence_m', 'n/a')} slope_ratio={feature_row.get('slope_ratio', 'n/a')}"
    )


def draw_wrapped(draw, xy: tuple[int, int], text: str, *, font, fill, width_chars: int, line_spacing: int = 3) -> None:
    y = xy[1]
    for line in textwrap.wrap(text, width=width_chars):
        draw.text((xy[0], y), line, fill=fill, font=font)
        bbox = draw.textbbox((xy[0], y), line, font=font)
        y += (bbox[3] - bbox[1]) + line_spacing


def site_plate(score_row: dict[str, str], chip_row: dict[str, str], relief_row: dict[str, str], rgb_row: dict[str, str], feature_row: dict[str, str]):
    from PIL import Image, ImageDraw

    title_font = load_font(18, bold=True)
    body_font = load_font(13)
    panels = [rgb_panel(chip_row), *relief_panels(relief_row)]
    width = len(panels) * PANEL_SIZE
    height = ROW_HEADER_HEIGHT + PANEL_SIZE + TITLE_HEIGHT
    canvas = Image.new("RGB", (width, height), (250, 249, 246))
    draw = ImageDraw.Draw(canvas)
    title = f"{score_row['name']} ({score_row['municipality']})"
    draw.text((10, 9), title, fill=(20, 22, 24), font=title_font)
    draw_wrapped(draw, (10, 36), metric_text(score_row, rgb_row, feature_row), font=body_font, fill=(55, 58, 60), width_chars=140)
    for index, image in enumerate(panels):
        canvas.paste(image, (index * PANEL_SIZE, ROW_HEADER_HEIGHT))
    return canvas


def watchlist(score_row: dict[str, str], rgb_row: dict[str, str]) -> str:
    if score_row["label_class"] != "1":
        return ""
    reasons = []
    if int(score_row.get("rank_desc") or 0) > 100:
        reasons.append("positive_low_relief_rank")
    if int(rgb_row.get("rank_desc_in_dataset") or 0) > 100:
        reasons.append("positive_low_rgb_rank")
    return ",".join(reasons)


def diagnostic_rows(args: argparse.Namespace) -> tuple[list[dict[str, str]], list[object]]:
    chip = by_sample(read_tsv(args.chip_manifest))
    relief = by_sample(read_tsv(args.relief_manifest))
    features = by_sample(read_tsv(args.features))
    rgb = by_sample(read_tsv(args.rgb_scores))
    scores = [
        row
        for row in read_tsv(args.relief_scores)
        if row.get("final_split") == "test_o_val" and row.get("status") == "ok"
    ]
    scores.sort(key=lambda row: int(row.get("rank_desc") or 999999))
    args.out_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, str]] = []
    plates: list[object] = []
    for row in scores:
        sample_id = row["sample_id"]
        chip_row = chip[sample_id]
        relief_row = relief[sample_id]
        rgb_row = rgb.get(sample_id, {})
        feature_row = features.get(sample_id, {})
        plate = site_plate(row, chip_row, relief_row, rgb_row, feature_row)
        out_png = args.out_dir / f"{int(row['rank_desc']):03d}-{slugify(row['name'])}.png"
        plate.save(out_png, optimize=True)
        plates.append(plate)
        rows.append(
            {
                "sample_id": sample_id,
                "tile_id": row["tile_id"],
                "label_class": row["label_class"],
                "label_role": row["label_role"],
                "name": row["name"],
                "municipality": row["municipality"],
                "parish": row["parish"],
                "rgb_probability": rgb_row.get("probability", ""),
                "rgb_rank": rgb_row.get("rank_desc_in_dataset", ""),
                "relief_score": row["relief_score"],
                "relief_rank": row["rank_desc"],
                "dem_prominence_m": feature_row.get("dem_prominence_m", ""),
                "slope_ratio": feature_row.get("slope_ratio", ""),
                "lrm_abs_ratio": feature_row.get("lrm_abs_ratio", ""),
                "ring_sector_coverage": feature_row.get("ring_sector_coverage", ""),
                "diagnostic_png": rel_to_project(out_png),
                "watchlist_reason": watchlist(row, rgb_row),
            }
        )
    return rows, plates


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
    sheet.save(path, optimize=True)


def write_report(path: Path, rows: list[dict[str, str]], contact_path: Path) -> None:
    def find_name(fragment: str) -> dict[str, str] | None:
        return next((row for row in rows if fragment in row["name"]), None)

    quinta = find_name("Quint")
    pedreira = find_name("Pedreira")
    vilasuso = find_name("Vilasuso")
    pena = find_name("Pena Lopesa")
    hard_negative = next((row for row in rows if row["label_class"] == "0"), None)
    lines = [
        "# O Val relief diagnostics",
        "",
        f"Generated: {GENERATED_AT}",
        "",
        "## What This Is",
        "",
        "A visual diagnostic sheet for the five O Val holdouts, combining PNOA RGB, MDT5 elevation, slope and local relief with the same 120 m reference radius used by the baseline.",
        "This is for error analysis only; it is not a detector and it does not create new archaeological claims.",
        "",
        "## Contact Sheet",
        "",
        f"![O Val relief diagnostics]({rel_to_project(contact_path)})",
        "",
        "## Rows",
        "",
        "| Relief rank | RGB rank | Class | Name | Prominence m | Slope ratio | LRM abs ratio | Watchlist |",
        "|---:|---:|---:|---|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['relief_rank']} | {row['rgb_rank']} | {row['label_class']} | `{row['name']}` | {row['dem_prominence_m']} | {row['slope_ratio']} | {row['lrm_abs_ratio']} | {row['watchlist_reason'] or ''} |"
        )
    lines.extend(["", "## Reading", ""])
    if quinta:
        lines.append(f"- `{quinta['name']}` is the clearest O Val relief hit: high global relief rank and high slope contrast.")
    if pedreira and vilasuso:
        lines.append(
            f"- `{pedreira['name']}` and `{vilasuso['name']}` remain positive but middle-ranked; both need richer LiDAR derivatives before using them as strong detector examples."
        )
    if pena:
        lines.append(
            f"- `{pena['name']}` is now explicitly on the watchlist because both RGB and MDT5 relief rank it low; this may be a centering, visibility, morphology or source-resolution issue."
        )
    if hard_negative:
        lines.append(
            f"- `{hard_negative['name']}` behaves as a useful hard negative because it receives a non-trivial relief score while not being a castro label."
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chip-manifest", type=Path, default=DEFAULT_CHIP_MANIFEST)
    parser.add_argument("--relief-manifest", type=Path, default=DEFAULT_RELIEF_MANIFEST)
    parser.add_argument("--features", type=Path, default=DEFAULT_FEATURES)
    parser.add_argument("--relief-scores", type=Path, default=DEFAULT_RELIEF_SCORES)
    parser.add_argument("--rgb-scores", type=Path, default=DEFAULT_RGB_SCORES)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--out-tsv", type=Path, default=DEFAULT_OUT_TSV)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def resolve_args(args: argparse.Namespace) -> argparse.Namespace:
    for attr in ("chip_manifest", "relief_manifest", "features", "relief_scores", "rgb_scores", "out_dir", "out_tsv", "report"):
        value = getattr(args, attr)
        setattr(args, attr, value if value.is_absolute() else PROJECT_ROOT / value)
    return args


def main() -> None:
    require_runtime()
    args = resolve_args(parse_args())
    rows, plates = diagnostic_rows(args)
    contact_path = args.out_dir / "o_val_contact_sheet.png"
    contact_sheet(contact_path, plates)
    write_tsv(args.out_tsv, rows, FIELDS)
    write_report(args.report, rows, contact_path)
    print(f"diagnostic_rows={len(rows)}")
    print(f"wrote={rel_to_project(args.out_tsv)}")
    print(f"report={rel_to_project(args.report)}")
    print(f"contact_sheet={rel_to_project(contact_path)}")


if __name__ == "__main__":
    main()
