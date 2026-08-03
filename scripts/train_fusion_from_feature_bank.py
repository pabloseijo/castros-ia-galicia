#!/usr/bin/env python3
"""Train the fusion ranker from pre-extracted feature banks.

The existing trainer rebuilds features from RGB and relief manifests. Once
features live in their own TSVs — which is how the landscape negatives and
the Galicia sweep are produced — training should just consume them.

Reports the mámoa-specific error rate alongside the usual metrics, because
that is the failure this change is meant to move.
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from train_weak_label_rgb_baseline import (  # noqa: E402
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
DEFAULT_BANK = PROJECT_ROOT / "data/weak-label-fusion-v1/weak_label_rgb_relief_msrm_full_features.tsv"
DEFAULT_OUT_DIR = PROJECT_ROOT / "data/weak-label-fusion-v1"

METRIC_FIELDS = [
    "subset",
    "rows",
    "positives",
    "negatives",
    "roc_auc",
    "average_precision",
    "precision_at_50",
    "recall_at_50",
    "median_positive_rank",
]


def feature_columns(rows: list[dict[str, str]]) -> list[str]:
    prefixes = ("rgb__", "relief__", "relief_variant__", "msrm__")
    return [name for name in rows[0] if name.startswith(prefixes)]


def label_of(row: dict[str, str]) -> int:
    return 1 if str(row.get("label_class", "")).strip() in {"1", "positive"} else 0


def subset_of(row: dict[str, str]) -> str:
    return row.get("final_split") or row.get("dataset") or ""


def metric_row(subset: str, rows: list[dict[str, str]], scores: list[float]) -> dict[str, str]:
    labels = [label_of(r) for r in rows]
    positives = sum(labels)
    order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    ranks = [0] * len(scores)
    for rank, idx in enumerate(order, start=1):
        ranks[idx] = rank
    pos_ranks = [ranks[i] for i, l in enumerate(labels) if l == 1]
    p50, r50 = precision_recall_at(labels, scores, 50)
    return {
        "subset": subset,
        "rows": str(len(rows)),
        "positives": str(positives),
        "negatives": str(len(rows) - positives),
        "roc_auc": roc_auc(labels, scores),
        "average_precision": average_precision(labels, scores),
        "precision_at_50": p50,
        "recall_at_50": r50,
        "median_positive_rank": f"{statistics.median(pos_ranks):.1f}" if pos_ranks else "",
    }


def mamoa_report(rows: list[dict[str, str]], scores: list[float], top_n: int = 25) -> dict:
    """What fraction of the worst false positives are burial mounds."""
    order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    negatives = [i for i in order if label_of(rows[i]) == 0][:top_n]
    types = Counter(rows[i].get("negative_type", "") or "unknown" for i in negatives)
    mamoas = sum(count for name, count in types.items() if "megalithic" in name)
    return {"top_n": len(negatives), "mamoas": mamoas, "composition": dict(types.most_common(5))}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bank", type=Path, action="append", default=None)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--artifact-prefix", default="weak_label_fusion_v2")
    parser.add_argument("--report", type=Path, default=PROJECT_ROOT / "reports/weak_label_fusion_v2.md")
    parser.add_argument("--train-subset", default="train")
    parser.add_argument("--epochs", type=int, default=900)
    parser.add_argument("--learning-rate", type=float, default=0.06)
    parser.add_argument("--l2", type=float, default=0.02)
    parser.add_argument("--baseline-metrics", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    import numpy as np

    args = parse_args()
    banks = args.bank or [DEFAULT_BANK]
    banks = [b if b.is_absolute() else PROJECT_ROOT / b for b in banks]
    args.out_dir = args.out_dir if args.out_dir.is_absolute() else PROJECT_ROOT / args.out_dir
    args.report = args.report if args.report.is_absolute() else PROJECT_ROOT / args.report

    rows: list[dict[str, str]] = []
    provenance = Counter()
    for bank in banks:
        loaded = [r for r in read_tsv(bank) if r.get("status") == "ok"]
        provenance[bank.name] = len(loaded)
        rows.extend(loaded)
    if not rows:
        raise SystemExit("no usable feature rows")

    columns = feature_columns(rows)
    x_all = np.array([[parse_float(r.get(c)) for c in columns] for r in rows], dtype="float64")
    y_all = np.array([label_of(r) for r in rows], dtype="float64")

    train_idx = [i for i, r in enumerate(rows) if subset_of(r) == args.train_subset]
    if not train_idx:
        raise SystemExit(f"no rows in train subset '{args.train_subset}'")

    model = fit_logistic(
        x_all[train_idx], y_all[train_idx],
        epochs=args.epochs, learning_rate=args.learning_rate, l2=args.l2,
    )
    probs = [float(p) for p in predict(model, x_all)]

    by_subset: dict[str, list[int]] = {}
    for i, r in enumerate(rows):
        by_subset.setdefault(subset_of(r), []).append(i)
    by_subset["holdouts"] = [
        i for i, r in enumerate(rows) if subset_of(r) in {"test_o_val", "test_trasancos"}
    ]

    metrics = []
    for subset in ("train", "val", "test", "holdouts", "test_trasancos", "test_o_val"):
        idx = by_subset.get(subset, [])
        if len(idx) < 5:
            continue
        sub_rows = [rows[i] for i in idx]
        sub_scores = [probs[i] for i in idx]
        if len({label_of(r) for r in sub_rows}) < 2:
            continue
        metrics.append(metric_row(subset, sub_rows, sub_scores))

    hold = by_subset.get("holdouts", [])
    mamoas = mamoa_report([rows[i] for i in hold], [probs[i] for i in hold]) if hold else {}

    args.out_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = args.out_dir / f"{args.artifact_prefix}_metrics.tsv"
    write_tsv(metrics_path, metrics, METRIC_FIELDS)

    model_path = args.out_dir / f"{args.artifact_prefix}_model.json"
    model_path.write_text(
        json.dumps(
            {
                "generated_at": "2026-08-03T00:00:00Z",
                "model": "numpy_logistic_regression_fusion_from_feature_bank",
                "feature_names": columns,
                "weights": model["weights"].tolist(),
                "feature_mean": model["feature_mean"].tolist(),
                "feature_std": model["feature_std"].tolist(),
                "last_loss": model["last_loss"],
                "banks": {k: v for k, v in provenance.items()},
                "train_rows": len(train_idx),
            },
            indent=1,
        ),
        encoding="utf-8",
    )

    baseline = {}
    if args.baseline_metrics and Path(args.baseline_metrics).exists():
        for row in read_tsv(Path(args.baseline_metrics)):
            key = row.get("subset") or row.get("dataset", "")
            if row.get("subset") == "all" or not row.get("subset"):
                key = row.get("dataset", "")
            baseline[key] = row

    lines = [
        "# Fusion v2 — trained from feature banks",
        "",
        f"Feature columns: `{len(columns)}` · training rows: `{len(train_idx)}` (subset `{args.train_subset}`)",
        "",
        "## Banks used",
        "",
        "| bank | rows |",
        "|---|---:|",
    ]
    for name, count in provenance.items():
        lines.append(f"| `{name}` | `{count}` |")

    lines += [
        "",
        "## Metrics",
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

    if mamoas:
        lines += [
            "",
            "## Dominant false positive on holdouts",
            "",
            f"- top-`{mamoas['top_n']}` false positives that are megalithic mounds: **`{mamoas['mamoas']}`**",
            f"- composition: `{mamoas['composition']}`",
            "",
            "This is the number the landscape negatives are meant to move. If it",
            "has not fallen, the new negatives taught the model about ordinary",
            "ground without helping it separate castros from burial mounds.",
            "",
        ]

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")

    for row in metrics:
        print(f"{row['subset']}: AUC {row['roc_auc']} AP {row['average_precision']} P@50 {row['precision_at_50']}")
    if mamoas:
        print(f"mamoas_in_top25_fp={mamoas['mamoas']}")
    print(f"model={rel_to_project(model_path)}")
    print(f"report={rel_to_project(args.report)}")


if __name__ == "__main__":
    main()
