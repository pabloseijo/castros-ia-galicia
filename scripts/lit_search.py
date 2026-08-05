#!/usr/bin/env python3
"""Búsqueda de literatura delegable a cualquier nodo, con el control de calidad dentro.

Existe porque el `2026-08-05` una consulta improvisada a OpenAlex, ordenada por
citas, devolvió para un problema de arqueología con LiDAR: una encuesta de imagen
médica, otra de biosensores y una taxonomía del metaverso. Es el mismo fallo
registrado ya tres veces en este proyecto. La respuesta no es «tener más cuidado»,
es **meter las reglas en el código** para que la siguiente búsqueda no pueda
saltárselas:

1. **Nunca se ordena por citas.** El recuento de citas mide popularidad del campo,
   no pertinencia al problema; en un dominio pequeño como la arqueología
   computacional siempre gana la encuesta genérica de otro campo. Se ordena por
   solapamiento léxico con la consulta y se muestra la cita solo como dato.
2. **Se exige DOI y publicación con nombre.** Sin las dos cosas no entra.
3. **Las encuestas genéricas se descartan por defecto** (`--allow-surveys` para
   reabrirlas): son las que más citas acumulan y las que menos dicen sobre un
   problema concreto.
4. **Los preprints se marcan, no se mezclan** (`--include-preprints` para incluirlos).
5. **Concurrencia con semáforo por dominio**, backoff y caché por consulta, para
   ser cortés con APIs públicas y poder reanudar.

Fuentes: OpenAlex, Crossref y Europe PMC, las tres sin clave. Es un complemento
para volumen, **no** un sustituto de las skills `paper-lookup` y
`literature-review`, que son las que mandan según `CLAUDE.md`. Y encontrar un
candidato no autoriza a citarlo: la regla de profundidad exige leer el texto.

Uso:
    python3 scripts/lit_search.py --topics topics.tsv --out resultados.tsv
    python3 scripts/lit_search.py --query "hard negative mining archaeological LiDAR"
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

MAILTO = "kelterastudio@gmail.com"
UA = f"castros-ia-lit-search (+{MAILTO})"

# Semáforo por dominio: cortesía con el servidor remoto, no límite propio.
SEMAPHORES = defaultdict(lambda: threading.Semaphore(3))
PRINT_LOCK = threading.Lock()

# Títulos que casi siempre son encuestas genéricas de otro campo.
SURVEY_RX = re.compile(
    r"\b(a\s+)?(comprehensive\s+)?(systematic\s+)?"
    r"(review|survey|overview|taxonomy|tutorial|state[- ]of[- ]the[- ]art)\b",
    re.I)

PREPRINT_VENUES = {"arxiv", "biorxiv", "medrxiv", "ssrn", "research square",
                   "preprints.org", "techrxiv", "hal", "zenodo", "osf preprints"}

STOP = set("""a an the of for and or in on to with without using via from by at as is are
be this that these those we our their its it new towards toward based approach method
methods study studies analysis application applications use used""".split())


def tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{3,}", (text or "").lower())} - STOP


def http_json(url: str, host_key: str, tries: int = 3):
    for attempt in range(tries):
        try:
            with SEMAPHORES[host_key]:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=45) as r:
                    return json.load(r)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
                json.JSONDecodeError) as e:
            if attempt == tries - 1:
                with PRINT_LOCK:
                    print(f"# FALLO {host_key}: {e}", file=sys.stderr)
                return None
            time.sleep(2 ** attempt * 2)
    return None


def from_openalex(query: str, per_page: int, year_from: int):
    params = {"search": query, "per-page": str(per_page), "mailto": MAILTO,
              "filter": f"from_publication_date:{year_from}-01-01,type:article"}
    d = http_json("https://api.openalex.org/works?" + urllib.parse.urlencode(params),
                  "openalex")
    out = []
    for w in (d or {}).get("results", []):
        src = ((w.get("primary_location") or {}).get("source") or {}) or {}
        oa = w.get("open_access") or {}
        out.append({"title": w.get("title") or "", "year": w.get("publication_year"),
                    "doi": (w.get("doi") or "").replace("https://doi.org/", ""),
                    "venue": src.get("display_name") or "", "cites": w.get("cited_by_count", 0),
                    "oa_url": oa.get("oa_url") or "", "source_api": "openalex"})
    return out


def from_crossref(query: str, per_page: int, year_from: int):
    params = {"query.bibliographic": query, "rows": str(per_page), "mailto": MAILTO,
              "filter": f"from-pub-date:{year_from}-01-01,type:journal-article",
              "select": "title,container-title,issued,DOI,is-referenced-by-count"}
    d = http_json("https://api.crossref.org/works?" + urllib.parse.urlencode(params),
                  "crossref")
    out = []
    for w in ((d or {}).get("message") or {}).get("items", []):
        ct = w.get("container-title") or [""]
        parts = (w.get("issued") or {}).get("date-parts") or [[None]]
        out.append({"title": (w.get("title") or [""])[0], "year": parts[0][0],
                    "doi": w.get("DOI", ""), "venue": ct[0] if ct else "",
                    "cites": w.get("is-referenced-by-count", 0),
                    "oa_url": "", "source_api": "crossref"})
    return out


def from_europepmc(query: str, per_page: int, year_from: int):
    params = {"query": f'{query} AND (FIRST_PDATE:[{year_from}-01-01 TO 2030-12-31])',
              "format": "json", "pageSize": str(per_page), "resultType": "lite"}
    d = http_json("https://www.ebi.ac.uk/europepmc/webservices/rest/search?"
                  + urllib.parse.urlencode(params), "europepmc")
    if d and "errCode" in json.dumps(d)[:400]:      # falla con HTTP 200
        return []
    out = []
    for w in ((d or {}).get("resultList") or {}).get("result", []):
        out.append({"title": w.get("title") or "", "year": w.get("pubYear"),
                    "doi": w.get("doi", ""), "venue": w.get("journalTitle") or "",
                    "cites": w.get("citedByCount", 0), "oa_url": "",
                    "source_api": "europepmc"})
    return out


FETCHERS = {"openalex": from_openalex, "crossref": from_crossref,
            "europepmc": from_europepmc}


def normalizar_ano(v):
    """Europe PMC devuelve `pubYear` como texto y las otras APIs como entero.

    Sin esto, ordenar por año revienta con `TypeError: bad operand type for
    unary -: 'str'` en cuanto se mezcla Europe PMC con OpenAlex o Crossref, que
    es justo lo que pasa al ampliar la búsqueda a imagen médica.
    """
    try:
        return int(str(v)[:4])
    except (TypeError, ValueError):
        return 0


def search_one(bucket: str, query: str, args, cache_dir: Path):
    key = hashlib.sha1(f"{bucket}|{query}|{args.year_from}".encode()).hexdigest()[:16]
    cf = cache_dir / f"{key}.json"
    if cf.exists() and not args.no_cache:
        rows = json.loads(cf.read_text(encoding="utf-8"))
    else:
        rows = []
        for name in args.apis:
            rows += FETCHERS[name](query, args.per_api, args.year_from) or []
        cf.write_text(json.dumps(rows), encoding="utf-8")
    qtok = tokens(query)
    for r in rows:
        r["bucket"], r["query"] = bucket, query
        r["year"] = normalizar_ano(r.get("year"))
        # Relevancia por solapamiento lexico, NO por citas.
        r["relevance"] = round(len(tokens(r["title"]) & qtok) / max(len(qtok), 1), 3)
        r["is_preprint"] = (r.get("venue") or "").strip().lower() in PREPRINT_VENUES
        r["is_survey"] = bool(SURVEY_RX.search(r.get("title") or ""))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--topics", type=Path,
                    help="TSV con columnas bucket y query, una consulta por fila")
    ap.add_argument("--query", action="append", help="consulta suelta; repetible")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--apis", nargs="+", default=["openalex", "crossref"],
                    choices=sorted(FETCHERS))
    ap.add_argument("--per-api", type=int, default=15)
    ap.add_argument("--year-from", type=int, default=2018)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--min-relevance", type=float, default=0.2)
    ap.add_argument("--allow-surveys", action="store_true")
    ap.add_argument("--include-preprints", action="store_true")
    ap.add_argument("--cache-dir", type=Path, default=Path(".lit-cache"))
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()

    tasks = []
    if args.topics:
        for r in csv.DictReader(open(args.topics, encoding="utf-8"), delimiter="\t"):
            tasks.append((r.get("bucket", "sin-bucket"), r["query"]))
    for q in (args.query or []):
        tasks.append(("cli", q))
    if not tasks:
        raise SystemExit("hacen falta --topics o --query")

    args.cache_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(search_one, b, q, args, args.cache_dir): q for b, q in tasks}
        for i, f in enumerate(as_completed(futs), 1):
            try:
                rows += f.result()
            except Exception as e:
                print(f"# FALLO consulta: {e}", file=sys.stderr)
            print(f"# {i}/{len(tasks)} consultas", file=sys.stderr)

    # Filtros de calidad, y se informa de cuanto descarta cada uno.
    stats = defaultdict(int)
    keep = []
    for r in rows:
        if not r.get("doi"):
            stats["sin DOI"] += 1; continue
        if not (r.get("venue") or "").strip():
            stats["sin publicacion"] += 1; continue
        if r["is_survey"] and not args.allow_surveys:
            stats["encuesta generica"] += 1; continue
        if r["is_preprint"] and not args.include_preprints:
            stats["preprint"] += 1; continue
        if r["relevance"] < args.min_relevance:
            stats["poco relevante"] += 1; continue
        keep.append(r)

    seen, uniq = set(), []
    for r in sorted(keep, key=lambda x: (-x["relevance"], -(x["year"] or 0))):
        d = r["doi"].lower()
        if d in seen:
            continue
        seen.add(d)
        uniq.append(r)

    cols = ["bucket", "relevance", "year", "cites", "venue", "title", "doi",
            "oa_url", "source_api", "query"]
    fh = open(args.out, "w", newline="", encoding="utf-8") if args.out else sys.stdout
    w = csv.DictWriter(fh, fieldnames=cols, delimiter="\t", extrasaction="ignore")
    w.writeheader()
    for r in uniq:
        w.writerow(r)
    if args.out:
        fh.close()

    print(f"# {len(rows)} brutos -> {len(uniq)} unicos tras filtros", file=sys.stderr)
    for k, v in sorted(stats.items(), key=lambda x: -x[1]):
        print(f"#   descartados por {k}: {v}", file=sys.stderr)
    print("# ordenado por RELEVANCIA lexica, nunca por citas", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
