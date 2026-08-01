#!/usr/bin/env python3
"""Audit weak-label relief coverage and write the Spain/Portugal policy note."""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GENERATED_AT = "2026-08-01T00:00:00Z"

DATASETS = [
    {
        "dataset": "holdouts",
        "chip_manifest": PROJECT_ROOT / "data/weak-label-splits-v1/weak_label_chip_export_holdouts.tsv",
        "relief_manifest": PROJECT_ROOT / "data/weak-label-relief-v1/weak_label_relief_wcs_holdouts.tsv",
    },
    {
        "dataset": "val",
        "chip_manifest": PROJECT_ROOT / "data/weak-label-splits-v1/weak_label_chip_export_val.tsv",
        "relief_manifest": PROJECT_ROOT / "data/weak-label-relief-v1/weak_label_relief_wcs_val.tsv",
    },
    {
        "dataset": "train_mini",
        "chip_manifest": PROJECT_ROOT / "data/weak-label-splits-v1/weak_label_chip_export_train_mini.tsv",
        "relief_manifest": PROJECT_ROOT / "data/weak-label-relief-v1/weak_label_relief_wcs_train_mini.tsv",
    },
]

MASTER_SPLITS = PROJECT_ROOT / "data/weak-label-splits-v1/weak_label_master.tsv"
OUT_DIR = PROJECT_ROOT / "data/weak-label-relief-v1"
COVERAGE_SUMMARY = OUT_DIR / "weak_label_relief_coverage_policy.tsv"
PLANNED_SUMMARY = OUT_DIR / "weak_label_relief_planned_country_summary.tsv"
UNSUPPORTED_ROWS = OUT_DIR / "weak_label_relief_unsupported_country_rows.tsv"
REPORT = PROJECT_ROOT / "reports/weak_label_relief_coverage_policy_v1.md"

OFFICIAL_SOURCES = [
    {
        "name": "DGT Modelos Digitais do Relevo",
        "url": "https://www.dgterritorio.gov.pt/atividades/cartografia/cartografia-topografica/modelos-digitais",
        "evidence": "Portugal continental has LiDAR access through the DGT data centre or the QGIS CDD Downloader plugin, with LAZ and derived MDT/MDS GeoTIFF products at 0.5 m, 2 m and 10 m.",
        "implication": "Portugal needs its own DGT/CDD ingestion path; the current Spanish WCS target should not be stretched across the border.",
    },
    {
        "name": "DGT LiDAR Portugal Continental",
        "url": "https://www.dgterritorio.gov.pt/levantamento-lidar-de-portugal-continental-0",
        "evidence": "DGT states that the 2024-2025 LiDAR data can be downloaded from the DGT data centre, that each access is limited to about 200 km2, and that an API is planned; about 90% of mainland coverage is available while the northwest remains in production.",
        "implication": "Northern Portugal may still have holes; the pipeline must record download availability per tile before using Portuguese relief in metrics.",
    },
    {
        "name": "dados.gov.pt LiDAR Portugal Continental",
        "url": "https://dados.gov.pt/pt/datasets/dados-lidar-de-portugal-continental/",
        "evidence": "The open-data catalogue describes 2024 airborne LiDAR, 10 points/m2, LAS point clouds and MDT/MDS products at 50 cm and 2 m resolution under CC BY 4.0.",
        "implication": "The correct Portugal relief v2 source is technically strong, but it is a separate provider and CRS/vertical-datum problem.",
    },
]

SUMMARY_FIELDS = [
    "dataset",
    "final_split",
    "country",
    "label_role",
    "label_class",
    "total_rows",
    "rgb_valid_rows",
    "relief_valid_rows",
    "relief_unsupported_country_rows",
    "relief_failed_or_invalid_rows",
    "relief_missing_rows",
    "relief_usable_rate",
    "policy_bucket",
]

PLANNED_FIELDS = [
    "final_split",
    "country",
    "label_role",
    "label_class",
    "planned_rows",
    "policy_bucket",
]

UNSUPPORTED_FIELDS = [
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
    "longitude",
    "latitude",
    "wms_source",
    "wms_layer",
    "dem_status",
    "error",
]


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, dialect="excel-tab"))


def write_tsv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, dialect="excel-tab", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def rel(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT))


def key(row: dict[str, str]) -> tuple[str, str]:
    return row.get("tile_id", ""), row.get("sample_id", "")


def policy_bucket(country: str, relief_valid_rows: int, total_rows: int) -> str:
    if country == "ES" and relief_valid_rows == total_rows:
        return "relief_fusion_v1_allowed"
    if country == "ES":
        return "relief_fusion_v1_partial_check_required"
    if country == "PT":
        return "rgb_only_until_portugal_dem_provider"
    return "manual_policy_review_required"


