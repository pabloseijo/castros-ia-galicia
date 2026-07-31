#!/usr/bin/env python3
"""
Build the Castros IA Galicia MVP dataset from the Mimir source corpus.

The script is deliberately conservative. It creates a master table and geospatial
outputs for known/potential castro records, but it marks generated negatives and
weak toponymic entries as review-only. A model should not treat those rows as
archaeological facts.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import sqlite3
import struct
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def find_mimir_root(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        if (candidate / "index.md").exists() and (candidate / "wiki/aldea").exists():
            return candidate
    raise RuntimeError("Could not find Mimir root from project path")


MIMIR_ROOT = find_mimir_root(PROJECT_ROOT)
SOURCE_DIR = MIMIR_ROOT / "wiki/aldea/fuentes/datos/castros-trasancos"
OUT_DIR = PROJECT_ROOT / "data/processed/castros-trasancos-mvp"
GENERATED_AT = "2026-07-31T00:00:00Z"

STRICT_MUNICIPALITIES = {
    "Ferrol",
    "Narón",
    "Neda",
    "Fene",
    "Valdoviño",
    "San Sadurniño",
}

SPATIAL_SPLIT_BY_MUNICIPALITY = {
    "Ferrol": "train",
    "Valdoviño": "train",
    "Neda": "train",
    "San Sadurniño": "val",
    "Narón": "test",
}

MUNICIPALITY_BY_GA_PREFIX = {
    "GA15036": "Ferrol",
    "REF15036": "Ferrol",
    "GA15054": "Narón",
    "TO15054": "Narón",
    "GA15055": "Neda",
    "TOP15055": "Neda",
    "GA15035": "Fene",
    "RE15035": "Fene",
    "GA15087": "Valdoviño",
    "GA15076": "San Sadurniño",
}

O_VAL_TOKENS = {
    "quintá",
    "quinta",
    "castro do val",
    "vilasuso",
    "pedreira",
    "pena lopesa",
    "monte do castro",
    "pena grande",
    "cercado neolítico da lagoa",
    "cercado neolitico da lagoa",
}

GENERIC_ALIASES = {
    "castro",
    "castros",
    "croa",
    "croas",
    "cercado",
    "monte do castro",
}

EXCLUDE_NAME_RE = re.compile(
    r"\b("
    r"cat[aá]logo municipal|torre\b|m[aá]moa|mamoa|mui[nñ]o|muino|fervenza|"
    r"ponte\b|cruceiro|capilla|ermita|igrexa|iglesia|villa romana|"
    r"petroglifo|pazo|casa palacio|castelo de narah[ií]o|castillo"
    r")\b",
    re.IGNORECASE,
)

CASTRO_RE = re.compile(r"\b(castro|castros|croa|croas|castrelo|castrill[oó]n|tralocastro)\b", re.IGNORECASE)
ALIAS_BLOCKLIST_RE = re.compile(
    r"\b("
    r"actuaci[oó]ns?|autorizables|correctoras|secretario xeral|localizaci[oó]n|"
    r"clasificaci[oó]n|categor[ií]a do solo|empregamos o sistema|comentarios|"
    r"loading|anterior ben cultural|seguinte ben cultural"
    r")\b",
    re.IGNORECASE,
)


@dataclass
class Site:
    site_id: str
    primary_name: str
    municipality: str
    parish: str = ""
    place: str = ""
    scope: str = "trasancos_estricto"
    ga_code: str = ""
    aliases: set[str] = field(default_factory=set)
    record_type: str = ""
    confidence: str = ""
    source_tier: str = ""
    conservation_state: str = ""
    lat: float | None = None
    lon: float | None = None
    coord_source: str = ""
    coord_status: str = "missing"
    sources: set[str] = field(default_factory=set)
    urls: set[str] = field(default_factory=set)
    notes: list[str] = field(default_factory=list)
    needs_review: set[str] = field(default_factory=set)
    dataset_use: str = "review_only"
    split: str = "review_only"

    def add_aliases(self, *values: str) -> None:
        for value in values:
            for alias in split_aliases(value):
                if alias:
                    self.aliases.add(alias)

    def add_source(self, label: str, url: str = "") -> None:
        if label:
            self.sources.add(label)
        if url:
            self.urls.add(url)


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, dialect="excel-tab"))


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_tsv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, dialect="excel-tab")
        writer.writeheader()
        writer.writerows(rows)


def clean(value: str | None) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\n", " ").split()).strip()


def norm(value: str | None) -> str:
    value = clean(value).lower()
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.replace("ñ", "n")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    value = re.sub(r"\b(castro|castros|croa|croas|de|do|da|dos|das|o|a|os|as|ou|y|e)\b", " ", value)
    return " ".join(value.split())


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", clean(value).lower())
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.replace("ñ", "n")
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value or "sen-nome"


def split_aliases(value: str | None) -> list[str]:
    value = clean(value)
    if not value:
        return []
    value = extract_alias_label(value)
    parts = re.split(r"\s*/\s*|\s+ou\s+|\s+y\s+|;", value, flags=re.IGNORECASE)
    out = []
    for part in parts + [value]:
        part = clean_alias_candidate(part)
        if not is_plausible_alias(part):
            continue
        out.append(part)
        stripped_castro = re.sub(r"^Castro\s+(de|do|da|dos|das)\s+", "", part, flags=re.IGNORECASE).strip()
        if is_plausible_alias(stripped_castro):
            out.append(stripped_castro)
    return unique([item for item in out if item])


def extract_alias_label(value: str) -> str:
    value = clean(value)
    code_match = re.search(
        r"C[ÓO]DIGO:\s*([^°]+?)(?:\s*C[ÓO]DIGO\s+GA\b|\s+LOCALIZACI[ÓO]N\b|\s+CLASIFICACI[ÓO]N\b|$)",
        value,
        flags=re.IGNORECASE,
    )
    if code_match:
        return clean(code_match.group(1))

    if len(value) > 160:
        castro_match = re.search(
            r"(?:X-\d+\s+)?(?:Castro|Cercado)\s+(?:de|do|da|dos|das)?\s*[^:;|]{2,90}",
            value,
            flags=re.IGNORECASE,
        )
        if castro_match:
            return clean(castro_match.group(0))
    return value


def clean_alias_candidate(value: str) -> str:
    value = clean(value)
    value = re.split(
        r"\b(?:CLASIFICACI[ÓO]N|C[ÓO]DIGO\s+GA|LOCALIZACI[ÓO]N|ACTUACI[ÓO]NS?)\b",
        value,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    value = re.sub(r"^[^0-9A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+", "", value)
    value = re.sub(r"[^0-9A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+$", "", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def is_plausible_alias(value: str) -> bool:
    value = clean(value)
    if not value or len(value) > 100:
        return False
    if unaccent(value).lower() in GENERIC_ALIASES:
        return False
    if ALIAS_BLOCKLIST_RE.search(unaccent(value).lower()):
        return False
    letters = re.findall(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", value)
    if len(letters) < 2:
        return False
    alnum = re.findall(r"[0-9A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", value)
    if len(alnum) / max(len(value), 1) < 0.45:
        return False
    if re.search(r"([!()°])\1{3,}", value):
        return False
    return True


def unique(items: Iterable[str]) -> list[str]:
    seen = set()
    out = []
    for item in items:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def canonical_municipality(value: str, code: str = "") -> str:
    value = clean(value)
    aliases = {
        "Naron": "Narón",
        "Narón": "Narón",
        "Valdoviñ": "Valdoviño",
        "Valdovino": "Valdoviño",
        "Valdoviño": "Valdoviño",
        "San Sadurnino": "San Sadurniño",
        "San Sadurniño": "San Sadurniño",
        "Fene": "Fene",
        "Ferrol": "Ferrol",
        "Neda": "Neda",
    }
    for prefix, municipality in MUNICIPALITY_BY_GA_PREFIX.items():
        if code and code.startswith(prefix):
            return municipality
    return aliases.get(value, value)


def infer_record_municipality(record: dict[str, str]) -> str:
    code = clean(record.get("ga_code", "")).upper()
    municipality = canonical_municipality(record.get("municipality", ""), code)
    haystack = unaccent(" ".join([record.get("parish", ""), record.get("place", ""), record.get("name", "")]).lower())
    if "o val" in haystack or "santa maria a maior" in haystack or "sta. maria la mayor del val" in haystack:
        return "Narón"
    return municipality


def unaccent(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in value if not unicodedata.combining(ch))


def code_from_text(value: str) -> str:
    match = re.search(r"\b(?:GA|REF|RE|TO|TOP)\d{8,9}\b", clean(value), flags=re.IGNORECASE)
    return match.group(0).upper() if match else ""


def site_key(row: dict[str, str]) -> str:
    code = clean(row.get("codigo", "")).upper()
    if code and code not in {"E", "EN TRÁMITE", "EN TRAMITE"}:
        return f"code:{code}"
    municipality = canonical_municipality(row.get("municipio", ""), code)
    return "site:" + "|".join(
        [
            slugify(municipality),
            slugify(row.get("nombre", "")),
            slugify(row.get("parroquia", "")),
            slugify(row.get("lugar", "")),
        ]
    )


def should_exclude_site_name(name: str) -> bool:
    if CASTRO_RE.search(name):
        if re.search(r"\b(r[ií]o castro|castro sto|castro santo|iglesia y castro)\b", name, flags=re.IGNORECASE):
            return False
        return False
    if "Santa Comba" in name and "Necrópolis" in name:
        return False
    return bool(EXCLUDE_NAME_RE.search(name))


def classify_official(row: dict[str, str]) -> tuple[str, str, str, str, list[str]]:
    name = clean(row.get("nombre", ""))
    code = clean(row.get("codigo", "")).upper()
    source = clean(row.get("fuente", ""))
    notes: list[str] = []

    if "Cercado neolítico" in name or "Cercado neolitico" in name:
        return (
            "conflict_neolithic_or_castro",
            "medium",
            "official_catalog_conflict",
            "review_only",
            ["Pena Grande/Lagoa: no usar como positivo hasta resolver castro vs cercado neolítico."],
        )
    if source.startswith("Plan Sectorial"):
        return ("official_plan_reference", "medium_high", "official_context", "review_only", [])
    if code.startswith("REF") or code.startswith("RE") or code.startswith("TO") or code.startswith("TOP"):
        return ("official_reference_or_toponym", "medium", "official_reference", "review_only", [])
    if code.startswith("GA"):
        return ("official_castro", "high", "official_catalog", "positive_candidate", [])
    return ("official_uncoded_castro", "medium_high", "official_catalog_uncoded", "positive_candidate", notes)


def parse_decimal_coord(value: str, min_value: float, max_value: float) -> float | None:
    for match in re.finditer(r"[-+]?\d+(?:\.\d+)?", clean(value)):
        try:
            number = float(match.group(0))
        except ValueError:
            continue
        if min_value <= number <= max_value:
            return number
    return None


def extract_coords(record: dict[str, str]) -> tuple[float | None, float | None]:
    lat = parse_decimal_coord(record.get("lat", ""), 42.0, 45.0)
    lon = parse_decimal_coord(record.get("lon", ""), -9.5, -7.0)
    if lat is not None and lon is not None:
        return lat, lon

    utm_x = parse_decimal_coord(record.get("utm_x", ""), 450000, 650000)
    utm_y = parse_decimal_coord(record.get("utm_y", ""), 4700000, 4900000)
    if utm_x is not None and utm_y is not None:
        return utm29n_to_wgs84(utm_x, utm_y)
    return None, None


def utm29n_to_wgs84(easting: float, northing: float) -> tuple[float, float]:
    # ETRS89 and WGS84 differ by less than the accuracy needed for this MVP.
    a = 6378137.0
    f = 1 / 298.257223563
    k0 = 0.9996
    e = math.sqrt(f * (2 - f))
    e1sq = e * e / (1 - e * e)
    x = easting - 500000.0
    y = northing
    lon0 = math.radians((29 - 1) * 6 - 180 + 3)

    m = y / k0
    mu = m / (a * (1 - e**2 / 4 - 3 * e**4 / 64 - 5 * e**6 / 256))
    e1 = (1 - math.sqrt(1 - e**2)) / (1 + math.sqrt(1 - e**2))
    j1 = 3 * e1 / 2 - 27 * e1**3 / 32
    j2 = 21 * e1**2 / 16 - 55 * e1**4 / 32
    j3 = 151 * e1**3 / 96
    j4 = 1097 * e1**4 / 512
    fp = mu + j1 * math.sin(2 * mu) + j2 * math.sin(4 * mu) + j3 * math.sin(6 * mu) + j4 * math.sin(8 * mu)
    c1 = e1sq * math.cos(fp) ** 2
    t1 = math.tan(fp) ** 2
    r1 = a * (1 - e**2) / (1 - e**2 * math.sin(fp) ** 2) ** 1.5
    n1 = a / math.sqrt(1 - e**2 * math.sin(fp) ** 2)
    d = x / (n1 * k0)
    q1 = n1 * math.tan(fp) / r1
    q2 = d**2 / 2
    q3 = (5 + 3 * t1 + 10 * c1 - 4 * c1**2 - 9 * e1sq) * d**4 / 24
    q4 = (61 + 90 * t1 + 298 * c1 + 45 * t1**2 - 252 * e1sq - 3 * c1**2) * d**6 / 720
    lat = fp - q1 * (q2 - q3 + q4)
    q5 = d
    q6 = (1 + 2 * t1 + c1) * d**3 / 6
    q7 = (5 - 2 * c1 + 28 * t1 - 3 * c1**2 + 8 * e1sq + 24 * t1**2) * d**5 / 120
    lon = lon0 + (q5 - q6 + q7) / math.cos(fp)
    return math.degrees(lat), math.degrees(lon)


def match_score(site: Site, record: dict[str, str]) -> int:
    rec_code = clean(record.get("ga_code", "")).upper()
    if site.ga_code and rec_code and site.ga_code == rec_code:
        return 100

    rec_municipality = infer_record_municipality(record)
    if rec_municipality and site.municipality and rec_municipality != site.municipality:
        # Patrimonio Galego sometimes carries a wrong municipality in the scrape;
        # allow code matches above, but keep name-only matches strict.
        return 0

    rec_name = clean(record.get("name", ""))
    rec_norm = norm(rec_name)
    if not rec_norm:
        return 0
    aliases = {norm(site.primary_name), *(norm(alias) for alias in site.aliases)}
    aliases = {alias for alias in aliases if alias}
    if rec_norm in aliases:
        return 80
    if rec_norm == "val" and (site.ga_code == "GA15054002" or any("quinta" in alias for alias in aliases)):
        return 75
    if "santa comba" in rec_norm and any("santa comba" in alias for alias in aliases):
        return 70
    for alias in aliases:
        if alias and len(alias) >= 4 and (alias in rec_norm or rec_norm in alias):
            return 60
    return 0


def choose_dataset_use(site: Site) -> tuple[str, str]:
    note = " ".join(site.notes).lower()
    state = (site.conservation_state or "").lower()
    raw_haystack = unaccent(" ".join([site.primary_name, " ".join(site.aliases), site.parish, site.place]).lower())

    if site.scope != "trasancos_estricto":
        return "exclude_out_of_scope", "exclude"
    if site.record_type in {"conflict_neolithic_or_castro", "toponymic_candidate"}:
        return "review_only", "review_only"
    if "desaparecido" in state or "desaparecido" in note or "destruido" in state or "destruido" in note:
        return "positive_damaged_review", "review_only"
    if site.coord_status == "missing":
        return "needs_geocoding", "review_only"
    if site.municipality == "Narón" and (
        "o val" in raw_haystack
        or "santa maria a maior" in raw_haystack
        or any(token in raw_haystack for token in O_VAL_TOKENS)
    ):
        return "positive_o_val_holdout", "test_o_val"
    if site.confidence in {"high", "medium_high"} and site.record_type in {"official_castro", "official_uncoded_castro"}:
        split = SPATIAL_SPLIT_BY_MUNICIPALITY.get(site.municipality)
        if split == "train":
            return "train_positive_candidate", "train"
        if split == "val":
            return "val_positive_candidate", "val"
        if split == "test":
            return "test_positive_candidate", "test"
        return "review_only", "review_only"
    return "review_only", "review_only"


def deterministic_bucket(value: str) -> int:
    return int(hashlib.sha1(value.encode("utf-8")).hexdigest()[:8], 16) % 100


def source_priority(source: str) -> int:
    priorities = {
        "Patrimonio Galego": 90,
        "Artabro": 80,
        "Galipedia": 60,
        "PXOM Narón 2023/2024": 95,
        "Fálame de San Sadurniño": 40,
    }
    return priorities.get(source, 20)


def build_sites() -> tuple[list[Site], list[dict[str, str]], list[dict[str, str]]]:
    official_rows = read_tsv(SOURCE_DIR / "catalogos-oficiais-castros-trasancos.tsv")
    pena_rows = read_tsv(SOURCE_DIR / "catalogacion-pena-calameo-1991-2010.tsv")
    san_rows = read_tsv(SOURCE_DIR / "san-sadurnino-pistas-falame-galipedia.tsv")
    records = read_json(SOURCE_DIR / "castros_trasancos_records.json")

    sites_by_key: dict[str, Site] = {}
    source_index_notes: list[dict[str, str]] = []

    for row in official_rows:
        name = clean(row.get("nombre", ""))
        code = clean(row.get("codigo", "")).upper()
        municipality = canonical_municipality(row.get("municipio", ""), code)
        if not name or should_exclude_site_name(name):
            source_index_notes.append({**row, "decision": "non_castro_or_source_reference"})
            continue
        record_type, confidence, source_tier, dataset_use, notes = classify_official(row)
        key = site_key(row)
        if key not in sites_by_key:
            site_id = make_site_id(municipality, name, code)
            sites_by_key[key] = Site(
                site_id=site_id,
                primary_name=name,
                municipality=municipality,
                parish=clean(row.get("parroquia", "")),
                place=clean(row.get("lugar", "")),
                ga_code="" if code in {"E", "EN TRÁMITE", "EN TRAMITE"} else code,
                record_type=record_type,
                confidence=confidence,
                source_tier=source_tier,
                dataset_use=dataset_use,
            )
        site = sites_by_key[key]
        site.add_aliases(name, row.get("lugar", ""))
        site.add_source(row.get("fuente", ""), row.get("url", ""))
        site.notes.extend(notes)
        if clean(row.get("notas", "")):
            site.notes.append(clean(row.get("notas", "")))
        if row.get("parroquia") and row["parroquia"] not in site.parish:
            site.parish = merge_text(site.parish, row["parroquia"])
        if row.get("lugar") and row["lugar"] not in site.place:
            site.place = merge_text(site.place, row["lugar"])

    out_of_scope_rows: list[dict[str, str]] = []
    for row in pena_rows:
        municipality = canonical_municipality(row.get("ambito", ""))
        if row.get("nota") != "Trasancos estricto":
            out_of_scope_rows.append(row)
            continue
        matched = find_best_site(sites_by_key.values(), municipality, row.get("nombre", ""))
        if matched:
            matched.add_aliases(row.get("nombre", ""))
            matched.add_source(row.get("fuente", ""), row.get("url", ""))
            if row.get("estado_en_fuente"):
                matched.conservation_state = merge_text(matched.conservation_state, row["estado_en_fuente"])
            matched.notes.append(f"Presente en lista clásica Pena/Calaméo nº {row.get('numero')}.")
            continue
        name = clean(row.get("nombre", ""))
        key = "pena:" + "|".join([slugify(municipality), slugify(name), slugify(row.get("parroquia_lugar", ""))])
        site = Site(
            site_id=make_site_id(municipality, name, ""),
            primary_name=name if CASTRO_RE.search(name) else f"Castro de {name}",
            municipality=municipality,
            parish=clean(row.get("parroquia_lugar", "")),
            scope="trasancos_estricto",
            record_type="classical_catalog_reference",
            confidence="medium_low",
            source_tier="classical_secondary_catalog",
            conservation_state=clean(row.get("estado_en_fuente", "")),
        )
        site.add_aliases(name)
        site.add_source(row.get("fuente", ""), row.get("url", ""))
        site.notes.append("Entrada de la lista clásica Pena/Calaméo pendiente de reconciliación con catálogo oficial.")
        sites_by_key[key] = site

    for row in san_rows:
        name = clean(row.get("nombre_normalizado", ""))
        code = code_from_text(row.get("codigo_o_indicio", ""))
        matched = None
        if code:
            matched = find_by_code(sites_by_key.values(), code)
        if not matched:
            matched = find_best_site(sites_by_key.values(), "San Sadurniño", name)
        if matched:
            matched.add_aliases(name, row.get("variantes", ""))
            matched.add_source("Fálame/Galipedia/O Noso Patrimonio", row.get("url", ""))
            if code and not matched.ga_code:
                matched.ga_code = code
            matched.notes.append(clean(row.get("aportacion", "")))
            continue
        key = "san-pista:" + slugify(name)
        site = Site(
            site_id=make_site_id("San Sadurniño", name, code),
            primary_name=name,
            municipality="San Sadurniño",
            parish=clean(row.get("parroquia_lugar", "")),
            ga_code=code,
            record_type="toponymic_candidate",
            confidence="low",
            source_tier="local_toponymic_hint",
        )
        site.add_aliases(name, row.get("variantes", ""))
        site.add_source("Fálame/Galipedia/O Noso Patrimonio", row.get("url", ""))
        site.notes.append(clean(row.get("aportacion", "")))
        site.needs_review.add("Contrastar con PXOM/Xunta antes de usar como positivo.")
        sites_by_key[key] = site

    enrich_with_scrape_records(list(sites_by_key.values()), records)
    add_unmatched_web_candidates(sites_by_key, records)
    finalize_sites(list(sites_by_key.values()))

    return sorted(sites_by_key.values(), key=lambda s: (s.municipality, s.site_id)), out_of_scope_rows, source_index_notes


def make_site_id(municipality: str, name: str, code: str) -> str:
    if code and code not in {"E", "EN TRÁMITE", "EN TRAMITE"}:
        return f"tra-{slugify(municipality)}-{slugify(code)}"
    return f"tra-{slugify(municipality)}-{slugify(name)[:64]}"


def merge_text(old: str, new: str) -> str:
    old = clean(old)
    new = clean(new)
    if not old:
        return new
    if not new or new in old:
        return old
    return f"{old} | {new}"


def clean_status_value(value: str) -> str:
    value = clean(value)
    if not value:
        return ""
    value = re.split(r"\bACTUACI[ÓO]NS?\s+", value, maxsplit=1, flags=re.IGNORECASE)[0]
    value = clean(value)
    if not value:
        return ""
    if len(value) > 120 and not re.search(
        r"\b(regular|bo|malo|moi malo|desaparecido|destru[ií]do|deteriorado)\b",
        value,
        flags=re.IGNORECASE,
    ):
        return ""
    return value[:160].strip()


def find_by_code(sites: Iterable[Site], code: str) -> Site | None:
    code = clean(code).upper()
    for site in sites:
        if site.ga_code and site.ga_code == code:
            return site
    return None


def find_best_site(sites: Iterable[Site], municipality: str, name: str) -> Site | None:
    municipality = canonical_municipality(municipality)
    name_norm = norm(name)
    best: tuple[int, Site] | None = None
    for site in sites:
        if municipality and site.municipality != municipality:
            continue
        aliases = {norm(site.primary_name), *(norm(alias) for alias in site.aliases)}
        score = 0
        if name_norm in aliases:
            score = 90
        else:
            for alias in aliases:
                if alias and name_norm and len(name_norm) >= 4 and (name_norm in alias or alias in name_norm):
                    score = max(score, 60)
        if score and (best is None or score > best[0]):
            best = (score, site)
    return best[1] if best else None


def enrich_with_scrape_records(sites: list[Site], records: list[dict[str, str]]) -> None:
    coord_candidates: dict[str, list[tuple[int, float, float, str]]] = defaultdict(list)
    for record in records:
        if record.get("source_type") in {"context_or_bibliography", "search_results"}:
            continue
        if not useful_site_record(record):
            continue
        best: tuple[int, Site] | None = None
        for site in sites:
            score = match_score(site, record)
            if score and (best is None or score > best[0]):
                best = (score, site)
        if not best:
            continue
        site = best[1]
        site.add_aliases(record.get("name", ""))
        site.add_source(record.get("source", ""), record.get("url", ""))
        if record.get("ga_code") and not site.ga_code and clean(record["ga_code"]).upper() not in {"E", "EN TRÁMITE"}:
            site.ga_code = clean(record["ga_code"]).upper()
        status = clean_status_value(record.get("status", ""))
        if status:
            site.conservation_state = merge_text(site.conservation_state, status)
        lat, lon = extract_coords(record)
        if lat is not None and lon is not None:
            coord_candidates[site.site_id].append((source_priority(record.get("source", "")), lat, lon, record.get("source", "")))

    by_id = {site.site_id: site for site in sites}
    for site_id, candidates in coord_candidates.items():
        candidates.sort(reverse=True)
        _, lat, lon, source = candidates[0]
        site = by_id[site_id]
        site.lat = lat
        site.lon = lon
        site.coord_source = source
        site.coord_status = "point_from_source"
        if len(candidates) > 1:
            site.notes.append(f"{len(candidates)} coordenadas candidatas en fuentes; se eligió {source} por prioridad.")


def useful_site_record(record: dict[str, str]) -> bool:
    name = clean(record.get("name", ""))
    if not name:
        return False
    if EXCLUDE_NAME_RE.search(name) and not CASTRO_RE.search(name):
        return False
    return bool(CASTRO_RE.search(name) or "Cercado neolítico" in name or "Cercado neolitico" in name)


def add_unmatched_web_candidates(sites_by_key: dict[str, Site], records: list[dict[str, str]]) -> None:
    existing_sites = list(sites_by_key.values())
    for record in records:
        if record.get("source_type") in {"context_or_bibliography", "search_results"}:
            continue
        if not useful_site_record(record):
            continue
        code = clean(record.get("ga_code", "")).upper()
        municipality = infer_record_municipality(record)
        if municipality not in STRICT_MUNICIPALITIES:
            continue
        if code and find_by_code(existing_sites, code):
            continue
        if find_best_site(existing_sites, municipality, record.get("name", "")):
            continue
        name = clean(record.get("name", ""))
        is_cercado_conflict = "Cercado neolítico" in name or "Cercado neolitico" in name
        key = "web:" + "|".join([slugify(municipality), slugify(name), slugify(record.get("place", ""))])
        site = Site(
            site_id=make_site_id(municipality, name, code),
            primary_name=name,
            municipality=municipality,
            parish=clean(record.get("parish", "")),
            place=clean(record.get("place", "")),
            ga_code=code if code not in {"E", "EN TRÁMITE", "EN TRAMITE"} else "",
            record_type="conflict_neolithic_or_castro" if is_cercado_conflict else "web_catalog_candidate",
            confidence="medium" if record.get("source") in {"Patrimonio Galego", "Artabro"} else "medium_low",
            source_tier="web_catalog_conflict" if is_cercado_conflict else record.get("source_type", ""),
        )
        site.add_aliases(name)
        site.add_source(record.get("source", ""), record.get("url", ""))
        status = clean_status_value(record.get("status", ""))
        if status:
            site.conservation_state = status
        lat, lon = extract_coords(record)
        if lat is not None and lon is not None:
            site.lat = lat
            site.lon = lon
            site.coord_source = clean(record.get("source", ""))
            site.coord_status = "point_from_source"
        site.notes.append("Candidato procedente de catálogo web no reconciliado con la tabla oficial normalizada.")
        if is_cercado_conflict:
            site.notes.append("Caso Pena Grande/Lagoa: no usar como positivo hasta resolver castro vs cercado neolítico.")
        site.needs_review.add("Reconciliar manualmente antes de usar como positivo fuerte.")
        sites_by_key[key] = site
        existing_sites.append(site)


def finalize_sites(sites: list[Site]) -> None:
    seen_ids: dict[str, int] = {}
    for site in sites:
        if site.site_id in seen_ids:
            seen_ids[site.site_id] += 1
            site.site_id = f"{site.site_id}-{seen_ids[site.site_id]}"
        else:
            seen_ids[site.site_id] = 1
        if not site.conservation_state:
            note = " ".join(site.notes).lower()
            if "desaparecido" in note or "destruido" in note or "destruído" in note:
                site.conservation_state = "desaparecido/deteriorado"
            else:
                site.conservation_state = "desconocido"
        if site.record_type.startswith("official") and site.coord_status == "missing":
            site.needs_review.add("Buscar/revisar coordenadas antes de crear tiles.")
        site.dataset_use, site.split = choose_dataset_use(site)


def site_to_row(site: Site) -> dict[str, str]:
    return {
        "site_id": site.site_id,
        "primary_name": site.primary_name,
        "aliases": "; ".join(sorted(site.aliases)),
        "municipality": site.municipality,
        "parish": site.parish,
        "place": site.place,
        "scope": site.scope,
        "ga_code": site.ga_code,
        "record_type": site.record_type,
        "confidence": site.confidence,
        "source_tier": site.source_tier,
        "conservation_state": site.conservation_state,
        "lat_wgs84": f"{site.lat:.8f}" if site.lat is not None else "",
        "lon_wgs84": f"{site.lon:.8f}" if site.lon is not None else "",
        "coord_status": site.coord_status,
        "coord_source": site.coord_source,
        "dataset_use": site.dataset_use,
        "split": site.split,
        "needs_review": "; ".join(sorted(site.needs_review)),
        "sources": "; ".join(sorted(site.sources)),
        "urls": "; ".join(sorted(site.urls)),
        "notes": " | ".join(unique(site.notes)),
    }


def build_geojson(sites: list[Site], include_review_only: bool = True) -> dict:
    features = []
    for site in sites:
        if site.lat is None or site.lon is None:
            continue
        if not include_review_only and site.split == "review_only":
            continue
        props = site_to_row(site)
        props.pop("lat_wgs84", None)
        props.pop("lon_wgs84", None)
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [site.lon, site.lat]},
                "properties": props,
            }
        )
    return {
        "type": "FeatureCollection",
        "name": "castros_trasancos_master",
        "crs": {"type": "name", "properties": {"name": "EPSG:4326"}},
        "features": features,
    }


def build_negative_candidates(sites: list[Site], count_limit: int = 160) -> list[dict[str, str]]:
    coords = [(s.lat, s.lon) for s in sites if s.lat is not None and s.lon is not None]
    if not coords:
        return []
    min_lat = max(43.40, min(lat for lat, _ in coords) - 0.015)
    max_lat = min(43.68, max(lat for lat, _ in coords) + 0.015)
    min_lon = max(-8.36, min(lon for _, lon in coords) - 0.015)
    max_lon = min(-7.94, max(lon for _, lon in coords) + 0.015)
    step = 0.015
    rows = []
    idx = 1
    lat = min_lat
    while lat <= max_lat and len(rows) < count_limit:
        lon = min_lon
        while lon <= max_lon and len(rows) < count_limit:
            if min(haversine_m(lat, lon, s.lat, s.lon) for s in sites if s.lat is not None and s.lon is not None) >= 1200:
                rows.append(
                    {
                        "negative_id": f"neg-tra-{idx:04d}",
                        "lat_wgs84": f"{lat:.8f}",
                        "lon_wgs84": f"{lon:.8f}",
                        "status": "generated_candidate_requires_qgis_review",
                        "use": "hard_negative_candidate",
                        "notes": "Punto generado automáticamente lejos de positivos conocidos; no asumir que sea negativo real sin revisión visual.",
                    }
                )
                idx += 1
            lon += step
        lat += step
    return rows


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * radius * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def write_geojson(path: Path, geojson: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(geojson, ensure_ascii=False, indent=2), encoding="utf-8")


def write_gpkg_points(path: Path, sites: list[Site]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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
            last_change DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            min_x DOUBLE, min_y DOUBLE, max_x DOUBLE, max_y DOUBLE,
            srs_id INTEGER,
            CONSTRAINT fk_gc_r_srs_id FOREIGN KEY (srs_id) REFERENCES gpkg_spatial_ref_sys(srs_id)
        );
        CREATE TABLE gpkg_geometry_columns (
            table_name TEXT NOT NULL,
            column_name TEXT NOT NULL,
            geometry_type_name TEXT NOT NULL,
            srs_id INTEGER NOT NULL,
            z TINYINT NOT NULL,
            m TINYINT NOT NULL,
            PRIMARY KEY (table_name, column_name),
            CONSTRAINT fk_gc_tn FOREIGN KEY (table_name) REFERENCES gpkg_contents(table_name),
            CONSTRAINT fk_gc_srs FOREIGN KEY (srs_id) REFERENCES gpkg_spatial_ref_sys(srs_id)
        );
        CREATE TABLE castros_master (
            fid INTEGER PRIMARY KEY AUTOINCREMENT,
            geom BLOB NOT NULL,
            site_id TEXT,
            primary_name TEXT,
            municipality TEXT,
            parish TEXT,
            place TEXT,
            ga_code TEXT,
            record_type TEXT,
            confidence TEXT,
            dataset_use TEXT,
            split TEXT,
            coord_source TEXT,
            notes TEXT
        );
        """
    )
    geo_sites = [s for s in sites if s.lat is not None and s.lon is not None]
    min_x = min((s.lon for s in geo_sites), default=None)
    max_x = max((s.lon for s in geo_sites), default=None)
    min_y = min((s.lat for s in geo_sites), default=None)
    max_y = max((s.lat for s in geo_sites), default=None)
    cur.execute(
        """
        INSERT INTO gpkg_contents
        (table_name, data_type, identifier, description, last_change, min_x, min_y, max_x, max_y, srs_id)
        VALUES (?, 'features', ?, ?, ?, ?, ?, ?, ?, 4326)
        """,
        (
            "castros_master",
            "castros_master",
            "Castros IA Galicia MVP master points generated from Mimir",
            GENERATED_AT,
            min_x,
            min_y,
            max_x,
            max_y,
        ),
    )
    cur.execute("INSERT INTO gpkg_geometry_columns VALUES ('castros_master', 'geom', 'POINT', 4326, 0, 0)")
    for site in geo_sites:
        geom = gpkg_point_blob(site.lon, site.lat)
        cur.execute(
            """
            INSERT INTO castros_master
            (geom, site_id, primary_name, municipality, parish, place, ga_code, record_type,
             confidence, dataset_use, split, coord_source, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                geom,
                site.site_id,
                site.primary_name,
                site.municipality,
                site.parish,
                site.place,
                site.ga_code,
                site.record_type,
                site.confidence,
                site.dataset_use,
                site.split,
                site.coord_source,
                " | ".join(unique(site.notes))[:2000],
            ),
        )
    conn.commit()
    conn.close()


def gpkg_point_blob(lon: float, lat: float) -> bytes:
    header = b"GP" + bytes([0, 1]) + struct.pack("<i", 4326)
    wkb = struct.pack("<BIdd", 1, 1, lon, lat)
    return header + wkb


def write_negative_geojson(path: Path, negatives: list[dict[str, str]]) -> None:
    features = []
    for row in negatives:
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(row["lon_wgs84"]), float(row["lat_wgs84"])],
                },
                "properties": row,
            }
        )
    write_geojson(
        path,
        {
            "type": "FeatureCollection",
            "name": "hard_negative_candidates",
            "crs": {"type": "name", "properties": {"name": "EPSG:4326"}},
            "features": features,
        },
    )


def write_raster_manifest(path: Path) -> None:
    tfg_root = Path("/Users/pabloseijo/Documents/TFG")
    local_files = []
    if tfg_root.exists():
        for pattern in ("*.tif", "*.tiff", "*.laz", "*.las", "*.gpkg", "*.geojson", "*.qgz"):
            local_files.extend(tfg_root.rglob(pattern))
    lines = [
        "# Raster/Data Manifest - Castros IA Galicia MVP",
        "",
        "generated: 2026-07-31",
        "crs_target: EPSG:25829  # ETRS89 / UTM zone 29N; existing Viladonga labels use EPSG:32629, near-equivalent for MVP",
        "heavy_data_policy: keep outside Mimir; do not commit PNOA/LiDAR rasters to wiki",
        "recommended_data_root: /Users/pabloseijo/Documents/CastrosIA/data",
        "",
        "official_sources:",
        "  - name: CNIG LiDAR 3a Cobertura 2022-2025",
        "    url: https://centrodedescargas.cnig.es/CentroDescargas/lidar-tercera-cobertura",
        "    use: preferred LAZ source for new Trasancos processing",
        "  - name: CNIG LiDAR 2a Cobertura 2015-2021",
        "    url: https://centrodedescargas.cnig.es/CentroDescargas/lidar-segunda-cobertura",
        "    use: fallback LAZ source where 3a coverage is unavailable",
        "  - name: CNIG PNOA Maxima Actualidad",
        "    url: https://centrodedescargas.cnig.es/CentroDescargas/ortofoto-pnoa-maxima-actualidad",
        "    use: orthoimage COG tiles for visual/texture channel",
        "  - name: PNOA productos LiDAR y MDT",
        "    url: https://pnoa.ign.es/pnoa-lidar/productos-a-descarga",
        "    use: LAZ/MDT/MDS references and product definitions",
        "  - name: Xunta Galicia centro de descargas",
        "    url: https://mapas.xunta.gal/es/mapas/informacion-geografica/centro-de-descargas",
        "    use: regional vector/raster layers and cartographic cross-checks",
        "",
        "areas:",
        "  - name: trasancos_bbox",
        "    bbox_wgs84: [-8.36, 43.40, -7.94, 43.68]",
        "    status: mvp_search_area",
        "  - name: o_val_holdout",
        "    note: held-out narrative/inference area; do not train on it in first MVP",
        "",
        "derived_products_required:",
        "  - dem_05m_or_1m",
        "  - hillshade_315_45",
        "  - slope_degrees",
        "  - local_relief_model_radius_50m",
        "  - local_relief_model_radius_100m",
        "  - msrm_multiscale_relief",
        "  - pnoa_rgb",
        "  - optional_sentinel2_ndvi_moisture_swir",
        "",
        "local_existing_files:",
    ]
    if local_files:
        for file_path in sorted(local_files):
            try:
                size = file_path.stat().st_size
            except OSError:
                size = 0
            lines.append(f"  - path: {file_path}")
            lines.append(f"    size_bytes: {size}")
    else:
        lines.append("  []")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_report(path: Path, sites: list[Site], negatives: list[dict[str, str]]) -> None:
    counts = defaultdict(int)
    for site in sites:
        counts[f"record_type:{site.record_type}"] += 1
        counts[f"split:{site.split}"] += 1
        counts[f"dataset_use:{site.dataset_use}"] += 1
        counts[f"municipality:{site.municipality}"] += 1
        if site.lat is not None and site.lon is not None:
            counts["with_coordinates"] += 1
        else:
            counts["missing_coordinates"] += 1

    lines = [
        "# Dataset MVP Castros IA Galicia",
        "",
        "Generado: 2026-07-31",
        "",
        "## Resumen",
        "",
        f"- Sitios/pistas en tabla maestra: {len(sites)}",
        f"- Sitios con coordenadas WGS84: {counts['with_coordinates']}",
        f"- Sitios sin coordenadas: {counts['missing_coordinates']}",
        f"- Candidatos negativos generados para revisar en QGIS: {len(negatives)}",
        "",
        "## Particiones",
        "",
    ]
    for key in sorted(k for k in counts if k.startswith("split:")):
        lines.append(f"- {key.removeprefix('split:')}: {counts[key]}")
    lines.extend(["", "## Usos de dataset", ""])
    for key in sorted(k for k in counts if k.startswith("dataset_use:")):
        lines.append(f"- {key.removeprefix('dataset_use:')}: {counts[key]}")
    lines.extend(["", "## Municipios", ""])
    for key in sorted(k for k in counts if k.startswith("municipality:")):
        lines.append(f"- {key.removeprefix('municipality:')}: {counts[key]}")
    lines.extend(
        [
            "",
            "## Lectura operativa",
            "",
            "- La salida lista para QGIS está en `castros_trasancos_master.geojson` y `castros_trasancos_master.gpkg`.",
            "- O Val queda como `test_o_val`/holdout cuando hay coordenadas, para no entrenar el primer modelo con el territorio narrativo principal.",
            "- Las filas `review_only`, `needs_geocoding` y `positive_damaged_review` no deben entrar en entrenamiento hasta revisión manual.",
            "- Los negativos generados son solo semillas espaciales para revisar, no negativos arqueológicos confirmados.",
            "",
            "## Siguiente ejecución real",
            "",
            "1. Abrir el GeoPackage en QGIS.",
            "2. Revisar coordenadas y fusionar duplicados dudosos.",
            "3. Dibujar polígonos/buffers por yacimiento entrenable.",
            "4. Descargar PNOA/LiDAR de CNIG para Trasancos en `/Users/pabloseijo/Documents/CastrosIA/data`.",
            "5. Generar hillshade, slope, LRM/MSRM y recortes 512x512.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sites, out_of_scope, source_notes = build_sites()

    rows = [site_to_row(site) for site in sites]
    master_fields = [
        "site_id",
        "primary_name",
        "aliases",
        "municipality",
        "parish",
        "place",
        "scope",
        "ga_code",
        "record_type",
        "confidence",
        "source_tier",
        "conservation_state",
        "lat_wgs84",
        "lon_wgs84",
        "coord_status",
        "coord_source",
        "dataset_use",
        "split",
        "needs_review",
        "sources",
        "urls",
        "notes",
    ]
    write_tsv(OUT_DIR / "castros_trasancos_master.tsv", rows, master_fields)
    write_geojson(OUT_DIR / "castros_trasancos_master.geojson", build_geojson(sites))
    write_geojson(OUT_DIR / "castros_trasancos_mvp_trainable.geojson", build_geojson(sites, include_review_only=False))
    write_gpkg_points(OUT_DIR / "castros_trasancos_master.gpkg", sites)

    split_rows = [
        {
            "site_id": row["site_id"],
            "primary_name": row["primary_name"],
            "municipality": row["municipality"],
            "dataset_use": row["dataset_use"],
            "split": row["split"],
            "lat_wgs84": row["lat_wgs84"],
            "lon_wgs84": row["lon_wgs84"],
            "notes": row["notes"],
        }
        for row in rows
    ]
    write_tsv(
        OUT_DIR / "castros_trasancos_mvp_splits.tsv",
        split_rows,
        ["site_id", "primary_name", "municipality", "dataset_use", "split", "lat_wgs84", "lon_wgs84", "notes"],
    )

    negatives = build_negative_candidates(sites)
    write_tsv(
        OUT_DIR / "hard_negative_candidates.tsv",
        negatives,
        ["negative_id", "lat_wgs84", "lon_wgs84", "status", "use", "notes"],
    )
    write_negative_geojson(OUT_DIR / "hard_negative_candidates.geojson", negatives)

    write_tsv(
        OUT_DIR / "out_of_scope_bezoucos.tsv",
        out_of_scope,
        ["ambito", "numero", "nombre", "parroquia_lugar", "estado_en_fuente", "fuente", "url", "nota"],
    )
    if source_notes:
        write_tsv(
            OUT_DIR / "non_castro_source_references.tsv",
            source_notes,
            ["municipio", "nombre", "codigo", "parroquia", "lugar", "fuente", "url", "notas", "decision"],
        )

    write_raster_manifest(OUT_DIR / "raster_manifest.yaml")
    write_report(OUT_DIR / "README_dataset.md", sites, negatives)
    print(f"Wrote dataset to {OUT_DIR}")
    print(f"Master rows: {len(sites)}")
    print(f"GeoJSON points: {sum(1 for s in sites if s.lat is not None and s.lon is not None)}")
    print(f"Negative review candidates: {len(negatives)}")


if __name__ == "__main__":
    main()
