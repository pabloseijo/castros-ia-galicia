#!/usr/bin/env python3
"""Derive multi-scale relief (MSRM) features for weak-label rows.

The fixed 120 m ring radius and single 50 m LRM radius of the v1 relief
baseline assume one castro size. This script follows Orengo & Petrie's
multi-scale relief model instead: it builds local relief at a ladder of
radii, composes them into an MSRM raster, and sweeps candidate ring radii
so each row reports the scale at which its ring signal is strongest.

It reuses the MDT GeoTIFFs already exported under data/external and does
not download anything.
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import statistics
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MASTER = PROJECT_ROOT / "data/weak-label-splits-v1/weak_label_master.tsv"
DEFAULT_OUT_DIR = PROJECT_ROOT / "data/weak-label-msrm-v1"
DEFAULT_REPORT = PROJECT_ROOT / "reports/weak_label_msrm_features_v1.md"

GENERATED_AT = "2026-08-02T00:00:00Z"
RING_SECTORS = 36
DEFAULT_SCALES_M = "15,30,60,120,240"
DEFAULT_RING_RADII_M = "40,60,80,100,120,150,180,220"

SCALE_FEATURE_TEMPLATES = [
    "lrm{tag}_abs_ratio",
    "lrm{tag}_core_delta",
]

BASE_FEATURE_NAMES = [
    "msrm_abs_annulus_mean",
    "msrm_abs_context_mean",
    "msrm_abs_ratio",
    "msrm_core_mean",
    "msrm_context_mean",
    "msrm_core_delta",
    "msrm_ring_coverage",
    "msrm_ring_balance",
    "best_ring_radius_m",
    "best_ring_coverage",
    "best_ring_balance",
    "best_ring_abs_ratio",
    "ring_radius_sharpness",
    "dominant_scale_m",
    "dominant_scale_ratio",
    "scale_ratio_spread",
    "scale_response_entropy",
]

META_FIELDS = [
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
    "dem_path",
]

METRIC_FIELDS = [
    "subset",
    "variant",
    "rows",
    "positives",
    "negatives",
    "roc_auc",
    "average_precision",
    "precision_at_50",
    "recall_at_50",
    "median_positive_rank",
]


def scale_tag(radius_m: float) -> str:
    return f"_{int(round(radius_m))}m"


def scale_feature_names(scales: list[float]) -> list[str]:
    names = []
    for radius in scales:
        tag = scale_tag(radius)
        for template in SCALE_FEATURE_TEMPLATES:
            names.append(template.format(tag=tag))
    return names


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, dialect="excel-tab"))


def write_tsv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=fields,
            dialect="excel-tab",
            extrasaction="ignore",
            lineterminator="\n",
        )
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
        result = float(value)
    except (TypeError, ValueError):
        return fallback
    return result if math.isfinite(result) else fallback


def parse_scale_list(raw: str) -> list[float]:
    values = [float(item.strip()) for item in raw.split(",") if item.strip()]
    if not values:
        raise SystemExit("empty scale list")
    return sorted(values)


def safe_ratio(num: float, den: float) -> float:
    if abs(den) < 1e-9:
        return 0.0
    return num / den


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


def mask_mean(values) -> float:
    import numpy as np

    values = values[np.isfinite(values)]
    return float(values.mean()) if values.size else 0.0


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def geometry_cache(shape: tuple[int, int]):
    import numpy as np

    height, width = shape
    yy, xx = np.indices((height, width))
    cx = (width - 1) / 2.0
    cy = (height - 1) / 2.0
    distance_px = np.hypot(xx - cx, yy - cy)
    angles = (np.arctan2(yy - cy, xx - cx) + 2.0 * math.pi) % (2.0 * math.pi)
    sectors = np.floor(angles / (2.0 * math.pi / RING_SECTORS)).astype("int16")
    return distance_px, sectors


def ring_masks(distance_px, shape: tuple[int, int], radius_m: float, resolution: float):
    height, width = shape
    radius_px = clamp(radius_m / max(resolution, 0.1), 3.0, min(width, height) * 0.45)
    annulus_half = clamp(radius_px * 0.16, 2.0, 8.0)
    core = distance_px <= radius_px * 0.62
    annulus = (distance_px >= radius_px - annulus_half) & (distance_px <= radius_px + annulus_half)
    context_start = radius_px + annulus_half * 2.0
    context_end = min(min(width, height) * 0.48, max(context_start + annulus_half * 3.0, radius_px * 1.9))
    context = (distance_px >= context_start) & (distance_px <= context_end)
    if not context.any():
        context = distance_px >= min(radius_px * 1.25, min(width, height) * 0.40)
    return core, annulus, context


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


def build_multiscale_relief(dem, resolution: float, scales_m: list[float]):
    """Return per-scale LRM rasters plus the composed MSRM raster."""
    import numpy as np

    layers = []
    for radius_m in scales_m:
        radius_px = max(1, int(round(radius_m / max(resolution, 0.1))))
        layers.append((dem - box_mean(dem, radius_px)).astype("float32"))
    # Normalise each scale by its own spread so no single radius dominates
    # the composite purely because larger windows leave larger residuals.
    scaled = []
    for layer in layers:
        spread = float(np.nanstd(layer))
        scaled.append(layer / spread if spread > 1e-9 else layer)
    msrm = np.mean(np.stack(scaled, axis=0), axis=0).astype("float32")
    return layers, msrm


def shannon_entropy(values: list[float]) -> float:
    positives = [value for value in values if value > 0]
    total = sum(positives)
    if total <= 1e-9 or len(positives) < 2:
        return 0.0
    entropy = 0.0
    for value in positives:
        p = value / total
        entropy -= p * math.log(p)
    return entropy / math.log(len(positives))


def msrm_feature_row(
    row: dict[str, str],
    master: dict[str, str],
    scales_m: list[float],
    ring_radii_m: list[float],
) -> dict[str, str]:
    import numpy as np
    import rasterio

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
        dem = fill_nodata(dem)
        layers, msrm = build_multiscale_relief(dem, resolution, scales_m)
        distance_px, sectors = geometry_cache(dem.shape)
        msrm_abs = np.abs(msrm)

        features: dict[str, float] = {}

        # Per-scale ring response at the reference radius, so the model can
        # see which castro size the terrain actually answers to.
        scale_ratios = []
        for radius_m, layer in zip(scales_m, layers):
            core, annulus, context = ring_masks(distance_px, dem.shape, 120.0, resolution)
            layer_abs = np.abs(layer)
            abs_annulus = mask_mean(layer_abs[annulus])
            abs_context = mask_mean(layer_abs[context])
            ratio = safe_ratio(abs_annulus, abs_context)
            core_delta = mask_mean(layer[core]) - mask_mean(layer[context])
            tag = scale_tag(radius_m)
            features[f"lrm{tag}_abs_ratio"] = ratio
            features[f"lrm{tag}_core_delta"] = core_delta
            scale_ratios.append(ratio)

        best_scale_index = max(range(len(scale_ratios)), key=lambda idx: scale_ratios[idx])
        features["dominant_scale_m"] = float(scales_m[best_scale_index])
        features["dominant_scale_ratio"] = scale_ratios[best_scale_index]
        features["scale_ratio_spread"] = (
            float(max(scale_ratios) - min(scale_ratios)) if scale_ratios else 0.0
        )
        features["scale_response_entropy"] = shannon_entropy(scale_ratios)

        # Sweep ring radii on the composite so a small castro and a large
        # one are both allowed to peak at their own geometry.
        sweep = []
        for radius_m in ring_radii_m:
            core, annulus, context = ring_masks(distance_px, dem.shape, radius_m, resolution)
            coverage, balance = ring_sector_metrics(msrm_abs, annulus, context, sectors)
            abs_annulus = mask_mean(msrm_abs[annulus])
            abs_context = mask_mean(msrm_abs[context])
            sweep.append(
                {
                    "radius_m": radius_m,
                    "coverage": coverage,
                    "balance": balance,
                    "abs_ratio": safe_ratio(abs_annulus, abs_context),
                }
            )
        best = max(sweep, key=lambda item: item["coverage"] * item["balance"])
        coverages = [item["coverage"] for item in sweep]
        features["best_ring_radius_m"] = float(best["radius_m"])
        features["best_ring_coverage"] = float(best["coverage"])
        features["best_ring_balance"] = float(best["balance"])
        features["best_ring_abs_ratio"] = float(best["abs_ratio"])
        features["ring_radius_sharpness"] = (
            float(max(coverages) - statistics.mean(coverages)) if coverages else 0.0
        )

        core, annulus, context = ring_masks(distance_px, dem.shape, 120.0, resolution)
        coverage, balance = ring_sector_metrics(msrm_abs, annulus, context, sectors)
        msrm_abs_annulus = mask_mean(msrm_abs[annulus])
        msrm_abs_context = mask_mean(msrm_abs[context])
        msrm_core = mask_mean(msrm[core])
        msrm_context = mask_mean(msrm[context])
        features["msrm_abs_annulus_mean"] = msrm_abs_annulus
        features["msrm_abs_context_mean"] = msrm_abs_context
        features["msrm_abs_ratio"] = safe_ratio(msrm_abs_annulus, msrm_abs_context)
        features["msrm_core_mean"] = msrm_core
        features["msrm_context_mean"] = msrm_context
        features["msrm_core_delta"] = msrm_core - msrm_context
        features["msrm_ring_coverage"] = coverage
        features["msrm_ring_balance"] = balance

        for name, value in features.items():
            result[name] = f"{float(value):.8f}"
        result["status"] = "ok"
    except Exception as exc:
        result["error"] = str(exc)
    return result


_WORKER_STATE: dict[str, object] = {}


def _worker_init(scales_m: list[float], ring_radii_m: list[float]) -> None:
    _WORKER_STATE["scales_m"] = scales_m
    _WORKER_STATE["ring_radii_m"] = ring_radii_m


def _worker_run(payload: tuple[dict[str, str], dict[str, str]]) -> dict[str, str]:
    row, master = payload
    return msrm_feature_row(
        row,
        master,
        _WORKER_STATE["scales_m"],  # type: ignore[arg-type]
        _WORKER_STATE["ring_radii_m"],  # type: ignore[arg-type]
    )


def robust_z(values: list[float]) -> list[float]:
    median = statistics.median(values) if values else 0.0
    deviations = [abs(value - median) for value in values]
    mad = statistics.median(deviations) if deviations else 0.0
    scale = 1.4826 * mad if mad > 1e-9 else (statistics.pstdev(values) if len(values) > 1 else 1.0)
    if scale <= 1e-9:
        scale = 1.0
    return [(value - median) / scale for value in values]


def rank_desc(scores: list[float]) -> list[int]:
    order = sorted(range(len(scores)), key=lambda idx: scores[idx], reverse=True)
    ranks = [0] * len(scores)
    for rank, idx in enumerate(order, start=1):
        ranks[idx] = rank
    return ranks


def roc_auc(labels: list[int], scores: list[float]) -> float:
    pairs = sorted(zip(scores, labels), key=lambda item: item[0])
    positives = sum(labels)
    negatives = len(labels) - positives
    if positives == 0 or negatives == 0:
        return 0.0
    rank_sum = 0.0
    index = 0
    rank = 1
    while index < len(pairs):
        stop = index
        while stop + 1 < len(pairs) and pairs[stop + 1][0] == pairs[index][0]:
            stop += 1
        average_rank = (rank + (rank + (stop - index))) / 2.0
        for cursor in range(index, stop + 1):
            if pairs[cursor][1] == 1:
                rank_sum += average_rank
        rank += stop - index + 1
        index = stop + 1
    return (rank_sum - positives * (positives + 1) / 2.0) / (positives * negatives)


def average_precision(labels: list[int], scores: list[float]) -> float:
    order = sorted(range(len(scores)), key=lambda idx: scores[idx], reverse=True)
    positives = sum(labels)
    if positives == 0:
        return 0.0
    hits = 0
    total = 0.0
    for position, idx in enumerate(order, start=1):
        if labels[idx] == 1:
            hits += 1
            total += hits / position
    return total / positives


def precision_recall_at_k(labels: list[int], scores: list[float], k: int) -> tuple[float, float]:
    order = sorted(range(len(scores)), key=lambda idx: scores[idx], reverse=True)
    positives = sum(labels)
    top = order[:k]
    hits = sum(labels[idx] for idx in top)
    precision = hits / len(top) if top else 0.0
    recall = hits / positives if positives else 0.0
    return precision, recall


def metric_row(subset: str, variant: str, labels: list[int], scores: list[float]) -> dict[str, str]:
    positives = sum(labels)
    ranks = rank_desc(scores)
    positive_ranks = [ranks[idx] for idx, label in enumerate(labels) if label == 1]
    precision_50, recall_50 = precision_recall_at_k(labels, scores, 50)
    return {
        "subset": subset,
        "variant": variant,
        "rows": str(len(labels)),
        "positives": str(positives),
        "negatives": str(len(labels) - positives),
        "roc_auc": f"{roc_auc(labels, scores):.6f}",
        "average_precision": f"{average_precision(labels, scores):.6f}",
        "precision_at_50": f"{precision_50:.6f}",
        "recall_at_50": f"{recall_50:.6f}",
        "median_positive_rank": f"{statistics.median(positive_ranks):.1f}" if positive_ranks else "",
    }


def build_msrm_score(ok_rows: list[dict[str, str]]) -> list[float]:
    components = {
        "best_ring_coverage": 0.30,
        "best_ring_abs_ratio": 0.25,
        "msrm_core_delta": 0.20,
        "best_ring_balance": 0.15,
        "ring_radius_sharpness": 0.10,
    }
    scores = [0.0 for _row in ok_rows]
    for feature_name, weight in components.items():
        z_values = robust_z([parse_float(row.get(feature_name)) for row in ok_rows])
        for index, z_value in enumerate(z_values):
            scores[index] += weight * z_value
    return scores


def subset_rows(rows: list[dict[str, str]], subset: str) -> list[dict[str, str]]:
    if subset == "all":
        return rows
    if subset == "holdouts":
        return [row for row in rows if row["final_split"] in {"test_o_val", "test_trasancos"}]
    return [row for row in rows if row["final_split"] == subset]


def write_report(
    path: Path,
    args: argparse.Namespace,
    ok_rows: list[dict[str, str]],
    failed_rows: list[dict[str, str]],
    metrics: list[dict[str, str]],
    scales_m: list[float],
    ring_radii_m: list[float],
) -> None:
    from collections import Counter

    dominant = Counter(row.get("dominant_scale_m", "") for row in ok_rows)
    best_radius = Counter(row.get("best_ring_radius_m", "") for row in ok_rows)
    positives = [row for row in ok_rows if str(row.get("label_class", "")).strip() in {"1", "positive"}]
    dominant_pos = Counter(row.get("dominant_scale_m", "") for row in positives)

    lines = [
        "# Weak-label MSRM multi-scale relief features v1",
        "",
        f"Generated at: `{GENERATED_AT}`",
        f"Scales (m): `{', '.join(str(int(value)) for value in scales_m)}`",
        f"Ring radii swept (m): `{', '.join(str(int(value)) for value in ring_radii_m)}`",
        "",
        "## Coverage",
        "",
        f"- rows processed: `{len(ok_rows) + len(failed_rows)}`",
        f"- rows ok: `{len(ok_rows)}`",
        f"- rows failed: `{len(failed_rows)}`",
        "",
        "## Dominant scale distribution (all rows)",
        "",
        "| dominant_scale_m | rows |",
        "|---|---:|",
    ]
    for value, count in sorted(dominant.items(), key=lambda item: parse_float(item[0])):
        lines.append(f"| `{value}` | `{count}` |")
    lines += [
        "",
        "## Dominant scale distribution (positives only)",
        "",
        "| dominant_scale_m | positives |",
        "|---|---:|",
    ]
    for value, count in sorted(dominant_pos.items(), key=lambda item: parse_float(item[0])):
        lines.append(f"| `{value}` | `{count}` |")
    lines += [
        "",
        "## Best ring radius distribution",
        "",
        "| best_ring_radius_m | rows |",
        "|---|---:|",
    ]
    for value, count in sorted(best_radius.items(), key=lambda item: parse_float(item[0])):
        lines.append(f"| `{value}` | `{count}` |")
    lines += [
        "",
        "## Standalone MSRM ranking metrics",
        "",
        "| subset | rows | positives | ROC-AUC | AP | P@50 | R@50 | median positive rank |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in metrics:
        lines.append(
            f"| `{row['subset']}` | `{row['rows']}` | `{row['positives']}` | `{row['roc_auc']}` | "
            f"`{row['average_precision']}` | `{row['precision_at_50']}` | `{row['recall_at_50']}` | "
            f"`{row['median_positive_rank']}` |"
        )
    lines += [
        "",
        "## Reading",
        "",
        "These features are not a replacement ranker. They exist so the fusion",
        "model can stop assuming a single castro size: `dominant_scale_m` and",
        "`best_ring_radius_m` report the geometry each row actually answers to,",
        "and the per-scale ratios expose small and large enclosures separately.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--master", type=Path, default=DEFAULT_MASTER)
    parser.add_argument(
        "--relief-manifest",
        type=Path,
        action="append",
        default=None,
        help="Relief WCS manifest TSV; repeat to merge several splits.",
    )
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--dataset-name", default="full")
    parser.add_argument("--scales-m", default=DEFAULT_SCALES_M)
    parser.add_argument("--ring-radii-m", default=DEFAULT_RING_RADII_M)
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    parser.add_argument("--limit", type=int, default=0)
    return parser.parse_args()


def resolve_args(args: argparse.Namespace) -> argparse.Namespace:
    if not args.relief_manifest:
        args.relief_manifest = [
            PROJECT_ROOT / "data/weak-label-relief-v1/weak_label_relief_wcs_holdouts.tsv",
            PROJECT_ROOT / "data/weak-label-relief-v1/weak_label_relief_wcs_val.tsv",
            PROJECT_ROOT / "data/weak-label-relief-v1/weak_label_relief_wcs_test.tsv",
            PROJECT_ROOT / "data/weak-label-relief-v1/weak_label_relief_wcs_train.tsv",
        ]
    args.relief_manifest = [
        path if path.is_absolute() else PROJECT_ROOT / path for path in args.relief_manifest
    ]
    for attr in ("master", "out_dir", "report"):
        value = getattr(args, attr)
        setattr(args, attr, value if value.is_absolute() else PROJECT_ROOT / value)
    return args


def main() -> None:
    args = resolve_args(parse_args())
    scales_m = parse_scale_list(args.scales_m)
    ring_radii_m = parse_scale_list(args.ring_radii_m)

    master = {row["sample_id"]: row for row in read_tsv(args.master)}

    relief_rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for manifest in args.relief_manifest:
        if not manifest.exists():
            continue
        for row in read_tsv(manifest):
            key = row.get("tile_id") or row.get("sample_id", "")
            if key in seen:
                continue
            seen.add(key)
            relief_rows.append(row)
    if not relief_rows:
        raise SystemExit("no relief manifest rows found")
    if args.limit:
        relief_rows = relief_rows[: args.limit]

    payloads = [(row, master.get(row.get("sample_id", ""), {})) for row in relief_rows]

    feature_rows: list[dict[str, str]] = []
    workers = max(1, int(args.workers))
    if workers == 1:
        _worker_init(scales_m, ring_radii_m)
        for payload in payloads:
            feature_rows.append(_worker_run(payload))
    else:
        with ProcessPoolExecutor(
            max_workers=workers,
            initializer=_worker_init,
            initargs=(scales_m, ring_radii_m),
        ) as pool:
            futures = [pool.submit(_worker_run, payload) for payload in payloads]
            for future in as_completed(futures):
                feature_rows.append(future.result())

    feature_rows.sort(key=lambda row: row.get("tile_id", ""))
    ok_rows = [row for row in feature_rows if row["status"] == "ok"]
    failed_rows = [row for row in feature_rows if row["status"] != "ok"]

    feature_names = BASE_FEATURE_NAMES + scale_feature_names(scales_m)
    feature_fields = META_FIELDS + feature_names + ["status", "error"]

    out_features = args.out_dir / f"weak_label_msrm_features_{args.dataset_name}.tsv"
    write_tsv(out_features, feature_rows, feature_fields)

    scores = build_msrm_score(ok_rows)
    ranks = rank_desc(scores)
    score_rows = []
    for index, row in enumerate(ok_rows):
        score_rows.append(
            {
                **{key: row.get(key, "") for key in META_FIELDS},
                "msrm_score": f"{scores[index]:.8f}",
                "rank_desc": str(ranks[index]),
                "dominant_scale_m": row.get("dominant_scale_m", ""),
                "best_ring_radius_m": row.get("best_ring_radius_m", ""),
            }
        )
    out_scores = args.out_dir / f"weak_label_msrm_scores_{args.dataset_name}.tsv"
    write_tsv(
        out_scores,
        score_rows,
        META_FIELDS + ["msrm_score", "rank_desc", "dominant_scale_m", "best_ring_radius_m"],
    )

    metrics = []
    for subset in ("all", "train", "val", "test", "holdouts", "test_trasancos", "test_o_val"):
        rows = subset_rows(ok_rows, subset)
        if len(rows) < 5:
            continue
        labels = [1 if str(row.get("label_class", "")).strip() in {"1", "positive"} else 0 for row in rows]
        if sum(labels) == 0 or sum(labels) == len(labels):
            continue
        subset_scores = build_msrm_score(rows)
        metrics.append(metric_row(subset, "msrm_standalone", labels, subset_scores))
    out_metrics = args.out_dir / f"weak_label_msrm_metrics_{args.dataset_name}.tsv"
    write_tsv(out_metrics, metrics, METRIC_FIELDS)

    write_report(args.report, args, ok_rows, failed_rows, metrics, scales_m, ring_radii_m)

    print(f"rows_ok={len(ok_rows)} rows_failed={len(failed_rows)}")
    print(f"features={rel_to_project(out_features)}")
    print(f"scores={rel_to_project(out_scores)}")
    print(f"metrics={rel_to_project(out_metrics)}")
    print(f"report={rel_to_project(args.report)}")


if __name__ == "__main__":
    main()
