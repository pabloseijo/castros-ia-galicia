#!/usr/bin/env python3
"""Build a broad morphology control bank for castro detection.

The output is a review bank, not a training dataset. Official catalogue points
are useful seeds, but morphology and final labels still need human/QGIS review.
"""

from __future__ import annotations

import csv
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = PROJECT_ROOT / "data/morphology-bank"
REPORTS_DIR = PROJECT_ROOT / "reports"

GENERATED_AT = "2026-08-01T00:00:00Z"
USER_AGENT = "Mozilla/5.0 castros-ia-galicia/1.0"

PBA_DATASET_URL = "https://datos.gob.es/es/catalogo/a12002994-plan-basico-autonomico-de-galicia-afecciones-del-patrimonio-cultural"
PBA_LAYER_URL = "https://ideg.xunta.gal/servizos/rest/services/PBA/Afeccions_PatrimonioCultural/MapServer/11/query"
PBA_LAYER_METADATA_URL = "https://ideg.xunta.gal/servizos/rest/services/PBA/Afeccions_PatrimonioCultural/MapServer/11"

DGPC_AGOL_ITEM_URL = "https://www.arcgis.com/home/item.html?id=051ecb3b6f1048cebdab360de305fae4"
DGPC_SERVICE_URL = "https://geo.patrimoniocultural.gov.pt/arcgis/rest/services/PatrimonioArqueologico/Sitios_Arqueologicos/MapServer"
DGPC_LAYER_URL = f"{DGPC_SERVICE_URL}/0/query"
DGPC_LAYER_METADATA_URL = "https://geo.patrimoniocultural.gov.pt/arcgis/rest/services/PatrimonioArqueologico/Sitios_Arqueologicos/MapServer/0"

NORTHERN_PORTUGAL_DISTRICTS = [
    "Viana do Castelo",
    "Braga",
    "Porto",
    "Vila Real",
    "Bragança",
]

PBA_POSITIVE_WHERE = """
(
  TIPOLOXIA like '%Castro%' OR TIPOLOXIA like '%castro%' OR
  TIPOLOXIA like '%castrexo%' OR TIPOLOXIA like '%Castrexo%' OR
  TIPOLOXIA = 'Casto' OR
  NOME like '%Castro%' OR NOME like '%castro%' OR
  NOME like '%Croa%' OR NOME like '%croa%' OR
  NOME like '%Castrel%' OR NOME like '%castrel%' OR
  NOME like '%Castrill%' OR NOME like '%castrill%' OR
  NOME like '%Castriz%' OR NOME like '%castriz%' OR
  NOME like '%Tralocastro%' OR NOME like '%tralocastro%'
)
"""

PT_NORTH_WHERE = "DISTRITO in ('Viana do Castelo','Braga','Porto','Vila Real','Bragança')"
PT_POSITIVE_TERMS = """
(
  Designacao like '%Castro%' OR Designacao like '%castro%' OR
  SiteName like '%Castro%' OR SiteName like '%castro%' OR
  Tipo_Principal like '%Castro%' OR Tipo_Principal like '%castro%' OR
  Outros_Tipos like '%Castro%' OR Outros_Tipos like '%castro%' OR
  Designacao like '%Citânia%' OR Designacao like '%citânia%' OR
  Designacao like '%Citania%' OR Designacao like '%citania%' OR
  SiteName like '%Citânia%' OR SiteName like '%citânia%' OR
  SiteName like '%Citania%' OR SiteName like '%citania%' OR
  Tipo_Principal like '%Citânia%' OR Tipo_Principal like '%Citania%' OR
  Outros_Tipos like '%Citânia%' OR Outros_Tipos like '%Citania%' OR
  Designacao like '%Cividade%' OR Designacao like '%cividade%' OR
  SiteName like '%Cividade%' OR SiteName like '%cividade%' OR
  Tipo_Principal like '%Cividade%' OR Tipo_Principal like '%cividade%' OR
  Outros_Tipos like '%Cividade%' OR Outros_Tipos like '%cividade%' OR
  Designacao like '%Povoado fortificado%' OR Designacao like '%povoado fortificado%' OR
  SiteName like '%Povoado fortificado%' OR SiteName like '%povoado fortificado%' OR
  Outros_Tipos like '%Povoado fortificado%' OR Outros_Tipos like '%povoado fortificado%'
)
"""
PT_POSITIVE_WHERE = f"({PT_NORTH_WHERE}) AND {PT_POSITIVE_TERMS}"

