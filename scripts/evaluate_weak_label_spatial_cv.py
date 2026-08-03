#!/usr/bin/env python3
"""Spatially blocked cross-validation for the RGB+relief fusion ranker.

The v1 metrics come from a single train/val/test cut. With spatially
autocorrelated data that reports one draw, not a range, and a random cut
would report an optimistic one. This script refits the same logistic
fusion under two regimes over the same rows:

- ``block``  : folds hold out whole spatial blocks (country|province|municipality)
- ``random`` : folds hold out random rows, ignoring geography

The gap between them is the autocorrelation premium the project should
never claim as generalisation. It also emits per-block recall so a good
average cannot hide a region the ranker never recovers.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from train_weak_label_rgb_baseline import (
    average_precision,
    fit_logistic,
    parse_float,
    precision_recall_at,
    predict,
    read_tsv,
    rel_to_project,
    roc_auc,
    write_tsv,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FEATURES = PROJECT_ROOT / "data/weak-label-fusion-v1/weak_label_rgb_relief_full_features.tsv"
DEFAULT_MASTER = PROJECT_ROOT / "data/weak-label-splits-v1/weak_label_master.tsv"
DEFAULT_MSRM_FEATURES = PROJECT_ROOT / "data/weak-label-msrm-v1/weak_label_msrm_features_full.tsv"
DEFAULT_OUT_DIR = PROJECT_ROOT / "data/weak-label-spatial-cv-v1"
DEFAULT_REPORT = PROJECT_ROOT / "reports/weak_label_spatial_cv_v1.md"

GENERATED_AT = "2026-08-02T00:00:00Z"

FOLD_FIELDS = [
    "regime",
    "fold",
    "train_rows",
    "test_rows",
    "test_positives",
    "test_negatives",
    "blocks_held_out",
    "roc_auc",
    "average_precision",
    "precision_at_50",
    "recall_at_50",
    "median_positive_rank",
]

SUMMARY_FIELDS = [
    "regime",
    "feature_set",
    "folds",
    "roc_auc_mean",
    "roc_auc_std",
    "roc_auc_min",
    "roc_auc_max",
    "average_precision_mean",
    "average_precision_std",
    "average_precision_min",
    "average_precision_max",
]

BLOCK_FIELDS = [
    "spatial_block_id",
    "province_or_district",
    "municipality",
    "rows",
    "positives",
    "held_out_in_fold",
    "positives_recovered_top_decile",
    "recall_top_decile",
    "median_positive_rank_pct",
]


def feature_columns(rows: list[dict[str, str]], prefixes: tuple[str, ...]) -> list[str]:
    if not rows:
        return []
    return [name for name in rows[0] if name.startswith(prefixes)]


def label_of(row: dict[str, str]) -> int:
    return 1 if str(row.get("label_class", "")).strip() in {"1", "positive"} else 0


def build_matrix(rows: list[dict[str, str]], columns: list[str]):
    import numpy as np

    x = np.array([[parse_float(row.get(name)) for name in columns] for row in rows], dtype="float64")
    y = np.array([label_of(row) for row in rows], dtype="float64")
    return x, y


def fold_metric_row(
    regime: str,
    fold: int,
    train_rows: int,
    labels: list[int],
    scores: list[float],
    blocks_held_out: int,
) -> dict[str, str]:
    positives = sum(labels)
    order = sorted(range(len(scores)), key=lambda idx: scores[idx], reverse=True)
    ranks = [0] * len(scores)
    for rank, idx in enumerate(order, start=1):
        ranks[idx] = rank
    positive_ranks = [ranks[idx] for idx, label in enumerate(labels) if label == 1]
    # These helpers return pre-formatted strings (or "n/a"), not floats.
    precision_50, recall_50 = precision_recall_at(labels, scores, 50)
    return {
        "regime": regime,
        "fold": str(fold),
        "train_rows": str(train_rows),
        "test_rows": str(len(labels)),
        "test_positives": str(positives),
        "test_negatives": str(len(labels) - positives),
        "blocks_held_out": str(blocks_held_out),
        "roc_auc": roc_auc(labels, scores),
        "average_precision": average_precision(labels, scores),
        "precision_at_50": precision_50,
        "recall_at_50": recall_50,
        "median_positive_rank": f"{statistics.median(positive_ranks):.1f}" if positive_ranks else "",
    }


def assign_block_folds(rows: list[dict[str, str]], block_of: dict[int, str], folds: int, seed: int) -> list[list[int]]:
    """Greedily balance positives across folds while keeping blocks intact."""
    block_rows: dict[str, list[int]] = defaultdict(list)
    for index, _row in enumerate(rows):
        block_rows[block_of[index]].append(index)

    block_positives = {
        block: sum(label_of(rows[index]) for index in indices) for block, indices in block_rows.items()
    }
    ordered_blocks = sorted(block_rows, key=lambda block: (-block_positives[block], block))
    rng = random.Random(seed)
    rng.shuffle(ordered_blocks)
    ordered_blocks.sort(key=lambda block: -block_positives[block])

    buckets: list[list[int]] = [[] for _ in range(folds)]
    bucket_positives = [0] * folds
    for block in ordered_blocks:
        target = min(range(folds), key=lambda idx: (bucket_positives[idx], len(buckets[idx])))
        buckets[target].extend(block_rows[block])
        bucket_positives[target] += block_positives[block]
    return buckets


def assign_random_folds(row_count: int, folds: int, seed: int) -> list[list[int]]:
    indices = list(range(row_count))
    rng = random.Random(seed)
    rng.shuffle(indices)
    buckets: list[list[int]] = [[] for _ in range(folds)]
    for position, index in enumerate(indices):
        buckets[position % folds].append(index)
    return buckets


def run_regime(
    regime: str,
    rows: list[dict[str, str]],
    columns: list[str],
    buckets: list[list[int]],
    block_of: dict[int, str],
    args: argparse.Namespace,
) -> tuple[list[dict[str, str]], dict[int, float]]:
    import numpy as np

    x_all, y_all = build_matrix(rows, columns)
    fold_rows: list[dict[str, str]] = []
    out_of_fold_score: dict[int, float] = {}

    for fold, test_indices in enumerate(buckets, start=1):
        if not test_indices:
            continue
        test_set = set(test_indices)
        train_indices = [index for index in range(len(rows)) if index not in test_set]
        y_train = y_all[train_indices]
        if len(set(y_train.tolist())) < 2:
            continue
        y_test = y_all[test_indices]
        if len(set(y_test.tolist())) < 2:
            continue

        model = fit_logistic(
            x_all[train_indices],
            y_train,
            epochs=args.epochs,
            learning_rate=args.learning_rate,
            l2=args.l2,
        )
        probabilities = predict(model, x_all[test_indices])
        scores = [float(value) for value in probabilities]
        labels = [int(value) for value in y_test.tolist()]
        for position, index in enumerate(test_indices):
            out_of_fold_score[index] = scores[position]

        blocks_held_out = len({block_of[index] for index in test_indices})
        fold_rows.append(
            fold_metric_row(regime, fold, len(train_indices), labels, scores, blocks_held_out)
        )

    return fold_rows, out_of_fold_score


def summarise(regime: str, feature_set: str, fold_rows: list[dict[str, str]]) -> dict[str, str]:
    aucs = [
        float(row["roc_auc"])
        for row in fold_rows
        if row["regime"] == regime and row["roc_auc"] not in {"", "n/a"}
    ]
    aps = [
        float(row["average_precision"])
        for row in fold_rows
        if row["regime"] == regime and row["average_precision"] not in {"", "n/a"}
    ]
    if not aucs or not aps:
        return {}
    return {
        "regime": regime,
        "feature_set": feature_set,
        "folds": str(len(aucs)),
        "roc_auc_mean": f"{statistics.mean(aucs):.6f}",
        "roc_auc_std": f"{statistics.pstdev(aucs):.6f}" if len(aucs) > 1 else "0.000000",
        "roc_auc_min": f"{min(aucs):.6f}",
        "roc_auc_max": f"{max(aucs):.6f}",
        "average_precision_mean": f"{statistics.mean(aps):.6f}",
        "average_precision_std": f"{statistics.pstdev(aps):.6f}" if len(aps) > 1 else "0.000000",
        "average_precision_min": f"{min(aps):.6f}",
        "average_precision_max": f"{max(aps):.6f}",
    }


def block_report_rows(
    rows: list[dict[str, str]],
    block_of: dict[int, str],
    scores: dict[int, float],
    master: dict[str, dict[str, str]],
    buckets: list[list[int]],
) -> list[dict[str, str]]:
    fold_of: dict[int, int] = {}
    for fold, indices in enumerate(buckets, start=1):
        for index in indices:
            fold_of[index] = fold

    scored = [(index, scores[index]) for index in scores]
    scored.sort(key=lambda item: item[1], reverse=True)
    total = len(scored)
    decile_cut = max(1, total // 10)
    top_decile = {index for index, _score in scored[:decile_cut]}
    rank_pct: dict[int, float] = {}
    for position, (index, _score) in enumerate(scored, start=1):
        rank_pct[index] = position / total if total else 0.0

    grouped: dict[str, list[int]] = defaultdict(list)
    for index in scores:
        grouped[block_of[index]].append(index)

    out: list[dict[str, str]] = []
    for block, indices in grouped.items():
        positives = [index for index in indices if label_of(rows[index]) == 1]
        if not positives:
            continue
        recovered = [index for index in positives if index in top_decile]
        sample = master.get(rows[indices[0]].get("sample_id", ""), {})
        positive_pcts = [rank_pct[index] for index in positives]
        out.append(
            {
                "spatial_block_id": block,
                "province_or_district": sample.get("province_or_district", ""),
                "municipality": rows[indices[0]].get("municipality", ""),
                "rows": str(len(indices)),
                "positives": str(len(positives)),
                "held_out_in_fold": str(fold_of.get(indices[0], "")),
                "positives_recovered_top_decile": str(len(recovered)),
                "recall_top_decile": f"{len(recovered) / len(positives):.6f}",
                "median_positive_rank_pct": f"{statistics.median(positive_pcts):.6f}",
            }
        )
    out.sort(key=lambda row: (float(row["recall_top_decile"]), -int(row["positives"])))
    return out


def write_report(
    path: Path,
    args: argparse.Namespace,
    fold_rows: list[dict[str, str]],
    summaries: list[dict[str, str]],
    block_rows: list[dict[str, str]],
    columns_by_set: dict[str, list[str]],
    row_count: int,
    block_count: int,
) -> None:
    block_summary = next((row for row in summaries if row["regime"] == "block" and row["feature_set"] == "fusion"), {})
    random_summary = next((row for row in summaries if row["regime"] == "random" and row["feature_set"] == "fusion"), {})
    premium = ""
    if block_summary and random_summary:
        premium = f"{float(random_summary['roc_auc_mean']) - float(block_summary['roc_auc_mean']):+.6f}"

    lines = [
        "# Weak-label spatial cross-validation v1",
        "",
        f"Generated at: `{GENERATED_AT}`",
        f"Rows: `{row_count}` · spatial blocks: `{block_count}` · folds: `{args.folds}`",
        "",
        "## Why this exists",
        "",
        "The headline v1 numbers (`val` AUC `0.905931`, `test` AUC `0.910299`,",
        "holdouts AUC `0.925281`) come from one spatial cut. They are a single",
        "draw. This run refits the same fusion under repeated spatially blocked",
        "folds to report a range, and under random folds to measure how much",
        "spatial autocorrelation would have inflated the same model.",
        "",
        "## Summary",
        "",
        "| regime | feature set | folds | ROC-AUC mean | ROC-AUC std | ROC-AUC min | ROC-AUC max | AP mean | AP std |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summaries:
        lines.append(
            f"| `{row['regime']}` | `{row['feature_set']}` | `{row['folds']}` | `{row['roc_auc_mean']}` | "
            f"`{row['roc_auc_std']}` | `{row['roc_auc_min']}` | `{row['roc_auc_max']}` | "
            f"`{row['average_precision_mean']}` | `{row['average_precision_std']}` |"
        )

    if premium:
        lines += [
            "",
            f"**Autocorrelation premium (random minus block, fusion ROC-AUC): `{premium}`.**",
            "",
            "Any figure quoted from a random split carries this much unearned",
            "credit. Only the blocked number describes moving to new ground.",
        ]

    lines += [
        "",
        "## Feature sets compared",
        "",
        "| feature set | columns |",
        "|---|---:|",
    ]
    for name, columns in columns_by_set.items():
        lines.append(f"| `{name}` | `{len(columns)}` |")

    lines += [
        "",
        "## Per-fold detail",
        "",
        "| regime | fold | train rows | test rows | positives | blocks held out | ROC-AUC | AP | P@50 | R@50 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in fold_rows:
        lines.append(
            f"| `{row['regime']}` | `{row['fold']}` | `{row['train_rows']}` | `{row['test_rows']}` | "
            f"`{row['test_positives']}` | `{row['blocks_held_out']}` | `{row['roc_auc']}` | "
            f"`{row['average_precision']}` | `{row['precision_at_50']}` | `{row['recall_at_50']}` |"
        )

    worst = [row for row in block_rows if float(row["recall_top_decile"]) < 0.5][:25]
    lines += [
        "",
        "## Blocks the ranker does not recover (out-of-fold, top-decile recall < 0.5)",
        "",
        f"Blocks with positives: `{len(block_rows)}` · below half recall: "
        f"`{sum(1 for row in block_rows if float(row['recall_top_decile']) < 0.5)}`",
        "",
        "| block | province/district | municipality | positives | recovered | recall | median positive rank pct |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for row in worst:
        lines.append(
            f"| `{row['spatial_block_id']}` | {row['province_or_district']} | {row['municipality']} | "
            f"`{row['positives']}` | `{row['positives_recovered_top_decile']}` | "
            f"`{row['recall_top_decile']}` | `{row['median_positive_rank_pct']}` |"
        )

    lines += [
        "",
        "## Reading",
        "",
        "- The blocked mean, not the single-split number, is what to quote when",
        "  claiming the ranker transfers to unsurveyed ground.",
        "- The spread across folds is the honest error bar. A narrow spread on a",
        "  small holdout is still a small holdout.",
        "- The per-block table is the geographic error surface: a block with many",
        "  positives and low recall is a morphology or landscape the model has",
        "  not learned, not noise.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", type=Path, default=DEFAULT_FEATURES)
    parser.add_argument("--master", type=Path, default=DEFAULT_MASTER)
    parser.add_argument("--msrm-features", type=Path, default=DEFAULT_MSRM_FEATURES)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--seed", type=int, default=20260802)
    parser.add_argument("--epochs", type=int, default=400)
    parser.add_argument("--learning-rate", type=float, default=0.35)
    parser.add_argument("--l2", type=float, default=0.002)
    parser.add_argument("--skip-msrm", action="store_true")
    return parser.parse_args()


def resolve_args(args: argparse.Namespace) -> argparse.Namespace:
    for attr in ("features", "master", "msrm_features", "out_dir", "report"):
        value = getattr(args, attr)
        setattr(args, attr, value if value.is_absolute() else PROJECT_ROOT / value)
    return args


def main() -> None:
    args = resolve_args(parse_args())

    feature_rows = [row for row in read_tsv(args.features) if row.get("status", "ok") == "ok"]
    if not feature_rows:
        raise SystemExit("no usable fusion feature rows")

    master = {row["sample_id"]: row for row in read_tsv(args.master)}

    msrm_by_sample: dict[str, dict[str, str]] = {}
    if not args.skip_msrm and args.msrm_features.exists():
        for row in read_tsv(args.msrm_features):
            if row.get("status") == "ok":
                msrm_by_sample[row.get("sample_id", "")] = row

    rows: list[dict[str, str]] = []
    block_of: dict[int, str] = {}
    for row in feature_rows:
        sample_id = row.get("sample_id", "")
        meta = master.get(sample_id, {})
        block = meta.get("spatial_block_id", "") or "|".join(
            [row.get("country", ""), row.get("municipality", "")]
        )
        merged = dict(row)
        msrm_row = msrm_by_sample.get(sample_id)
        if msrm_row:
            for name, value in msrm_row.items():
                if name.startswith(("msrm_", "lrm_", "best_ring", "dominant_scale", "scale_", "ring_radius")):
                    merged[f"msrm__{name}"] = value
        block_of[len(rows)] = block
        rows.append(merged)

    fusion_columns = feature_columns(rows, ("rgb__", "relief__"))
    msrm_columns = feature_columns(rows, ("msrm__",))
    columns_by_set = {"fusion": fusion_columns}
    if msrm_columns and len(msrm_by_sample) >= len(rows) * 0.9:
        columns_by_set["fusion_plus_msrm"] = fusion_columns + msrm_columns

    block_buckets = assign_block_folds(rows, block_of, args.folds, args.seed)
    random_buckets = assign_random_folds(len(rows), args.folds, args.seed)

    all_fold_rows: list[dict[str, str]] = []
    summaries: list[dict[str, str]] = []
    block_scores: dict[int, float] = {}

    for feature_set, columns in columns_by_set.items():
        for regime, buckets in (("block", block_buckets), ("random", random_buckets)):
            fold_rows, out_of_fold = run_regime(regime, rows, columns, buckets, block_of, args)
            tagged = []
            for row in fold_rows:
                tagged_row = dict(row)
                tagged_row["regime"] = regime
                tagged_row["feature_set"] = feature_set
                tagged.append(tagged_row)
            all_fold_rows.extend(tagged)
            summary = summarise(regime, feature_set, fold_rows)
            if summary:
                summaries.append(summary)
            if feature_set == "fusion" and regime == "block":
                block_scores = out_of_fold

    args.out_dir.mkdir(parents=True, exist_ok=True)
    fold_path = args.out_dir / "weak_label_spatial_cv_folds.tsv"
    write_tsv(fold_path, all_fold_rows, FOLD_FIELDS + ["feature_set"])
    summary_path = args.out_dir / "weak_label_spatial_cv_summary.tsv"
    write_tsv(summary_path, summaries, SUMMARY_FIELDS)

    blocks = block_report_rows(rows, block_of, block_scores, master, block_buckets)
    block_path = args.out_dir / "weak_label_spatial_cv_blocks.tsv"
    write_tsv(block_path, blocks, BLOCK_FIELDS)

    write_report(
        args.report,
        args,
        all_fold_rows,
        summaries,
        blocks,
        columns_by_set,
        len(rows),
        len(set(block_of.values())),
    )

    for summary in summaries:
        print(
            f"{summary['feature_set']}/{summary['regime']}: "
            f"AUC {summary['roc_auc_mean']} +/- {summary['roc_auc_std']} "
            f"AP {summary['average_precision_mean']}"
        )
    print(f"folds={rel_to_project(fold_path)}")
    print(f"summary={rel_to_project(summary_path)}")
    print(f"blocks={rel_to_project(block_path)}")
    print(f"report={rel_to_project(args.report)}")


if __name__ == "__main__":
    main()
