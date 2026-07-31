#!/usr/bin/env python3
"""Query the Xunta PBA heritage catalogue for geocoding blockers.

The script is intentionally conservative: it writes candidate reports but does
not inject coordinates into the training dataset. Several blockers are aliases,
duplicates, or non-castro heritage records, so automatic ingestion would create
false progress.
"""

from __future__ import annotations

import csv
import json
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = PROJECT_ROOT / "reports"
QGIS_REVIEW_DIR = PROJECT_ROOT / "data/qgis-review"

PBA_DATASET_URL = "https://datos.gob.es/es/catalogo/a12002994-plan-basico-autonomico-de-galicia-afecciones-del-patrimonio-cultural"
PBA_REST_BASE = "https://ideg.xunta.gal/servizos/rest/services/PBA/Afeccions_PatrimonioCultural/MapServer"
PBA_LAYER_ID = 11
PBA_LAYER_URL = f"{PBA_REST_BASE}/{PBA_LAYER_ID}/query"

USER_AGENT = "Mozilla/5.0 castros-ia-galicia/1.0"
TARGET_MUNICIPALITIES = ["Fene", "Ferrol", "Narón", "Neda", "San Sadurniño", "Valdoviño"]

PBA_OUT_FIELDS = ",".join(
    [
        "NOME",
        "CONCELLO",
        "PARROQUIA",
        "LUGAR",
        "ID_IPAGA",
        "COD_IMPRES",
        "TIPOLOXIA",
        "XENERICO",
        "FICHA",
        "X",
        "Y",
        "OBSERVACIO",
    ]
)


