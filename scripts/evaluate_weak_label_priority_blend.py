#!/usr/bin/env python3
"""Evaluate review-priority blends over RGB+relief weak-label scores."""

from __future__ import annotations

import argparse
import math
import statistics
from collections import defaultdict
from pathlib import Path

from train_weak_label_rgb_baseline import (
    METRIC_FIELDS,
    average_precision,
    parse_float,
    precision_recall_at,
    ranks_desc,
    read_tsv,
    rel_to_project,
    roc_auc,
    write_tsv,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FEATURES = PROJECT_ROOT / "data/weak-label-fusion-v1/weak_label_rgb_relief_features.tsv"
DEFAULT_SCORES = PROJECT_ROOT / "data/weak-label-fusion-v1/weak_label_rgb_relief_scores.tsv"
DEFAULT_FUSION_METRICS = PROJECT_ROOT / "data/weak-label-fusion-v1/weak_label_rgb_relief_metrics.tsv"
OUT_DIR = PROJECT_ROOT / "data/weak-label-fusion-v1"
DEFAULT_REPORT = PROJECT_ROOT / "reports/weak_label_priority_blend_v1.md"

GENERATED_AT = "2026-08-01T00:00:00Z"

BLENDS = {
    "fusion_only": (1.0, 0.0, "sum"),
    "archetype_only": (0.0, 1.0, "sum"),
    "mean": (0.5, 0.5, "sum"),
    "fusion70_arch30": (0.7, 0.3, "sum"),
    "max_safety": (1.0, 1.0, "max"),
}

SCORE_FIELDS = [
    "blend",
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
    "fusion_logit_z",
    "archetype_score",
    "archetype_z",
    "blend_score",
    "rank_desc_in_dataset",
]

METRIC_FIELDS_WITH_BLEND = ["blend", *METRIC_FIELDS]


def robust_z(values: list[float]) -> list[float]:
    if not values:
        return []
    median = statistics.median(values)
    deviations = [abs(value - median) for value in values]
    mad = statistics.median(deviations)
    scale = 1.4826 * mad if mad > 1e-9 else (statistics.pstdev(values) if len(values) > 1 else 1.0)
    if scale <= 1e-9:
        scale = 1.0
    return [(value - median) / scale for value in values]


def logit(probability: float) -> float:
    clipped = min(max(probability, 1e-6), 1.0 - 1e-6)
    return math.log(clipped / (1.0 - clipped))


def feature_lookup(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    return {row["sample_id"]: row for row in rows if row.get("status") == "ok"}


def base_rows(score_rows: list[dict[str, str]], features_by_sample: dict[str, dict[str, str]]) -> list[dict[str, str]]:
    out = []
    for score_row in score_rows:
        feature_row = features_by_sample.get(score_row["sample_id"])
        if feature_row is None:
            continue
        row = dict(score_row)
        row["fusion_probability"] = score_row["probability"]
        row["fusion_logit"] = f"{logit(parse_float(score_row['probability'])):.8f}"
        row["archetype_score"] = feature_row.get("relief_variant__archetype_max", "0")
        out.append(row)
    return out


def score_blend(fusion_z: float, archetype_z: float, fusion_weight: float, archetype_weight: float, mode: str) -> float:
    if mode == "max":
        return max(fusion_z, archetype_z)
    return fusion_weight * fusion_z + archetype_weight * archetype_z


def build_score_rows(base: list[dict[str, str]]) -> list[dict[str, str]]:
    rows = []
    by_dataset: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in base:
        by_dataset[row["dataset"]].append(row)

    for dataset, dataset_rows in sorted(by_dataset.items()):
        fusion_z = robust_z([parse_float(row["fusion_logit"]) for row in dataset_rows])
        archetype_z = robust_z([parse_float(row["archetype_score"]) for row in dataset_rows])
        for blend, (fusion_weight, archetype_weight, mode) in BLENDS.items():
            raw_scores = [
                score_blend(fz, az, fusion_weight, archetype_weight, mode)
                for fz, az in zip(fusion_z, archetype_z)
            ]
            ranks = ranks_desc(raw_scores)
            for row, fz, az, blend_score, rank in zip(dataset_rows, fusion_z, archetype_z, raw_scores, ranks):
                rows.append(
                    {
                        "blend": blend,
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
                        "fusion_probability": row["fusion_probability"],
                        "fusion_logit_z": f"{fz:.8f}",
                        "archetype_score": row["archetype_score"],
                        "archetype_z": f"{az:.8f}",
                        "blend_score": f"{blend_score:.8f}",
                        "rank_desc_in_dataset": str(rank),
                    }
                )
    return rows


def metric_row(blend: str, dataset: str, subset: str, rows: list[dict[str, str]]) -> dict[str, str]:
    labels = [int(row["label_class"]) for row in rows]
    scores = [parse_float(row["blend_score"]) for row in rows]
    ranks = ranks_desc(scores)
    pos_ranks = [rank for rank, label in zip(ranks, labels) if label == 1]
    p10, r10 = precision_recall_at(labels, scores, 10)
    p50, r50 = precision_recall_at(labels, scores, 50)
    p100, r100 = precision_recall_at(labels, scores, 100)
    return {
        "blend": blend,
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
    by_blend_dataset: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in score_rows:
        by_blend_dataset[(row["blend"], row["dataset"])].append(row)
    for (blend, dataset), dataset_rows in sorted(by_blend_dataset.items()):
        rows.append(metric_row(blend, dataset, "all", dataset_rows))
        by_split: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in dataset_rows:
            by_split[row["final_split"]].append(row)
        if len(by_split) > 1:
            for split, split_rows in sorted(by_split.items()):
                rows.append(metric_row(blend, dataset, f"split:{split}", split_rows))
    return rows


def metric_lookup(rows: list[dict[str, str]], blend: str, dataset: str, subset: str = "all") -> dict[str, str]:
    return next((row for row in rows if row["blend"] == blend and row["dataset"] == dataset and row["subset"] == subset), {})


def load_fusion_references(path: Path) -> list[str]:
    if not path.exists():
        return []
    out = []
    for row in read_tsv(path):
        if row.get("subset") in {"all", "split:test_o_val", "split:test_trasancos"}:
            out.append(
                f"- fusion {row['dataset']} {row['subset']}: ROC-AUC `{row['roc_auc']}`, AP `{row['average_precision']}`, P@50 `{row['precision_at_50']}`."
            )
    return out


def artifact_path(args: argparse.Namespace, suffix: str) -> Path:
    return args.out_dir / f"{args.artifact_prefix}_{suffix}"


def o_val_rank(score_rows: list[dict[str, str]], blend: str, name: str) -> str:
    for row in score_rows:
        if row["blend"] == blend and row["final_split"] == "test_o_val" and row["name"] == name:
            return row["rank_desc_in_dataset"]
    return "n/a"


def o_val_summary(score_rows: list[dict[str, str]]) -> list[str]:
    lines = []
    names = [
        "O Castro (Castro de Quintá)",
        "Castro da Pedreira",
        "Monte do Castro (Castro de Vilasuso)",
        "Mámoa do Val/Mámoa de Santa Margarida",
        "Castro de Pena Lopesa",
    ]
    for blend in ("fusion_only", "max_safety", "fusion70_arch30", "mean", "archetype_only"):
        blend_rows = [row for row in score_rows if row["blend"] == blend and row["final_split"] == "test_o_val"]
        rank_by_name = {row["name"]: row for row in blend_rows}
        lines.append(f"### {blend}")
        lines.append("")
        lines.append("| Rank | Class | Score | Name |")
        lines.append("|---:|---:|---:|---|")
        for name in names:
            row = rank_by_name.get(name)
            if row:
                lines.append(f"| {row['rank_desc_in_dataset']} | {row['label_class']} | {row['blend_score']} | `{row['name']}` |")
        lines.append("")
    return lines


def write_report(path: Path, args: argparse.Namespace, score_rows: list[dict[str, str]], metric_rows: list[dict[str, str]]) -> None:
    lines = [
        "# Weak-label priority blend v1",
        "",
        f"Generated: {GENERATED_AT}",
        "",
        "## What This Is",
        "",
        "A review-priority stress test over the RGB+relief fusion baseline. It compares the supervised fusion score with the morphology-aware `archetype_max` relief channel.",
        "This does not claim better detection; it shows whether a second safety queue can rescue atypical castro forms that the global ranker suppresses.",
        "",
        "## Files",
        "",
        f"- Fusion features: `{rel_to_project(args.features)}`",
        f"- Fusion scores: `{rel_to_project(args.scores)}`",
        f"- Blend score TSV: `{rel_to_project(artifact_path(args, 'scores.tsv'))}`",
        f"- Blend metrics TSV: `{rel_to_project(artifact_path(args, 'metrics.tsv'))}`",
        "",
        "## Blend Logic",
        "",
        "- `fusion_only`: supervised RGB+relief ranker, normalized by dataset.",
        "- `archetype_only`: morphology channel only, using the strongest relief archetype.",
        "- `mean`: equal blend of the two normalized channels.",
        "- `fusion70_arch30`: conservative blend biased toward supervised fusion.",
        "- `max_safety`: takes the better of fusion or archetype per row; useful as a review safety queue.",
        "",
        "## Metrics",
        "",
        "| Blend | Dataset | Subset | Rows | Pos | Neg | ROC-AUC | AP | P@50 | R@50 | Best pos rank | Median pos rank |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in metric_rows:
        if row["subset"] == "all" or row["subset"].startswith("split:test_"):
            lines.append(
                "| {blend} | {dataset} | {subset} | {rows} | {positives} | {negatives} | {roc_auc} | {average_precision} | {precision_at_50} | {recall_at_50} | {best_positive_rank} | {median_positive_rank} |".format(
                    **row
                )
            )
    references = load_fusion_references(args.fusion_metrics)
    if references:
        lines.extend(["", "## Fusion Reference", ""])
        lines.extend(references)
    max_holdouts = metric_lookup(metric_rows, "max_safety", "holdouts")
    max_val = metric_lookup(metric_rows, "max_safety", "val")
    fusion70_val = metric_lookup(metric_rows, "fusion70_arch30", "val")
    pena_fusion = o_val_rank(score_rows, "fusion_only", "Castro de Pena Lopesa")
    pena_max = o_val_rank(score_rows, "max_safety", "Castro de Pena Lopesa")
    mamoa_max = o_val_rank(score_rows, "max_safety", "Mámoa do Val/Mámoa de Santa Margarida")
    lines.extend(
        [
            "",
            "## Reading",
            "",
            f"- `max_safety` holdouts: ROC-AUC `{max_holdouts.get('roc_auc', 'n/a')}`, AP `{max_holdouts.get('average_precision', 'n/a')}`, P@50 `{max_holdouts.get('precision_at_50', 'n/a')}`.",
            f"- `max_safety` val: ROC-AUC `{max_val.get('roc_auc', 'n/a')}`, AP `{max_val.get('average_precision', 'n/a')}`, P@50 `{max_val.get('precision_at_50', 'n/a')}`.",
            f"- `fusion70_arch30` val: ROC-AUC `{fusion70_val.get('roc_auc', 'n/a')}`, AP `{fusion70_val.get('average_precision', 'n/a')}`, P@50 `{fusion70_val.get('precision_at_50', 'n/a')}`.",
            "- The supervised fusion score remains the main global ranker. `max_safety` is a separate review lane for rare morphologies, not the final detector score.",
            "",
            "## O Val Reading",
            "",
        ]
    )
    lines.extend(o_val_summary(score_rows))
    lines.extend(
        [
            "## Interpretation",
            "",
            f"- `max_safety` tests the treatment of `Castro de Pena Lopesa`: supervised fusion rank `{pena_fusion}`, `max_safety` rank `{pena_max}`; local mámoa `max_safety` rank `{mamoa_max}`.",
            "- The cost is lower top-50 precision on holdouts, so the correct operational use is two queues: main queue by fusion score, safety queue by morphology rescue.",
            "- This directly addresses the current bottleneck: castros are not one shape, so the review workflow must preserve several shape hypotheses at once.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", type=Path, default=DEFAULT_FEATURES)
    parser.add_argument("--scores", type=Path, default=DEFAULT_SCORES)
    parser.add_argument("--fusion-metrics", type=Path, default=DEFAULT_FUSION_METRICS)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--artifact-prefix", default="weak_label_priority_blend")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def resolve_args(args: argparse.Namespace) -> argparse.Namespace:
    args.features = args.features if args.features.is_absolute() else PROJECT_ROOT / args.features
    args.scores = args.scores if args.scores.is_absolute() else PROJECT_ROOT / args.scores
    args.fusion_metrics = args.fusion_metrics if args.fusion_metrics.is_absolute() else PROJECT_ROOT / args.fusion_metrics
    args.out_dir = args.out_dir if args.out_dir.is_absolute() else PROJECT_ROOT / args.out_dir
    args.report = args.report if args.report.is_absolute() else PROJECT_ROOT / args.report
    if "/" in args.artifact_prefix or "\\" in args.artifact_prefix:
        raise SystemExit("--artifact-prefix must be a file stem, not a path")
    return args


def main() -> None:
    args = resolve_args(parse_args())
    features_by_sample = feature_lookup(read_tsv(args.features))
    base = base_rows(read_tsv(args.scores), features_by_sample)
    score_rows = build_score_rows(base)
    metric_rows = build_metric_rows(score_rows)
    score_path = artifact_path(args, "scores.tsv")
    metric_path = artifact_path(args, "metrics.tsv")
    write_tsv(score_path, score_rows, SCORE_FIELDS)
    write_tsv(metric_path, metric_rows, METRIC_FIELDS_WITH_BLEND)
    write_report(args.report, args, score_rows, metric_rows)
    print(f"base_rows={len(base)}")
    print(f"score_rows={len(score_rows)}")
    print(f"metric_rows={len(metric_rows)}")
    print(f"wrote={rel_to_project(score_path)}")
    print(f"report={rel_to_project(args.report)}")


if __name__ == "__main__":
    main()
