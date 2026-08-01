#!/usr/bin/env python3
"""Train an auditable RGB+relief weak-label chip ranker."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from evaluate_weak_label_relief_score_variants import VARIANT_COMPONENTS, VARIANT_NAMES
from train_weak_label_rgb_baseline import (
    FEATURE_NAMES as RGB_FEATURE_NAMES,
    METRIC_FIELDS,
    average_precision,
    fit_logistic,
    parse_float,
    precision_recall_at,
    predict,
    ranks_desc,
    read_tsv,
    rel_to_project,
    roc_auc,
    write_tsv,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RGB_FEATURES = PROJECT_ROOT / "data/weak-label-baseline-v1/weak_label_rgb_baseline_features.tsv"
DEFAULT_RGB_METRICS = PROJECT_ROOT / "data/weak-label-baseline-v1/weak_label_rgb_baseline_metrics.tsv"
DEFAULT_RELIEF_FEATURES = [
    PROJECT_ROOT / "data/weak-label-relief-v1/weak_label_relief_features_train_mini.tsv",
    PROJECT_ROOT / "data/weak-label-relief-v1/weak_label_relief_features_val.tsv",
    PROJECT_ROOT / "data/weak-label-relief-v1/weak_label_relief_features_holdouts.tsv",
]
DEFAULT_RELIEF_METRICS = [
    PROJECT_ROOT / "data/weak-label-relief-v1/weak_label_relief_metrics_train_mini.tsv",
    PROJECT_ROOT / "data/weak-label-relief-v1/weak_label_relief_metrics_val.tsv",
    PROJECT_ROOT / "data/weak-label-relief-v1/weak_label_relief_metrics_holdouts.tsv",
]
OUT_DIR = PROJECT_ROOT / "data/weak-label-fusion-v1"
DEFAULT_REPORT = PROJECT_ROOT / "reports/weak_label_rgb_relief_baseline_v1.md"

GENERATED_AT = "2026-08-01T00:00:00Z"

RELIEF_FEATURE_NAMES = [
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

FUSION_FEATURE_NAMES = [
    *[f"rgb__{name}" for name in RGB_FEATURE_NAMES],
    *[f"relief__{name}" for name in RELIEF_FEATURE_NAMES],
    *[f"relief_variant__{name}" for name in VARIANT_NAMES],
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
    "name",
    "municipality",
    "parish",
    "morphology_proxy",
    "negative_type",
    *FUSION_FEATURE_NAMES,
    "error",
    "status",
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
    "name",
    "municipality",
    "parish",
    "morphology_proxy",
    "negative_type",
    "probability",
    "rank_desc_in_dataset",
    "error",
    "status",
]


def require_runtime() -> None:
    missing = []
    for module in ("numpy",):
        try:
            __import__(module)
        except Exception:
            missing.append(module)
    if missing:
        raise SystemExit(f"Missing Python modules: {', '.join(missing)}")


def artifact_path(args: argparse.Namespace, suffix: str) -> Path:
    return args.out_dir / f"{args.artifact_prefix}_{suffix}"


def dataset_from_relief_path(path: Path) -> str:
    stem = path.stem
    prefix = "weak_label_relief_features_"
    return stem[len(prefix) :] if stem.startswith(prefix) else stem


def load_relief_feature_rows(paths: list[Path]) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for path in paths:
        dataset = dataset_from_relief_path(path)
        for row in read_tsv(path):
            enriched = dict(row)
            enriched["dataset"] = dataset
            out[row["sample_id"]] = enriched
    return out


def robust_params(rows: list[dict[str, str]], feature_name: str) -> tuple[float, float]:
    values = [parse_float(row.get(feature_name, "0")) for row in rows]
    median = statistics.median(values) if values else 0.0
    deviations = [abs(value - median) for value in values]
    mad = statistics.median(deviations) if deviations else 0.0
    scale = 1.4826 * mad if mad > 1e-9 else (statistics.pstdev(values) if len(values) > 1 else 1.0)
    return median, scale if scale > 1e-9 else 1.0


def fit_variant_scaler(train_relief_rows: list[dict[str, str]]) -> dict[str, tuple[float, float]]:
    feature_names = sorted({name for components in VARIANT_COMPONENTS.values() for name in components})
    return {name: robust_params(train_relief_rows, name) for name in feature_names}


def variant_scores(row: dict[str, str], scaler: dict[str, tuple[float, float]]) -> dict[str, float]:
    scores = {}
    for variant_name, components in VARIANT_COMPONENTS.items():
        total = 0.0
        for feature_name, weight in components.items():
            median, scale = scaler[feature_name]
            total += weight * ((parse_float(row.get(feature_name, "0")) - median) / scale)
        scores[variant_name] = total
    scores["archetype_max"] = max(scores.values()) if scores else 0.0
    return scores


def build_feature_rows(rgb_rows: list[dict[str, str]], relief_by_sample: dict[str, dict[str, str]], train_dataset: str) -> list[dict[str, str]]:
    train_relief_rows = [
        relief_by_sample[row["sample_id"]]
        for row in rgb_rows
        if row.get("dataset") == train_dataset
        and row.get("status") == "ok"
        and row.get("sample_id") in relief_by_sample
        and relief_by_sample[row["sample_id"]].get("status") == "ok"
    ]
    scaler = fit_variant_scaler(train_relief_rows)
    out = []
    for rgb_row in rgb_rows:
        relief_row = relief_by_sample.get(rgb_row.get("sample_id", ""))
        result = {
            "dataset": rgb_row.get("dataset", ""),
            "tile_id": rgb_row.get("tile_id", ""),
            "sample_id": rgb_row.get("sample_id", ""),
            "bank_id": rgb_row.get("bank_id", ""),
            "label_class": rgb_row.get("label_class", ""),
            "label_role": rgb_row.get("label_role", ""),
            "final_split": rgb_row.get("final_split", ""),
            "country": rgb_row.get("country", ""),
            "name": rgb_row.get("name", ""),
            "municipality": rgb_row.get("municipality", ""),
            "parish": rgb_row.get("parish", ""),
            "morphology_proxy": rgb_row.get("morphology_proxy", ""),
            "negative_type": rgb_row.get("negative_type", ""),
            "status": "failed",
            "error": "",
        }
        if rgb_row.get("status") != "ok":
            result["error"] = f"rgb_status:{rgb_row.get('status', '')}:{rgb_row.get('error', '')}"
        elif relief_row is None:
            result["error"] = "missing_relief_features"
        elif relief_row.get("status") != "ok":
            result["error"] = f"relief_status:{relief_row.get('status', '')}:{relief_row.get('error', '')}"
        else:
            for name in RGB_FEATURE_NAMES:
                result[f"rgb__{name}"] = rgb_row.get(name, "0")
            for name in RELIEF_FEATURE_NAMES:
                result[f"relief__{name}"] = relief_row.get(name, "0")
            for name, value in variant_scores(relief_row, scaler).items():
                result[f"relief_variant__{name}"] = f"{value:.8f}"
            result["status"] = "ok"
        out.append(result)
    return out


def matrix_from_rows(rows: list[dict[str, str]]):
    import numpy as np

    ok_rows = [row for row in rows if row["status"] == "ok"]
    x = np.array([[parse_float(row[name]) for name in FUSION_FEATURE_NAMES] for row in ok_rows], dtype="float64")
    y = np.array([int(row["label_class"]) for row in ok_rows], dtype="float64")
    return ok_rows, x, y


def build_score_rows(feature_rows: list[dict[str, str]], model: dict) -> list[dict[str, str]]:
    ok_rows, x, _y = matrix_from_rows(feature_rows)
    probs = predict(model, x)
    dataset_to_indices: dict[str, list[int]] = defaultdict(list)
    for idx, row in enumerate(ok_rows):
        dataset_to_indices[row["dataset"]].append(idx)
    ranks_by_idx: dict[int, int] = {}
    for _dataset, indices in dataset_to_indices.items():
        ranks = ranks_desc([float(probs[idx]) for idx in indices])
        for rank, idx in zip(ranks, indices):
            ranks_by_idx[idx] = rank
    score_rows = []
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
                "name": row["name"],
                "municipality": row["municipality"],
                "parish": row["parish"],
                "morphology_proxy": row["morphology_proxy"],
                "negative_type": row["negative_type"],
                "probability": f"{float(probs[idx]):.8f}",
                "rank_desc_in_dataset": str(ranks_by_idx[idx]),
                "status": row["status"],
                "error": row["error"],
            }
        )
    return score_rows


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


def build_metric_rows(score_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    rows = []
    by_dataset: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in score_rows:
        by_dataset[row["dataset"]].append(row)
    for dataset, dataset_rows in sorted(by_dataset.items()):
        rows.append(metric_row(dataset, "all", dataset_rows))
        by_split: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in dataset_rows:
            by_split[row["final_split"]].append(row)
        if len(by_split) > 1:
            for split, split_rows in sorted(by_split.items()):
                rows.append(metric_row(dataset, f"split:{split}", split_rows))
    return rows


def metric_lookup(rows: list[dict[str, str]], dataset: str, subset: str = "all") -> dict[str, str]:
    return next((row for row in rows if row["dataset"] == dataset and row["subset"] == subset), {})


def signal_status(metric_rows: list[dict[str, str]]) -> str:
    val = metric_lookup(metric_rows, "val")
    holdouts = metric_lookup(metric_rows, "holdouts")
    try:
        val_auc = float(val.get("roc_auc", "nan"))
        holdout_auc = float(holdouts.get("roc_auc", "nan"))
    except ValueError:
        return "fusion_signal_not_evaluable"
    if val_auc >= 0.70 and holdout_auc >= 0.70:
        return "rgb_relief_ranking_signal_present"
    if val_auc >= 0.60 or holdout_auc >= 0.60:
        return "rgb_relief_signal_ambiguous"
    return "rgb_relief_signal_not_reliable"


def load_reference_metrics(path: Path, label: str) -> list[str]:
    if not path.exists():
        return []
    rows = read_tsv(path)
    out = []
    for row in rows:
        if row.get("subset") == "all" and row.get("dataset", row.get("subset")) in {"val", "holdouts", "train_mini"}:
            dataset = row.get("dataset", "holdouts")
            out.append(f"- {label} {dataset}: ROC-AUC `{row['roc_auc']}`, AP `{row['average_precision']}`.")
        elif label == "relief" and row.get("subset") == "all":
            dataset = path.stem.replace("weak_label_relief_metrics_", "")
            out.append(f"- {label} {dataset}: ROC-AUC `{row['roc_auc']}`, AP `{row['average_precision']}`.")
    return out


def top_rows(score_rows: list[dict[str, str]], dataset: str, limit: int = 10) -> list[dict[str, str]]:
    rows = [row for row in score_rows if row["dataset"] == dataset]
    return sorted(rows, key=lambda row: parse_float(row["probability"]), reverse=True)[:limit]


def o_val_rows(score_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(
        [row for row in score_rows if row["final_split"] == "test_o_val"],
        key=lambda row: parse_float(row["probability"]),
        reverse=True,
    )


def write_model(path: Path, model: dict) -> None:
    payload = {
        "generated_at": GENERATED_AT,
        "model": "numpy_logistic_regression_handcrafted_rgb_relief_features",
        "feature_names": FUSION_FEATURE_NAMES,
        "weights": [float(value) for value in model["weights"]],
        "feature_mean": [float(value) for value in model["feature_mean"]],
        "feature_std": [float(value) for value in model["feature_std"]],
        "last_loss": float(model["last_loss"]),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_report(path: Path, args: argparse.Namespace, feature_rows: list[dict[str, str]], score_rows: list[dict[str, str]], metric_rows: list[dict[str, str]], model: dict) -> None:
    feature_path = artifact_path(args, "features.tsv")
    score_path = artifact_path(args, "scores.tsv")
    metric_path = artifact_path(args, "metrics.tsv")
    model_path = artifact_path(args, "model.json")
    feature_counts = Counter(row["status"] for row in feature_rows)
    dataset_counts = Counter(row["dataset"] for row in score_rows)
    class_counts = Counter((row["dataset"], row["label_role"]) for row in score_rows)
    lines = [
        "# Weak-label RGB+relief baseline v1",
        "",
        f"Generated: {GENERATED_AT}",
        "",
        "## What This Is",
        "",
        "Minimal fusion ranker over weak labels. It joins the existing RGB handcrafted features with MDT5 relief features and morphology-aware relief variants.",
        "It is a ranking sanity check for review prioritization, not an archaeological detector.",
        "",
        "## Files",
        "",
        f"- RGB feature TSV: `{rel_to_project(args.rgb_features)}`",
        f"- Relief feature TSVs: {', '.join(f'`{rel_to_project(path)}`' for path in args.relief_features)}",
        f"- Feature table: `{rel_to_project(feature_path)}`",
        f"- Score table: `{rel_to_project(score_path)}`",
        f"- Metrics table: `{rel_to_project(metric_path)}`",
        f"- Model weights JSON: `{rel_to_project(model_path)}`",
        "",
        "## Training Setup",
        "",
        f"- Train dataset: `{args.train_dataset}`",
        f"- Feature count: {len(FUSION_FEATURE_NAMES)}",
        f"- Logistic epochs: {args.epochs}",
        f"- Learning rate: {args.learning_rate}",
        f"- L2: {args.l2}",
        f"- Final train loss: {model['last_loss']:.6f}",
        f"- Signal status: `{signal_status(metric_rows)}`",
        "",
        "## Feature Rows",
        "",
    ]
    for status, count in sorted(feature_counts.items()):
        lines.append(f"- {status}: {count}")
    lines.extend(["", "## Dataset Counts", ""])
    for dataset, count in sorted(dataset_counts.items()):
        lines.append(f"- {dataset}: {count} rows ({class_counts[(dataset, 'positive')]} positives, {class_counts[(dataset, 'hard_negative')]} hard negatives)")
    lines.extend(["", "## Metrics", ""])
    lines.append("| Dataset | Subset | Rows | Pos | Neg | ROC-AUC | AP | P@50 | R@50 | Best pos rank | Median pos rank |")
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for row in metric_rows:
        lines.append(
            "| {dataset} | {subset} | {rows} | {positives} | {negatives} | {roc_auc} | {average_precision} | {precision_at_50} | {recall_at_50} | {best_positive_rank} | {median_positive_rank} |".format(
                **row
            )
        )
    reference = load_reference_metrics(args.rgb_metrics, "RGB")
    for metric_path in args.relief_metrics:
        reference.extend(load_reference_metrics(metric_path, "relief"))
    if reference:
        lines.extend(["", "## References", ""])
        lines.extend(reference)
    lines.extend(["", "## Top Scores", ""])
    available_datasets = {row["dataset"] for row in score_rows}
    for dataset in ("test", "holdouts", "val"):
        if dataset not in available_datasets:
            continue
        lines.append(f"### {dataset}")
        lines.append("")
        lines.append("| Rank | Split | Class | Score | Name | Municipality |")
        lines.append("|---:|---|---:|---:|---|---|")
        for row in top_rows(score_rows, dataset, limit=10):
            lines.append(f"| {row['rank_desc_in_dataset']} | {row['final_split']} | {row['label_class']} | {row['probability']} | `{row['name'][:80]}` | {row['municipality']} |")
        lines.append("")
    o_val = o_val_rows(score_rows)
    if o_val:
        lines.extend(["## O Val Reading", ""])
        for row in o_val:
            label = "positive" if row["label_class"] == "1" else "hard_negative"
            lines.append(f"- rank `{row['rank_desc_in_dataset']}`: `{row['name']}` ({label}), score `{row['probability']}`.")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "Fusion should improve `val` without collapsing the spatial holdouts. If it only improves the tiny O Val subset, treat it as overfit/error-analysis evidence.",
            "The current labels are weak and negatives are not guaranteed true absences, so this model is for prioritization and ablation, not discovery claims.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rgb-features", type=Path, default=DEFAULT_RGB_FEATURES)
    parser.add_argument("--rgb-metrics", type=Path, default=DEFAULT_RGB_METRICS)
    parser.add_argument("--relief-features", type=Path, action="append", default=None)
    parser.add_argument("--relief-metrics", type=Path, action="append", default=None)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--artifact-prefix", default="weak_label_rgb_relief")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--train-dataset", default="train_mini")
    parser.add_argument("--epochs", type=int, default=900)
    parser.add_argument("--learning-rate", type=float, default=0.06)
    parser.add_argument("--l2", type=float, default=0.02)
    return parser.parse_args()


def resolve_args(args: argparse.Namespace) -> argparse.Namespace:
    args.rgb_features = args.rgb_features if args.rgb_features.is_absolute() else PROJECT_ROOT / args.rgb_features
    args.rgb_metrics = args.rgb_metrics if args.rgb_metrics.is_absolute() else PROJECT_ROOT / args.rgb_metrics
    args.relief_features = [
        path if path.is_absolute() else PROJECT_ROOT / path
        for path in (args.relief_features or DEFAULT_RELIEF_FEATURES)
    ]
    args.relief_metrics = [
        path if path.is_absolute() else PROJECT_ROOT / path
        for path in (args.relief_metrics or DEFAULT_RELIEF_METRICS)
    ]
    args.out_dir = args.out_dir if args.out_dir.is_absolute() else PROJECT_ROOT / args.out_dir
    if not args.artifact_prefix or any(char in args.artifact_prefix for char in "/\\"):
        raise SystemExit("--artifact-prefix must be a non-empty file-name prefix, not a path.")
    args.report = args.report if args.report.is_absolute() else PROJECT_ROOT / args.report
    return args


def main() -> None:
    require_runtime()
    args = resolve_args(parse_args())
    rgb_rows = read_tsv(args.rgb_features)
    relief_by_sample = load_relief_feature_rows(args.relief_features)
    feature_rows = build_feature_rows(rgb_rows, relief_by_sample, args.train_dataset)
    train_rows = [row for row in feature_rows if row["dataset"] == args.train_dataset and row["status"] == "ok"]
    if not train_rows:
        raise SystemExit("No valid train rows found for fusion baseline.")
    _train_ok, x_train, y_train = matrix_from_rows(train_rows)
    if len(set(int(value) for value in y_train)) < 2:
        raise SystemExit("Train rows must include both classes.")
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