PBA_NEGATIVE_CATEGORIES = {
    "megalithic_mound": """
        TIPOLOXIA in ('Mámoa','Mámoa/Túmulo','Túmulo','Túmulo/Mámoa','Dolmen','Menhir','Pedrafita','Cista','Neolítico') OR
        TIPOLOXIA like '%Mámoa%' OR TIPOLOXIA like '%Mamoa%' OR
        NOME like '%Mámoa%' OR NOME like '%Mamoa%' OR
        NOME like '%Dolmen%' OR NOME like '%Pedrafita%' OR NOME like '%Pedra fita%'
    """,
    "rock_art_surface": """
        TIPOLOXIA in ('Petróglifo','Arte rupestre','Arte rupestre?','Gravado','Lugar con representación gráfica ao aire libre','Inscrición') OR
        TIPOLOXIA like '%Petróglifo%' OR TIPOLOXIA like '%Petroglifo%' OR
        NOME like '%Petróglifo%' OR NOME like '%Petroglifo%'
    """,
    "historic_fortification": """
        TIPOLOXIA in ('Castelo','Fortaleza','Torre','Estruturas defensivas','Estruturas defensivas?','Batería costeira')
    """,
    "roman_built_context": """
        TIPOLOXIA in ('Campamento romano','Calzada romana','Miliario','Romano','Romano/Medieval','Ara')
    """,
    "mining_or_quarry": """
        TIPOLOXIA in ('Explotación mineira')
    """,
    "necropolis_or_burial": """
        TIPOLOXIA in ('Necrópole','Sartego','Mosteiro/Necrópole','Capela/Necrópole')
    """,
}

PT_NEGATIVE_CATEGORIES = {
    "megalithic_mound": """
        Tipo_Principal in ('Anta/Dólmen','Dolmen','Mamoa','Menir','Cista','Cromeleque') OR
        Designacao like '%Mamoa%' OR SiteName like '%Mamoa%' OR
        Designacao like '%Dólmen%' OR Designacao like '%Dolmen%' OR
        SiteName like '%Dólmen%' OR SiteName like '%Dolmen%'
    """,
    "rock_art_surface": """
        Tipo_Principal in ('Arte Rupestre','Inscultura','Inscrição') OR Outros_Tipos like '%Arte Rupestre%'
    """,
    "historic_fortification": """
        Tipo_Principal in ('Castelo','Castelo Roqueiro','Fortificação','Fortim','Atalaia')
    """,
    "roman_built_context": """
        Tipo_Principal in ('Villa','Vila','Calçada','Ponte','Aqueduto','Forum','Fórum','Termas') OR PERIODOS like '%Romano%'
    """,
    "mining_or_quarry": """
        Tipo_Principal in ('Exploração Mineral','Conheira','Escorial')
    """,
    "necropolis_or_burial": """
        Tipo_Principal in ('Necrópole','Cemitério','Sepultura','Sarcófago')
    """,
}

POSITIVE_FIELDS = [
    "bank_id",
    "country",
    "region",
    "province_or_district",
    "municipality",
    "parish",
    "place",
    "name",
    "source",
    "source_quality",
    "source_url",
    "record_url",
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
    "proxy_tags",
    "review_priority",
    "review_reason",
    "training_use",
    "generated_at",
]

NEGATIVE_FIELDS = [
    "bank_id",
    "country",
    "region",
    "province_or_district",
    "municipality",
    "parish",
    "place",
    "name",
    "source",
    "source_quality",
    "source_url",
    "record_url",
    "source_record_id",
    "source_code",
    "typology",
    "generic_type",
    "periods",
    "longitude",
    "latitude",
    "coord_precision",
    "negative_type",
    "negative_confidence",
    "review_priority",
    "review_reason",
    "training_use",
    "generated_at",
]


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