DECISION_RULES = {
    "tra-fene-almieiras": {
        "decision": "still_blocked",
        "reason": "No PBA catalogue hit for Almieiras/Limodre in the queried fields.",
    },
    "tra-fene-fontenova": {
        "decision": "duplicate_or_alias",
        "pba_id_ipaga": "GA15035007",
        "reason": "PBA has Castro de Magalofes at A Fontenova; dataset already has GA15035007 as a separate row.",
    },
    "tra-fene-ga15035011": {
        "decision": "coordinate_for_review_reconcile_duplicate",
        "pba_id_ipaga": "GA15035011",
        "reason": "Exact code match, but PBA names it Castro das Pias/Castro de Cardoeiro and flags location/duplicate in OBSERVACIO.",
    },
    "tra-fene-loureiros": {
        "decision": "duplicate_or_alias",
        "pba_id_ipaga": "GA15035010",
        "reason": "PBA has Castro de Barallobre in Os Loureiros; treat the Pena row as a damaged/alias row to reconcile.",
    },
    "tra-fene-ovra": {
        "decision": "duplicate_or_alias",
        "pba_id_ipaga": "GA15035009",
        "reason": "PBA has Castro de Orra in Sillobre; likely Ovra/Orra spelling reconciliation, not a new site.",
    },
    "tra-fene-re15035002": {
        "decision": "still_blocked",
        "reason": "No PBA hit for RE15035002 or Castro do Sartego; only an unrelated Sartego da Fonte dos Mouros achado appears.",
    },
    "tra-fene-san-esteban-de-perlio": {
        "decision": "duplicate_possible_needs_human",
        "pba_id_ipaga": "GA15035011",
        "reason": "Likely points toward the As Pias/Cardoeiro/Cordoeiro cluster, but name-only evidence is too weak to geocode automatically.",
    },
    "tra-ferrol-canido": {
        "decision": "coordinate_for_damaged_review",
        "pba_id_ipaga": "RE15036007",
        "reason": "Exact PBA reference-name match; keep review-only because the source row is marked damaged/disappeared.",
    },
    "tra-ferrol-ferreiros": {
        "decision": "still_blocked",
        "reason": "PBA match for Ferreiros is a mamoa in Brion, not Castro de Ferreiros in Mandia.",
    },
    "tra-ferrol-o-xeixo": {
        "decision": "duplicate_or_alias",
        "pba_id_ipaga": "GA15036006",
        "reason": "PBA has Castro de Leixa/A Croa de Leixa in San Pedro de Leixa; likely the same target as O Xeixo.",
    },
    "tra-ferrol-papoy": {
        "decision": "duplicate_or_alias",
        "pba_id_ipaga": "GA15036003",
        "reason": "PBA has Castro de Marmancon/Castro de Papoi; Papoy should reconcile to that existing official row.",
    },
    "tra-naron-o-castro": {
        "decision": "duplicate_or_alias",
        "pba_id_ipaga": "GA15054006",
        "reason": "PBA has Castro de Petouzal/Castro da Croa in O Castro/Couto; dataset already has the official Petouzal row.",
    },
    "tra-neda-castros": {
        "decision": "coordinate_for_review_not_training",
        "pba_id_ipaga": "TO15055002",
        "reason": "Exact topographic/toponymic PBA reference; not enough to promote as a training positive.",
    },
    "tra-neda-monte-de-rabadena": {
        "decision": "coordinate_for_review_not_training",
        "pba_id_ipaga": "GA15055005",
        "reason": "Exact code from the prior note, but PBA names it Cazoletas do Monte da Rabadena, not a castro.",
    },
    "tra-neda-santa-maria-de-neda": {
        "decision": "still_blocked",
        "reason": "Same parish as Castro de Ancos, but no PBA name/code supports automatic equivalence.",
    },
    "tra-san-sadurnino-a-croa-naraio": {
        "decision": "coordinate_for_toponymic_review",
        "pba_name": "A Croa",
        "pba_municipality": "San Sadurniño",
        "pba_parish_contains": "Naraio",
        "reason": "PBA has A Croa in Naraio/O Batan, but no ID_IPAGA; keep toponymic review-only.",
    },
    "tra-san-sadurnino-castro-das-croas": {
        "decision": "coordinate_for_review_reconcile_duplicate",
        "pba_id_ipaga": "GA15076006",
        "reason": "Strong PBA name match; reconcile with existing Castro de San Sadurnino/Galipedia row before training.",
    },
    "tra-san-sadurnino-coto-da-croa-ou-a-croa-do-castro": {
        "decision": "coordinate_for_review",
        "pba_id_ipaga": "GA15076005",
        "reason": "PBA has Coto da Croa in Bardaos/O Castro.",
    },
    "tra-san-sadurnino-coto-da-croa-ou-a-croa-do-castro-2": {
        "decision": "coordinate_for_review",
        "pba_id_ipaga": "GA15076004",
        "reason": "PBA has A Croa do Castro in Santa Marina do Monte/Escoitadoira.",
    },
    "tra-san-sadurnino-fraga": {
        "decision": "still_blocked",
        "reason": "No PBA Castro de Fraga match in San Sadurnino/Bardaos.",
    },
    "tra-san-sadurnino-o-picho": {
        "decision": "still_blocked",
        "reason": "PBA Picho hits are fountains, not castro evidence.",
    },
    "tra-san-sadurnino-san-cristobal": {
        "decision": "still_blocked",
        "reason": "No PBA San Cristobal/San Sadurnino castro match in the queried layer.",
    },
    "tra-san-sadurnino-tralocastro": {
        "decision": "still_blocked",
        "reason": "No San Sadurnino Tralocastro hit; Ferrol Tralocastro is a different official site.",
    },
    "tra-valdovino-as-filgueiras": {
        "decision": "still_blocked",
        "reason": "PBA Filgueiras hits are in San Sadurnino and are not Valdovino/Meiras castros.",
    },
    "tra-valdovino-ga15087017": {
        "decision": "coordinate_for_review_not_training",
        "pba_id_ipaga": "GA15087017",
        "reason": "Exact code match, but PBA typology is Medieval, so do not use as castro training positive without review.",
    },
    "tra-valdovino-praia-frouxeira": {
        "decision": "duplicate_or_alias",
        "pba_id_ipaga": "GA15087009",
        "reason": "PBA has Castro de Punta Frouxeira; reconcile with existing official GA15087009 row.",
    },
}


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, dialect="excel-tab"))


def write_tsv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, dialect="excel-tab")
        writer.writeheader()
        writer.writerows(rows)


def pba_query(where: str, *, count: int = 2000) -> list[dict[str, str]]:
    params = {
        "where": where,
        "outFields": PBA_OUT_FIELDS,
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "pjson",
        "resultRecordCount": str(count),
        "orderByFields": "CONCELLO,NOME",
    }
    request = Request(
        PBA_LAYER_URL + "?" + urlencode(params),
        headers={"User-Agent": USER_AGENT, "Cache-Control": "no-cache"},
    )
    with urlopen(request, timeout=60) as response:
        payload = json.load(response)
    if "error" in payload:
        raise RuntimeError(payload["error"])
    rows: list[dict[str, str]] = []
    for feature in payload.get("features", []):
        attrs = {key.lower(): clean(value) for key, value in feature.get("attributes", {}).items()}
        geom = feature.get("geometry") or {}
        attrs["lon_wgs84"] = clean(geom.get("x", ""))
        attrs["lat_wgs84"] = clean(geom.get("y", ""))
        rows.append(attrs)
    return rows


