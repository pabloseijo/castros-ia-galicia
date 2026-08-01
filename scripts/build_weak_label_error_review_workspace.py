#!/usr/bin/env python3
"""Build a QGIS-ready workspace for weak-label error review lanes."""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import struct
from collections import Counter, defaultdict
from pathlib import Path

from train_weak_label_rgb_baseline import parse_float, read_tsv, rel_to_project


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QUEUE = PROJECT_ROOT / "data/weak-label-fusion-v1/weak_label_error_review_queue.tsv"
DEFAULT_VISUAL_BATCH = PROJECT_ROOT / "data/weak-label-fusion-v1/weak_label_error_review_visual_batch.tsv"
DEFAULT_OUT_DIR = PROJECT_ROOT / "data/weak-label-error-review-workspace-v1"
DEFAULT_REPORT = PROJECT_ROOT / "reports/weak_label_error_review_workspace_v1.md"

GENERATED_AT = "2026-08-01T00:00:00Z"
SRS_ID = 4326

LANE_LAYER_NAMES = {
    "mamoa_false_positive_review": "lane_mamoa_false_positive",
    "mamoa_specialist_positive_review": "lane_mamoa_specialist_positive",
    "morphology_rescue_review": "lane_morphology_rescue",
    "low_positive_review": "lane_low_positive",
    "weak_negative_review": "lane_weak_negative",
}

TASK_FIELDS = [
    "review_id",
    "sample_review_key",
    "duplicate_count",
    "duplicate_queues",
    "review_priority",
    "queue",
    "priority_order",
    "review_lane",
    "dataset",
    "final_split",
    "sample_id",
    "bank_id",
    "label_class",
    "label_role",
    "suggested_taxonomy",
    "suggested_decision",
    "boundary_action",
    "review_status",
    "review_notes",
    "final_taxonomy",
    "final_decision",
    "pretriage_order",
    "pretriage_group",
    "pretriage_decision",
    "pretriage_confidence",
    "training_use_after_review",
    "do_not_use_as",
    "visual_reading",
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
    "specialist_probability",
    "specialist_rank",
    "specialist_mean_rank",
    "rank_delta_fusion_to_max",
    "negative_type",
    "morphology_proxy",
    "visual_sheet",
    "review_reason",
]

TAXONOMY_ROWS = [
    {
        "taxonomy_label": "castro",
        "group": "positive",
        "training_use": "positive_candidate_after_boundary_review",
        "definition": "Recinto castrexo plausible: croa, muralla, foso, terraplén o plataforma coherente con castro.",
        "decision_rule": "Aceptar solo con forma/contexto suficiente; si no hay límite visible, dejar como needs_followup.",
    },
    {
        "taxonomy_label": "mamoa",
        "group": "hard_negative_archaeological",
        "training_use": "hard_negative_not_absence",
        "definition": "Túmulo megalítico o monumento funerario no-castro.",
        "decision_rule": "No usar como ausencia arqueológica; sirve para separar castro frente a monumento circular.",
    },
    {
        "taxonomy_label": "petroglifo",
        "group": "hard_negative_archaeological",
        "training_use": "hard_negative_not_absence",
        "definition": "Superficie de arte rupestre o entidad catalogada de arte rupestre.",
        "decision_rule": "Mantener como no-castro arqueológico; no convertir en fondo negativo genérico.",
    },
    {
        "taxonomy_label": "fortificacion_historica",
        "group": "hard_negative_archaeological",
        "training_use": "hard_negative_not_absence",
        "definition": "Fortificación histórica no castrexa.",
        "decision_rule": "Separar de castros por cronología/tipo; puede compartir señal defensiva.",
    },
    {
        "taxonomy_label": "cantera_mina",
        "group": "hard_negative_modern_or_extractiva",
        "training_use": "hard_negative_if_confirmed",
        "definition": "Corte extractivo, cantera, mina o alteración de terreno no arqueológica.",
        "decision_rule": "Aceptar como negativo si PNOA/LiDAR/contexto no sugieren estructura arqueológica.",
    },
    {
        "taxonomy_label": "ruido_moderno",
        "group": "hard_negative_modern",
        "training_use": "hard_negative_if_confirmed",
        "definition": "Carretera, urbanización, edificio, depósito, pista forestal u otra forma moderna.",
        "decision_rule": "Aceptar como negativo tras comprobación visual clara.",
    },
    {
        "taxonomy_label": "outro_arqueologico",
        "group": "hard_negative_archaeological",
        "training_use": "hard_negative_not_absence",
        "definition": "Elemento arqueológico no-castro que no encaja en las categorías anteriores.",
        "decision_rule": "No tratar como fondo; revisar si debe tener especialista propio.",
    },
    {
        "taxonomy_label": "non_decidible",
        "group": "uncertain",
        "training_use": "exclude_until_reviewed",
        "definition": "Caso ambiguo, sin señal suficiente o con imagen/relieve insuficiente.",
        "decision_rule": "Excluir de entrenamiento fuerte hasta revisión adicional.",
    },
]


