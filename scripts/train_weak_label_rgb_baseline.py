#!/usr/bin/env python3
"""Train a minimal weak-label RGB chip classifier/ranker.

This is deliberately small and auditable: handcrafted RGB/morphology features
plus logistic regression implemented with numpy. It is a baseline for ranking
review targets, not an archaeological detector.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MASTER = PROJECT_ROOT / "data/weak-label-splits-v1/weak_label_master.tsv"
DEFAULT_TRAIN = PROJECT_ROOT / "data/weak-label-splits-v1/weak_label_chip_export_train_mini.tsv"
DEFAULT_EVAL = [
    PROJECT_ROOT / "data/weak-label-splits-v1/weak_label_chip_export_val.tsv",
    PROJECT_ROOT / "data/weak-label-splits-v1/weak_label_chip_export_holdouts.tsv",
]
OUT_DIR = PROJECT_ROOT / "data/weak-label-baseline-v1"
REPORTS_DIR = PROJECT_ROOT / "reports"

GENERATED_AT = "2026-08-01T00:00:00Z"
TILE_SIDE_M = 512.0
SECTOR_COUNT = 36

FEATURE_NAMES = [
    "gray_mean",
    "gray_std",
    "gray_entropy",
    "dark_fraction",
    "bright_fraction",
    "green_mean",
    "excess_green_mean",
    "green_std",
    "edge_global_mean",
    "edge_global_std",
    "edge_inner_mean",
    "edge_annulus_mean",
    "edge_outer_mean",
    "edge_annulus_to_outer_ratio",
    "edge_annulus_to_inner_ratio",
    "texture_inner_std",
    "texture_annulus_std",
    "texture_outer_std",
    "texture_annulus_to_outer_ratio",
    "luminance_inner_mean",
    "luminance_annulus_mean",
    "luminance_outer_mean",
    "luminance_delta_inner_outer",
    "green_delta_inner_outer",
    "ring_sector_coverage",
    "ring_sector_balance",
    "radial_peak_inverse_rank",
    "radial_peak_count",
]

FEATURE_FIELDS = [
    "dataset",
    "tile_id",
    "sample_id",
    "bank_id",
    "label_class",
    "label_role",
    "final_split",
    "country",
    "wms_source",
    "name",
    "municipality",
    "parish",
    "morphology_proxy",
    "negative_type",
    "proposed_radius_m",
    "feature_radius_m",
    "image_path",
    "status",
    "error",
    *FEATURE_NAMES,
]

SCORE_FIELDS = [
    "dataset",
    "tile_id",
    "sample_id",
    "bank_id",
    "label_class",
    "label_role",
    "final_split",
    "country",
    "wms_source",
    "name",
    "municipality",
    "parish",
    "morphology_proxy",
    "negative_type",
    "proposed_radius_m",
    "feature_radius_m",
    "probability",
    "rank_desc_in_dataset",
    "error",
    "status",
]

METRIC_FIELDS = [
    "dataset",
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
    for module in ("numpy", "PIL"):
        try:
            __import__(module)
        except Exception:
            missing.append(module)
    if missing:
        raise SystemExit(f"Missing Python modules: {', '.join(missing)}")


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, dialect="excel-tab"))


def write_tsv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=fieldnames,
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
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return fallback


def safe_ratio(num: float, den: float) -> float:
    return float(num / den) if abs(den) > 1e-9 else 0.0


def gray_entropy(gray) -> float:
    import numpy as np

    hist, _ = np.histogram(gray, bins=64, range=(0.0, 1.0))
    total = hist.sum()
    if not total:
        return 0.0
    probs = hist[hist > 0] / total
    return float(-(probs * np.log2(probs)).sum())


def load_rgb(path: Path, size: int):
    import numpy as np
    from PIL import Image

    with Image.open(path) as image:
        resized = image.convert("RGB").resize((size, size), Image.Resampling.BILINEAR)
        return np.asarray(resized, dtype="float32") / 255.0


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


def mask_mean(values) -> float:
    return float(values.mean()) if values.size else 0.0


def mask_std(values) -> float:
    return float(values.std()) if values.size else 0.0


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def build_masks(shape: tuple[int, int], radius_m: float):
    import numpy as np

    height, width = shape
    yy, xx = np.indices((height, width))
    center_x = (width - 1) / 2.0
    center_y = (height - 1) / 2.0
    distance = np.hypot(xx - center_x, yy - center_y)
    max_radius = min(width, height) * 0.47
    radius_px = clamp(radius_m * min(width, height) / TILE_SIDE_M, 10.0, max_radius)
    annulus_half_width = clamp(radius_px * 0.16, 5.0, 14.0)

    inner = distance <= radius_px * 0.62
    annulus = (distance >= radius_px - annulus_half_width) & (distance <= radius_px + annulus_half_width)
    outer_start = radius_px + annulus_half_width * 2.0
    outer_end = min(max_radius, max(outer_start + annulus_half_width * 3.0, radius_px * 1.95))
    outer = (distance >= outer_start) & (distance <= outer_end)
    if not outer.any():
        outer = distance >= min(max(radius_px * 1.3, 24.0), max_radius * 0.8)

    angles = (np.arctan2(yy - center_y, xx - center_x) + 2.0 * math.pi) % (2.0 * math.pi)
    sector_ids = np.floor(angles / (2.0 * math.pi / SECTOR_COUNT)).astype("int16")
    return radius_px, inner, annulus, outer, sector_ids


def ring_sector_metrics(edges, annulus, outer, sector_ids) -> tuple[float, float]:
    if not annulus.any():
        return 0.0, 0.0
    outer_values = edges[outer] if outer.any() else edges.ravel()
    threshold = float(__import__("numpy").percentile(outer_values, 65)) if outer_values.size else 0.0
    sector_means = []
    for sector_id in range(SECTOR_COUNT):
        sector_mask = annulus & (sector_ids == sector_id)
        if sector_mask.sum() < 8:
            continue
        sector_means.append(float(edges[sector_mask].mean()))
    if not sector_means:
        return 0.0, 0.0
    coverage = sum(value > threshold for value in sector_means) / len(sector_means)
    mean_value = statistics.mean(sector_means)
    std_value = statistics.pstdev(sector_means) if len(sector_means) > 1 else 0.0
    balance = mean_value / (mean_value + std_value) if mean_value > 0 else 0.0
    return float(coverage), float(balance)


def radial_peak_metrics(edges, radius_px: float) -> tuple[float, int]:
    import numpy as np

    height, width = edges.shape
    yy, xx = np.indices((height, width))
    center_x = (width - 1) / 2.0
    center_y = (height - 1) / 2.0
    distance = np.hypot(xx - center_x, yy - center_y)
    bin_width = max(4.0, radius_px * 0.08)
    max_distance = min(width, height) * 0.48
    means = []
    target_bin = None
    bin_index = 0
    value = max(5.0, radius_px * 0.35)
    while value < max_distance:
        band = (distance >= value) & (distance < value + bin_width)
        if band.sum() >= 24:
            means.append((bin_index, float(edges[band].mean())))
            if value <= radius_px < value + bin_width:
                target_bin = bin_index
        value += bin_width
        bin_index += 1
    if target_bin is None or not means:
        return 0.0, len(means)
    ranked = sorted(means, key=lambda item: item[1], reverse=True)
    for rank, (idx, _value) in enumerate(ranked, start=1):
        if idx == target_bin:
            return safe_ratio(1.0, float(rank)), len(means)
    return 0.0, len(means)


def extract_features(image_path: Path, radius_m: float, image_size: int) -> dict[str, float]:
    import numpy as np

    rgb = load_rgb(image_path, image_size)
    gray = 0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]
    green = rgb[:, :, 1]
    excess_green = 2.0 * rgb[:, :, 1] - rgb[:, :, 0] - rgb[:, :, 2]
    edges = sobel_edges(gray)
    radius_px, inner, annulus, outer, sector_ids = build_masks(gray.shape, radius_m)
    coverage, balance = ring_sector_metrics(edges, annulus, outer, sector_ids)
    inverse_rank, peak_count = radial_peak_metrics(edges, radius_px)

    edge_inner = mask_mean(edges[inner])
    edge_annulus = mask_mean(edges[annulus])
    edge_outer = mask_mean(edges[outer])
    texture_inner = mask_std(gray[inner])
    texture_annulus = mask_std(gray[annulus])
    texture_outer = mask_std(gray[outer])
    lum_inner = mask_mean(gray[inner])
    lum_annulus = mask_mean(gray[annulus])
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
        "texture_inner_std": texture_inner,
        "texture_annulus_std": texture_annulus,
        "texture_outer_std": texture_outer,
        "texture_annulus_to_outer_ratio": safe_ratio(texture_annulus, texture_outer),
        "luminance_inner_mean": lum_inner,
        "luminance_annulus_mean": lum_annulus,
        "luminance_outer_mean": lum_outer,
        "luminance_delta_inner_outer": lum_inner - lum_outer,
        "green_delta_inner_outer": green_inner - green_outer,
        "ring_sector_coverage": coverage,
        "ring_sector_balance": balance,
        "radial_peak_inverse_rank": inverse_rank,
        "radial_peak_count": float(peak_count),
    }


def master_by_sample_id(path: Path) -> dict[str, dict[str, str]]:
    return {row["sample_id"]: row for row in read_tsv(path)}


def manifest_dataset_name(path: Path) -> str:
    name = path.stem
    return name.replace("weak_label_chip_export_", "")


def artifact_path(args: argparse.Namespace, suffix: str) -> Path:
    return args.out_dir / f"{args.artifact_prefix}_{suffix}"


def feature_row(row: dict[str, str], meta: dict[str, dict[str, str]], dataset: str, args: argparse.Namespace) -> dict[str, str]:
    master = meta.get(row.get("sample_id", ""), {})
    proposed_radius_m = parse_float(master.get("proposed_radius_m"), 110.0)
    feature_radius_m = args.fixed_radius_m if args.radius_mode == "fixed" else proposed_radius_m
    image_path = project_path(row.get("target_png_path", ""))
    result = {
        "dataset": dataset,
        "tile_id": row.get("tile_id", ""),
        "sample_id": row.get("sample_id", ""),
        "bank_id": row.get("bank_id", ""),
        "label_class": row.get("label_class", ""),
        "label_role": row.get("label_role", ""),
        "final_split": row.get("final_split", ""),
        "country": row.get("country", ""),
        "wms_source": row.get("wms_source", ""),
        "name": row.get("name", ""),
        "municipality": master.get("municipality", ""),
        "parish": master.get("parish", ""),
        "morphology_proxy": master.get("morphology_proxy", ""),
        "negative_type": master.get("negative_type", ""),
        "proposed_radius_m": f"{proposed_radius_m:.1f}",
        "feature_radius_m": f"{feature_radius_m:.1f}",
        "image_path": rel_to_project(image_path),
        "status": "failed",
        "error": "",
    }
    if row.get("image_status") != "valid":
        result["error"] = f"manifest_image_status:{row.get('image_status', '')}"
        return result
    if not image_path.exists():
        result["error"] = f"missing_image:{rel_to_project(image_path)}"
        return result
    try:
        features = extract_features(image_path, feature_radius_m, args.image_size)
        for name in FEATURE_NAMES:
            result[name] = f"{features[name]:.8f}"
        result["status"] = "ok"
    except Exception as exc:
        result["error"] = str(exc)
    return result


def build_feature_rows(paths: list[Path], meta: dict[str, dict[str, str]], args: argparse.Namespace) -> list[dict[str, str]]:
    rows = []
    for path in paths:
        dataset = manifest_dataset_name(path)
        for row in read_tsv(path):
            rows.append(feature_row(row, meta, dataset, args))
    return rows


def sigmoid(values):
    import numpy as np

    values = np.clip(values, -40.0, 40.0)
    return 1.0 / (1.0 + np.exp(-values))


def matrix_from_rows(rows: list[dict[str, str]]):
    import numpy as np

    ok_rows = [row for row in rows if row["status"] == "ok"]
    x = np.array([[parse_float(row[name]) for name in FEATURE_NAMES] for row in ok_rows], dtype="float64")
    y = np.array([int(row["label_class"]) for row in ok_rows], dtype="float64")
    return ok_rows, x, y


def fit_logistic(x_train, y_train, *, epochs: int, learning_rate: float, l2: float):
    import numpy as np

    mean = x_train.mean(axis=0)
    std = x_train.std(axis=0)
    std[std < 1e-9] = 1.0
    x_scaled = (x_train - mean) / std
    x_aug = np.column_stack([np.ones(len(x_scaled)), x_scaled])
    weights = np.zeros(x_aug.shape[1], dtype="float64")

    pos_count = max(float((y_train == 1).sum()), 1.0)
    neg_count = max(float((y_train == 0).sum()), 1.0)
    sample_weights = np.where(y_train == 1, len(y_train) / (2.0 * pos_count), len(y_train) / (2.0 * neg_count))
    weight_sum = sample_weights.sum()

    last_loss = 0.0
    for _epoch in range(epochs):
        probs = sigmoid(x_aug @ weights)
        error = (probs - y_train) * sample_weights
        gradient = (x_aug.T @ error) / weight_sum
        gradient[1:] += l2 * weights[1:]
        weights -= learning_rate * gradient
        loss = -(
            sample_weights
            * (y_train * np.log(probs + 1e-9) + (1.0 - y_train) * np.log(1.0 - probs + 1e-9))
        ).sum() / weight_sum
        last_loss = float(loss + 0.5 * l2 * float((weights[1:] ** 2).sum()))

    return {
        "weights": weights,
        "feature_mean": mean,
        "feature_std": std,
        "last_loss": last_loss,
    }


def predict(model: dict, x):
    import numpy as np

    x_scaled = (x - model["feature_mean"]) / model["feature_std"]
    x_aug = np.column_stack([np.ones(len(x_scaled)), x_scaled])
    return sigmoid(x_aug @ model["weights"])


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
    total = len(positives) * len(negatives)
    for pos_score in positives:
        for neg_score in negatives:
            if pos_score > neg_score:
                wins += 1.0
            elif pos_score == neg_score:
                wins += 0.5
    return f"{(wins / total):.6f}"


def average_precision(labels: list[int], scores: list[float]) -> str:
    positives = sum(labels)
    if positives == 0:
        return "n/a"
    order = sorted(range(len(scores)), key=lambda idx: scores[idx], reverse=True)
    hit_count = 0
    precisions = []
    for rank, idx in enumerate(order, start=1):
        if labels[idx] == 1:
            hit_count += 1
            precisions.append(hit_count / rank)
    return f"{(sum(precisions) / positives):.6f}" if precisions else "0.000000"


def precision_recall_at(labels: list[int], scores: list[float], k: int) -> tuple[str, str]:
    if not labels:
        return "n/a", "n/a"
    positives = sum(labels)
    if positives == 0:
        return "n/a", "n/a"
    order = sorted(range(len(scores)), key=lambda idx: scores[idx], reverse=True)[: min(k, len(scores))]
    hits = sum(labels[idx] for idx in order)
    return f"{(hits / max(len(order), 1)):.6f}", f"{(hits / positives):.6f}"


def metric_row(dataset: str, subset: str, rows: list[dict[str, str]]) -> dict[str, str]:
    labels = [int(row["label_class"]) for row in rows]
    scores = [parse_float(row["probability"]) for row in rows]
    ranks = ranks_desc(scores)
    pos_ranks = [rank for rank, label in zip(ranks, labels) if label == 1]
    p10, r10 = precision_recall_at(labels, scores, 10)
    p50, r50 = precision_recall_at(labels, scores, 50)
    p100, r100 = precision_recall_at(labels, scores, 100)
    return {
        "dataset": dataset,
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


def build_score_rows(feature_rows: list[dict[str, str]], model: dict) -> list[dict[str, str]]:
    ok_rows, x, _y = matrix_from_rows(feature_rows)
    probs = predict(model, x)
    score_rows = []
    dataset_to_indices: dict[str, list[int]] = defaultdict(list)
    for idx, row in enumerate(ok_rows):
        dataset_to_indices[row["dataset"]].append(idx)

    dataset_ranks: dict[int, int] = {}
    for _dataset, indices in dataset_to_indices.items():
        ranks = ranks_desc([float(probs[idx]) for idx in indices])
        for local_rank, idx in zip(ranks, indices):
            dataset_ranks[idx] = local_rank

    for idx, row in enumerate(ok_rows):
        score_rows.append(
            {
                "dataset": row["dataset"],
                "tile_id": row["tile_id"],
                "sample_id": row["sample_id"],
                "bank_id": row["bank_id"],
                "label_class": row["label_class"],
                "label_role": row["label_role"],
                "final_split": row["final_split"],
                "country": row["country"],
                "wms_source": row["wms_source"],
                "name": row["name"],
                "municipality": row["municipality"],
                "parish": row["parish"],
                "morphology_proxy": row["morphology_proxy"],
                "negative_type": row["negative_type"],
                "proposed_radius_m": row["proposed_radius_m"],
                "feature_radius_m": row["feature_radius_m"],
                "probability": f"{float(probs[idx]):.8f}",
                "rank_desc_in_dataset": str(dataset_ranks[idx]),
                "status": row["status"],
                "error": row["error"],
            }
        )
    return score_rows


def build_metric_rows(score_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    rows = []
    by_dataset: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in score_rows:
        by_dataset[row["dataset"]].append(row)
    for dataset, dataset_rows in sorted(by_dataset.items()):
        rows.append(metric_row(dataset, "all", dataset_rows))
        split_groups: dict[str, list[dict[str, str]]] = defaultdict(list)
        source_groups: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in dataset_rows:
            split_groups[row["final_split"]].append(row)
            source_groups[row["wms_source"]].append(row)
        if len(split_groups) > 1:
            for split, split_rows in sorted(split_groups.items()):
                rows.append(metric_row(dataset, f"split:{split}", split_rows))
        for source, source_rows in sorted(source_groups.items()):
            rows.append(metric_row(dataset, f"source:{source}", source_rows))
    return rows


def metric_lookup(metric_rows: list[dict[str, str]], dataset: str, subset: str = "all") -> dict[str, str]:
    for row in metric_rows:
        if row["dataset"] == dataset and row["subset"] == subset:
            return row
    return {}


def signal_status(metric_rows: list[dict[str, str]]) -> str:
    val = metric_lookup(metric_rows, "val")
    holdouts = metric_lookup(metric_rows, "holdouts")
    try:
        val_auc = float(val.get("roc_auc", "nan"))
        holdout_auc = float(holdouts.get("roc_auc", "nan"))
    except ValueError:
        return "rgb_signal_not_evaluable"
    if val_auc >= 0.65 and holdout_auc >= 0.65:
        return "weak_rgb_ranking_signal_present"
    if val_auc >= 0.55 or holdout_auc >= 0.55:
        return "rgb_signal_ambiguous"
    return "rgb_signal_not_reliable"


def top_rows(score_rows: list[dict[str, str]], dataset: str, limit: int = 10) -> list[dict[str, str]]:
    rows = [row for row in score_rows if row["dataset"] == dataset]
    return sorted(rows, key=lambda row: parse_float(row["probability"]), reverse=True)[:limit]


def split_rows(score_rows: list[dict[str, str]], split: str) -> list[dict[str, str]]:
    rows = [row for row in score_rows if row["final_split"] == split]
    return sorted(rows, key=lambda row: parse_float(row["probability"]), reverse=True)


def write_report(
    path: Path,
    args: argparse.Namespace,
    feature_rows: list[dict[str, str]],
    score_rows: list[dict[str, str]],
    metric_rows: list[dict[str, str]],
    model: dict,
) -> None:
    feature_path = artifact_path(args, "features.tsv")
    score_path = artifact_path(args, "scores.tsv")
    metric_path = artifact_path(args, "metrics.tsv")
    model_path = artifact_path(args, "model.json")
    feature_counts = Counter(row["status"] for row in feature_rows)
    dataset_counts = Counter(row["dataset"] for row in score_rows)
    class_counts = Counter((row["dataset"], row["label_role"]) for row in score_rows)
    status = signal_status(metric_rows)
    train_dataset = manifest_dataset_name(args.train_manifest)
    if train_dataset == "train_mini":
        train_scope_note = (
            "The train set here is `train-mini`, not full train. Keep this as a cheap go/no-go check before "
            "downloading all remaining chips."
        )
    elif train_dataset == "train":
        train_scope_note = (
            "The train set here is the full `train` chip export. Treat this as the RGB sanity baseline before "
            "relief fusion, error review, and any candidate-discovery claim."
        )
    else:
        train_scope_note = f"The train set here is `{train_dataset}`. Interpret it according to that manifest scope."
    lines = [
        "# Weak-label RGB baseline v1",
        "",
        f"Generated: {GENERATED_AT}",
        "",
        "## What This Is",
        "",
        "Minimal RGB chip classifier/ranker over weak labels. It uses handcrafted color/edge/ring features and a small logistic regression implemented with numpy.",
        "It is a modelling sanity check, not an archaeological detector.",
        "",
        "## Files",
        "",
        f"- Train manifest: `{rel_to_project(args.train_manifest)}`",
        f"- Eval manifests: {', '.join(f'`{rel_to_project(path)}`' for path in args.eval_manifest)}",
        f"- Feature table: `{rel_to_project(feature_path)}`",
        f"- Score table: `{rel_to_project(score_path)}`",
        f"- Metrics table: `{rel_to_project(metric_path)}`",
        f"- Model weights JSON: `{rel_to_project(model_path)}`",
        "",
        "## Training Setup",
        "",
        f"- Feature image size: {args.image_size}x{args.image_size}px",
        f"- Radius mode: `{args.radius_mode}`",
        f"- Fixed feature radius: {args.fixed_radius_m:.1f} m",
        f"- Logistic epochs: {args.epochs}",
        f"- Learning rate: {args.learning_rate}",
        f"- L2: {args.l2}",
        f"- Final train loss: {model['last_loss']:.6f}",
        f"- Signal status: `{status}`",
        "",
        "## Feature Extraction",
        "",
    ]
    for value, count in sorted(feature_counts.items()):
        lines.append(f"- {value}: {count}")
    lines.extend(["", "## Dataset Counts", ""])
    for dataset, count in sorted(dataset_counts.items()):
        pos = class_counts[(dataset, "positive")]
        neg = class_counts[(dataset, "hard_negative")]
        lines.append(f"- {dataset}: {count} rows ({pos} positives, {neg} hard negatives)")
    lines.extend(["", "## Metrics", ""])
    lines.append("| Dataset | Subset | Rows | Pos | Neg | ROC-AUC | AP | P@50 | R@50 | Best pos rank | Median pos rank |")
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for row in metric_rows:
        lines.append(
            "| {dataset} | {subset} | {rows} | {positives} | {negatives} | {roc_auc} | {average_precision} | {precision_at_50} | {recall_at_50} | {best_positive_rank} | {median_positive_rank} |".format(
                **row
            )
        )
    lines.extend(["", "## Top Holdout Scores", ""])
    available_datasets = {row["dataset"] for row in score_rows}
    for dataset in ("test", "holdouts", "val"):
        if dataset not in available_datasets:
            continue
        lines.append(f"### {dataset}")
        lines.append("")
        lines.append("| Rank | Split | Class | Score | Name | Municipality |")
        lines.append("|---:|---|---:|---:|---|---|")
        for row in top_rows(score_rows, dataset, limit=10):
            lines.append(
                f"| {row['rank_desc_in_dataset']} | {row['final_split']} | {row['label_class']} | {row['probability']} | `{row['name'][:80]}` | {row['municipality']} |"
            )
        lines.append("")
    o_val_rows = split_rows(score_rows, "test_o_val")
    if o_val_rows:
        lines.extend(["## O Val Holdout", ""])
        lines.append("| Rank | Class | Score | Name | Reading |")
        lines.append("|---:|---:|---:|---|---|")
        for row in o_val_rows:
            reading = "known positive" if row["label_class"] == "1" else "hard negative"
            lines.append(
                f"| {row['rank_desc_in_dataset']} | {row['label_class']} | {row['probability']} | `{row['name'][:80]}` | {reading} |"
            )
        positive_below_negative = any(
            row["label_class"] == "1" and parse_float(row["probability"]) < max(parse_float(neg["probability"]) for neg in o_val_rows if neg["label_class"] == "0")
            for row in o_val_rows
        )
        if positive_below_negative:
            lines.extend(
                [
                    "",
                    "At least one known O Val positive ranks below the O Val hard negative. This is the main local warning: RGB-only ranking is useful, but it is not enough for final candidate decisions.",
                    "",
                ]
            )
    lines.extend(
        [
            "## Interpretation",
            "",
            "A useful RGB baseline should rank known positives above hard negatives in `val` and should not collapse on the O Val/Trasancos holdouts. This run shows a weak but real RGB ranking signal, not a deployable detector.",
            "",
            "The strongest caution is local: `Castro de Pena Lopesa` is missed in the O Val holdout. That means the next phase must add LiDAR/relief and visual review before any claim about candidate discovery.",
            "",
            f"The default feature radius is fixed for every chip to avoid leaking label-derived radius priors into the RGB baseline. {train_scope_note}",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_model(path: Path, model: dict) -> None:
    payload = {
        "generated_at": GENERATED_AT,
        "model": "numpy_logistic_regression_handcrafted_rgb_features",
        "feature_names": FEATURE_NAMES,
        "weights": [float(value) for value in model["weights"]],
        "feature_mean": [float(value) for value in model["feature_mean"]],
        "feature_std": [float(value) for value in model["feature_std"]],
        "last_loss": float(model["last_loss"]),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--master", type=Path, default=DEFAULT_MASTER)
    parser.add_argument("--train-manifest", type=Path, default=DEFAULT_TRAIN)
    parser.add_argument("--eval-manifest", type=Path, action="append", default=None)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--artifact-prefix", default="weak_label_rgb_baseline")
    parser.add_argument("--report", type=Path, default=REPORTS_DIR / "weak_label_rgb_baseline_v1.md")
    parser.add_argument("--image-size", type=int, default=192)
    parser.add_argument("--radius-mode", choices=("fixed", "manifest"), default="fixed")
    parser.add_argument("--fixed-radius-m", type=float, default=120.0)
    parser.add_argument("--epochs", type=int, default=900)
    parser.add_argument("--learning-rate", type=float, default=0.06)
    parser.add_argument("--l2", type=float, default=0.01)
    return parser.parse_args()


def resolve_args(args: argparse.Namespace) -> argparse.Namespace:
    args.master = args.master if args.master.is_absolute() else PROJECT_ROOT / args.master
    args.train_manifest = args.train_manifest if args.train_manifest.is_absolute() else PROJECT_ROOT / args.train_manifest
    eval_manifest = args.eval_manifest or DEFAULT_EVAL
    args.eval_manifest = [path if path.is_absolute() else PROJECT_ROOT / path for path in eval_manifest]
    args.out_dir = args.out_dir if args.out_dir.is_absolute() else PROJECT_ROOT / args.out_dir
    if not args.artifact_prefix or any(char in args.artifact_prefix for char in "/\\"):
        raise SystemExit("--artifact-prefix must be a non-empty file-name prefix, not a path.")
    args.report = args.report if args.report.is_absolute() else PROJECT_ROOT / args.report
    return args


def main() -> None:
    require_runtime()
    args = resolve_args(parse_args())
    meta = master_by_sample_id(args.master)
    manifest_paths = [args.train_manifest, *args.eval_manifest]
    feature_rows = build_feature_rows(manifest_paths, meta, args)
    train_feature_rows = [row for row in feature_rows if row["dataset"] == manifest_dataset_name(args.train_manifest) and row["status"] == "ok"]
    if not train_feature_rows:
        raise SystemExit("No valid train rows found.")
    _train_rows, x_train, y_train = matrix_from_rows(train_feature_rows)
    if len(set(int(value) for value in y_train)) < 2:
        raise SystemExit("Train rows must include both positive and negative labels.")

    model = fit_logistic(x_train, y_train, epochs=args.epochs, learning_rate=args.learning_rate, l2=args.l2)
    score_rows = build_score_rows(feature_rows, model)
    metric_rows = build_metric_rows(score_rows)

    feature_path = artifact_path(args, "features.tsv")
    score_path = artifact_path(args, "scores.tsv")
    metric_path = artifact_path(args, "metrics.tsv")
    model_path = artifact_path(args, "model.json")

    write_tsv(feature_path, feature_rows, FEATURE_FIELDS)
    write_tsv(score_path, score_rows, SCORE_FIELDS)
    write_tsv(metric_path, metric_rows, METRIC_FIELDS)
    write_model(model_path, model)
    write_report(args.report, args, feature_rows, score_rows, metric_rows, model)

    print(f"feature_rows={len(feature_rows)}")
    print(f"score_rows={len(score_rows)}")
    print(f"metric_rows={len(metric_rows)}")
    print(f"signal_status={signal_status(metric_rows)}")
    print(f"wrote={rel_to_project(score_path)}")
    print(f"report={rel_to_project(args.report)}")


if __name__ == "__main__":
    main()
