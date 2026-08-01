#!/usr/bin/env python3
"""Build an autonomous, non-final decision seed for the P0 review queue."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

from train_weak_label_rgb_baseline import parse_float, read_tsv, rel_to_project


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DOSSIER = PROJECT_ROOT / "data/weak-label-error-review-workspace-v1/p0_visual_dossier.tsv"
DEFAULT_OUT_TSV = PROJECT_ROOT / "data/weak-label-error-review-workspace-v1/p0_decision_seed.tsv"
DEFAULT_OUT_GEOJSON = PROJECT_ROOT / "data/weak-label-error-review-workspace-v1/p0_decision_seed.geojson"
DEFAULT_OUT_GPKG = PROJECT_ROOT / "data/weak-label-error-review-workspace-v1/p0_decision_seed_v1.gpkg"
DEFAULT_REPORT = PROJECT_ROOT / "reports/weak_label_p0_decision_seed_v1.md"

GENERATED_AT = "2026-08-01T00:00:00Z"
SOURCE_CRS = "EPSG:4326"
BUFFER_CRS = "EPSG:25829"
REVIEW_BUFFER_M = 120.0

SEED_FIELDS = [
    "decision_seed_id",
    "dossier_order",
    "sample_review_key",
    "sample_id",
    "autonomous_seed_status",
    "accepted_label_status",
    "can_enter_training_now",
    "autonomous_decision",
    "training_gate",
    "proposed_training_use",
    "geometry_action",
    "seed_geometry_role",
    "review_risk",
    "next_qgis_action",
    "pretriage_group",
    "pretriage_decision",
    "pretriage_confidence",
    "suggested_taxonomy",
    "label_class",
    "name",
    "municipality",
    "parish",
    "country",
    "longitude",
    "latitude",
    "fusion_probability",
    "fusion_rank",
    "max_safety_rank",
    "specialist_probability",
    "specialist_rank",
    "specialist_mean_rank",
    "negative_type",
    "morphology_proxy",
    "visual_card",
    "review_buffer_m",
    "source_queues",
    "source_lanes",
    "source_review_ids",
    "rationale",
]


def require_runtime() -> None:
    missing = []
    for module in ("geopandas", "shapely", "pyproj"):
        try:
            __import__(module)
        except Exception:
            missing.append(module)
    if missing:
        raise SystemExit(f"Missing Python modules: {', '.join(missing)}")


def write_tsv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            dialect="excel-tab",
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def taxonomic_decision(row: dict[str, str]) -> dict[str, str]:
    taxonomy = row.get("suggested_taxonomy", "")
    group = row.get("pretriage_group", "")
    morphology = row.get("morphology_proxy", "")
    if taxonomy == "castro":
        if "promontory" in morphology:
            review_risk = "variable_morphology_promontory_boundary_risk"
        elif group == "o_val_local_first":
            review_risk = "local_holdout_boundary_risk"
        else:
            review_risk = "positive_boundary_uncertainty"
        return {
            "autonomous_decision": "positive_boundary_review_required",
            "training_gate": "needs_reviewed_polygon_before_strong_training",
            "proposed_training_use": "positive_candidate_after_boundary_review",
            "geometry_action": "draw_or_refine_visible_castro_boundary",
            "seed_geometry_role": "review_search_area_not_label",
            "review_risk": review_risk,
            "next_qgis_action": "inspect_RGB_DEM_slope_LRM_then_draw_boundary_or_mark_needs_followup",
            "rationale": (
                "Known positive or specialist rescue; use the buffer only as a review search area. "
                "Do not convert this seed into an accepted positive polygon without boundary review."
            ),
        }
    if taxonomy == "mamoa":
        return {
            "autonomous_decision": "confirm_specific_archaeological_hard_negative",
            "training_gate": "eligible_only_after_taxonomy_confirmation",
            "proposed_training_use": "mamoa_specific_hard_negative_not_generic_absence",
            "geometry_action": "confirm_mound_non_castro_and_keep_separate_from_absence",
            "seed_geometry_role": "mamoa_review_buffer_not_absence_area",
            "review_risk": "archaeological_distractor_not_absence",
            "next_qgis_action": "confirm_mamoa_taxonomy_or_mark_non_decidible",
            "rationale": (
                "Catalogued mamoa/distractor pattern; useful for castro-vs-mamoa separation only after review. "
                "Do not use as generic background absence."
            ),
        }
    return {
        "autonomous_decision": "defer_non_decidible_review",
        "training_gate": "exclude_until_reviewed",
        "proposed_training_use": "exclude_until_reviewed",
        "geometry_action": "inspect_context_before_any_label",
        "seed_geometry_role": "review_search_area_not_label",
        "review_risk": "taxonomy_uncertain",
        "next_qgis_action": "mark_non_decidible_unless_evidence_is_clear",
        "rationale": "Taxonomy is not strong enough for autonomous seeding.",
    }


def decision_rows(dossier_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    rows = []
    for row in dossier_rows:
        decision = taxonomic_decision(row)
        seed = {field: "" for field in SEED_FIELDS}
        seed.update(row)
        seed.update(decision)
        seed["decision_seed_id"] = f"p0-seed-{int(row['dossier_order']):03d}"
        seed["autonomous_seed_status"] = "proposed_not_final"
        seed["accepted_label_status"] = "not_accepted"
        seed["can_enter_training_now"] = "no"
        seed["review_buffer_m"] = f"{REVIEW_BUFFER_M:.0f}"
        rows.append(seed)
    return rows


def build_geodataframes(rows: list[dict[str, str]]):
    import geopandas as gpd
    from shapely.geometry import Point

    records = []
    geometries = []
    for row in rows:
        lon = parse_float(row.get("longitude", ""))
        lat = parse_float(row.get("latitude", ""))
        record = {field: row.get(field, "") for field in SEED_FIELDS}
        records.append(record)
        geometries.append(Point(lon, lat))

    points = gpd.GeoDataFrame(records, geometry=geometries, crs=SOURCE_CRS)
    buffers = points.to_crs(BUFFER_CRS).copy()
    buffers["geometry"] = buffers.geometry.buffer(REVIEW_BUFFER_M)
    buffers = buffers.to_crs(SOURCE_CRS)
    buffers["seed_geometry_role"] = buffers["seed_geometry_role"].astype(str)
    return points, buffers


def write_geodata(points, buffers, out_geojson: Path, out_gpkg: Path) -> None:
    out_geojson.parent.mkdir(parents=True, exist_ok=True)
    points.to_file(out_geojson, driver="GeoJSON")
    if out_gpkg.exists():
        out_gpkg.unlink()
    points.to_file(out_gpkg, layer="p0_decision_seed_points", driver="GPKG")
    buffers.to_file(out_gpkg, layer="p0_review_buffers_120m", driver="GPKG")


def write_report(path: Path, rows: list[dict[str, str]], out_tsv: Path, out_geojson: Path, out_gpkg: Path) -> None:
    by_taxonomy = Counter(row["suggested_taxonomy"] for row in rows)
    by_decision = Counter(row["autonomous_decision"] for row in rows)
    by_training_gate = Counter(row["training_gate"] for row in rows)

    lines = [
        "# Weak-label P0 decision seed v1",
        "",
        f"Generated: {GENERATED_AT}",
        "",
        "## What This Is",
        "",
        "This is an autonomous decision seed for the P0 weak-label review queue.",
        "It is not a final annotation layer, not an archaeological discovery report, and not a strong training dataset.",
        "Every row keeps `autonomous_seed_status=proposed_not_final`, `accepted_label_status=not_accepted` and `can_enter_training_now=no`.",
        "",
        "## Outputs",
        "",
        f"- TSV: `{rel_to_project(out_tsv)}`",
        f"- GeoJSON points: `{rel_to_project(out_geojson)}`",
        f"- GeoPackage: `{rel_to_project(out_gpkg)}`",
        f"- GPKG layer: `p0_decision_seed_points`",
        f"- GPKG layer: `p0_review_buffers_120m`",
        "",
        "## Counts",
        "",
        f"- rows: `{len(rows)}`",
        "",
        "### Suggested taxonomy",
        "",
    ]
    for key, value in by_taxonomy.most_common():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "### Autonomous decision", ""])
    for key, value in by_decision.most_common():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "### Training gate", ""])
    for key, value in by_training_gate.most_common():
        lines.append(f"- `{key}`: `{value}`")

    lines.extend(
        [
            "",
            "## Review Order",
            "",
            "| Order | Taxonomy | Autonomous decision | Training gate | Name | Card |",
            "|---:|---|---|---|---|---|",
        ]
    )
    for row in rows:
        lines.append(
            f"| {row['dossier_order']} | `{row['suggested_taxonomy']}` | `{row['autonomous_decision']}` | "
            f"`{row['training_gate']}` | `{row['name']}` | `{row['visual_card']}` |"
        )

    lines.extend(
        [
            "",
            "## Use In QGIS",
            "",
            "1. Open `p0_decision_seed_v1.gpkg` together with `weak_label_error_review_workspace_v1.gpkg`.",
            "2. Use `p0_review_buffers_120m` only as a search area.",
            "3. For castros, draw a reviewed boundary in the editable annotation workspace only when the form is defensible.",
            "4. For mamoas, confirm taxonomy as a specific archaeological hard negative; do not convert it into generic absence.",
            "5. Leave uncertain cases as `non_decidible`.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dossier", type=Path, default=DEFAULT_DOSSIER)
    parser.add_argument("--out-tsv", type=Path, default=DEFAULT_OUT_TSV)
    parser.add_argument("--out-geojson", type=Path, default=DEFAULT_OUT_GEOJSON)
    parser.add_argument("--out-gpkg", type=Path, default=DEFAULT_OUT_GPKG)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_ROOT / path


def main() -> None:
    require_runtime()
    args = parse_args()
    dossier = resolve_path(args.dossier)
    out_tsv = resolve_path(args.out_tsv)
    out_geojson = resolve_path(args.out_geojson)
    out_gpkg = resolve_path(args.out_gpkg)
    report = resolve_path(args.report)

    rows = decision_rows(read_tsv(dossier))
    points, buffers = build_geodataframes(rows)
    write_tsv(out_tsv, rows, SEED_FIELDS)
    write_geodata(points, buffers, out_geojson, out_gpkg)
    write_report(report, rows, out_tsv, out_geojson, out_gpkg)

    print(f"decision_seed_rows={len(rows)}")
    print(f"points={len(points)}")
    print(f"buffers={len(buffers)}")
    print(f"wrote={rel_to_project(out_tsv)}")
    print(f"geojson={rel_to_project(out_geojson)}")
    print(f"gpkg={rel_to_project(out_gpkg)}")
    print(f"report={rel_to_project(report)}")


if __name__ == "__main__":
    main()