def write_tsv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            dialect="excel-tab",
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def layer_name_for_lane(lane: str) -> str:
    return LANE_LAYER_NAMES.get(lane, f"lane_{lane[:40]}")


def review_priority(row: dict[str, str]) -> str:
    lane = row.get("review_lane", "")
    queue = row.get("queue", "")
    final_split = row.get("final_split", "")
    if final_split == "test_o_val":
        return "P0"
    if lane in {"mamoa_false_positive_review", "mamoa_specialist_positive_review"} and row.get("dataset") == "holdouts":
        return "P0"
    if queue.startswith("holdout_"):
        return "P1"
    if lane == "morphology_rescue_review":
        return "P1"
    return "P2"


def suggested_taxonomy(row: dict[str, str]) -> str:
    if row.get("label_class") == "1":
        return "castro"
    negative_type = row.get("negative_type", "")
    if negative_type == "megalithic_mound":
        return "mamoa"
    if negative_type == "rock_art_surface":
        return "petroglifo"
    if negative_type == "historic_fortification":
        return "fortificacion_historica"
    if negative_type in {"quarry", "mine", "quarry_or_mine"}:
        return "cantera_mina"
    if negative_type:
        return "outro_arqueologico"
    return "non_decidible"


def suggested_decision(row: dict[str, str]) -> str:
    lane = row.get("review_lane", "")
    if lane == "mamoa_false_positive_review":
        return "confirm_non_castro_archaeological_hard_negative"
    if lane == "mamoa_specialist_positive_review":
        return "inspect_as_positive_rescue"
    if lane == "morphology_rescue_review":
        return "inspect_morphology_rescue"
    if lane == "low_positive_review":
        return "inspect_low_rank_known_positive"
    return "inspect_weak_negative_no_absence_claim"


def boundary_action(row: dict[str, str]) -> str:
    taxonomy = suggested_taxonomy(row)
    if taxonomy == "castro":
        return "If visible, draw croa/muralla/recinto polygon; otherwise mark needs_followup."
    if taxonomy == "mamoa":
        return "Confirm mound/non-castro; do not treat as generic absence."
    if taxonomy in {"petroglifo", "fortificacion_historica", "outro_arqueologico"}:
        return "Confirm non-castro archaeological class; keep separate from generic negatives."
    if taxonomy in {"cantera_mina", "ruido_moderno"}:
        return "Accept as hard negative only if no plausible archaeological form remains."
    return "Mark non_decidible unless visual/context evidence is strong."


def pretriage_group(row: dict[str, str]) -> str:
    if row.get("final_split") == "test_o_val":
        return "o_val_local_first"
    if row.get("review_lane") == "mamoa_specialist_positive_review":
        return "positive_rescue"
    if row.get("review_lane") == "mamoa_false_positive_review" and parse_float(row.get("specialist_rank", "999999")) <= 35:
        return "mamoa_strong_model_confuser"
    if row.get("review_lane") == "mamoa_false_positive_review":
        return "mamoa_archaeological_hard_negative"
    if row.get("review_lane") == "morphology_rescue_review":
        return "morphology_rescue"
    if row.get("review_lane") == "low_positive_review":
        return "low_rank_positive"
    return "weak_negative_later"