def service_layers() -> list[dict[str, str]]:
    request = Request(
        PBA_REST_BASE + "?f=pjson",
        headers={"User-Agent": USER_AGENT, "Cache-Control": "no-cache"},
    )
    with urlopen(request, timeout=60) as response:
        payload = json.load(response)
    return [{"id": clean(layer.get("id")), "name": clean(layer.get("name"))} for layer in payload.get("layers", [])]


def clean(value: object) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\n", " ").split()).strip()


def castro_like_where() -> str:
    municipalities = ",".join(f"'{name}'" for name in TARGET_MUNICIPALITIES)
    code_prefixes = [
        "GA15035",
        "GA15036",
        "GA15054",
        "GA15055",
        "GA15076",
        "GA15087",
        "RE15036",
        "TO15055",
    ]
    code_filter = " OR ".join(f"ID_IPAGA like '{prefix}%'" for prefix in code_prefixes)
    text_filter = " OR ".join(
        [
            "NOME like '%Castro%'",
            "NOME like '%castro%'",
            "NOME like '%Croa%'",
            "NOME like '%croa%'",
            "NOME like '%Castr%'",
            "TIPOLOXIA like '%Castro%'",
            "TIPOLOXIA like '%castro%'",
            "NOME like '%Rabadeña%'",
            "NOME like '%Frouxeira%'",
            "NOME like '%Sartego%'",
            "NOME like '%Meirás%'",
            "NOME like '%Canido%'",
        ]
    )
    return f"CONCELLO in ({municipalities}) AND ({text_filter} OR {code_filter})"


