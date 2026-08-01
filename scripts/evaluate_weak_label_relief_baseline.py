#!/usr/bin/env python3
"""Evaluate a weak relief ranking baseline over exported MDT chips."""

from __future__ import annotations

import argparse
import csv
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MASTER = PROJECT_ROOT / "data/weak-label-splits-v1/weak_label_master.tsv"
DEFAULT_RELIEF = PROJECT_ROOT / "data/weak-label-relief-v1/weak_label_relief_wcs_holdouts.tsv"
DEFAULT_RGB_METRICS = PROJECT_ROOT / "data/weak-label-baseline-v1/weak_label_rgb_baseline_metrics.tsv"
DEFAULT_OUT_DIR = PROJECT_ROOT / "data/weak-label-relief-v1"
DEFAULT_REPORT = PROJECT_ROOT / "reports/weak_label_relief_baseline_holdouts.md"

GENERATED_AT = "2026-08-01T00:00:00Z"
RING_SECTORS = 36

FEATURE_NAMES = [
    "dem_core_mean",
    "dem_context_mean",
    "dem_prominence_m",
    "slope_annulus_mean",
    "slope_context_mean",
    "slope_ratio",
    "lrm_abs_annulus_mean",
    "lrm_abs_context_mean",
    "lrm_abs_ratio",
    "lrm_core_mean",
    "lrm_context_mean",
    "lrm_core_delta",
    "hillshade_edge_annulus_mean",
    "hillshade_edge_context_mean",
    "hillshade_edge_ratio",
    "ring_sector_coverage",
    "ring_sector_balance",
]

FEATURE_FIELDS = [
    "tile_id",
    "sample_id",
    "bank_id",
    "label_class",
    "label_role",
    "final_split",
    "country",
    "name",
    "municipality",
    "parish",
    "morphology_proxy",
    "negative_type",
    "feature_radius_m",
    "dem_path",
    "status",
    "error",
    *FEATURE_NAMES,
]

SCORE_FIELDS = [
    "tile_id",
    "sample_id",
    "bank_id",
    "label_class",
    "label_role",
    "final_split",
    "country",
    "name",
    "municipality",
    "parish",
    "morphology_proxy",
    "negative_type",
    "feature_radius_m",
    "relief_score",
    "rank_desc",
    "status",
    "error",
]

METRIC_FIELDS = [
    "subset",
    "rows",
    "positives",
    "negatives",
    "roc_auc",
    "average_precision",
    "precision_at_10",
    "recall_at_10",
    "precision_at_50",
    "recall_at_50",
    "precision_at_100",
    "recall_at_100",
    "best_positive_rank",
    "median_positive_rank",
]


def require_runtime() -> None:
    missing = []
    for module in ("numpy", "rasterio"):
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


def parse_float(value: object, fallback: float = 0.0) -> float:
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return fallback


def safe_ratio(num: float, den: float) -> float:
    return float(num / den) if abs(den) > 1e-9 else 0.0


def fill_nodata(array):
    import numpy as np

    arr = array.astype("float32", copy=True)
    finite = np.isfinite(arr)
    if finite.all():
        return arr
    if not finite.any():
        return np.zeros_like(arr, dtype="float32")
    arr[~finite] = float(np.nanmean(arr))
    return arr


def box_mean(array, radius: int):
    import numpy as np

    radius = max(1, int(radius))
    kernel = 2 * radius + 1
    padded = np.pad(array, radius, mode="edge")
    integral = np.pad(padded, ((1, 0), (1, 0)), mode="constant", constant_values=0).cumsum(axis=0).cumsum(axis=1)
    summed = integral[kernel:, kernel:] - integral[:-kernel, kernel:] - integral[kernel:, :-kernel] + integral[:-kernel, :-kernel]
    return (summed / float(kernel * kernel)).astype("float32")


def derive_products(dem, resolution: float, lrm_radius_m: float):
    import numpy as np

    dem = fill_nodata(dem)
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
    hillshade = np.clip(hillshade, 0, 255).astype("float32")
    lrm_radius_px = max(1, int(round(lrm_radius_m / resolution)))
    lrm = (dem - box_mean(dem, lrm_radius_px)).astype("float32")
    return dem, slope, hillshade, lrm


def sobel_edges(array):
    import numpy as np

    arr = fill_nodata(array)
    min_value = float(arr.min())
    max_value = float(arr.max())
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