def pretriage_decision(row: dict[str, str]) -> str:
    lane = row.get("review_lane", "")
    if row.get("final_split") == "test_o_val" and lane == "mamoa_false_positive_review":
        return "confirm_local_mamoa_non_castro_hard_negative"
    if row.get("final_split") == "test_o_val" and lane == "mamoa_specialist_positive_review":
        return "local_positive_boundary_review"
    if lane == "mamoa_false_positive_review":
        return "confirm_mamoa_specific_hard_negative"
    if lane == "mamoa_specialist_positive_review":
        return "positive_boundary_review"
    if lane == "morphology_rescue_review":
        return "morphology_boundary_review"
    if lane == "low_positive_review":
        return "visibility_or_centroid_review"
    return "defer_weak_negative_review"


def pretriage_confidence(row: dict[str, str]) -> str:
    lane = row.get("review_lane", "")
    specialist_rank = parse_float(row.get("specialist_rank", "999999"))
    if lane == "mamoa_false_positive_review" and specialist_rank <= 35:
        return "high_taxonomy_high_confusion"
    if lane == "mamoa_false_positive_review":
        return "high_taxonomy_medium_confusion"
    if lane == "mamoa_specialist_positive_review" and specialist_rank <= 3:
        return "high_model_signal_boundary_needed"
    if lane == "mamoa_specialist_positive_review":
        return "medium_model_signal_boundary_needed"
    if lane == "morphology_rescue_review":
        return "medium_morphology_signal_boundary_needed"
    return "low_pretriage_confidence"


def training_use_after_review(row: dict[str, str]) -> str:
    taxonomy = suggested_taxonomy(row)
    if taxonomy == "castro":
        return "positive_candidate_after_boundary_review"
    if taxonomy in {"mamoa", "petroglifo", "fortificacion_historica", "outro_arqueologico"}:
        return "archaeological_hard_negative_not_generic_absence"
    if taxonomy in {"cantera_mina", "ruido_moderno"}:
        return "generic_hard_negative_if_confirmed"
    return "exclude_until_reviewed"


def do_not_use_as(row: dict[str, str]) -> str:
    taxonomy = suggested_taxonomy(row)
    if taxonomy in {"mamoa", "petroglifo", "fortificacion_historica", "outro_arqueologico"}:
        return "generic_absence"
    if taxonomy == "castro":
        return "new_discovery_claim_without_review"
    return "training_label_without_review"


def visual_reading(row: dict[str, str]) -> str:
    lane = row.get("review_lane", "")
    morphology = row.get("morphology_proxy", "")
    if lane == "mamoa_false_positive_review":
        return "Contact sheets show castro-like circular/anular relief distractors; confirm taxonomy and keep as specific archaeological hard negatives."
    if lane == "mamoa_specialist_positive_review" and "coastal_promontory" in morphology:
        return "Contact sheets show coastal/promontory morphology; inspect boundary instead of penalizing non-round shape."
    if lane == "mamoa_specialist_positive_review":
        return "Specialist score is strong against mamoa distractors; inspect visible boundary and source context before accepting."
    if lane == "morphology_rescue_review":
        return "Morphology channel raises the point; inspect whether slope/LRM expresses a real enclosure or only terrain edge."
    if lane == "low_positive_review":
        return "Known positive remains low in fusion; inspect centering, visibility, vegetation and morphology proxy."
    return "Weak negative review only after holdout lanes; do not treat as proven absence."


def load_visual_sheet_by_sample(path: Path) -> dict[tuple[str, str], str]:
    if not path.exists():
        return {}
    out = {}
    for row in read_tsv(path):
        out[(row.get("queue", ""), row.get("sample_id", ""))] = row.get("visual_sheet", "")
    return out


