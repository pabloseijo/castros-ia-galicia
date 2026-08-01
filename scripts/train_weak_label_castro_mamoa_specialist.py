#!/usr/bin/env python3
"""Train a weak-label specialist for castro-vs-mamoa confusion."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from train_weak_label_rgb_baseline import (
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
from train_weak_label_rgb_relief_baseline import FUSION_FEATURE_NAMES


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FEATURES = PROJECT_ROOT / "data/weak-label-fusion-v1/weak_label_rgb_relief_features.tsv"
DEFAULT_FUSION_SCORES = PROJECT_ROOT / "data/weak-label-fusion-v1/weak_label_rgb_relief_scores.tsv"
DEFAULT_PRIORITY_SCORES = PROJECT_ROOT / "data/weak-label-fusion-v1/weak_label_priority_blend_scores.tsv"
OUT_DIR = PROJECT_ROOT / "data/weak-label-fusion-v1"
DEFAULT_REPORT = PROJECT_ROOT / "reports/weak_label_castro_mamoa_specialist_v1.md"

GENERATED_AT = "2026-08-01T00:00:00Z"
SPECIALIST_NEGATIVE_TYPE = "megalithic_mound"

SCORE_NAMES = [
    "fusion_reference",
    "castro_mamoa_specialist",
    "fusion_specialist_mean",
    "fusion_specialist_product",
    "fusion70_specialist30",
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
    "fusion_probability",
    "specialist_probability",
    "fusion_specialist_mean",
    "fusion_specialist_product",
    "fusion70_specialist30",
    "fusion_rank",
    "specialist_rank",
    "mean_rank",
    "product_rank",
    "fusion70_rank",
    "max_safety_rank",
]

METRIC_FIELDS_WITH_SCORE = ["score_name", *METRIC_FIELDS]


def require_runtime() -> None:
    missing = []
    for module in ("numpy",):
        try:
            __import__(module)
        except Exception:
            missing.append(module)
    if missing:
        raise SystemExit(f"Missing Python modules: {', '.join(missing)}")


def score_lookup(path: Path) -> dict[str, dict[str, str]]:
    return {row["sample_id"]: row for row in read_tsv(path)}


def max_safety_lookup(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    return {
        row["sample_id"]: row
        for row in read_tsv(path)
        if row.get("blend") == "max_safety"
    }


def training_rows(rows: list[dict[str, str]], train_dataset: str) -> list[dict[str, str]]:
    return [
        row
        for row in rows
        if row.get("status") == "ok"
        and row.get("dataset") == train_dataset
        and (row.get("label_class") == "1" or row.get("negative_type") == SPECIALIST_NEGATIVE_TYPE)
    ]


def matrix(rows: list[dict[str, str]]):
    import numpy as np

    x = np.array([[parse_float(row[name]) for name in FUSION_FEATURE_NAMES] for row in rows], dtype="float64")
    y = np.array([int(row["label_class"]) for row in rows], dtype="float64")
    return x, y


def ok_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in rows if row.get("status") == "ok"]


def build_score_rows(feature_rows: list[dict[str, str]], model: dict, fusion_by_sample: dict[str, dict[str, str]], max_by_sample: dict[str, dict[str, str]]) -> list[dict[str, str]]:
    rows = ok_rows(feature_rows)
    x, _y = matrix(rows)
    specialist_probs = predict(model, x)
    raw_rows = []
    for row, specialist_probability in zip(rows, specialist_probs):
        fusion = fusion_by_sample[row["sample_id"]]
        fusion_probability = parse_float(fusion.get("probability", "0"))
        specialist_probability = float(specialist_probability)
        raw_rows.append(
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
                "fusion_probability": f"{fusion_probability:.8f}",
                "specialist_probability": f"{specialist_probability:.8f}",
                "fusion_specialist_mean": f"{((fusion_probability + specialist_probability) / 2.0):.8f}",
                "fusion_specialist_product": f"{(fusion_probability * specialist_probability):.8f}",
                "fusion70_specialist30": f"{(0.7 * fusion_probability + 0.3 * specialist_probability):.8f}",
                "fusion_rank": "",
                "specialist_rank": "",
                "mean_rank": "",
                "product_rank": "",
                "fusion70_rank": "",
                "max_safety_rank": max_by_sample.get(row["sample_id"], {}).get("rank_desc_in_dataset", ""),
            }
        )

    rank_fields = {
        "fusion_probability": "fusion_rank",
        "specialist_probability": "specialist_rank",
        "fusion_specialist_mean": "mean_rank",
        "fusion_specialist_product": "product_rank",
        "fusion70_specialist30": "fusion70_rank",
    }
    by_dataset: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(raw_rows):
        by_dataset[row["dataset"]].append(index)
    for _dataset, indices in by_dataset.items():
        for score_field, rank_field in rank_fields.items():
            ranks = ranks_desc([parse_float(raw_rows[index][score_field]) for index in indices])
            for rank, index in zip(ranks, indices):
                raw_rows[index][rank_field] = str(rank)
    return raw_rows


def score_value(row: dict[str, str], score_name: str) -> str:
    if score_name == "fusion_reference":
        return row["fusion_probability"]
    if score_name == "castro_mamoa_specialist":
        return row["specialist_probability"]
    if score_name == "fusion_specialist_mean":
        return row["fusion_specialist_mean"]
    if score_name == "fusion_specialist_product":
        return row["fusion_specialist_product"]
    if score_name == "fusion70_specialist30":
        return row["fusion70_specialist30"]
    raise KeyError(score_name)


def metric_row(score_name: str, dataset: str, subset: str, rows: list[dict[str, str]]) -> dict[str, str]:
    labels = [int(row["label_class"]) for row in rows]
    scores = [parse_float(score_value(row, score_name)) for row in rows]
    ranks = ranks_desc(scores)
    pos_ranks = [rank for rank, label in zip(ranks, labels) if label == 1]
    p10, r10 = precision_recall_at(labels, scores, 10)
    p50, r50 = precision_recall_at(labels, scores, 50)
    p100, r100 = precision_recall_at(labels, scores, 100)
    return {
        "score_name": score_name,
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
    out = []
    by_dataset: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in score_rows:
        by_dataset[row["dataset"]].append(row)
    for score_name in SCORE_NAMES:
        for dataset, rows in sorted(by_dataset.items()):
            out.append(metric_row(score_name, dataset, "all", rows))
            mamoa_rows = [row for row in rows if row["label_class"] == "1" or row["negative_type"] == SPECIALIST_NEGATIVE_TYPE]
            if len(mamoa_rows) != len(rows):
                out.append(metric_row(score_name, dataset, "castro_vs_mamoa", mamoa_rows))
            by_split: dict[str, list[dict[str, str]]] = defaultdict(list)
            for row in rows:
                by_split[row["final_split"]].append(row)
            if len(by_split) > 1:
                for split, split_rows in sorted(by_split.items()):
                    out.append(metric_row(score_name, dataset, f"split:{split}", split_rows))
    return out


def metric_lookup(metrics: list[dict[str, str]], score_name: str, dataset: str, subset: str = "all") -> dict[str, str]:
    return next((row for row in metrics if row["score_name"] == score_name and row["dataset"] == dataset and row["subset"] == subset), {})


def write_model(path: Path, model: dict, train_counts: Counter, args: argparse.Namespace) -> None:
    payload = {
        "generated_at": GENERATED_AT,
        "model": "numpy_logistic_regression_castro_vs_mamoa_specialist",
        "train_dataset": args.train_dataset,
        "specialist_negative_type": SPECIALIST_NEGATIVE_TYPE,
        "train_counts": dict(train_counts),
        "feature_names": FUSION_FEATURE_NAMES,
        "weights": [float(value) for value in model["weights"]],
        "feature_mean": [float(value) for value in model["feature_mean"]],
        "feature_std": [float(value) for value in model["feature_std"]],
        "last_loss": float(model["last_loss"]),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def o_val_rows(score_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in score_rows if row["final_split"] == "test_o_val"]


def write_report(path: Path, args: argparse.Namespace, score_rows: list[dict[str, str]], metrics: list[dict[str, str]], train_counts: Counter, model: dict) -> None:
    fusion_holdout = metric_lookup(metrics, "fusion_reference", "holdouts")
    mean_holdout = metric_lookup(metrics, "fusion_specialist_mean", "holdouts")
    specialist_holdout = metric_lookup(metrics, "castro_mamoa_specialist", "holdouts")
    mean_val = metric_lookup(metrics, "fusion_specialist_mean", "val")
    lines = [
        "# Weak-label castro-vs-mamoa specialist v1",
        "",
        f"Generated: {GENERATED_AT}",
        "",
        "## What This Is",
        "",
        "A specialist ranker for the main false-positive pattern found in the error review batch: castros confused with mamoas/megalithic mounds.",
        "It is trained only on `train_mini` positives plus `train_mini` negatives whose `negative_type` is `megalithic_mound`.",
        "This is an error-analysis layer, not an archaeological detector.",
        "",
        "## Files",
        "",
        f"- Feature table: `{rel_to_project(args.features)}`",
        f"- Score table: `data/weak-label-fusion-v1/weak_label_castro_mamoa_specialist_scores.tsv`",
        f"- Metrics table: `data/weak-label-fusion-v1/weak_label_castro_mamoa_specialist_metrics.tsv`",
        f"- Model JSON: `data/weak-label-fusion-v1/weak_label_castro_mamoa_specialist_model.json`",
        "",
        "## Training Setup",
        "",
        f"- Train dataset: `{args.train_dataset}`",
        f"- Positives: `{train_counts['positive']}`",
        f"- Mamoa negatives: `{train_counts[SPECIALIST_NEGATIVE_TYPE]}`",
        f"- Feature count: `{len(FUSION_FEATURE_NAMES)}`",
        f"- Final train loss: `{model['last_loss']:.6f}`",
        "",
        "## Main Result",
        "",
        f"- Fusion holdouts: ROC-AUC `{fusion_holdout.get('roc_auc', 'n/a')}`, AP `{fusion_holdout.get('average_precision', 'n/a')}`, P@50 `{fusion_holdout.get('precision_at_50', 'n/a')}`.",
        f"- Specialist holdouts: ROC-AUC `{specialist_holdout.get('roc_auc', 'n/a')}`, AP `{specialist_holdout.get('average_precision', 'n/a')}`, P@50 `{specialist_holdout.get('precision_at_50', 'n/a')}`.",
        f"- Fusion+specialist mean holdouts: ROC-AUC `{mean_holdout.get('roc_auc', 'n/a')}`, AP `{mean_holdout.get('average_precision', 'n/a')}`, P@50 `{mean_holdout.get('precision_at_50', 'n/a')}`.",
        f"- Fusion+specialist mean val: ROC-AUC `{mean_val.get('roc_auc', 'n/a')}`, AP `{mean_val.get('average_precision', 'n/a')}`, P@50 `{mean_val.get('precision_at_50', 'n/a')}`.",
        "",
        "## Metrics",
        "",
        "| Score | Dataset | Subset | Rows | Pos | Neg | ROC-AUC | AP | P@50 | R@50 | Median pos rank |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in metrics:
        if row["subset"] == "all" or row["subset"] in {"castro_vs_mamoa", "split:test_o_val", "split:test_trasancos"}:
            lines.append(
                "| {score_name} | {dataset} | {subset} | {rows} | {positives} | {negatives} | {roc_auc} | {average_precision} | {precision_at_50} | {recall_at_50} | {median_positive_rank} |".format(
                    **row
                )
            )

    lines.extend(
        [
            "",
            "## O Val Reading",
            "",
            "| Fusion rank | Specialist rank | Mean rank | Product rank | Max-safety rank | Class | Fusion | Specialist | Name |",
            "|---:|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for row in sorted(o_val_rows(score_rows), key=lambda item: int(item["fusion_rank"])):
        lines.append(
            f"| {row['fusion_rank']} | {row['specialist_rank']} | {row['mean_rank']} | {row['product_rank']} | {row['max_safety_rank']} | {row['label_class']} | {row['fusion_probability']} | {row['specialist_probability']} | `{row['name']}` |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- The specialist improves the explicit castro-vs-mamoa bottleneck and supports treating mamoas as a separate hard-negative family.",
            "- It ranks `Castro de Pena Lopesa` very high by specialist probability, which confirms that the fusion failure is not simple absence of signal.",
            "- The product score still inherits the low fusion score for Pena Lopesa, so the project should keep three lanes: main fusion, morphology safety, and mamoa specialist.",
            "- This layer should inform QGIS review and hard-negative mining before exporting full `test/train`.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", type=Path, default=DEFAULT_FEATURES)
    parser.add_argument("--fusion-scores", type=Path, default=DEFAULT_FUSION_SCORES)
    parser.add_argument("--priority-scores", type=Path, default=DEFAULT_PRIORITY_SCORES)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--train-dataset", default="train_mini")
    parser.add_argument("--epochs", type=int, default=900)
    parser.add_argument("--learning-rate", type=float, default=0.06)
    parser.add_argument("--l2", type=float, default=0.02)
    return parser.parse_args()


def resolve_args(args: argparse.Namespace) -> argparse.Namespace:
    for attr in ("features", "fusion_scores", "priority_scores", "out_dir", "report"):
        value = getattr(args, attr)
        setattr(args, attr, value if value.is_absolute() else PROJECT_ROOT / value)
    return args


def main() -> None:
    require_runtime()
    args = resolve_args(parse_args())
    feature_rows = read_tsv(args.features)
    train = training_rows(feature_rows, args.train_dataset)
    if not train:
        raise SystemExit("No specialist training rows found.")
    train_counts = Counter("positive" if row["label_class"] == "1" else row["negative_type"] for row in train)
    x_train, y_train = matrix(train)
    if len(set(int(value) for value in y_train)) < 2:
        raise SystemExit("Specialist train rows must include positives and mamoa negatives.")
    model = fit_logistic(x_train, y_train, epochs=args.epochs, learning_rate=args.learning_rate, l2=args.l2)
    score_rows = build_score_rows(ok_rows(feature_rows), model, score_lookup(args.fusion_scores), max_safety_lookup(args.priority_scores))
    metric_rows = build_metric_rows(score_rows)

    score_path = args.out_dir / "weak_label_castro_mamoa_specialist_scores.tsv"
    metric_path = args.out_dir / "weak_label_castro_mamoa_specialist_metrics.tsv"
    model_path = args.out_dir / "weak_label_castro_mamoa_specialist_model.json"
    write_tsv(score_path, score_rows, SCORE_FIELDS)
    write_tsv(metric_path, metric_rows, METRIC_FIELDS_WITH_SCORE)
    write_model(model_path, model, train_counts, args)
    write_report(args.report, args, score_rows, metric_rows, train_counts, model)
    print(f"train_rows={len(train)}")
    print(f"score_rows={len(score_rows)}")
    print(f"metric_rows={len(metric_rows)}")
    print(f"wrote={rel_to_project(score_path)}")
    print(f"report={rel_to_project(args.report)}")


if __name__ == "__main__":
    main()