def grouped_summary_for_dataset(dataset: str, chip_rows: list[dict[str, str]], relief_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    relief_by_key = {key(row): row for row in relief_rows}
    grouped: dict[tuple[str, str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in chip_rows:
        grouped[(row.get("final_split", ""), row.get("country", ""), row.get("label_role", ""), row.get("label_class", ""))].append(row)

    out = []
    for (final_split, country, label_role, label_class), rows in sorted(grouped.items()):
        rgb_valid = sum(1 for row in rows if row.get("image_status") == "valid")
        relief_statuses = [relief_by_key.get(key(row), {}).get("dem_status", "missing_relief_manifest") for row in rows]
        relief_valid = sum(1 for status in relief_statuses if status == "valid")
        unsupported = sum(1 for status in relief_statuses if status == "unsupported_country")
        missing = sum(1 for status in relief_statuses if status == "missing_relief_manifest")
        failed = len(rows) - relief_valid - unsupported - missing
        total = len(rows)
        out.append(
            {
                "dataset": dataset,
                "final_split": final_split,
                "country": country,
                "label_role": label_role,
                "label_class": label_class,
                "total_rows": str(total),
                "rgb_valid_rows": str(rgb_valid),
                "relief_valid_rows": str(relief_valid),
                "relief_unsupported_country_rows": str(unsupported),
                "relief_failed_or_invalid_rows": str(failed),
                "relief_missing_rows": str(missing),
                "relief_usable_rate": f"{relief_valid / total:.6f}" if total else "0.000000",
                "policy_bucket": policy_bucket(country, relief_valid, total),
            }
        )
    return out


def unsupported_rows_for_dataset(dataset: str, chip_rows: list[dict[str, str]], relief_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    relief_by_key = {key(row): row for row in relief_rows}
    out = []
    for row in chip_rows:
        relief_row = relief_by_key.get(key(row), {})
        if relief_row.get("dem_status") != "unsupported_country":
            continue
        out.append(
            {
                "dataset": dataset,
                "tile_id": row.get("tile_id", ""),
                "sample_id": row.get("sample_id", ""),
                "bank_id": row.get("bank_id", ""),
                "label_class": row.get("label_class", ""),
                "label_role": row.get("label_role", ""),
                "final_split": row.get("final_split", ""),
                "country": row.get("country", ""),
                "name": row.get("name", ""),
                "municipality": row.get("municipality", ""),
                "parish": row.get("parish", ""),
                "longitude": row.get("longitude", ""),
                "latitude": row.get("latitude", ""),
                "wms_source": row.get("wms_source", ""),
                "wms_layer": row.get("wms_layer", ""),
                "dem_status": relief_row.get("dem_status", ""),
                "error": relief_row.get("error", ""),
            }
        )
    return out


def planned_summary(master_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    counts = Counter(
        (
            row.get("final_split", ""),
            row.get("country", ""),
            row.get("label_role", ""),
            row.get("label_class", ""),
        )
        for row in master_rows
        if row.get("final_split") not in {"excluded_review", ""}
    )
    rows = []
    for (final_split, country, label_role, label_class), count in sorted(counts.items()):
        bucket = "planned_relief_provider_needed" if country == "PT" else "planned_spanish_mdt5_provider"
        rows.append(
            {
                "final_split": final_split,
                "country": country,
                "label_role": label_role,
                "label_class": label_class,
                "planned_rows": str(count),
                "policy_bucket": bucket,
            }
        )
    return rows


def markdown_table(rows: list[dict[str, str]], fields: list[str], *, limit: int = 20) -> list[str]:
    shown = rows[:limit]
    lines = [
        "| " + " | ".join(fields) + " |",
        "| " + " | ".join("---" for _ in fields) + " |",
    ]
    for row in shown:
        values = [str(row.get(field, "")).replace("|", "/") for field in fields]
        lines.append("| " + " | ".join(values) + " |")
    if len(rows) > limit:
        values = ["..."] + [f"{len(rows) - limit} more rows not shown"] + [""] * max(0, len(fields) - 2)
        lines.append("| " + " | ".join(values) + " |")
    return lines


def write_report(
    coverage_rows: list[dict[str, str]],
    planned_rows: list[dict[str, str]],
    unsupported_rows: list[dict[str, str]],
) -> None:
    dataset_totals: dict[str, Counter[str]] = defaultdict(Counter)
    for row in coverage_rows:
        dataset_totals[row["dataset"]]["total"] += int(row["total_rows"])
        dataset_totals[row["dataset"]]["valid"] += int(row["relief_valid_rows"])
        dataset_totals[row["dataset"]]["unsupported"] += int(row["relief_unsupported_country_rows"])
        dataset_totals[row["dataset"]]["failed"] += int(row["relief_failed_or_invalid_rows"])
        dataset_totals[row["dataset"]]["missing"] += int(row["relief_missing_rows"])

    planned_country_totals = Counter()
    for row in planned_rows:
        planned_country_totals[row["country"]] += int(row["planned_rows"])

    lines = [
        "# Weak-label relief coverage policy v1",
        "",
        f"Generated: {GENERATED_AT}",
        "",
        "## Decision",
        "",
        "The current RGB+relief baseline is a Spain-relief experiment. Portuguese rows remain valid for RGB-only diagnostics, but they must not be treated as relief failures or mixed into fused relief metrics until a separate Portugal DEM/DTM provider is implemented and audited.",
        "",
        "Operational policy:",
        "",
        "- `ES` rows with valid MDT5 chips can enter `relief_fusion_v1`.",
        "- `PT` rows stay `rgb_only_until_portugal_dem_provider`.",
        "- Global metrics must be reported as `RGB all`, `relief-valid Spain`, and `Portugal RGB-only/pending DEM`, not as one uniform fused benchmark.",
        "- Any Portugal relief v2 must write provider, CRS, vertical reference, resolution and source availability per tile.",
        "",
        "## Files",
        "",
        f"- Coverage summary: `{rel(COVERAGE_SUMMARY)}`",
        f"- Planned split country summary: `{rel(PLANNED_SUMMARY)}`",
        f"- Unsupported Portugal rows: `{rel(UNSUPPORTED_ROWS)}`",
        "",
        "## Existing Export Coverage",
        "",
        "| dataset | total | relief_valid | unsupported_country | failed_or_invalid | missing | relief_usable_rate |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for dataset, counts in sorted(dataset_totals.items()):
        total = counts["total"]
        rate = counts["valid"] / total if total else 0.0
        lines.append(
            f"| {dataset} | {total} | {counts['valid']} | {counts['unsupported']} | {counts['failed']} | {counts['missing']} | {rate:.6f} |"
        )

    lines.extend(
        [
            "",
            "## Detail By Split, Country And Role",
            "",
            *markdown_table(
                coverage_rows,
                [
                    "dataset",
                    "final_split",
                    "country",
                    "label_role",
                    "total_rows",
                    "relief_valid_rows",
                    "relief_unsupported_country_rows",
                    "policy_bucket",
                ],
                limit=30,
            ),
            "",
            "## Planned Weak-label Footprint",
            "",
            f"- Planned ES rows: `{planned_country_totals.get('ES', 0)}`.",
            f"- Planned PT rows: `{planned_country_totals.get('PT', 0)}`.",
            "",
            *markdown_table(
                planned_rows,
                ["final_split", "country", "label_role", "planned_rows", "policy_bucket"],
                limit=30,
            ),
            "",
            "## Official Portugal Relief Sources Checked",
            "",
        ]
    )
    for source in OFFICIAL_SOURCES:
        lines.extend(
            [
                f"### {source['name']}",
                "",
                f"- URL: {source['url']}",
                f"- Evidence: {source['evidence']}",
                f"- Implication: {source['implication']}",
                "",
            ]
        )

    lines.extend(
        [
            "## Why This Remains Blocked For Fusion",
            "",
            "The Spanish export script requests `Elevacion25830_5` from the Spanish MDT WCS in `EPSG:25830`. That is correct for Spain/Galicia, but not for Portugal. DGT Portugal exposes strong LiDAR/MDT data, yet through a different distribution path and Portuguese reference system. Mixing those two without an explicit provider adapter would make the model look more complete than it is.",
            "",
            "The immediate unblock is therefore not to fake Portuguese relief, but to keep v1 honest and add a Portugal DEM provider as a separate v2 task.",
            "",
            "## Next Engineering Step",
            "",
            "Build `export_weak_label_relief_dgt_pt.py` only after a small CDD inventory test confirms tile addressing, download URLs, CRS, licensing metadata and coverage in the north of Portugal. Until then, use RGB for Portugal and relief/fusion for Spain.",
            "",
            "## Unsupported Row Sample",
            "",
            *markdown_table(
                unsupported_rows,
                ["dataset", "final_split", "label_role", "name", "municipality", "dem_status"],
                limit=20,
            ),
        ]
    )
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    coverage_rows: list[dict[str, str]] = []
    unsupported_rows: list[dict[str, str]] = []
    for config in DATASETS:
        chip_rows = read_tsv(config["chip_manifest"])
        relief_rows = read_tsv(config["relief_manifest"])
        coverage_rows.extend(grouped_summary_for_dataset(config["dataset"], chip_rows, relief_rows))
        unsupported_rows.extend(unsupported_rows_for_dataset(config["dataset"], chip_rows, relief_rows))

    planned_rows = planned_summary(read_tsv(MASTER_SPLITS))
    write_tsv(COVERAGE_SUMMARY, coverage_rows, SUMMARY_FIELDS)
    write_tsv(PLANNED_SUMMARY, planned_rows, PLANNED_FIELDS)
    write_tsv(UNSUPPORTED_ROWS, unsupported_rows, UNSUPPORTED_FIELDS)
    write_report(coverage_rows, planned_rows, unsupported_rows)

    print(f"coverage_rows={len(coverage_rows)}")
    print(f"planned_rows={len(planned_rows)}")
    print(f"unsupported_rows={len(unsupported_rows)}")
    print(f"wrote={rel(COVERAGE_SUMMARY)}")
    print(f"wrote={rel(PLANNED_SUMMARY)}")
    print(f"wrote={rel(UNSUPPORTED_ROWS)}")
    print(f"report={rel(REPORT)}")


if __name__ == "__main__":
    main()