def enrich_tasks(rows: list[dict[str, str]], visual_sheet_by_sample: dict[tuple[str, str], str]) -> list[dict[str, str]]:
    out = []
    duplicate_count = Counter(row.get("sample_id", "") for row in rows)
    duplicate_queues: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        duplicate_queues[row.get("sample_id", "")].add(row.get("queue", ""))
    sorted_rows = sorted(
        rows,
        key=lambda row: (
            {"P0": 0, "P1": 1, "P2": 2}.get(review_priority(row), 9),
            row.get("review_lane", ""),
            row.get("queue", ""),
            int(row.get("priority_order") or 999999),
        ),
    )
    for idx, row in enumerate(sorted_rows, start=1):
        task = {field: "" for field in TASK_FIELDS}
        task.update(row)
        task["review_id"] = f"err-review-{idx:04d}"
        task["sample_review_key"] = row.get("sample_id", "")
        task["duplicate_count"] = str(duplicate_count[row.get("sample_id", "")])
        task["duplicate_queues"] = ";".join(sorted(duplicate_queues[row.get("sample_id", "")]))
        task["review_priority"] = review_priority(row)
        task["suggested_taxonomy"] = suggested_taxonomy(row)
        task["suggested_decision"] = suggested_decision(row)
        task["boundary_action"] = boundary_action(row)
        task["review_status"] = "pending"
        task["final_taxonomy"] = ""
        task["final_decision"] = ""
        task["pretriage_order"] = ""
        task["pretriage_group"] = pretriage_group(row)
        task["pretriage_decision"] = pretriage_decision(row)
        task["pretriage_confidence"] = pretriage_confidence(row)
        task["training_use_after_review"] = training_use_after_review(row)
        task["do_not_use_as"] = do_not_use_as(row)
        task["visual_reading"] = visual_reading(row)
        task["visual_sheet"] = visual_sheet_by_sample.get((row.get("queue", ""), row.get("sample_id", "")), "")
        task["review_notes"] = ""
        out.append(task)
    return out


def pretriage_sort_key(row: dict[str, str]) -> tuple[int, int, int]:
    group_order = {
        "o_val_local_first": 0,
        "positive_rescue": 1,
        "mamoa_strong_model_confuser": 2,
        "mamoa_archaeological_hard_negative": 3,
        "morphology_rescue": 4,
        "low_rank_positive": 5,
        "weak_negative_later": 6,
    }
    return (
        group_order.get(row.get("pretriage_group", ""), 99),
        int(row.get("specialist_rank") or 999999),
        int(row.get("fusion_rank") or 999999),
    )


def apply_pretriage_order(tasks: list[dict[str, str]]) -> None:
    p0_unique = sorted(
        unique_by_sample([row for row in tasks if row["review_priority"] == "P0"]),
        key=pretriage_sort_key,
    )
    order_by_sample = {row["sample_id"]: str(idx) for idx, row in enumerate(p0_unique, start=1)}
    for row in tasks:
        if row["sample_id"] in order_by_sample and row["review_priority"] == "P0":
            row["pretriage_order"] = order_by_sample[row["sample_id"]]


def unique_by_sample(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    out = []
    seen = set()
    for row in rows:
        sample_id = row.get("sample_id", "")
        if sample_id in seen:
            continue
        seen.add(sample_id)
        out.append(row)
    return out


def feature(row: dict[str, str]) -> dict:
    lon = parse_float(row.get("longitude", ""))
    lat = parse_float(row.get("latitude", ""))
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {field: row.get(field, "") for field in TASK_FIELDS if field not in {"longitude", "latitude"}},
    }


def geojson_rows(rows: list[dict[str, str]]) -> dict:
    features = [
        feature(row)
        for row in rows
        if row.get("longitude") not in {"", "n/a"} and row.get("latitude") not in {"", "n/a"}
    ]
    return {"type": "FeatureCollection", "features": features}