def write_tsv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, dialect="excel-tab", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def request_json(url: str, params: dict[str, str]) -> dict:
    data = urlencode(params).encode("utf-8")
    request = Request(
        url,
        data=data,
        headers={
            "User-Agent": USER_AGENT,
            "Cache-Control": "no-cache",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with urlopen(request, timeout=90) as response:
        payload = json.load(response)
    if "error" in payload:
        raise RuntimeError(f"ArcGIS query failed for {url}: {payload['error']}")
    return payload


def arcgis_count(layer_query_url: str, where: str) -> int:
    payload = request_json(layer_query_url, {"where": compact_sql(where), "returnCountOnly": "true", "f": "pjson"})
    return int(payload.get("count", 0))


def arcgis_query(
    layer_query_url: str,
    where: str,
    out_fields: str,
    *,
    page_size: int,
    order_by: str,
) -> list[dict[str, object]]:
    total = arcgis_count(layer_query_url, where)
    rows: list[dict[str, object]] = []
    offset = 0
    while offset < total:
        params = {
            "where": compact_sql(where),
            "outFields": out_fields,
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "pjson",
            "resultRecordCount": str(page_size),
            "resultOffset": str(offset),
        }
        if order_by:
            params["orderByFields"] = order_by
        payload = request_json(layer_query_url, params)
        features = payload.get("features", [])
        if not features:
            break
        rows.extend(features)
        offset += len(features)
    return rows


def compact_sql(where: str) -> str:
    return " ".join(where.split())


def attrs(feature: dict[str, object]) -> dict[str, str]:
    return {str(key).lower(): clean(value) for key, value in (feature.get("attributes") or {}).items()}


def geometry_lon_lat(feature: dict[str, object], attributes: dict[str, str]) -> tuple[str, str]:
    geometry = feature.get("geometry") or {}
    lon = clean(geometry.get("x")) if isinstance(geometry, dict) else ""
    lat = clean(geometry.get("y")) if isinstance(geometry, dict) else ""
    lon = lon or attributes.get("longitude", "")
    lat = lat or attributes.get("latitude", "")
    return lon, lat


def source_record_id(attributes: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = attributes.get(key.lower(), "")
        if value:
            return value
    return ""


def classify_positive_confidence(country: str, name: str, typology: str, generic_type: str) -> str:
    text = norm(f"{name} {typology} {generic_type}")
    type_text = norm(typology)
    if "castro" in type_text or "castrexo" in type_text or "citania" in type_text or "cividade" in type_text:
        return "high_official_typology"
    if country == "PT" and any(token in text for token in ["castro", "citania", "cividade", "povoado fortificado"]):
        return "medium_official_name_or_type"
    if any(token in text for token in ["castro", "croa", "castrel", "castrill", "castriz", "tralocastro"]):
        return "medium_official_name_or_type"
    if "def" in norm(generic_type):
        return "low_defensive_context_review"
    return "low_toponymic_review"


def morphology_proxy(name: str, typology: str, periods: str = "") -> tuple[str, str, str, str]:
    text = norm(f"{name} {typology} {periods}")
    tags: list[str] = []
    if any(token in text for token in ["punta", "ponta", "cabo", "praia", "playa", "frouxeira", "barona", "baronha", "mar", "illa", "ilha", "costa", "litoral"]):
        tags.append("coastal_promontory_hint")
    if any(token in text for token in ["citania", "cividade"]):
        tags.append("large_castrexo_civitas_hint")
    if any(token in text for token in ["croa", "coroa"]):
        tags.append("croa_top_ring_hint")
    if any(token in text for token in ["castrel", "castrill", "castriz", "castrelo"]):
        tags.append("castrel_toponym_hint")
    if any(token in text for token in ["monte", "coto", "couto", "alto", "outeiro", "pena", "penha", "pico", "penedo", "santa luzia", "sanfins", "briteiros"]):
        tags.append("hilltop_hint")
    if any(token in text for token in ["foso", "foxo", "mural", "muralha", "muralla", "fortificado", "fortificada"]):
        tags.append("earthwork_or_wall_hint")
    if any(token in text for token in ["rio", "ribeira", "rego", "val", "vale", "veiga"]):
        tags.append("valley_or_river_edge_hint")
    if not tags:
        tags.append("generic_castro_hint")

    terrain = "unknown_terrain_pending_visual_review"
    if "coastal_promontory_hint" in tags:
        terrain = "coastal_or_promontory_proxy"
    elif "hilltop_hint" in tags or "croa_top_ring_hint" in tags:
        terrain = "hilltop_or_ridge_proxy"
    elif "valley_or_river_edge_hint" in tags:
        terrain = "valley_or_river_edge_proxy"

    primary = tags[0]
    if primary == "generic_castro_hint":
        priority = "P2"
        reason = "Generic official castro/toponym seed; useful for coverage, but morphology must be checked visually."
    elif primary in {"coastal_promontory_hint", "large_castrexo_civitas_hint", "earthwork_or_wall_hint"}:
        priority = "P0"
        reason = "High-diversity morphology proxy for early QGIS review."
    else:
        priority = "P1"
        reason = "Useful morphology proxy, pending visual confirmation."
    return primary, terrain, ";".join(tags), priority + "|" + reason


def build_pba_positive(feature: dict[str, object]) -> dict[str, str]:
    a = attrs(feature)
    lon, lat = geometry_lon_lat(feature, a)
    oid = source_record_id(a, "objectid_1", "objectid")
    source_code = a.get("id_ipaga") or a.get("cod_impres")
    name = a.get("nome", "")
    typology = a.get("tipoloxia", "")
    proxy, terrain, tags, priority_reason = morphology_proxy(name, typology)
    priority, reason = priority_reason.split("|", 1)
    confidence = classify_positive_confidence("ES", name, typology, a.get("xenerico", ""))
    if confidence.startswith("low") and priority == "P0":
        priority = "P1"
    return {
        "bank_id": f"pos-es-pba-{slugify(oid or source_code or name)}",
        "country": "ES",
        "region": "Galicia",
        "province_or_district": a.get("provincia", ""),
        "municipality": a.get("concello", ""),
        "parish": a.get("parroquia", ""),
        "place": a.get("lugar", ""),
        "name": name,
        "source": "Xunta PBA Catálogo. Elementos (xuño 2026)",
        "source_quality": "official_catalogue_seed",
        "source_url": PBA_DATASET_URL,
        "record_url": a.get("ficha", ""),
        "source_record_id": oid,
        "source_code": source_code,
        "typology": typology,
        "generic_type": a.get("xenerico", ""),
        "periods": "",
        "longitude": lon,
        "latitude": lat,
        "coord_precision": "catalogue_point_wgs84",
        "positive_confidence": confidence,
        "morphology_proxy": proxy,
        "terrain_context_proxy": terrain,
        "proxy_tags": tags,
        "review_priority": priority,
        "review_reason": reason,
        "training_use": "positive_seed_requires_qgis_boundary_review",
        "generated_at": GENERATED_AT,
    }


def build_pt_positive(feature: dict[str, object]) -> dict[str, str]:
    a = attrs(feature)
    lon, lat = geometry_lon_lat(feature, a)
    oid = source_record_id(a, "objectid")
    name = a.get("designacao") or a.get("sitename", "")
    typology = a.get("tipo_principal", "")
    other_types = a.get("outros_tipos", "")
    periods = a.get("periodos", "")
    proxy, terrain, tags, priority_reason = morphology_proxy(name, f"{typology} {other_types}", periods)
    priority, reason = priority_reason.split("|", 1)
    return {
        "bank_id": f"pos-pt-dgpc-{slugify(oid or a.get('cns') or name)}",
        "country": "PT",
        "region": "Norte de Portugal",
        "province_or_district": a.get("distrito", ""),
        "municipality": a.get("concelho", ""),
        "parish": a.get("freguesia", ""),
        "place": "",
        "name": name,
        "source": "DGPC Portal do Arqueólogo Sitios_Arqueologicos",
        "source_quality": "official_catalogue_seed",
        "source_url": DGPC_AGOL_ITEM_URL,
        "record_url": a.get("url", ""),
        "source_record_id": oid,
        "source_code": a.get("cns", "") or a.get("code", ""),
        "typology": typology,
        "generic_type": other_types,
        "periods": periods,
        "longitude": lon,
        "latitude": lat,
        "coord_precision": a.get("precisao", "") or a.get("precisao_metrica", "") or "catalogue_point_wgs84",
        "positive_confidence": classify_positive_confidence("PT", name, f"{typology} {other_types}", ""),
        "morphology_proxy": proxy,
        "terrain_context_proxy": terrain,
        "proxy_tags": tags,
        "review_priority": priority,
        "review_reason": reason,
        "training_use": "positive_seed_requires_qgis_boundary_review",
        "generated_at": GENERATED_AT,
    }


def negative_review_priority(negative_type: str, name: str, typology: str) -> tuple[str, str]:
    text = norm(f"{name} {typology}")
    if negative_type in {"megalithic_mound", "historic_fortification"}:
        return "P0", "Hard negative with shape/context likely to confuse a castro detector; review early."
    if "foso" in text or "foxo" in text or "mural" in text:
        return "P0", "Non-castro defensive/earthwork language can produce false positives; review early."
    if negative_type in {"roman_built_context", "mining_or_quarry"}:
        return "P1", "Built or disturbed landscape context useful as a hard negative after visual check."
    return "P2", "Domain negative useful for breadth, lower priority than mound/fortification distractors."


def build_pba_negative(feature: dict[str, object], negative_type: str) -> dict[str, str]:
    a = attrs(feature)
    lon, lat = geometry_lon_lat(feature, a)
    oid = source_record_id(a, "objectid_1", "objectid")
    name = a.get("nome", "")
    typology = a.get("tipoloxia", "")
    priority, reason = negative_review_priority(negative_type, name, typology)
    return {
        "bank_id": f"neg-es-pba-{slugify(oid or a.get('id_ipaga') or a.get('cod_impres') or name)}",
        "country": "ES",
        "region": "Galicia",
        "province_or_district": a.get("provincia", ""),
        "municipality": a.get("concello", ""),
        "parish": a.get("parroquia", ""),
        "place": a.get("lugar", ""),
        "name": name,
        "source": "Xunta PBA Catálogo. Elementos (xuño 2026)",
        "source_quality": "official_non_castro_heritage_seed",
        "source_url": PBA_DATASET_URL,
        "record_url": a.get("ficha", ""),
        "source_record_id": oid,
        "source_code": a.get("id_ipaga") or a.get("cod_impres"),
        "typology": typology,
        "generic_type": a.get("xenerico", ""),
        "periods": "",
        "longitude": lon,
        "latitude": lat,
        "coord_precision": "catalogue_point_wgs84",
        "negative_type": negative_type,
        "negative_confidence": "official_non_castro_heritage_needs_visual_review",
        "review_priority": priority,
        "review_reason": reason,
        "training_use": "hard_negative_candidate_requires_qgis_review",
        "generated_at": GENERATED_AT,
    }


def build_pt_negative(feature: dict[str, object], negative_type: str) -> dict[str, str]:
    a = attrs(feature)
    lon, lat = geometry_lon_lat(feature, a)
    oid = source_record_id(a, "objectid")
    name = a.get("designacao") or a.get("sitename", "")
    typology = a.get("tipo_principal", "")
    priority, reason = negative_review_priority(negative_type, name, f"{typology} {a.get('outros_tipos', '')}")
    return {
        "bank_id": f"neg-pt-dgpc-{slugify(oid or a.get('cns') or name)}",
        "country": "PT",
        "region": "Norte de Portugal",
        "province_or_district": a.get("distrito", ""),
        "municipality": a.get("concelho", ""),
        "parish": a.get("freguesia", ""),
        "place": "",
        "name": name,
        "source": "DGPC Portal do Arqueólogo Sitios_Arqueologicos",
        "source_quality": "official_non_castro_heritage_seed",
        "source_url": DGPC_AGOL_ITEM_URL,
        "record_url": a.get("url", ""),
        "source_record_id": oid,
        "source_code": a.get("cns", "") or a.get("code", ""),
        "typology": typology,
        "generic_type": a.get("outros_tipos", ""),
        "periods": a.get("periodos", ""),
        "longitude": lon,
        "latitude": lat,
        "coord_precision": a.get("precisao", "") or a.get("precisao_metrica", "") or "catalogue_point_wgs84",
        "negative_type": negative_type,
        "negative_confidence": "official_non_castro_heritage_needs_visual_review",
        "review_priority": priority,
        "review_reason": reason,
        "training_use": "hard_negative_candidate_requires_qgis_review",
        "generated_at": GENERATED_AT,
    }


def collect_positive_rows() -> list[dict[str, str]]:
    pba_features = arcgis_query(
        PBA_LAYER_URL,
        PBA_POSITIVE_WHERE,
        "OBJECTID,OBJECTID_1,NOME,PROVINCIA,CONCELLO,PARROQUIA,LUGAR,ID_IPAGA,COD_IMPRES,TIPOLOXIA,XENERICO,FICHA",
        page_size=1000,
        order_by="PROVINCIA,CONCELLO,NOME",
    )
    pt_features = arcgis_query(
        DGPC_LAYER_URL,
        PT_POSITIVE_WHERE,
        "OBJECTID,CODE,URL,DISTRITO,CONCELHO,FREGUESIA,LATITUDE,LONGITUDE,PERIODOS,Tipo_Principal,Outros_Tipos,Designacao,CNS,PRECISAO,Precisao_Metrica,SiteName",
        page_size=40000,
        order_by="DISTRITO,CONCELHO,Designacao",
    )
    rows = [build_pba_positive(feature) for feature in pba_features]
    rows.extend(build_pt_positive(feature) for feature in pt_features)
    return sorted(rows, key=lambda row: (row["country"], row["province_or_district"], row["municipality"], row["name"], row["bank_id"]))


def collect_negative_rows() -> list[dict[str, str]]:
    rows_by_id: dict[str, dict[str, str]] = {}
    pba_positive_exclusion = f"NOT {PBA_POSITIVE_WHERE}"
    for negative_type, where in PBA_NEGATIVE_CATEGORIES.items():
        features = arcgis_query(
            PBA_LAYER_URL,
            f"({where}) AND ({pba_positive_exclusion})",
            "OBJECTID,OBJECTID_1,NOME,PROVINCIA,CONCELLO,PARROQUIA,LUGAR,ID_IPAGA,COD_IMPRES,TIPOLOXIA,XENERICO,FICHA",
            page_size=1000,
            order_by="PROVINCIA,CONCELLO,NOME",
        )
        for feature in features:
            row = build_pba_negative(feature, negative_type)
            merge_negative_row(rows_by_id, row, negative_type)

    pt_positive_exclusion = f"NOT {PT_POSITIVE_TERMS}"
    for negative_type, where in PT_NEGATIVE_CATEGORIES.items():
        features = arcgis_query(
            DGPC_LAYER_URL,
            f"({PT_NORTH_WHERE}) AND ({where}) AND ({pt_positive_exclusion})",
            "OBJECTID,CODE,URL,DISTRITO,CONCELHO,FREGUESIA,LATITUDE,LONGITUDE,PERIODOS,Tipo_Principal,Outros_Tipos,Designacao,CNS,PRECISAO,Precisao_Metrica,SiteName",
            page_size=40000,
            order_by="DISTRITO,CONCELHO,Designacao",
        )
        for feature in features:
            row = build_pt_negative(feature, negative_type)
            merge_negative_row(rows_by_id, row, negative_type)

    return sorted(rows_by_id.values(), key=lambda row: (row["country"], row["province_or_district"], row["municipality"], row["negative_type"], row["name"], row["bank_id"]))


def merge_negative_row(rows_by_id: dict[str, dict[str, str]], row: dict[str, str], negative_type: str) -> None:
    existing = rows_by_id.get(row["bank_id"])
    if not existing:
        rows_by_id[row["bank_id"]] = row
        return
    types = set(existing["negative_type"].split(";"))
    types.add(negative_type)
    existing["negative_type"] = ";".join(sorted(types))
    if row["review_priority"] < existing["review_priority"]:
        existing["review_priority"] = row["review_priority"]
        existing["review_reason"] = row["review_reason"]


def stratified_sample(rows: list[dict[str, str]], *, target: int, group_fields: list[str], priority_field: str) -> list[dict[str, str]]:
    groups: dict[tuple[str, ...], list[dict[str, str]]] = defaultdict(list)
    priority_order = {"P0": 0, "P1": 1, "P2": 2}
    for row in rows:
        key = tuple(row.get(field, "") for field in group_fields)
        groups[key].append(row)
    for group_rows in groups.values():
        group_rows.sort(
            key=lambda row: (
                priority_order.get(row.get(priority_field, "P2"), 9),
                row.get("positive_confidence", row.get("negative_confidence", "")),
                row.get("municipality", ""),
                row.get("name", ""),
            )
        )

    selected: list[dict[str, str]] = []
    keys = sorted(groups)
    while keys and len(selected) < target:
        next_keys: list[tuple[str, ...]] = []
        for key in keys:
            group_rows = groups[key]
            if group_rows and len(selected) < target:
                selected.append(group_rows.pop(0))
            if group_rows:
                next_keys.append(key)
        keys = next_keys
    return selected


def build_review_seed(positives: list[dict[str, str]], negatives: list[dict[str, str]]) -> list[dict[str, str]]:
    positive_seed = stratified_sample(
        positives,
        target=1200,
        group_fields=["country", "province_or_district", "morphology_proxy", "positive_confidence"],
        priority_field="review_priority",
    )
    negative_seed = stratified_sample(
        negatives,
        target=1200,
        group_fields=["country", "province_or_district", "negative_type"],
        priority_field="review_priority",
    )
    rows: list[dict[str, str]] = []
    for index, row in enumerate(positive_seed, start=1):
        merged = dict(row)
        merged["review_seed_id"] = f"review-pos-{index:04d}"
        merged["review_role"] = "positive"
        merged["class_hint"] = "castro_candidate"
        rows.append(merged)
    for index, row in enumerate(negative_seed, start=1):
        merged = dict(row)
        merged["review_seed_id"] = f"review-neg-{index:04d}"
        merged["review_role"] = "negative"
        merged["class_hint"] = "hard_negative_candidate"
        rows.append(merged)
    return rows


def source_register() -> list[dict[str, str]]:
    return [
        {
            "source_id": "xunta_pba_layer_11",
            "jurisdiction": "Galicia",
            "source_name": "Plan Básico Autonómico de Galicia. Afecciones del patrimonio cultural - Catálogo. Elementos (xuño 2026)",
            "source_type": "official_arcgis_feature_layer",
            "access_url": PBA_LAYER_METADATA_URL,
            "catalogue_url": PBA_DATASET_URL,
            "use_in_bank": "positive_castro_seeds_and_official_non_castro_distractors",
            "caution": "Catalogue points are seeds. Boundaries, morphology and final labels require QGIS review.",
        },
        {
            "source_id": "dgpc_portal_arqueologo_sitios",
            "jurisdiction": "Portugal continental",
            "source_name": "DGPC Portal do Arqueólogo - Sitios_Arqueologicos",
            "source_type": "official_arcgis_feature_layer",
            "access_url": DGPC_LAYER_METADATA_URL,
            "catalogue_url": DGPC_AGOL_ITEM_URL,
            "use_in_bank": "northern_portugal_castro_citania_cividade_seeds_and_non_castro_distractors",
            "caution": "Filtered to northern districts. Catalogue points are not reviewed site polygons.",
        },
        {
            "source_id": "dgpc_portal_arqueologo_service_context",
            "jurisdiction": "Portugal continental",
            "source_name": "DGPC PatrimonioArqueologico/Sitios_Arqueologicos MapServer",
            "source_type": "official_arcgis_map_service_context",
            "access_url": DGPC_SERVICE_URL,
            "catalogue_url": DGPC_SERVICE_URL,
            "use_in_bank": "source_provenance_context",
            "caution": "The service declares Portal do Arqueólogo provenance; extraction uses layer 0.",
        },
    ]


def write_geojson(path: Path, rows: list[dict[str, str]]) -> None:
    features = []
    for row in rows:
        lon = parse_float(row.get("longitude", ""))
        lat = parse_float(row.get("latitude", ""))
        if lon is None or lat is None:
            continue
        properties = {key: value for key, value in row.items() if key not in {"longitude", "latitude"}}
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": properties,
            }
        )
    payload = {"type": "FeatureCollection", "features": features}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_float(value: str) -> float | None:
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def count_by(rows: list[dict[str, str]], key: str) -> Counter[str]:
    return Counter(row.get(key, "") or "(blank)" for row in rows)


def write_summary_tsv(path: Path, positives: list[dict[str, str]], negatives: list[dict[str, str]], review_seed: list[dict[str, str]]) -> None:
    rows: list[dict[str, str]] = []
    for label, source_rows in [("positive_all", positives), ("negative_all", negatives), ("review_seed", review_seed)]:
        for field in ["country", "province_or_district", "positive_confidence", "morphology_proxy", "negative_type", "review_priority", "review_role"]:
            for value, count in sorted(count_by(source_rows, field).items()):
                if value == "(blank)":
                    continue
                rows.append({"dataset": label, "field": field, "value": value, "count": str(count)})
    write_tsv(path, rows, ["dataset", "field", "value", "count"])


def write_report(positives: list[dict[str, str]], negatives: list[dict[str, str]], review_seed: list[dict[str, str]]) -> None:
    positive_country = count_by(positives, "country")
    negative_country = count_by(negatives, "country")
    positive_confidence = count_by(positives, "positive_confidence")
    positive_proxy = count_by(positives, "morphology_proxy")
    negative_type = count_by(negatives, "negative_type")
    review_role = count_by(review_seed, "review_role")
    top_positive_places = Counter(
        f"{row['country']}:{row['province_or_district']}" for row in positives if row.get("province_or_district")
    )
    top_negative_places = Counter(
        f"{row['country']}:{row['province_or_district']}" for row in negatives if row.get("province_or_district")
    )

    lines = [
        "# Morphology Control Bank",
        "",
        f"Generated: {GENERATED_AT}",
        "",
        "## Scope",
        "",
        "This bank broadens the Viladonga pilot into a Galicia plus northern Portugal review corpus. It deliberately separates official positive castro/citania/cividade seeds from official non-castro heritage distractors. None of these points are final training polygons.",
        "",
        "## Official Sources",
        "",
        f"- Xunta PBA layer 11: {PBA_LAYER_METADATA_URL}",
        f"- Xunta data catalogue: {PBA_DATASET_URL}",
        f"- DGPC/Portal do Arqueologo ArcGIS item: {DGPC_AGOL_ITEM_URL}",
        f"- DGPC/Portal do Arqueologo service: {DGPC_SERVICE_URL}",
        f"- DGPC/Portal do Arqueologo layer: {DGPC_LAYER_METADATA_URL}",
        "",
        "## Counts",
        "",
        f"- Positive official castro-like seeds: {len(positives)}",
        f"- Official non-castro hard-negative distractors: {len(negatives)}",
        f"- Stratified QGIS review seed: {len(review_seed)} ({review_role.get('positive', 0)} positive, {review_role.get('negative', 0)} negative)",
        "",
        "### Positives by Country",
        "",
        *bullet_counts(positive_country),
        "",
        "### Positives by Confidence",
        "",
        *bullet_counts(positive_confidence),
        "",
        "### Positives by Morphology Proxy",
        "",
        *bullet_counts(positive_proxy),
        "",
        "### Positive Places",
        "",
        *bullet_counts(top_positive_places),
        "",
        "### Negatives by Country",
        "",
        *bullet_counts(negative_country),
        "",
        "### Negatives by Type",
        "",
        *bullet_counts(negative_type),
        "",
        "### Negative Places",
        "",
        *bullet_counts(top_negative_places),
        "",
        "## Files",
        "",
        "- data/morphology-bank/positive_castro_sources.tsv",
        "- data/morphology-bank/positive_castro_sources.geojson",
        "- data/morphology-bank/negative_distractor_sources.tsv",
        "- data/morphology-bank/negative_distractor_sources.geojson",
        "- data/morphology-bank/morphology_control_review_seed.tsv",
        "- data/morphology-bank/morphology_control_review_seed.geojson",
        "- data/morphology-bank/morphology_strata_summary.tsv",
        "- data/morphology-bank/source_register.tsv",
        "",
        "## Review Rules",
        "",
        "- Positive rows are catalogue seeds, not final site boundaries.",
        "- Morphology proxies are name/type heuristics used only to diversify QGIS review.",
        "- Negative rows are official non-castro heritage distractors; they still require visual review before training.",
        "- Natural empty-terrain negatives should be generated later from raster tiles after buffering away all catalogue heritage seeds.",
    ]
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "morphology_control_bank.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def bullet_counts(counter: Counter[str], limit: int = 16) -> list[str]:
    if not counter:
        return ["- none"]
    lines = [f"- {key}: {value}" for key, value in counter.most_common(limit)]
    if len(counter) > limit:
        lines.append(f"- other values: {sum(value for _, value in counter.most_common()[limit:])}")
    return lines


def main() -> None:
    positives = collect_positive_rows()
    negatives = collect_negative_rows()
    review_seed = build_review_seed(positives, negatives)

    write_tsv(OUT_DIR / "positive_castro_sources.tsv", positives, POSITIVE_FIELDS)
    write_geojson(OUT_DIR / "positive_castro_sources.geojson", positives)
    write_tsv(OUT_DIR / "negative_distractor_sources.tsv", negatives, NEGATIVE_FIELDS)
    write_geojson(OUT_DIR / "negative_distractor_sources.geojson", negatives)

    review_fields = ["review_seed_id", "review_role", "class_hint", *POSITIVE_FIELDS]
    review_fields.extend(field for field in NEGATIVE_FIELDS if field not in review_fields)
    write_tsv(OUT_DIR / "morphology_control_review_seed.tsv", review_seed, review_fields)
    write_geojson(OUT_DIR / "morphology_control_review_seed.geojson", review_seed)
    write_summary_tsv(OUT_DIR / "morphology_strata_summary.tsv", positives, negatives, review_seed)
    write_tsv(
        OUT_DIR / "source_register.tsv",
        source_register(),
        ["source_id", "jurisdiction", "source_name", "source_type", "access_url", "catalogue_url", "use_in_bank", "caution"],
    )
    write_report(positives, negatives, review_seed)

    print(f"Positive official castro-like seeds: {len(positives)}")
    print(f"Official non-castro hard-negative distractors: {len(negatives)}")
    print(f"Stratified review seed: {len(review_seed)}")
    print(f"Wrote {OUT_DIR}")
    print(f"Wrote {REPORTS_DIR / 'morphology_control_bank.md'}")


if __name__ == "__main__":
    main()
