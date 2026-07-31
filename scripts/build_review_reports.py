#!/usr/bin/env python3
"""Generate human-readable review queues and status reports."""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
QGIS_REVIEW_DIR = PROJECT_ROOT / "data/qgis-review"
REPORTS_DIR = PROJECT_ROOT / "reports"
QUEUES_DIR = PROJECT_ROOT / "data/review-queues"


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, dialect="excel-tab"))


def write_tsv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, dialect="excel-tab")
        writer.writeheader()
        writer.writerows(rows)


def sort_key(row: dict[str, str]) -> tuple[int, str, str]:
    priority_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    return (priority_order.get(row["priority"], 99), row["municipality"], row["primary_name"])


def build_queues(tasks: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    queues = {
        "p0_blockers": [row for row in tasks if row["priority"] == "P0"],
        "p1_training_candidates": [row for row in tasks if row["priority"] == "P1"],
        "p2_reconciliation": [row for row in tasks if row["priority"] == "P2"],
        "o_val_holdout": [row for row in tasks if row["split"] == "test_o_val" or row["parish"] in {"O Val", "Santa María Maior do Val"}],
        "needs_geocoding": [row for row in tasks if row["has_coordinates"] == "no"],
    }
    return {name: sorted(rows, key=sort_key) for name, rows in queues.items()}


def write_queue_files(queues: dict[str, list[dict[str, str]]]) -> None:
    fields = [
        "task_id",
        "priority",
        "site_id",
        "primary_name",
        "municipality",
        "parish",
        "dataset_use",
        "split",
        "has_coordinates",
        "qgis_action",
        "suggested_decision",
        "notes",
    ]
    for name, rows in queues.items():
        write_tsv(QUEUES_DIR / f"{name}.tsv", rows, fields)


def markdown_table(rows: list[dict[str, str]], limit: int = 20) -> list[str]:
    lines = ["| Prioridad | Sitio | Municipio | Split | Acción |", "|---|---|---|---|---|"]
    for row in rows[:limit]:
        lines.append(
            "| {priority} | {name} | {municipality} | {split} | {action} |".format(
                priority=row["priority"],
                name=row["primary_name"].replace("|", "/"),
                municipality=row["municipality"],
                split=row["split"],
                action=row["suggested_decision"],
            )
        )
    if len(rows) > limit:
        lines.append(f"| ... | {len(rows) - limit} tareas más |  |  |  |")
    return lines


def write_report(tasks: list[dict[str, str]], queues: dict[str, list[dict[str, str]]]) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    by_priority = Counter(row["priority"] for row in tasks)
    by_split = Counter(row["split"] for row in tasks)
    by_municipality = Counter(row["municipality"] for row in tasks)
    by_action = Counter(row["suggested_decision"] for row in tasks)

    lines: list[str] = [
        "# Review status report",
        "",
        "Generated: 2026-07-31",
        "",
        "## Summary",
        "",
        f"- Total site tasks: {len(tasks)}",
        f"- P0 blockers: {by_priority['P0']}",
        f"- P1 training/review candidates: {by_priority['P1']}",
        f"- P2 reconciliation tasks: {by_priority['P2']}",
        f"- Missing coordinates: {sum(1 for row in tasks if row['has_coordinates'] == 'no')}",
        "",
        "## Split counts",
        "",
    ]
    for split, count in sorted(by_split.items()):
        lines.append(f"- {split}: {count}")
    lines.extend(["", "## Municipality counts", ""])
    for municipality, count in sorted(by_municipality.items()):
        lines.append(f"- {municipality}: {count}")
    lines.extend(["", "## Suggested decisions", ""])
    for action, count in sorted(by_action.items()):
        lines.append(f"- {action}: {count}")

    for title, queue_name in [
        ("P0 Blockers", "p0_blockers"),
        ("O Val Holdout", "o_val_holdout"),
        ("Needs Geocoding", "needs_geocoding"),
        ("P1 Training Candidates", "p1_training_candidates"),
    ]:
        lines.extend(["", f"## {title}", ""])
        lines.extend(markdown_table(queues[queue_name]))

    lines.extend(
        [
            "",
            "## Operational conclusion",
            "",
            "Training is blocked until QGIS review produces at least one accepted polygon in `labels_reviewed` and at least one accepted negative area in `negative_areas_reviewed`.",
        ]
    )
    (REPORTS_DIR / "review_status.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_geocoding_blockers(geocoding_rows: list[dict[str, str]]) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    by_record_type = Counter(row["record_type"] for row in geocoding_rows)
    by_dataset_use = Counter(row["dataset_use"] for row in geocoding_rows)
    by_municipality = Counter(row["municipality"] for row in geocoding_rows)

    lines: list[str] = [
        "# Geocoding blockers",
        "",
        "Generated: 2026-07-31",
        "",
        f"- Pending rows: {len(geocoding_rows)}",
        "- Checked automatically: embedded UTM in source text, scraped decimal coordinates, coded Galipedia coordinate supplement and downloadable PDF text.",
        "- Rule: no coordinate is assigned from parish/place names alone.",
        "",
        "## By record type",
        "",
    ]
    for key, count in sorted(by_record_type.items()):
        lines.append(f"- {key}: {count}")
    lines.extend(["", "## By dataset use", ""])
    for key, count in sorted(by_dataset_use.items()):
        lines.append(f"- {key}: {count}")
    lines.extend(["", "## By municipality", ""])
    for key, count in sorted(by_municipality.items()):
        lines.append(f"- {key}: {count}")

    lines.extend(
        [
            "",
            "## Pending rows",
            "",
            "| Site | Municipality | Parish | Code | Type | Dataset use | Source |",
            "|---|---|---|---|---|---|---|",
        ]
    )
    for row in geocoding_rows:
        lines.append(
            "| {name} | {municipality} | {parish} | {code} | {record_type} | {dataset_use} | {source} |".format(
                name=row["primary_name"].replace("|", "/"),
                municipality=row["municipality"],
                parish=row["parish"].replace("|", "/"),
                code=row["ga_code"],
                record_type=row["record_type"],
                dataset_use=row["dataset_use"],
                source=row["sources"].replace("|", "/")[:120],
            )
        )

    lines.extend(
        [
            "",
            "## Operational conclusion",
            "",
            "These rows need manual source work, QGIS visual inspection, an official catalogue with coordinates, or a deliberate discard decision. They should not be converted into raster windows automatically.",
        ]
    )
    (REPORTS_DIR / "geocoding_blockers.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    tasks = read_tsv(QGIS_REVIEW_DIR / "qgis_review_tasks.tsv")
    geocoding_rows = read_tsv(QGIS_REVIEW_DIR / "geocoding_tasks.tsv")
    queues = build_queues(tasks)
    write_queue_files(queues)
    write_report(tasks, queues)
    write_geocoding_blockers(geocoding_rows)
    print("Wrote review queues and report")
    for name, rows in queues.items():
        print(f"{name}: {len(rows)}")


if __name__ == "__main__":
    main()