def exact_code_lookup(pba_rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    by_code: dict[str, dict[str, str]] = {}
    for row in pba_rows:
        code = row.get("id_ipaga", "")
        if code:
            by_code[code] = row
    return by_code


def find_named_candidate(rule: dict[str, str], pba_rows: list[dict[str, str]]) -> dict[str, str] | None:
    expected_name = unaccent(rule.get("pba_name", "").lower())
    expected_municipality = rule.get("pba_municipality", "")
    parish_contains = unaccent(rule.get("pba_parish_contains", "").lower())
    for row in pba_rows:
        if expected_municipality and row.get("concello") != expected_municipality:
            continue
        if expected_name and unaccent(row.get("nome", "").lower()) != expected_name:
            continue
        if parish_contains and parish_contains not in unaccent(row.get("parroquia", "").lower()):
            continue
        return row
    return None


def unaccent(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in value if not unicodedata.combining(ch))


def build_decisions(tasks: list[dict[str, str]], pba_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    by_code = exact_code_lookup(pba_rows)
    decisions: list[dict[str, str]] = []
    for task in tasks:
        site_id = task["site_id"]
        rule = DECISION_RULES.get(site_id, {"decision": "unclassified", "reason": "No manual rule yet."})
        pba_row = None
        if rule.get("pba_id_ipaga"):
            pba_row = by_code.get(rule["pba_id_ipaga"])
        if pba_row is None and rule.get("pba_name"):
            pba_row = find_named_candidate(rule, pba_rows)
        decisions.append(
            {
                "site_id": site_id,
                "primary_name": task["primary_name"],
                "municipality": task["municipality"],
                "parish": task["parish"],
                "current_dataset_use": task["dataset_use"],
                "decision": rule["decision"],
                "reason": rule["reason"],
                "pba_name": pba_row.get("nome", "") if pba_row else "",
                "pba_municipality": pba_row.get("concello", "") if pba_row else "",
                "pba_parish": pba_row.get("parroquia", "") if pba_row else "",
                "pba_place": pba_row.get("lugar", "") if pba_row else "",
                "pba_id_ipaga": pba_row.get("id_ipaga", "") if pba_row else rule.get("pba_id_ipaga", ""),
                "pba_cod_impres": pba_row.get("cod_impres", "") if pba_row else "",
                "pba_tipoloxia": pba_row.get("tipoloxia", "") if pba_row else "",
                "pba_x_etrs89_utm29": pba_row.get("x", "") if pba_row else "",
                "pba_y_etrs89_utm29": pba_row.get("y", "") if pba_row else "",
                "pba_lon_wgs84": pba_row.get("lon_wgs84", "") if pba_row else "",
                "pba_lat_wgs84": pba_row.get("lat_wgs84", "") if pba_row else "",
                "pba_observacio": pba_row.get("observacio", "") if pba_row else "",
            }
        )
    return decisions


def write_report(decisions: list[dict[str, str]], pba_rows: list[dict[str, str]], layers: list[dict[str, str]]) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    by_decision = Counter(row["decision"] for row in decisions)
    layer_11_name = next((row["name"] for row in layers if row["id"] == "11"), "layer 11")

    lines: list[str] = [
        "# PBA catalogue unlock report",
        "",
        f"Generated: {now}",
        "",
        "## Fact-checked sources",
        "",
        f"- Datos.gob dataset: {PBA_DATASET_URL}",
        f"- ArcGIS REST service: {PBA_REST_BASE}",
        f"- Queried feature layer: {PBA_LAYER_ID} / {layer_11_name}",
        "- CRS returned by the service is ETRS89 / UTM zone 29N in X/Y, with WGS84 lon/lat requested via `outSR=4326` for the candidate table.",
        "",
        "## Summary",
        "",
        f"- PBA heritage rows queried for Trasancos municipalities: {len(pba_rows)}",
        f"- Geocoding blockers analysed: {len(decisions)}",
    ]
    for decision, count in sorted(by_decision.items()):
        lines.append(f"- {decision}: {count}")

    lines.extend(
        [
            "",
            "## Operational reading",
            "",
            "- Rows marked `coordinate_for_*` can be placed in QGIS from PBA, but still need human review before they become labels.",
            "- Rows marked `duplicate_or_alias` should be merged or discarded against the stronger existing official row instead of becoming extra positives.",
            "- Rows marked `still_blocked` did not get enough official support from this PBA pass.",
            "- `coordinate_for_review_not_training` is deliberately strict: a coordinate exists, but the PBA typology/toponym does not support using it as a castro training positive.",
            "",
            "## Decisions",
            "",
            "| Site | Decision | PBA candidate | Code | Typology | WGS84 | Reason |",
            "|---|---|---|---|---|---|---|",
        ]
    )
    for row in decisions:
        candidate = " / ".join(part for part in [row["pba_name"], row["pba_parish"], row["pba_place"]] if part)
        coord = ""
        if row["pba_lat_wgs84"] and row["pba_lon_wgs84"]:
            coord = f"{float(row['pba_lat_wgs84']):.8f}, {float(row['pba_lon_wgs84']):.8f}"
        lines.append(
            "| {site} | {decision} | {candidate} | {code} | {typology} | {coord} | {reason} |".format(
                site=row["primary_name"].replace("|", "/"),
                decision=row["decision"],
                candidate=candidate.replace("|", "/"),
                code=row["pba_id_ipaga"],
                typology=row["pba_tipoloxia"],
                coord=coord,
                reason=row["reason"].replace("|", "/"),
            )
        )

    lines.extend(
        [
            "",
            "## Next unblock actions",
            "",
            "1. Merge/discard duplicate alias rows before expanding training positives.",
            "2. Add PBA coordinates only to review queues, not directly to `labels_reviewed`.",
            "3. For `still_blocked` rows, use the PBA visor/PXOM PDFs manually or remove them from the MVP geospatial scope.",
            "4. After QGIS review, draw accepted positives in `labels_reviewed` and accepted negative areas in `negative_areas_reviewed`.",
        ]
    )
    (REPORTS_DIR / "pba_catalog_unlock.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    pba_rows = pba_query(castro_like_where())
    layers = service_layers()
    tasks = read_tsv(QGIS_REVIEW_DIR / "geocoding_tasks.tsv")
    decisions = build_decisions(tasks, pba_rows)

    pba_fields = [
        "nome",
        "concello",
        "parroquia",
        "lugar",
        "id_ipaga",
        "cod_impres",
        "tipoloxia",
        "xenerico",
        "ficha",
        "x",
        "y",
        "lon_wgs84",
        "lat_wgs84",
        "observacio",
    ]
    decision_fields = [
        "site_id",
        "primary_name",
        "municipality",
        "parish",
        "current_dataset_use",
        "decision",
        "reason",
        "pba_name",
        "pba_municipality",
        "pba_parish",
        "pba_place",
        "pba_id_ipaga",
        "pba_cod_impres",
        "pba_tipoloxia",
        "pba_x_etrs89_utm29",
        "pba_y_etrs89_utm29",
        "pba_lon_wgs84",
        "pba_lat_wgs84",
        "pba_observacio",
    ]
    write_tsv(REPORTS_DIR / "pba_catalog_castro_like_snapshot.tsv", pba_rows, pba_fields)
    write_tsv(REPORTS_DIR / "pba_geocoding_candidate_decisions.tsv", decisions, decision_fields)
    write_report(decisions, pba_rows, layers)

    print(f"PBA rows: {len(pba_rows)}")
    for decision, count in sorted(Counter(row["decision"] for row in decisions).items()):
        print(f"{decision}: {count}")


if __name__ == "__main__":
    main()