def write_geojson(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(geojson_rows(rows), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def gpkg_point_blob(lon: float, lat: float) -> bytes:
    header = b"GP" + bytes([0, 1]) + struct.pack("<i", SRS_ID)
    return header + struct.pack("<BIdd", 1, 1, lon, lat)


def layer_bbox(rows: list[dict[str, str]]) -> tuple[float | None, float | None, float | None, float | None]:
    coords = [
        (parse_float(row.get("longitude", "")), parse_float(row.get("latitude", "")))
        for row in rows
        if row.get("longitude") not in {"", "n/a"} and row.get("latitude") not in {"", "n/a"}
    ]
    if not coords:
        return None, None, None, None
    lons = [lon for lon, _lat in coords]
    lats = [lat for _lon, lat in coords]
    return min(lons), min(lats), max(lons), max(lats)


def create_gpkg(path: Path, layers: dict[str, list[dict[str, str]]], tasks: list[dict[str, str]]) -> None:
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.executescript(
        """
        PRAGMA application_id=1196444487;
        PRAGMA user_version=10400;
        CREATE TABLE gpkg_spatial_ref_sys (
            srs_name TEXT NOT NULL,
            srs_id INTEGER NOT NULL PRIMARY KEY,
            organization TEXT NOT NULL,
            organization_coordsys_id INTEGER NOT NULL,
            definition TEXT NOT NULL,
            description TEXT
        );
        INSERT INTO gpkg_spatial_ref_sys VALUES
            ('Undefined Cartesian SRS', -1, 'NONE', -1, 'undefined', 'undefined Cartesian coordinate reference system'),
            ('Undefined geographic SRS', 0, 'NONE', 0, 'undefined', 'undefined geographic coordinate reference system'),
            ('WGS 84 geodetic', 4326, 'EPSG', 4326,
             'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]]',
             'longitude/latitude coordinates in decimal degrees on the WGS 84 spheroid');
        CREATE TABLE gpkg_contents (
            table_name TEXT NOT NULL PRIMARY KEY,
            data_type TEXT NOT NULL,
            identifier TEXT UNIQUE,
            description TEXT DEFAULT '',
            last_change DATETIME NOT NULL,
            min_x DOUBLE, min_y DOUBLE, max_x DOUBLE, max_y DOUBLE,
            srs_id INTEGER
        );
        CREATE TABLE gpkg_geometry_columns (
            table_name TEXT NOT NULL,
            column_name TEXT NOT NULL,
            geometry_type_name TEXT NOT NULL,
            srs_id INTEGER NOT NULL,
            z TINYINT NOT NULL,
            m TINYINT NOT NULL,
            PRIMARY KEY (table_name, column_name)
        );
        """
    )
    for table_name, rows in layers.items():
        columns_sql = ", ".join(f'"{field}" TEXT' for field in TASK_FIELDS if field not in {"longitude", "latitude"})
        cur.execute(
            f'CREATE TABLE "{table_name}" (fid INTEGER PRIMARY KEY AUTOINCREMENT, geom BLOB NOT NULL, {columns_sql})'
        )
        min_x, min_y, max_x, max_y = layer_bbox(rows)
        cur.execute(
            """
            INSERT INTO gpkg_contents
            (table_name, data_type, identifier, description, last_change, min_x, min_y, max_x, max_y, srs_id)
            VALUES (?, 'features', ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                table_name,
                table_name,
                "Weak-label error review lane layer",
                GENERATED_AT,
                min_x,
                min_y,
                max_x,
                max_y,
                SRS_ID,
            ),
        )
        cur.execute("INSERT INTO gpkg_geometry_columns VALUES (?, 'geom', 'POINT', ?, 0, 0)", (table_name, SRS_ID))
        field_list = ["geom", *[field for field in TASK_FIELDS if field not in {"longitude", "latitude"}]]
        placeholders = ", ".join("?" for _ in field_list)
        columns = ", ".join(f'"{field}"' for field in field_list)
        sql = f'INSERT INTO "{table_name}" ({columns}) VALUES ({placeholders})'
        for row in rows:
            lon = parse_float(row.get("longitude", ""))
            lat = parse_float(row.get("latitude", ""))
            values = [gpkg_point_blob(lon, lat)]
            values.extend(str(row.get(field, ""))[:3000] for field in field_list[1:])
            cur.execute(sql, values)

    cur.execute(
        """
        INSERT INTO gpkg_contents
        (table_name, data_type, identifier, description, last_change, min_x, min_y, max_x, max_y, srs_id)
        VALUES ('error_review_decisions', 'attributes', 'error_review_decisions',
                'Editable decision table template for weak-label error review', ?, NULL, NULL, NULL, NULL, NULL)
        """,
        (GENERATED_AT,),
    )
    cur.execute(
        """
        CREATE TABLE error_review_decisions (
            review_id TEXT PRIMARY KEY,
            review_status TEXT,
            final_taxonomy TEXT,
            final_decision TEXT,
            boundary_action TEXT,
            reviewed_by TEXT,
            reviewed_date TEXT,
            review_notes TEXT
        )
        """
    )
    for row in tasks:
        cur.execute(
            """
            INSERT INTO error_review_decisions
            VALUES (?, 'pending', '', '', ?, '', '', '')
            """,
            (row["review_id"], row["boundary_action"]),
        )
    conn.commit()
    conn.close()


def build_layers(tasks: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    layers: dict[str, list[dict[str, str]]] = {"all_error_review_points": tasks}
    layers["unique_error_review_points"] = unique_by_sample(tasks)
    for lane in LANE_LAYER_NAMES:
        layers[layer_name_for_lane(lane)] = [row for row in tasks if row["review_lane"] == lane]
    layers["o_val_focus"] = [row for row in tasks if row["final_split"] == "test_o_val"]
    layers["p0_first_pass"] = [row for row in tasks if row["review_priority"] == "P0"]
    layers["p0_unique_first_pass"] = unique_by_sample(layers["p0_first_pass"])
    layers["p0_pretriage"] = sorted(layers["p0_unique_first_pass"], key=pretriage_sort_key)
    return layers


def write_readme(path: Path, layers: dict[str, list[dict[str, str]]]) -> None:
    lines = [
        "# Weak-label error review workspace v1",
        "",
        f"Generated: {GENERATED_AT}",
        "",
        "## What This Is",
        "",
        "QGIS-ready package for reviewing the weak-label RGB+relief error queue by lane.",
        "It is a review workspace, not an archaeological discovery report.",
        "",
        "## Files",
        "",
        "- `weak_label_error_review_workspace_v1.gpkg`: all lanes as QGIS layers plus a decision template table.",
        "- `review_lane_tasks.tsv`: task table sorted by priority/lane.",
        "- `review_taxonomy.tsv`: minimal taxonomy for first-pass decisions.",
        "- `lanes/*.geojson`: one lightweight GeoJSON per lane.",
        "",
        "## Recommended Order",
        "",
        "1. Open `p0_pretriage` first.",
        "2. Filter or open `lane_mamoa_false_positive`.",
        "3. Then inspect `lane_mamoa_specialist_positive`.",
        "4. Then inspect `lane_morphology_rescue`.",
        "5. Leave validation weak negatives for a later, lower-confidence batch.",
        "",
        "## Fields To Use",
        "",
        "- `review_lane`: why the point is in the workspace.",
        "- `duplicate_count` / `duplicate_queues`: whether the same sample appears in multiple queues.",
        "- `pretriage_order`, `pretriage_group`, `pretriage_decision`: autonomous first-pass ordering and action.",
        "- `suggested_taxonomy`: first-pass category, not final truth.",
        "- `suggested_decision`: proposed action.",
        "- `boundary_action`: what to draw/confirm in QGIS.",
        "- `review_status`, `final_taxonomy`, `final_decision`, `review_notes`: editable decision fields.",
        "",
        "## Layer Counts",
        "",
    ]
    for layer, rows in layers.items():
        lines.append(f"- `{layer}`: {len(rows)}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_report(path: Path, out_dir: Path, layers: dict[str, list[dict[str, str]]], tasks: list[dict[str, str]]) -> None:
    lane_counts = Counter(row["review_lane"] for row in tasks)
    priority_counts = Counter(row["review_priority"] for row in tasks)
    taxonomy_counts = Counter(row["suggested_taxonomy"] for row in tasks)
    lines = [
        "# Weak-label error review workspace v1",
        "",
        f"Generated: {GENERATED_AT}",
        "",
        "## Files",
        "",
        f"- GPKG: `{rel_to_project(out_dir / 'weak_label_error_review_workspace_v1.gpkg')}`",
        f"- Tasks TSV: `{rel_to_project(out_dir / 'review_lane_tasks.tsv')}`",
        f"- Taxonomy TSV: `{rel_to_project(out_dir / 'review_taxonomy.tsv')}`",
        f"- Lane GeoJSON dir: `{rel_to_project(out_dir / 'lanes')}`",
        "",
        "## Counts",
        "",
        f"- total tasks: `{len(tasks)}`",
        "",
        "### By Priority",
        "",
    ]
    for key, value in sorted(priority_counts.items()):
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "### By Lane", ""])
    for key, value in lane_counts.most_common():
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "### By Suggested Taxonomy", ""])
    for key, value in taxonomy_counts.most_common():
        lines.append(f"- `{key}`: {value}")
    lines.extend(
        [
            "",
            "## O Val Focus",
            "",
            "| Review ID | Lane | Priority | Fusion rank | Max rank | Specialist rank | Suggested taxonomy | Name |",
            "|---|---|---|---:|---:|---:|---|---|",
        ]
    )
    for row in [task for task in tasks if task["final_split"] == "test_o_val"]:
        lines.append(
            f"| `{row['review_id']}` | `{row['review_lane']}` | `{row['review_priority']}` | {row['fusion_rank']} | {row['max_safety_rank']} | {row['specialist_rank']} | `{row['suggested_taxonomy']}` | `{row['name']}` |"
        )
    lines.extend(
        [
            "",
            "## P0 Pretriage",
            "",
            "| Order | Group | Decision | Confidence | Lane | Specialist rank | Name |",
            "|---:|---|---|---|---|---:|---|",
        ]
    )
    for row in layers.get("p0_pretriage", []):
        lines.append(
            f"| {row['pretriage_order']} | `{row['pretriage_group']}` | `{row['pretriage_decision']}` | `{row['pretriage_confidence']}` | `{row['review_lane']}` | {row['specialist_rank']} | `{row['name']}` |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- This package turns the model-error queue into QGIS layers that can be opened independently.",
            "- `mamoa_false_positive_review` should not be treated as generic background: these are archaeological hard negatives.",
            "- `mamoa_specialist_positive_review` is the key rescue lane for positives that the global fusion suppresses.",
            "- `p0_pretriage` is an autonomous first-pass triage, not a final archaeological decision.",
            "- No row in this package is a new site claim; every decision remains a review decision.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    parser.add_argument("--visual-batch", type=Path, default=DEFAULT_VISUAL_BATCH)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def resolve_args(args: argparse.Namespace) -> argparse.Namespace:
    args.queue = args.queue if args.queue.is_absolute() else PROJECT_ROOT / args.queue
    args.visual_batch = args.visual_batch if args.visual_batch.is_absolute() else PROJECT_ROOT / args.visual_batch
    args.out_dir = args.out_dir if args.out_dir.is_absolute() else PROJECT_ROOT / args.out_dir
    args.report = args.report if args.report.is_absolute() else PROJECT_ROOT / args.report
    return args


def main() -> None:
    args = resolve_args(parse_args())
    visual_sheet_by_sample = load_visual_sheet_by_sample(args.visual_batch)
    tasks = enrich_tasks(read_tsv(args.queue), visual_sheet_by_sample)
    apply_pretriage_order(tasks)
    layers = build_layers(tasks)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    lanes_dir = args.out_dir / "lanes"
    lanes_dir.mkdir(parents=True, exist_ok=True)

    write_tsv(args.out_dir / "review_lane_tasks.tsv", tasks, TASK_FIELDS)
    write_tsv(args.out_dir / "review_taxonomy.tsv", TAXONOMY_ROWS, list(TAXONOMY_ROWS[0].keys()))
    for layer, rows in layers.items():
        write_geojson(lanes_dir / f"{layer}.geojson", rows)
    create_gpkg(args.out_dir / "weak_label_error_review_workspace_v1.gpkg", layers, tasks)
    write_readme(args.out_dir / "README_error_review_workspace.md", layers)
    write_report(args.report, args.out_dir, layers, tasks)

    print(f"tasks={len(tasks)}")
    for layer, rows in layers.items():
        print(f"{layer}={len(rows)}")
    print(f"gpkg={rel_to_project(args.out_dir / 'weak_label_error_review_workspace_v1.gpkg')}")
    print(f"report={rel_to_project(args.report)}")


if __name__ == "__main__":
    main()
