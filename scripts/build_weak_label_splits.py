#!/usr/bin/env python3
"""Build broad weak-label train/val/test splits for castro detection.

This turns the full morphology bank into a reproducible modelling manifest.
It deliberately keeps the labels as weak/provisional: official catalogue points
are useful supervision seeds, but they are not final archaeological boundaries.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import statistics
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BANK_DIR = PROJECT_ROOT / "data/morphology-bank"
OUT_DIR = PROJECT_ROOT / "data/weak-label-splits-v1"
REPORTS_DIR = PROJECT_ROOT / "reports"

POSITIVE_IN = BANK_DIR / "positive_castro_sources.tsv"
NEGATIVE_IN = BANK_DIR / "negative_distractor_sources.tsv"
VISUAL_SCORES_IN = PROJECT_ROOT / "data/morphology-autoreview-v1/visual_signal_scores.tsv"

GENERATED_AT = "2026-08-01T00:00:00Z"
SPLIT_SALT = "castros-ia-galicia-weak-label-splits-v1"
TILE_SIDE_M = 512.0

TRASANCOS_MUNICIPALITIES = {
    "Fene",
    "Ferrol",
    "Narón",
    "Neda",
    "San Sadurniño",
    "Valdoviño",
}

POSITIVE_KEEP_TYPOLOGIES = {
    "castro",
    "povoado fortificado",
    "asentamento fortificado",
    "asentamento fortificado defensivo",
    "asentamento fortificado/defensivo",
    "povoado",
}

POSITIVE_KEEP_GENERIC_TYPES = {"def"}

NON_CASTRO_TYPOLOGY_TERMS = {
    "achado",
    "ara",
    "arte rupestre",
    "calzada",
    "capela",
    "casa",
    "cista",
    "cruceiro",
    "dolmen",
    "edificio",
    "estela",
    "explotacion",
    "explotación",
    "fonte",
    "gravado",
    "horreo",
    "hórreo",
    "igrexa",
    "iglesia",
    "inscripcion",
    "inscrição",
    "mamoa",
    "mámoa",
    "menhir",
    "miliario",
    "necropole",
    "necrópole",
    "neolitico",
    "neolítico",
    "petroglifo",
    "petróglifo",
    "residencial",
    "romano",
    "sartego",
    "tumulo",
    "túmulo",
    "villa",
}

FALSE_NAME_STARTS = {
    "casa",
    "casa reitoral",
    "edificio",
    "farois",
    "fonte",
    "horreo",
    "hórreo",
    "igrexa",
    "iglesia",
    "lavadoiro",
    "mamoa",
    "mámoa",
    "petroglifo",
    "petróglifo",
    "pontella",
    "porta",
    "rueiro",
    "rua",
    "rúa",
}

FALSE_GENERIC_TYPES = {"aru", "cru", "esc", "hor"}

FIELDS = [
    "sample_id",
    "bank_id",
    "label_class",
    "label_role",
    "weak_label_status",
    "weak_label_reason",
    "final_split",
    "split_family",
    "spatial_block_id",
    "country",
    "region",
    "province_or_district",
    "municipality",
    "parish",
    "place",
    "name",
    "source",
    "source_quality",
    "source_record_id",
    "source_code",
    "typology",
    "generic_type",
    "periods",
    "longitude",
    "latitude",
    "coord_precision",
    "positive_confidence",
    "morphology_proxy",
    "terrain_context_proxy",
    "negative_type",
    "negative_confidence",
    "review_priority",
    "source_training_use",
    "proposed_radius_m",
    "bbox_epsg4326",
    "visual_ring_signal_score",
    "visual_ring_signal_tier",
    "metric_eval_use",
    "training_use",
    "recommended_sampling_weight",
    "generated_at",
]

SUMMARY_FIELDS = ["dataset", "field", "value", "count"]

TILE_FIELDS = [
    "tile_id",
    "sample_id",
    "bank_id",
    "label_class",
    "label_role",
    "final_split",
    "country",
    "name",
    "longitude",
    "latitude",
    "bbox_epsg4326",
    "tile_side_m",
    "wms_source",
    "wms_base",
    "wms_layer",
    "target_png_path",
    "training_use",
]

ES_WMS_BASE = "https://www.ign.es/wms-inspire/pnoa-ma"
ES_WMS_LAYER = "OI.OrthoimageCoverage"
PT_WMS_BASE = "https://cartografia.dgterritorio.gov.pt/wms/ortos2021"
PT_WMS_LAYER = "Ortos2021-RGB"


def clean(value: object) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\n", " ").split()).strip()


def norm(value: object) -> str:
    value = clean(value).lower()
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def slugify(value: object) -> str:
    value = norm(value)
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value or "sen-nome"


def parse_float(value: object) -> float | None:
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, dialect="excel-tab"))


def write_tsv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, dialect="excel-tab", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_geojson(path: Path, rows: list[dict[str, str]]) -> None:
    features = []
    for row in rows:
        lon = parse_float(row.get("longitude"))
        lat = parse_float(row.get("latitude"))
        if lon is None or lat is None:
            continue
        props = {key: value for key, value in row.items() if key not in {"longitude", "latitude"}}
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": props,
            }
        )
    payload = {
        "type": "FeatureCollection",
        "name": "weak_label_splits_v1_points",
        "crs": {"type": "name", "properties": {"name": "EPSG:4326"}},
        "features": features,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def rel_to_project(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def block_hash_ratio(block_id: str) -> float:
    digest = hashlib.sha1(f"{SPLIT_SALT}|{block_id}".encode("utf-8")).hexdigest()
    return int(digest[:10], 16) / float(16**10 - 1)


def deterministic_regular_split(block_id: str) -> str:
    ratio = block_hash_ratio(block_id)
    if ratio < 0.70:
        return "train"
    if ratio < 0.85:
        return "val"
    return "test"


def bbox_around(lon: float, lat: float, side_m: float = TILE_SIDE_M) -> str:
    half = side_m / 2.0
    meters_per_degree_lat = 111_320.0
    meters_per_degree_lon = meters_per_degree_lat * max(math.cos(math.radians(lat)), 0.1)
    dlat = half / meters_per_degree_lat
    dlon = half / meters_per_degree_lon
    return f"{lon - dlon:.8f},{lat - dlat:.8f},{lon + dlon:.8f},{lat + dlat:.8f}"


def positive_radius_m(row: dict[str, str]) -> float:
    proxy = row.get("morphology_proxy", "")
    if proxy == "large_castrexo_civitas_hint":
        return 180.0
    if proxy == "coastal_promontory_hint":
        return 150.0
    if proxy == "earthwork_or_wall_hint":
        return 130.0
    if proxy == "croa_top_ring_hint":
        return 110.0
    if proxy == "castrel_toponym_hint":
        return 100.0
    if proxy == "hilltop_hint":
        return 120.0
    if proxy == "valley_or_river_edge_hint":
        return 120.0
    return 110.0


def negative_radius_m(row: dict[str, str]) -> float:
    negative_type = row.get("negative_type", "")
    if "megalithic_mound" in negative_type:
        return 45.0
    if "historic_fortification" in negative_type:
        return 100.0
    if "rock_art_surface" in negative_type:
        return 35.0
    if "roman_built_context" in negative_type:
        return 80.0
    if "mining_or_quarry" in negative_type:
        return 120.0
    if "necropolis_or_burial" in negative_type:
        return 50.0
    return 60.0


def is_o_val(row: dict[str, str]) -> bool:
    return row.get("municipality") == "Narón" and "o val" in norm(row.get("parish", ""))


def is_trasancos(row: dict[str, str]) -> bool:
    return row.get("province_or_district") == "A Coruña" and row.get("municipality") in TRASANCOS_MUNICIPALITIES


def spatial_block_id(row: dict[str, str]) -> str:
    return "|".join(
        [
            row.get("country", ""),
            row.get("province_or_district", ""),
            row.get("municipality", ""),
        ]
    )


def classify_positive(row: dict[str, str]) -> tuple[str, str]:
    name_norm = norm(row.get("name", ""))
    typology_norm = norm(row.get("typology", ""))
    generic_norm = norm(row.get("generic_type", ""))
    confidence = row.get("positive_confidence", "")
    source_code = row.get("source_code", "")

    typology_is_keep = typology_norm in POSITIVE_KEEP_TYPOLOGIES
    generic_is_keep = generic_norm in POSITIVE_KEEP_GENERIC_TYPES
    typology_is_non_castro = any(term in typology_norm for term in NON_CASTRO_TYPOLOGY_TERMS)
    generic_is_false = generic_norm in FALSE_GENERIC_TYPES
    name_starts_false = any(name_norm.startswith(term) for term in FALSE_NAME_STARTS)
    name_is_mound_or_rock = bool(re.search(r"\b(mamoa|mamoas|tumulo|tumulos|dolmen|petroglifo|petroglifos)\b", name_norm))
    modern_street_or_building = bool(re.search(r"\b(rua|edificio|casa|rosalia de castro|castro chane)\b", name_norm))

    if confidence == "low_toponymic_review":
        return "exclude_low_toponymic_review", "low confidence toponymic hint"
    if typology_is_keep or generic_is_keep or confidence == "high_official_typology":
        return "weak_positive_candidate", "official fortified/castro typology seed"
    if typology_is_non_castro or generic_is_false or name_starts_false or name_is_mound_or_rock or modern_street_or_building:
        return "exclude_probable_name_false_positive", "name/type looks like modern or non-castro heritage item"
    if source_code.startswith("GA") and "castro" in name_norm:
        return "weak_positive_candidate", "official GA code and castro name"
    if re.search(r"\b(castro|castros|croa|cividade|citania|citânia|castrel|castrill)\b", name_norm):
        return "weak_positive_candidate", "official catalogue name contains castro/croa/cividade term"
    return "exclude_ambiguous_positive_seed", "positive seed too ambiguous for weak-label training"


def final_split_for(row: dict[str, str], weak_label_status: str) -> tuple[str, str, str]:
    lon = parse_float(row.get("longitude"))
    lat = parse_float(row.get("latitude"))
    if lon is None or lat is None:
        return "excluded_no_coordinates", "excluded", "exclude_until_coordinates"
    if not weak_label_status.startswith("weak_"):
        return "excluded_review", "excluded", "exclude_until_independent_label_review"
    if is_o_val(row):
        return "test_o_val", "holdout_o_val", "holdout_eval_only"
    if is_trasancos(row):
        return "test_trasancos", "holdout_trasancos", "holdout_eval_only"
    block_id = spatial_block_id(row)
    split = deterministic_regular_split(block_id)
    return split, "regular_spatial_block", "weak_label_candidate_for_model_v1"


def visual_scores_by_bank_id() -> dict[str, dict[str, str]]:
    if not VISUAL_SCORES_IN.exists():
        return {}
    return {row["bank_id"]: row for row in read_tsv(VISUAL_SCORES_IN)}


def make_positive_row(raw: dict[str, str], visual_scores: dict[str, dict[str, str]]) -> dict[str, str]:
    status, reason = classify_positive(raw)
    split, family, training_use = final_split_for(raw, status)
    lon = parse_float(raw.get("longitude"))
    lat = parse_float(raw.get("latitude"))
    radius_m = positive_radius_m(raw)
    visual = visual_scores.get(raw.get("bank_id", ""), {})
    weight = "1.00" if training_use == "weak_label_candidate_for_model_v1" else "0.00"
    if status.startswith("exclude_"):
        weight = "0.00"
    return {
        "sample_id": f"wl-pos-{raw['bank_id']}",
        "bank_id": raw.get("bank_id", ""),
        "label_class": "1",
        "label_role": "positive",
        "weak_label_status": status,
        "weak_label_reason": reason,
        "final_split": split,
        "split_family": family,
        "spatial_block_id": spatial_block_id(raw),
        "country": raw.get("country", ""),
        "region": raw.get("region", ""),
        "province_or_district": raw.get("province_or_district", ""),
        "municipality": raw.get("municipality", ""),
        "parish": raw.get("parish", ""),
        "place": raw.get("place", ""),
        "name": raw.get("name", ""),
        "source": raw.get("source", ""),
        "source_quality": raw.get("source_quality", ""),
        "source_record_id": raw.get("source_record_id", ""),
        "source_code": raw.get("source_code", ""),
        "typology": raw.get("typology", ""),
        "generic_type": raw.get("generic_type", ""),
        "periods": raw.get("periods", ""),
        "longitude": raw.get("longitude", ""),
        "latitude": raw.get("latitude", ""),
        "coord_precision": raw.get("coord_precision", ""),
        "positive_confidence": raw.get("positive_confidence", ""),
        "morphology_proxy": raw.get("morphology_proxy", ""),
        "terrain_context_proxy": raw.get("terrain_context_proxy", ""),
        "negative_type": "",
        "negative_confidence": "",
        "review_priority": raw.get("review_priority", ""),
        "source_training_use": raw.get("training_use", ""),
        "proposed_radius_m": f"{radius_m:.1f}",
        "bbox_epsg4326": bbox_around(lon, lat) if lon is not None and lat is not None else "",
        "visual_ring_signal_score": visual.get("ring_signal_score", ""),
        "visual_ring_signal_tier": visual.get("ring_signal_tier", ""),
        "metric_eval_use": visual.get("metric_eval_use", ""),
        "training_use": training_use,
        "recommended_sampling_weight": weight,
        "generated_at": GENERATED_AT,
    }


def make_negative_row(raw: dict[str, str], visual_scores: dict[str, dict[str, str]]) -> dict[str, str]:
    status = "weak_hard_negative_candidate"
    split, family, training_use = final_split_for(raw, status)
    lon = parse_float(raw.get("longitude"))
    lat = parse_float(raw.get("latitude"))
    radius_m = negative_radius_m(raw)
    visual = visual_scores.get(raw.get("bank_id", ""), {})
    weight = "0.60" if training_use == "weak_label_candidate_for_model_v1" else "0.00"
    return {
        "sample_id": f"wl-neg-{raw['bank_id']}",
        "bank_id": raw.get("bank_id", ""),
        "label_class": "0",
        "label_role": "hard_negative",
        "weak_label_status": status,
        "weak_label_reason": "official non-castro heritage distractor",
        "final_split": split,
        "split_family": family,
        "spatial_block_id": spatial_block_id(raw),
        "country": raw.get("country", ""),
        "region": raw.get("region", ""),
        "province_or_district": raw.get("province_or_district", ""),
        "municipality": raw.get("municipality", ""),
        "parish": raw.get("parish", ""),
        "place": raw.get("place", ""),
        "name": raw.get("name", ""),
        "source": raw.get("source", ""),
        "source_quality": raw.get("source_quality", ""),
        "source_record_id": raw.get("source_record_id", ""),
        "source_code": raw.get("source_code", ""),
        "typology": raw.get("typology", ""),
        "generic_type": raw.get("generic_type", ""),
        "periods": raw.get("periods", ""),
        "longitude": raw.get("longitude", ""),
        "latitude": raw.get("latitude", ""),
        "coord_precision": raw.get("coord_precision", ""),
        "positive_confidence": "",
        "morphology_proxy": "",
        "terrain_context_proxy": "",
        "negative_type": raw.get("negative_type", ""),
        "negative_confidence": raw.get("negative_confidence", ""),
        "review_priority": raw.get("review_priority", ""),
        "source_training_use": raw.get("training_use", ""),
        "proposed_radius_m": f"{radius_m:.1f}",
        "bbox_epsg4326": bbox_around(lon, lat) if lon is not None and lat is not None else "",
        "visual_ring_signal_score": visual.get("ring_signal_score", ""),
        "visual_ring_signal_tier": visual.get("ring_signal_tier", ""),
        "metric_eval_use": visual.get("metric_eval_use", ""),
        "training_use": training_use,
        "recommended_sampling_weight": weight,
        "generated_at": GENERATED_AT,
    }


def add_counter(summary: list[dict[str, str]], rows: list[dict[str, str]], dataset: str, field: str) -> None:
    counter = Counter(row.get(field, "") for row in rows)
    for value, count in sorted(counter.items(), key=lambda item: (item[0], item[1])):
        summary.append({"dataset": dataset, "field": field, "value": value or "-", "count": str(count)})


def build_summary(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    summary: list[dict[str, str]] = []
    subsets = {
        "master": rows,
        "model_candidates": [row for row in rows if row["training_use"] == "weak_label_candidate_for_model_v1"],
        "holdouts": [row for row in rows if row["training_use"] == "holdout_eval_only"],
        "excluded": [row for row in rows if row["training_use"].startswith("exclude")],
    }
    for dataset, subset in subsets.items():
        for field in (
            "label_role",
            "label_class",
            "weak_label_status",
            "final_split",
            "country",
            "province_or_district",
            "morphology_proxy",
            "negative_type",
            "review_priority",
        ):
            add_counter(summary, subset, dataset, field)
    return summary


def wms_for_country(country: str) -> tuple[str, str, str]:
    if country == "PT":
        return "dgt_ortos2021_rgb", PT_WMS_BASE, PT_WMS_LAYER
    return "ign_pnoa_rgb", ES_WMS_BASE, ES_WMS_LAYER


def build_tile_manifest(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    tile_rows = []
    eligible = [
        row
        for row in rows
        if row["training_use"] in {"weak_label_candidate_for_model_v1", "holdout_eval_only"}
        and row.get("bbox_epsg4326")
    ]
    for idx, row in enumerate(eligible, start=1):
        wms_source, wms_base, wms_layer = wms_for_country(row["country"])
        split = row["final_split"]
        label = "positive" if row["label_class"] == "1" else "negative"
        tile_id = f"wl-tile-v1-{idx:05d}"
        tile_rows.append(
            {
                "tile_id": tile_id,
                "sample_id": row["sample_id"],
                "bank_id": row["bank_id"],
                "label_class": row["label_class"],
                "label_role": row["label_role"],
                "final_split": split,
                "country": row["country"],
                "name": row["name"],
                "longitude": row["longitude"],
                "latitude": row["latitude"],
                "bbox_epsg4326": row["bbox_epsg4326"],
                "tile_side_m": f"{TILE_SIDE_M:.0f}",
                "wms_source": wms_source,
                "wms_base": wms_base,
                "wms_layer": wms_layer,
                "target_png_path": f"data/external/weak-label-chips-v1/{split}/{label}/{tile_id}-{slugify(row['bank_id'])}.png",
                "training_use": row["training_use"],
            }
        )
    return tile_rows


def leakage_warnings(rows: list[dict[str, str]]) -> list[str]:
    warnings = []
    block_splits: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        if row["training_use"] != "weak_label_candidate_for_model_v1":
            continue
        block_splits[row["spatial_block_id"]].add(row["final_split"])
    leaking_blocks = {block: splits for block, splits in block_splits.items() if len(splits) > 1}
    if leaking_blocks:
        warnings.append(f"regular spatial blocks in multiple splits: {len(leaking_blocks)}")
    for municipality in sorted(TRASANCOS_MUNICIPALITIES):
        leaked = [
            row for row in rows
            if row["municipality"] == municipality and row["training_use"] == "weak_label_candidate_for_model_v1"
        ]
        if leaked:
            warnings.append(f"Trasancos municipality leaked into model training: {municipality} ({len(leaked)})")
    return warnings


def mean_score(rows: list[dict[str, str]]) -> str:
    scores = [parse_float(row.get("visual_ring_signal_score")) for row in rows if row.get("visual_ring_signal_score")]
    scores = [score for score in scores if score is not None]
    if not scores:
        return "n/a"
    return f"{statistics.mean(scores):.2f}"


def write_report(path: Path, rows: list[dict[str, str]], tile_rows: list[dict[str, str]], warnings: list[str]) -> None:
    model_rows = [row for row in rows if row["training_use"] == "weak_label_candidate_for_model_v1"]
    holdout_rows = [row for row in rows if row["training_use"] == "holdout_eval_only"]
    excluded_rows = [row for row in rows if row["training_use"].startswith("exclude")]
    positive_rows = [row for row in rows if row["label_class"] == "1"]
    positive_model = [row for row in model_rows if row["label_class"] == "1"]
    negative_model = [row for row in model_rows if row["label_class"] == "0"]
    split_counts = Counter((row["final_split"], row["label_role"]) for row in rows)
    status_counts = Counter(row["weak_label_status"] for row in rows)
    proxy_counts = Counter(row["morphology_proxy"] for row in positive_model if row.get("morphology_proxy"))
    negative_counts = Counter(row["negative_type"] for row in negative_model if row.get("negative_type"))

    lines = [
        "# Weak-label splits v1",
        "",
        f"Generated: {GENERATED_AT}",
        "",
        "## What This Is",
        "",
        "Broad provisional train/validation/test split for castro detection using the full morphology bank.",
        "This is a weak-label dataset: catalogue points and catalogue non-castro distractors are supervision seeds, not final archaeological boundaries.",
        "",
        "## Files",
        "",
        "- `data/weak-label-splits-v1/weak_label_master.tsv`",
        "- `data/weak-label-splits-v1/weak_label_train.tsv`",
        "- `data/weak-label-splits-v1/weak_label_val.tsv`",
        "- `data/weak-label-splits-v1/weak_label_test.tsv`",
        "- `data/weak-label-splits-v1/weak_label_test_trasancos.tsv`",
        "- `data/weak-label-splits-v1/weak_label_test_o_val.tsv`",
        "- `data/weak-label-splits-v1/weak_label_excluded_review.tsv`",
        "- `data/weak-label-splits-v1/weak_label_tile_manifest_512m.tsv`",
        "- `data/weak-label-splits-v1/weak_label_points.geojson`",
        "- `data/weak-label-splits-v1/weak_label_splits_v1.gpkg`",
        "",
        "## Counts",
        "",
        f"- Master rows: {len(rows)}",
        f"- Original positive seeds retained in master: {len(positive_rows)}",
        f"- Model-candidate rows: {len(model_rows)}",
        f"- Model positive candidates: {len(positive_model)}",
        f"- Model hard-negative candidates: {len(negative_model)}",
        f"- Holdout rows: {len(holdout_rows)}",
        f"- Excluded/review-only rows: {len(excluded_rows)}",
        f"- Tile manifest rows: {len(tile_rows)}",
        f"- Mean visual score where known: {mean_score(rows)}",
        "",
        "## Split Counts",
        "",
    ]
    for (split, role), count in sorted(split_counts.items()):
        lines.append(f"- {split}/{role}: {count}")
    lines.extend(["", "## Weak-label Status", ""])
    for status, count in sorted(status_counts.items()):
        lines.append(f"- {status}: {count}")
    lines.extend(["", "## Model Positive Morphology", ""])
    for proxy, count in sorted(proxy_counts.items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"- {proxy}: {count}")
    lines.extend(["", "## Model Hard-negative Types", ""])
    for negative_type, count in sorted(negative_counts.items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"- {negative_type}: {count}")
    lines.extend(
        [
            "",
            "## Spatial Policy",
            "",
            "- Regular rows are split by administrative spatial block: `country|province_or_district|municipality`.",
            "- O Val rows are forced to `test_o_val`.",
            "- Fene, Ferrol, Narón, Neda, San Sadurniño and Valdoviño are forced to `test_trasancos`, except O Val, which has its own holdout.",
            "- Rows with probable modern/toponymic false-positive risk stay in `excluded_review`.",
            "",
            "## Leakage Check",
            "",
        ]
    )
    if warnings:
        lines.extend(f"- WARNING: {warning}" for warning in warnings)
    else:
        lines.append("- OK: no regular spatial block appears in multiple train/val/test splits.")
        lines.append("- OK: no Trasancos municipality is used in model training.")
    lines.extend(
        [
            "",
            "## Training Use",
            "",
            "`weak_label_candidate_for_model_v1` can feed a first weak detector.",
            "`holdout_eval_only` is for evaluation and later inference over Trasancos/O Val.",
            "`exclude_until_independent_label_review` rows should not train the model.",
            "",
            "## Next Step",
            "",
            "Use `weak_label_tile_manifest_512m.tsv` to export chips outside Git under `data/external/weak-label-chips-v1/`, then train a baseline classifier/segmenter with class weighting and spatial holdout evaluation.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_split_files(rows: list[dict[str, str]]) -> None:
    write_tsv(OUT_DIR / "weak_label_master.tsv", rows, FIELDS)
    for split in ("train", "val", "test", "test_trasancos", "test_o_val"):
        split_rows = [row for row in rows if row["final_split"] == split]
        write_tsv(OUT_DIR / f"weak_label_{split}.tsv", split_rows, FIELDS)
    excluded_rows = [row for row in rows if row["final_split"].startswith("excluded")]
    write_tsv(OUT_DIR / "weak_label_excluded_review.tsv", excluded_rows, FIELDS)


def main() -> None:
    visual_scores = visual_scores_by_bank_id()
    positives = read_tsv(POSITIVE_IN)
    negatives = read_tsv(NEGATIVE_IN)
    rows = [make_positive_row(row, visual_scores) for row in positives]
    rows.extend(make_negative_row(row, visual_scores) for row in negatives)
    rows.sort(key=lambda row: (row["final_split"], row["label_class"], row["country"], row["province_or_district"], row["municipality"], row["bank_id"]))
    tile_rows = build_tile_manifest(rows)
    warnings = leakage_warnings(rows)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    write_split_files(rows)
    write_tsv(OUT_DIR / "weak_label_split_summary.tsv", build_summary(rows), SUMMARY_FIELDS)
    write_tsv(OUT_DIR / "weak_label_tile_manifest_512m.tsv", tile_rows, TILE_FIELDS)
    write_geojson(OUT_DIR / "weak_label_points.geojson", rows)
    write_report(REPORTS_DIR / "weak_label_splits_v1.md", rows, tile_rows, warnings)

    print(f"master_rows={len(rows)}")
    print(f"model_candidate_rows={sum(row['training_use'] == 'weak_label_candidate_for_model_v1' for row in rows)}")
    print(f"positive_model_candidates={sum(row['training_use'] == 'weak_label_candidate_for_model_v1' and row['label_class'] == '1' for row in rows)}")
    print(f"hard_negative_model_candidates={sum(row['training_use'] == 'weak_label_candidate_for_model_v1' and row['label_class'] == '0' for row in rows)}")
    print(f"holdout_rows={sum(row['training_use'] == 'holdout_eval_only' for row in rows)}")
    print(f"tile_manifest_rows={len(tile_rows)}")
    print(f"leakage_warnings={len(warnings)}")
    print(f"wrote={rel_to_project(REPORTS_DIR / 'weak_label_splits_v1.md')}")


if __name__ == "__main__":
    main()
