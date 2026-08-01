#!/usr/bin/env python3
"""Evaluate diagnostic relief score variants over weak-label holdouts."""

from __future__ import annotations

import argparse
import csv
import statistics
from collections import defaultdict
from pathlib import Path

from evaluate_weak_label_relief_baseline import METRIC_FIELDS, metric_row, parse_float, robust_z


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FEATURES = PROJECT_ROOT / "data/weak-label-relief-v1/weak_label_relief_features_holdouts.tsv"
DEFAULT_BASELINE_METRICS = PROJECT_ROOT / "data/weak-label-relief-v1/weak_label_relief_metrics_holdouts.tsv"
DEFAULT_OUT_DIR = PROJECT_ROOT / "data/weak-label-relief-v1"
DEFAULT_REPORT = PROJECT_ROOT / "reports/weak_label_relief_score_variants_holdouts.md"

GENERATED_AT = "2026-08-01T00:00:00Z"

VARIANT_COMPONENTS = {
    "hilltop": {
        "dem_prominence_m": 0.45,
        "slope_ratio": 0.20,
        "lrm_core_delta": 0.20,
        "ring_sector_coverage": 0.15,
    },
    "edge_ring": {
        "lrm_abs_ratio": 0.35,
        "slope_ratio": 0.25,
        "hillshade_edge_ratio": 0.20,
        "ring_sector_coverage": 0.20,
    },
    "promontory": {
        "lrm_abs_annulus_mean": 0.35,
        "hillshade_edge_annulus_mean": 0.25,
        "ring_sector_coverage": 0.25,
        "slope_annulus_mean": 0.15,
    },
}

VARIANT_NAMES = [*VARIANT_COMPONENTS.keys(), "archetype_max"]

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
    "best_variant",
    *[f"{name}_score" for name in VARIANT_NAMES],
    *[f"{name}_rank" for name in VARIANT_NAMES],
]

METRICS_FIELDS = ["variant", *METRIC_FIELDS]


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


def rank_scores(scores: list[float]) -> list[int]:
    order = sorted(range(len(scores)), key=lambda idx: scores[idx], reverse=True)
    ranks = [0] * len(scores)
    for rank, idx in enumerate(order, start=1):
        ranks[idx] = rank
    return ranks


def z_features(rows: list[dict[str, str]]) -> dict[str, list[float]]:
    feature_names = sorted({name for components in VARIANT_COMPONENTS.values() for name in components})
    return {
        name: robust_z([parse_float(row.get(name, "0")) for row in rows])
        for name in feature_names
    }


def compute_variant_scores(rows: list[dict[str, str]]) -> tuple[dict[str, list[float]], list[str]]:
    z = z_features(rows)
    scores: dict[str, list[float]] = {name: [0.0 for _row in rows] for name in VARIANT_COMPONENTS}
    for variant_name, components in VARIANT_COMPONENTS.items():
        for feature_name, weight in components.items():
            for index, value in enumerate(z[feature_name]):
                scores[variant_name][index] += weight * value

    best_variant = []
    max_scores = []
    for index in range(len(rows)):
        best_name = max(VARIANT_COMPONENTS, key=lambda name: scores[name][index])
        best_variant.append(best_name)
        max_scores.append(scores[best_name][index])
    scores["archetype_max"] = max_scores
    return scores, best_variant