def mask_mean(values) -> float:
    import numpy as np

    values = values[np.isfinite(values)]
    return float(values.mean()) if values.size else 0.0


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def build_masks(shape: tuple[int, int], radius_m: float, resolution: float):
    import numpy as np

    height, width = shape
    yy, xx = np.indices((height, width))
    cx = (width - 1) / 2.0
    cy = (height - 1) / 2.0
    distance_px = np.hypot(xx - cx, yy - cy)
    radius_px = clamp(radius_m / max(resolution, 0.1), 3.0, min(width, height) * 0.45)
    annulus_half = clamp(radius_px * 0.16, 2.0, 8.0)
    core = distance_px <= radius_px * 0.62
    annulus = (distance_px >= radius_px - annulus_half) & (distance_px <= radius_px + annulus_half)
    context_start = radius_px + annulus_half * 2.0
    context_end = min(min(width, height) * 0.48, max(context_start + annulus_half * 3.0, radius_px * 1.9))
    context = (distance_px >= context_start) & (distance_px <= context_end)
    if not context.any():
        context = distance_px >= min(radius_px * 1.25, min(width, height) * 0.40)
    angles = (np.arctan2(yy - cy, xx - cx) + 2.0 * math.pi) % (2.0 * math.pi)
    sectors = np.floor(angles / (2.0 * math.pi / RING_SECTORS)).astype("int16")
    return core, annulus, context, sectors


def ring_sector_metrics(values, annulus, context, sectors) -> tuple[float, float]:
    import numpy as np

    context_values = values[context]
    context_values = context_values[np.isfinite(context_values)]
    if not context_values.size:
        return 0.0, 0.0
    threshold = float(np.percentile(context_values, 65))
    sector_means = []
    for sector in range(RING_SECTORS):
        mask = annulus & (sectors == sector)
        if int(mask.sum()) < 2:
            continue
        sector_means.append(mask_mean(values[mask]))
    if not sector_means:
        return 0.0, 0.0
    coverage = sum(value > threshold for value in sector_means) / len(sector_means)
    mean_value = statistics.mean(sector_means)
    std_value = statistics.pstdev(sector_means) if len(sector_means) > 1 else 0.0
    balance = mean_value / (mean_value + std_value) if mean_value > 0 else 0.0
    return float(coverage), float(balance)


def master_by_sample_id(path: Path) -> dict[str, dict[str, str]]:
    return {row["sample_id"]: row for row in read_tsv(path)}


def feature_row(row: dict[str, str], meta: dict[str, dict[str, str]], args: argparse.Namespace) -> dict[str, str]:
    import numpy as np
    import rasterio

    master = meta.get(row.get("sample_id", ""), {})
    radius_m = args.fixed_radius_m
    path = project_path(row.get("target_dem_path", ""))
    result = {
        "tile_id": row.get("tile_id", ""),
        "sample_id": row.get("sample_id", ""),
        "bank_id": row.get("bank_id", ""),
        "label_class": row.get("label_class", ""),
        "label_role": row.get("label_role", ""),
        "final_split": row.get("final_split", ""),
        "country": row.get("country", ""),
        "name": row.get("name", ""),
        "municipality": master.get("municipality", ""),
        "parish": master.get("parish", ""),
        "morphology_proxy": master.get("morphology_proxy", ""),
        "negative_type": master.get("negative_type", ""),
        "feature_radius_m": f"{radius_m:.1f}",
        "dem_path": rel_to_project(path),
        "status": "failed",
        "error": "",
    }
    if row.get("dem_status") != "valid":
        result["error"] = f"manifest_dem_status:{row.get('dem_status', '')}"
        return result
    if not path.exists():
        result["error"] = f"missing_dem:{rel_to_project(path)}"
        return result
    try:
        with rasterio.open(path) as src:
            dem = src.read(1).astype("float32")
            if src.nodata is not None:
                dem[dem == src.nodata] = np.nan
            resolution = abs(float(src.res[0]))
        dem, slope, hillshade, lrm = derive_products(dem, resolution, args.lrm_radius_m)
        hillshade_edge = sobel_edges(hillshade)
        core, annulus, context, sectors = build_masks(dem.shape, radius_m, resolution)
        coverage, balance = ring_sector_metrics(np.abs(lrm), annulus, context, sectors)
        dem_core = mask_mean(dem[core])
        dem_context = mask_mean(dem[context])
        slope_annulus = mask_mean(slope[annulus])
        slope_context = mask_mean(slope[context])
        lrm_abs_annulus = mask_mean(np.abs(lrm[annulus]))
        lrm_abs_context = mask_mean(np.abs(lrm[context]))
        lrm_core = mask_mean(lrm[core])
        lrm_context = mask_mean(lrm[context])
        hillshade_edge_annulus = mask_mean(hillshade_edge[annulus])
        hillshade_edge_context = mask_mean(hillshade_edge[context])
        features = {
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
            "hillshade_edge_annulus_mean": hillshade_edge_annulus,
            "hillshade_edge_context_mean": hillshade_edge_context,
            "hillshade_edge_ratio": safe_ratio(hillshade_edge_annulus, hillshade_edge_context),
            "ring_sector_coverage": coverage,
            "ring_sector_balance": balance,
        }
        for name in FEATURE_NAMES:
            result[name] = f"{features[name]:.8f}"
        result["status"] = "ok"
    except Exception as exc:
        result["error"] = str(exc)
    return result


