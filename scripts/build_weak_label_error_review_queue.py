#!/usr/bin/env python3
"""Build a review queue from weak-label fusion errors and morphology rescues."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from train_weak_label_rgb_baseline import parse_float, read_tsv, rel_to_project, write_tsv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MASTER = PROJECT_ROOT / "data/weak-label-splits-v1/weak_label_master.tsv"
DEFAULT_FUSION_SCORES = PROJECT_ROOT / "data/weak-label-fusion-v1/weak_label_rgb_relief_scores.tsv"
DEFAULT_PRIORITY_SCORES = PROJECT_ROOT / "data/weak-label-fusion-v1/weak_label_priority_blend_scores.tsv"
OUT_DIR = PROJECT_ROOT / "data/weak-label-fusion-v1"
DEFAULT_REPORT = PROJECT_ROOT / "reports/weak_label_error_review_queue_v1.md"

GENERATED_AT = "2026-08-01T00:00:00Z"

QUEUE_FIELDS = [
    "queue",
    "priority_order",
    "dataset",
    "final_split",
    "sample_id",
    "bank_id",
    "label_class",
    "label_role",
    "name",
    "municipality",
    "parish",
    "country",
    "longitude",
    "latitude",
    "fusion_probability",
    "fusion_rank",
    "max_safety_rank",
    "archetype_only_rank",
    "rank_delta_fusion_to_max",
    "negative_type",
    "morphology_proxy",
    "review_reason",
]


def row_key(row: dict[str, str]) -> tuple[str, str]:
    return row.get("dataset", ""), row.get("sample_id", "")


def load_priority_by_blend(path: Path) -> dict[tuple[str, str, str], dict[str, str]]:
    out = {}
    for row in read_tsv(path):
        out[(row["blend"], row["dataset"], row["sample_id"])] = row
    return out


def enrich_rows(
    fusion_rows: list[dict[str, str]],
    master_by_sample: dict[str, dict[str, str]],
    priority_by_blend: dict[tuple[str, str, str], dict[str, str]],
) -> list[dict[str, str]]:
    out = []
    for fusion in fusion_rows:
        master = master_by_sample.get(fusion["sample_id"], {})
        dataset = fusion["dataset"]
        sample_id = fusion["sample_id"]
        max_safety = priority_by_blend.get(("max_safety", dataset, sample_id), {})
        archetype_only = priority_by_blend.get(("archetype_only", dataset, sample_id), {})
        fusion_rank = int(fusion.get("rank_desc_in_dataset", "0") or 0)
        max_rank = int(max_safety.get("rank_desc_in_dataset", fusion_rank) or fusion_rank)
        out.append(
            {
                **fusion,
                "longitude": master.get("longitude", ""),
                "latitude": master.get("latitude", ""),
                "fusion_probability": fusion.get("probability", ""),
                "fusion_rank": str(fusion_rank),
                "max_safety_rank": str(max_rank),
                "archetype_only_rank": archetype_only.get("rank_desc_in_dataset", ""),
                "rank_delta_fusion_to_max": str(fusion_rank - max_rank),
            }
        )
    return out


def ranked(rows: list[dict[str, str]], key_name: str, reverse: bool = True) -> list[dict[str, str]]:
    return sorted(rows, key=lambda row: parse_float(row.get(key_name, "0")), reverse=reverse)


def with_queue(queue: str, reason: str, rows: list[dict[str, str]], limit: int) -> list[dict[str, str]]:
    out = []
    for order, row in enumerate(rows[:limit], start=1):
        out.append(
            {
                "queue": queue,
                "priority_order": str(order),
                "dataset": row["dataset"],
                "final_split": row["final_split"],
                "sample_id": row["sample_id"],
                "bank_id": row["bank_id"],
                "label_class": row["label_class"],
                "label_role": row["label_role"],
                "name": row["name"],
                "municipality": row["municipality"],
                "parish": row["parish"],
                "country": row["country"],
                "longitude": row.get("longitude", ""),
                "latitude": row.get("latitude", ""),
                "fusion_probability": row["fusion_probability"],
                "fusion_rank": row["fusion_rank"],
                "max_safety_rank": row["max_safety_rank"],
                "archetype_only_rank": row.get("archetype_only_rank", ""),
                "rank_delta_fusion_to_max": row["rank_delta_fusion_to_max"],
                "negative_type": row["negative_type"],
                "morphology_proxy": row["morphology_proxy"],
                "review_reason": reason,
            }
        )
    return out


def build_queue_rows(enriched: list[dict[str, str]], holdout_limit: int, val_limit: int) -> list[dict[str, str]]:
    rows = []
    holdouts = [row for row in enriched if row["dataset"] == "holdouts"]
    val = [row for row in enriched if row["dataset"] == "val"]

    rows.extend(
        with_queue(
            "holdout_top_false_positives",
            "Known hard negative ranked high by the main fusion model; inspect as false-positive pattern.",
            ranked([row for row in holdouts if row["label_class"] == "0"], "fusion_probability"),
            holdout_limit,
        )
    )
    rows.extend(
        with_queue(
            "holdout_low_rank_positives",
            "Known positive ranked low by the main fusion model; inspect as false-negative morphology.",
            sorted([row for row in holdouts if row["label_class"] == "1"], key=lambda row: int(row["fusion_rank"]), reverse=True),
            holdout_limit,
        )
    )
    rows.extend(
        with_queue(
            "holdout_morphology_rescues",
            "Known positive moved upward by max_safety; inspect morphology archetype missed by the main model.",
            sorted(
                [
                    row
                    for row in holdouts
                    if row["label_class"] == "1" and int(row["rank_delta_fusion_to_max"]) > 0
                ],
                key=lambda row: int(row["rank_delta_fusion_to_max"]),
                reverse=True,
            ),
            holdout_limit,
        )
    )
    rows.extend(
        with_queue(
            "val_top_weak_negatives",
            "Weak-label negative ranked high on validation; inspect before treating it as true absence.",
            ranked([row for row in val if row["label_class"] == "0"], "fusion_probability"),
            val_limit,
        )
    )
    rows.extend(
        with_queue(
            "val_low_rank_weak_positives",
            "Weak positive ranked low on validation; inspect label noise, morphology and imagery quality.",
            sorted([row for row in val if row["label_class"] == "1"], key=lambda row: int(row["fusion_rank"]), reverse=True),
            val_limit,
        )
    )
    rows.extend(
        with_queue(
            "val_morphology_rescues",
            "Weak positive moved upward by max_safety; inspect as morphology-aware training evidence.",
            sorted(
                [
                    row
                    for row in val
                    if row["label_class"] == "1" and int(row["rank_delta_fusion_to_max"]) > 0
                ],
                key=lambda row: int(row["rank_delta_fusion_to_max"]),
                reverse=True,
            ),
            val_limit,
        )
    )
    return rows


def feature(row: dict[str, str]) -> dict:
    lon = parse_float(row.get("longitude", ""))
    lat = parse_float(row.get("latitude", ""))
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {field: row.get(field, "") for field in QUEUE_FIELDS if field not in {"longitude", "latitude"}},
    }


def write_geojson(path: Path, rows: list[dict[str, str]]) -> None:
    features = [
        feature(row)
        for row in rows
        if row.get("longitude") not in {"", "n/a"} and row.get("latitude") not in {"", "n/a"}
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def queue_counts(rows: list[dict[str, str]]) -> Counter:
    return Counter(row["queue"] for row in rows)


def o_val_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return sorted([row for row in rows if row["final_split"] == "test_o_val"], key=lambda row: int(row["fusion_rank"]))


def write_report(path: Path, args: argparse.Namespace, rows: list[dict[str, str]]) -> None:
    counts = queue_counts(rows)
    lines = [
        "# Weak-label error review queue v1",
        "",
        f"Generated: {GENERATED_AT}",
        "",
        "## What This Is",
        "",
        "A QGIS-ready review queue derived from the RGB+relief fusion baseline and the morphology safety blend.",
        "It turns model errors into inspection tasks: high-ranked hard negatives, low-ranked known positives and morphology rescues.",
        "",
        "## Files",
        "",
        f"- Queue TSV: `{rel_to_project(args.out_dir / 'weak_label_error_review_queue.tsv')}`",
        f"- Queue GeoJSON: `{rel_to_project(args.out_dir / 'weak_label_error_review_queue.geojson')}`",
        "",
        "## Queue Counts",
        "",
    ]
    for queue, count in sorted(counts.items()):
        lines.append(f"- `{queue}`: {count}")
    lines.extend(
        [
            "",
            "## O Val Rows In Queue",
            "",
            "| Queue | Fusion rank | Max-safety rank | Delta | Class | Name | Reason |",
            "|---|---:|---:|---:|---:|---|---|",
        ]
    )
    for row in o_val_rows(rows):
        lines.append(
            f"| `{row['queue']}` | {row['fusion_rank']} | {row['max_safety_rank']} | {row['rank_delta_fusion_to_max']} | {row['label_class']} | `{row['name']}` | {row['review_reason']} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Start QGIS inspection with `holdout_top_false_positives` and `holdout_low_rank_positives`; these explain what the model confuses in the local target area.",
            "- Use `holdout_morphology_rescues` as the sanity check for rare forms such as `Castro de Pena Lopesa`.",
            "- Validation queues are weak-label queues, not archaeological truth: a high-ranked negative may be a mislabeled absence, not a model error.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--master", type=Path, default=DEFAULT_MASTER)
    parser.add_argument("--fusion-scores", type=Path, default=DEFAULT_FUSION_SCORES)
    parser.add_argument("--priority-scores", type=Path, default=DEFAULT_PRIORITY_SCORES)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--holdout-limit", type=int, default=25)
    parser.add_argument("--val-limit", type=int, default=50)
    return parser.parse_args()


def resolve_args(args: argparse.Namespace) -> argparse.Namespace:
    args.master = args.master if args.master.is_absolute() else PROJECT_ROOT / args.master
    args.fusion_scores = args.fusion_scores if args.fusion_scores.is_absolute() else PROJECT_ROOT / args.fusion_scores
    args.priority_scores = args.priority_scores if args.priority_scores.is_absolute() else PROJECT_ROOT / args.priority_scores
    args.out_dir = args.out_dir if args.out_dir.is_absolute() else PROJECT_ROOT / args.out_dir
    args.report = args.report if args.report.is_absolute() else PROJECT_ROOT / args.report
    return args


def main() -> None:
    args = resolve_args(parse_args())
    master_by_sample = {row["sample_id"]: row for row in read_tsv(args.master)}
    priority_by_blend = load_priority_by_blend(args.priority_scores)
    enriched = enrich_rows(read_tsv(args.fusion_scores), master_by_sample, priority_by_blend)
    queue_rows = build_queue_rows(enriched, args.holdout_limit, args.val_limit)
    queue_path = args.out_dir / "weak_label_error_review_queue.tsv"
    geojson_path = args.out_dir / "weak_label_error_review_queue.geojson"
    write_tsv(queue_path, queue_rows, QUEUE_FIELDS)
    write_geojson(geojson_path, queue_rows)
    write_report(args.report, args, queue_rows)
    print(f"queue_rows={len(queue_rows)}")
    print(f"wrote={rel_to_project(queue_path)}")
    print(f"geojson={rel_to_project(geojson_path)}")
    print(f"report={rel_to_project(args.report)}")


if __name__ == "__main__":
    main()