def build_score_rows(feature_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    ok_rows = [row for row in feature_rows if row.get("status") == "ok"]
    scores, best_variant = compute_variant_scores(ok_rows)
    ranks = {name: rank_scores(values) for name, values in scores.items()}
    out = []
    for index, row in enumerate(ok_rows):
        score_row = {field: row.get(field, "") for field in SCORE_FIELDS}
        score_row["best_variant"] = best_variant[index]
        for name in VARIANT_NAMES:
            score_row[f"{name}_score"] = f"{scores[name][index]:.8f}"
            score_row[f"{name}_rank"] = str(ranks[name][index])
        out.append(score_row)
    return out


def rows_for_metric(score_rows: list[dict[str, str]], variant: str) -> list[dict[str, str]]:
    return [
        {
            "label_class": row["label_class"],
            "final_split": row["final_split"],
            "relief_score": row[f"{variant}_score"],
        }
        for row in score_rows
    ]


def metric_rows(score_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    out = []
    for variant in VARIANT_NAMES:
        rows = rows_for_metric(score_rows, variant)
        all_row = metric_row("all", rows)
        out.append({"variant": variant, **all_row})
        by_split: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in rows:
            by_split[row["final_split"]].append(row)
        for split, split_rows in sorted(by_split.items()):
            out.append({"variant": variant, **metric_row(f"split:{split}", split_rows)})
    return out


def best_metric(metrics: list[dict[str, str]], subset: str = "all") -> dict[str, str]:
    candidates = [row for row in metrics if row["subset"] == subset and row["roc_auc"] != "n/a"]
    return max(candidates, key=lambda row: parse_float(row["roc_auc"])) if candidates else {}


def load_baseline_summary(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [
        f"- single relief {row['subset']}: ROC-AUC `{row['roc_auc']}`, AP `{row['average_precision']}`."
        for row in read_tsv(path)
        if row.get("subset") in {"all", "split:test_o_val", "split:test_trasancos"}
    ]


def o_val_rows(score_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(
        [row for row in score_rows if row["final_split"] == "test_o_val"],
        key=lambda row: int(row["archetype_max_rank"]),
    )


def write_report(path: Path, args: argparse.Namespace, score_rows: list[dict[str, str]], metrics: list[dict[str, str]]) -> None:
    best = best_metric(metrics)
    best_o_val = best_metric(metrics, "split:test_o_val")
    variant_counts = defaultdict(int)
    for row in score_rows:
        variant_counts[row["best_variant"]] += 1
    lines = [
        "# Weak-label relief score variants",
        "",
        f"Generated: {GENERATED_AT}",
        "",
        "## What This Is",
        "",
        "A diagnostic comparison of simple relief scoring variants for variable castro morphologies. It reuses the same MDT5 features and does not download new data.",
        "This is model-formulation evidence, not final validation: the variants were inspected after the first single-score baseline and must be confirmed on broader train/val splits.",
        "",
        "## Files",
        "",
        f"- Score TSV: `{rel_to_project(args.out_dir / 'weak_label_relief_score_variants_holdouts.tsv')}`",
        f"- Metrics TSV: `{rel_to_project(args.out_dir / 'weak_label_relief_score_variant_metrics_holdouts.tsv')}`",
        "",
        "## Variant Logic",
        "",
        "- `hilltop`: favors positive topographic prominence plus slope/local-relief contrast.",
        "- `edge_ring`: favors ring/edge contrast without requiring the core to be higher than context.",
        "- `promontory`: favors strong annular relief and edge texture, useful for coastal/promontory shapes.",
        "- `archetype_max`: takes the strongest of the three morphology variants per site.",
        "",
        "## Best Overall",
        "",
        f"- Best all-subset variant: `{best.get('variant', 'n/a')}` with ROC-AUC `{best.get('roc_auc', 'n/a')}` and AP `{best.get('average_precision', 'n/a')}`.",
        f"- Best O Val variant: `{best_o_val.get('variant', 'n/a')}` with ROC-AUC `{best_o_val.get('roc_auc', 'n/a')}` and AP `{best_o_val.get('average_precision', 'n/a')}`.",
        "- O Val has only five holdout rows, so its perfect score is qualitative error-analysis evidence, not statistical proof.",
        "",
        "## Best Variant Counts",
        "",
    ]
    for variant, count in sorted(variant_counts.items()):
        lines.append(f"- {variant}: {count}")
    baseline_summary = load_baseline_summary(args.baseline_metrics)
    if baseline_summary:
        lines.extend(["", "## Single Relief Baseline Reference", ""])
        lines.extend(baseline_summary)
    lines.extend(["", "## Metrics", ""])
    lines.append("| Variant | Subset | Rows | Pos | Neg | ROC-AUC | AP | P@50 | R@50 | Best pos rank | Median pos rank |")
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for row in metrics:
        lines.append(
            "| {variant} | {subset} | {rows} | {positives} | {negatives} | {roc_auc} | {average_precision} | {precision_at_50} | {recall_at_50} | {best_positive_rank} | {median_positive_rank} |".format(
                **row
            )
        )
    lines.extend(["", "## O Val Archetype-Max Reading", ""])
    lines.append("| Archetype rank | Best variant | Hilltop rank | Edge-ring rank | Promontory rank | Class | Name |")
    lines.append("|---:|---|---:|---:|---:|---:|---|")
    for row in o_val_rows(score_rows):
        lines.append(
            f"| {row['archetype_max_rank']} | {row['best_variant']} | {row['hilltop_rank']} | {row['edge_ring_rank']} | {row['promontory_rank']} | {row['label_class']} | `{row['name']}` |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- A single prominence-heavy relief score misses some plausible castro morphologies, especially coastal/promontory cases.",
            "- The multi-variant score rescues `Castro de Pena Lopesa` because it no longer assumes that every castro is a raised hilltop.",
            "- This supports the project decision to train or rank with morphology-aware channels rather than one universal castro shape.",
            "- The next validation step is to run these variants over larger train/validation relief exports before treating them as detector features.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", type=Path, default=DEFAULT_FEATURES)
    parser.add_argument("--baseline-metrics", type=Path, default=DEFAULT_BASELINE_METRICS)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def resolve_args(args: argparse.Namespace) -> argparse.Namespace:
    for attr in ("features", "baseline_metrics", "out_dir", "report"):
        value = getattr(args, attr)
        setattr(args, attr, value if value.is_absolute() else PROJECT_ROOT / value)
    return args


def main() -> None:
    args = resolve_args(parse_args())
    feature_rows = read_tsv(args.features)
    score_rows = build_score_rows(feature_rows)
    metrics = metric_rows(score_rows)
    scores_path = args.out_dir / "weak_label_relief_score_variants_holdouts.tsv"
    metrics_path = args.out_dir / "weak_label_relief_score_variant_metrics_holdouts.tsv"
    write_tsv(scores_path, score_rows, SCORE_FIELDS)
    write_tsv(metrics_path, metrics, METRICS_FIELDS)
    write_report(args.report, args, score_rows, metrics)
    best = best_metric(metrics)
    print(f"score_rows={len(score_rows)}")
    print(f"best_variant={best.get('variant', 'n/a')}")
    print(f"best_auc={best.get('roc_auc', 'n/a')}")
    print(f"wrote={rel_to_project(scores_path)}")
    print(f"report={rel_to_project(args.report)}")


if __name__ == "__main__":
    main()