def robust_z(values: list[float]) -> list[float]:
    median = statistics.median(values) if values else 0.0
    deviations = [abs(value - median) for value in values]
    mad = statistics.median(deviations) if deviations else 0.0
    scale = 1.4826 * mad if mad > 1e-9 else (statistics.pstdev(values) if len(values) > 1 else 1.0)
    if scale <= 1e-9:
        scale = 1.0
    return [(value - median) / scale for value in values]


def build_score_rows(feature_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    ok_rows = [row for row in feature_rows if row["status"] == "ok"]
    components = {
        "dem_prominence_m": 0.35,
        "lrm_abs_ratio": 0.25,
        "slope_ratio": 0.20,
        "hillshade_edge_ratio": 0.10,
        "ring_sector_coverage": 0.10,
    }
    scores = [0.0 for _row in ok_rows]
    for feature_name, weight in components.items():
        z_values = robust_z([parse_float(row[feature_name]) for row in ok_rows])
        for index, z_value in enumerate(z_values):
            scores[index] += weight * z_value
    order = sorted(range(len(scores)), key=lambda idx: scores[idx], reverse=True)
    ranks = [0] * len(scores)
    for rank, idx in enumerate(order, start=1):
        ranks[idx] = rank
    score_rows = []
    for idx, row in enumerate(ok_rows):
        score_rows.append(
            {
                "tile_id": row["tile_id"],
                "sample_id": row["sample_id"],
                "bank_id": row["bank_id"],
                "label_class": row["label_class"],
                "label_role": row["label_role"],
                "final_split": row["final_split"],
                "country": row["country"],
                "name": row["name"],
                "municipality": row["municipality"],
                "parish": row["parish"],
                "morphology_proxy": row["morphology_proxy"],
                "negative_type": row["negative_type"],
                "feature_radius_m": row["feature_radius_m"],
                "relief_score": f"{scores[idx]:.8f}",
                "rank_desc": str(ranks[idx]),
                "status": row["status"],
                "error": row["error"],
            }
        )
    return score_rows


def ranks_desc(scores: list[float]) -> list[int]:
    order = sorted(range(len(scores)), key=lambda idx: scores[idx], reverse=True)
    ranks = [0] * len(scores)
    for rank, idx in enumerate(order, start=1):
        ranks[idx] = rank
    return ranks


def roc_auc(labels: list[int], scores: list[float]) -> str:
    positives = [score for label, score in zip(labels, scores) if label == 1]
    negatives = [score for label, score in zip(labels, scores) if label == 0]
    if not positives or not negatives:
        return "n/a"
    wins = 0.0
    for pos in positives:
        for neg in negatives:
            if pos > neg:
                wins += 1.0
            elif pos == neg:
                wins += 0.5
    return f"{wins / (len(positives) * len(negatives)):.6f}"


def average_precision(labels: list[int], scores: list[float]) -> str:
    positives = sum(labels)
    if positives == 0:
        return "n/a"
    order = sorted(range(len(scores)), key=lambda idx: scores[idx], reverse=True)
    hits = 0
    precisions = []
    for rank, idx in enumerate(order, start=1):
        if labels[idx] == 1:
            hits += 1
            precisions.append(hits / rank)
    return f"{sum(precisions) / positives:.6f}" if precisions else "0.000000"


def precision_recall_at(labels: list[int], scores: list[float], k: int) -> tuple[str, str]:
    positives = sum(labels)
    if positives == 0:
        return "n/a", "n/a"
    order = sorted(range(len(scores)), key=lambda idx: scores[idx], reverse=True)[: min(k, len(scores))]
    hits = sum(labels[idx] for idx in order)
    return f"{hits / max(len(order), 1):.6f}", f"{hits / positives:.6f}"


def metric_row(subset: str, rows: list[dict[str, str]]) -> dict[str, str]:
    labels = [int(row["label_class"]) for row in rows]
    scores = [parse_float(row["relief_score"]) for row in rows]
    ranks = ranks_desc(scores)
    pos_ranks = [rank for rank, label in zip(ranks, labels) if label == 1]
    p10, r10 = precision_recall_at(labels, scores, 10)
    p50, r50 = precision_recall_at(labels, scores, 50)
    p100, r100 = precision_recall_at(labels, scores, 100)
    return {
        "subset": subset,
        "rows": str(len(rows)),
        "positives": str(sum(labels)),
        "negatives": str(len(labels) - sum(labels)),
        "roc_auc": roc_auc(labels, scores),
        "average_precision": average_precision(labels, scores),
        "precision_at_10": p10,
        "recall_at_10": r10,
        "precision_at_50": p50,
        "recall_at_50": r50,
        "precision_at_100": p100,
        "recall_at_100": r100,
        "best_positive_rank": str(min(pos_ranks)) if pos_ranks else "n/a",
        "median_positive_rank": f"{statistics.median(pos_ranks):.1f}" if pos_ranks else "n/a",
    }


def build_metric_rows(score_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    rows = [metric_row("all", score_rows)]
    by_split: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in score_rows:
        by_split[row["final_split"]].append(row)
    for split, split_rows in sorted(by_split.items()):
        rows.append(metric_row(f"split:{split}", split_rows))
    return rows


def signal_status(metric_rows: list[dict[str, str]]) -> str:
    all_row = next((row for row in metric_rows if row["subset"] == "all"), {})
    try:
        auc = float(all_row.get("roc_auc", "nan"))
    except ValueError:
        return "relief_signal_not_evaluable"
    if auc >= 0.65:
        return "weak_relief_ranking_signal_present"
    if auc >= 0.55:
        return "relief_signal_ambiguous"
    return "relief_signal_not_reliable"


def load_rgb_summary(path: Path) -> list[str]:
    if not path.exists():
        return []
    rows = read_tsv(path)
    keep = [row for row in rows if row.get("dataset") == "holdouts" and row.get("subset") in {"all", "split:test_o_val", "split:test_trasancos"}]
    return [f"- RGB {row['subset']}: ROC-AUC `{row['roc_auc']}`, AP `{row['average_precision']}`." for row in keep]


def top_rows(rows: list[dict[str, str]], split: str | None = None, limit: int = 10) -> list[dict[str, str]]:
    subset = [row for row in rows if split is None or row["final_split"] == split]
    return sorted(subset, key=lambda row: parse_float(row["relief_score"]), reverse=True)[:limit]


def write_report(
    path: Path,
    args: argparse.Namespace,
    feature_rows: list[dict[str, str]],
    score_rows: list[dict[str, str]],
    metric_rows: list[dict[str, str]],
) -> None:
    feature_counts = Counter(row["status"] for row in feature_rows)
    status = signal_status(metric_rows)
    lines = [
        "# Weak-label relief baseline holdouts",
        "",
        f"Generated: {GENERATED_AT}",
        "",
        "## What This Is",
        "",
        "A first relief/MDT ranking baseline over O Val and Trasancos holdouts. It uses public MDT5 WCS crops, derives slope, hillshade and local relief in memory, then scores topographic/radial contrast.",
        "It is a ranking sanity check, not an archaeological detector.",
        "",
        "## Files",
        "",
        f"- Relief manifest: `{rel_to_project(args.relief_manifest)}`",
        f"- Feature TSV: `{rel_to_project(args.out_dir / 'weak_label_relief_features_holdouts.tsv')}`",
        f"- Score TSV: `{rel_to_project(args.out_dir / 'weak_label_relief_scores_holdouts.tsv')}`",
        f"- Metrics TSV: `{rel_to_project(args.out_dir / 'weak_label_relief_metrics_holdouts.tsv')}`",
        "",
        "## Setup",
        "",
        f"- Fixed feature radius: {args.fixed_radius_m:.1f} m",
        f"- LRM radius: {args.lrm_radius_m:.1f} m",
        f"- Signal status: `{status}`",
        "",
        "## Feature Extraction",
        "",
    ]
    for value, count in sorted(feature_counts.items()):
        lines.append(f"- {value}: {count}")
    lines.extend(["", "## Metrics", ""])
    lines.append("| Subset | Rows | Pos | Neg | ROC-AUC | AP | P@50 | R@50 | Best pos rank | Median pos rank |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for row in metric_rows:
        lines.append(
            "| {subset} | {rows} | {positives} | {negatives} | {roc_auc} | {average_precision} | {precision_at_50} | {recall_at_50} | {best_positive_rank} | {median_positive_rank} |".format(
                **row
            )
        )
    rgb_summary = load_rgb_summary(args.rgb_metrics)
    if rgb_summary:
        lines.extend(["", "## RGB Baseline Reference", ""])
        lines.extend(rgb_summary)
    lines.extend(["", "## Top Relief Scores", ""])
    for split in (None, "test_o_val", "test_trasancos"):
        title = "all" if split is None else split
        lines.append(f"### {title}")
        lines.append("")
        lines.append("| Rank | Split | Class | Score | Name | Municipality |")
        lines.append("|---:|---|---:|---:|---|---|")
        for row in top_rows(score_rows, split=split, limit=10):
            lines.append(f"| {row['rank_desc']} | {row['final_split']} | {row['label_class']} | {row['relief_score']} | `{row['name'][:80]}` | {row['municipality']} |")
        lines.append("")
    o_val = sorted([row for row in score_rows if row["final_split"] == "test_o_val"], key=lambda row: parse_float(row["relief_score"]), reverse=True)
    if o_val:
        lines.extend(["## O Val Relief Reading", ""])
        for row in o_val:
            label = "positive" if row["label_class"] == "1" else "hard_negative"
            lines.append(f"- rank `{row['rank_desc']}`: `{row['name']}` ({label}), score `{row['relief_score']}`.")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "Relief/MDT5 can detect broad topographic and radial contrast, but its 5 m grid is still coarse for buried walls or ditches. Treat this as a prioritization layer. Fine LiDAR/LAZ or richer derived products are still needed before candidate claims.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--master", type=Path, default=DEFAULT_MASTER)
    parser.add_argument("--relief-manifest", type=Path, default=DEFAULT_RELIEF)
    parser.add_argument("--rgb-metrics", type=Path, default=DEFAULT_RGB_METRICS)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--fixed-radius-m", type=float, default=120.0)
    parser.add_argument("--lrm-radius-m", type=float, default=50.0)
    return parser.parse_args()


def resolve_args(args: argparse.Namespace) -> argparse.Namespace:
    args.master = args.master if args.master.is_absolute() else PROJECT_ROOT / args.master
    args.relief_manifest = args.relief_manifest if args.relief_manifest.is_absolute() else PROJECT_ROOT / args.relief_manifest
    args.rgb_metrics = args.rgb_metrics if args.rgb_metrics.is_absolute() else PROJECT_ROOT / args.rgb_metrics
    args.out_dir = args.out_dir if args.out_dir.is_absolute() else PROJECT_ROOT / args.out_dir
    args.report = args.report if args.report.is_absolute() else PROJECT_ROOT / args.report
    return args


def main() -> None:
    require_runtime()
    args = resolve_args(parse_args())
    meta = master_by_sample_id(args.master)
    relief_rows = read_tsv(args.relief_manifest)
    feature_rows = [feature_row(row, meta, args) for row in relief_rows]
    score_rows = build_score_rows(feature_rows)
    metric_rows = build_metric_rows(score_rows)
    feature_path = args.out_dir / "weak_label_relief_features_holdouts.tsv"
    score_path = args.out_dir / "weak_label_relief_scores_holdouts.tsv"
    metric_path = args.out_dir / "weak_label_relief_metrics_holdouts.tsv"
    write_tsv(feature_path, feature_rows, FEATURE_FIELDS)
    write_tsv(score_path, score_rows, SCORE_FIELDS)
    write_tsv(metric_path, metric_rows, METRIC_FIELDS)
    write_report(args.report, args, feature_rows, score_rows, metric_rows)
    print(f"feature_rows={len(feature_rows)}")
    print(f"score_rows={len(score_rows)}")
    print(f"signal_status={signal_status(metric_rows)}")
    print(f"wrote={rel_to_project(score_path)}")
    print(f"report={rel_to_project(args.report)}")


if __name__ == "__main__":
    main()
