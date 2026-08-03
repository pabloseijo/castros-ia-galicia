#!/usr/bin/env python3
"""Archaeology-only literature bank: castro culture and the Atlantic Iron Age.

The existing banks are about *method* — detection, relief models, validation.
This one is about the object itself: what a castro is, how big, what shape,
how it sits in the landscape, how it was built and when. A detector that does
not encode that is guessing at rings.

Deliberately multilingual. OpenAlex and Crossref index Galician, Spanish and
Portuguese archaeology journals poorly, and those are exactly the venues where
castro scholarship lives, so every theme is queried in English and in Iberian
languages, and OpenAIRE/Zenodo/DOAJ are included to reach repository copies.

Concurrent with a per-host semaphore, jittered backoff, one log per worker and
progress on stdout.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import re
import threading
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = PROJECT_ROOT / "data/literature-bank-archaeology"
LOG_DIR = OUT_DIR / "worker-logs"
REPORT = PROJECT_ROOT / "reports/literature_bank_archaeology.md"
UA = "castros-ia-galicia/0.1 (archaeology literature survey; academic use)"

QUERIES: dict[str, list[str]] = {
    "castro_definition_chronology": [
        "castro culture chronology Iron Age northwest Iberia",
        "cultura castrexa cronoloxia Idade do Ferro Galicia",
        "cultura castreña cronología Edad del Hierro noroeste peninsular",
        "cultura castreja cronologia Idade do Ferro noroeste Portugal",
        "Bronze Age to Iron Age transition northwest Iberia settlement",
    ],
    "castro_architecture": [
        "castro domestic architecture roundhouse Iron Age Galicia",
        "arquitectura castrexa vivenda circular saba",
        "arquitectura castreña casa circular poblado fortificado",
        "castro rampart ditch defensive system construction",
        "muralla foso parapeto castro sistema defensivo construccion",
        "estruturas domesticas castrexas planta circular",
    ],
    "castro_morphometry_landscape": [
        "hillfort size area enclosure statistics northwest Iberia",
        "castro emplazamiento topografico altitud dominio visual",
        "castro settlement pattern territoriality catchment Galicia",
        "hillfort landscape location analysis Atlantic Iberia",
        "xacemento castrexo emprazamento paisaxe visibilidade",
        "castro tamaño superficie recinto hectareas",
    ],
    "castro_excavation_case_studies": [
        "Castro de Viladonga excavation Lugo",
        "Santa Trega Baroña Elviña castro escavacion",
        "San Cibrao de Las Citania Briteiros Sanfins excavation",
        "castro excavacion memoria campaña arqueologica Galicia",
        "povoado fortificado escavacao Minho citania",
    ],
    "castro_romanisation_abandonment": [
        "romanisation castro settlement continuity abandonment Gallaecia",
        "romanizacion castros continuidad abandono Gallaecia",
        "castro cultura material romana ceramica importacion",
        "late Iron Age Roman conquest northwest Iberia settlement change",
    ],
    "gallaeci_celtic_atlantic": [
        "Gallaeci Astures Callaeci ethnonym Iron Age sources",
        "Atlantic Celtic Iberia archaeology identity",
        "celtas Galicia Gallaecia poboadores Idade do Ferro",
        "Celtic west Atlantic facade Iron Age Europe archaeology",
        "epigrafia castrexa deuses indixenas Gallaecia",
    ],
    "castro_material_culture": [
        "castro metalwork gold torc Iron Age Galicia",
        "ourivesaria castrexa torques arracadas",
        "ceramica castrexa tipologia produccion",
        "castro subsistence agriculture palaeobotany Iron Age Iberia",
    ],
    "catalogue_heritage": [
        "inventario patrimonio arqueoloxico Galicia catalogo xacementos",
        "carta arqueologica catalogo castros provincia",
        "heritage inventory completeness archaeological survey bias",
        "archaeological site discovery bias survey coverage",
    ],
}

SOURCES = ("openalex", "crossref", "openaire", "semanticscholar", "doaj", "zenodo")

_sems = defaultdict(lambda: threading.Semaphore(2))
_lock = threading.Lock()
_done = 0


def _get(url: str, host: str, attempts: int = 4, timeout: int = 45) -> bytes | None:
    last = None
    for i in range(1, attempts + 1):
        try:
            with _sems[host]:
                req = urllib.request.Request(url, headers={
                    "User-Agent": UA, "Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    return r.read()
        except Exception as exc:
            last = exc
            if i == attempts:
                return None
            time.sleep(3.0 * (2 ** (i - 1)) + random.uniform(0, 2))
    return None


def _clean(t: str | None) -> str:
    if not t:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", str(t))).strip()


def _inv_abstract(inv) -> str:
    if not isinstance(inv, dict):
        return ""
    pos = {}
    for word, idxs in inv.items():
        for i in idxs:
            pos[i] = word
    return " ".join(pos[k] for k in sorted(pos))


def q_openalex(q):
    u = ("https://api.openalex.org/works?per-page=50&sort=relevance_score:desc"
         f"&search={urllib.parse.quote(q)}&mailto=kelterastudio@gmail.com")
    raw = _get(u, "openalex")
    if not raw:
        return []
    out = []
    for w in (json.loads(raw).get("results") or []):
        loc = (w.get("primary_location") or {}).get("source") or {}
        out.append({
            "source": "openalex", "title": _clean(w.get("title")),
            "year": w.get("publication_year") or "", "venue": _clean(loc.get("display_name")),
            "cited_by": w.get("cited_by_count") or 0,
            "is_oa": "yes" if (w.get("open_access") or {}).get("is_oa") else "no",
            "doi": (w.get("doi") or "").replace("https://doi.org/", ""),
            "pdf_url": ((w.get("best_oa_location") or {}) or {}).get("pdf_url") or "",
            "language": w.get("language") or "",
            "abstract": _clean(_inv_abstract(w.get("abstract_inverted_index"))),
        })
    return out


def q_crossref(q):
    u = f"https://api.crossref.org/works?rows=50&query={urllib.parse.quote(q)}&mailto=kelterastudio@gmail.com"
    raw = _get(u, "crossref")
    if not raw:
        return []
    out = []
    for w in (json.loads(raw).get("message", {}).get("items") or []):
        out.append({
            "source": "crossref", "title": _clean((w.get("title") or [""])[0]),
            "year": (w.get("issued", {}).get("date-parts") or [[""]])[0][0] or "",
            "venue": _clean((w.get("container-title") or [""])[0]),
            "cited_by": w.get("is-referenced-by-count") or 0, "is_oa": "",
            "doi": w.get("DOI") or "", "pdf_url": "", "language": w.get("language") or "",
            "abstract": _clean(w.get("abstract")),
        })
    return out


def q_openaire(q):
    u = ("https://api.openaire.eu/search/publications?format=json&size=50"
         f"&keywords={urllib.parse.quote(q)}")
    raw = _get(u, "openaire")
    if not raw:
        return []
    try:
        res = json.loads(raw)["response"]["results"]["result"]
    except Exception:
        return []
    if isinstance(res, dict):
        res = [res]
    out = []
    for r in res:
        try:
            md = r["metadata"]["oaf:entity"]["oaf:result"]
        except Exception:
            continue
        t = md.get("title")
        if isinstance(t, list):
            t = t[0]
        t = t.get("$", "") if isinstance(t, dict) else t
        d = md.get("description")
        if isinstance(d, list):
            d = d[0]
        d = d.get("$", "") if isinstance(d, dict) else d
        out.append({
            "source": "openaire", "title": _clean(t),
            "year": _clean((md.get("dateofacceptance") or {}).get("$", ""))[:4],
            "venue": "", "cited_by": 0, "is_oa": "", "doi": "", "pdf_url": "",
            "language": "", "abstract": _clean(d),
        })
    return out


def q_semanticscholar(q):
    u = ("https://api.semanticscholar.org/graph/v1/paper/search?limit=50"
         f"&query={urllib.parse.quote(q)}"
         "&fields=title,abstract,year,venue,citationCount,isOpenAccess,externalIds,openAccessPdf")
    raw = _get(u, "semanticscholar")
    if not raw:
        return []
    out = []
    for w in (json.loads(raw).get("data") or []):
        out.append({
            "source": "semanticscholar", "title": _clean(w.get("title")),
            "year": w.get("year") or "", "venue": _clean(w.get("venue")),
            "cited_by": w.get("citationCount") or 0,
            "is_oa": "yes" if w.get("isOpenAccess") else "no",
            "doi": (w.get("externalIds") or {}).get("DOI") or "",
            "pdf_url": (w.get("openAccessPdf") or {}).get("url") or "",
            "language": "", "abstract": _clean(w.get("abstract")),
        })
    return out


def q_doaj(q):
    u = f"https://doaj.org/api/search/articles/{urllib.parse.quote(q)}?pageSize=50"
    raw = _get(u, "doaj")
    if not raw:
        return []
    out = []
    for w in (json.loads(raw).get("results") or []):
        b = w.get("bibjson") or {}
        out.append({
            "source": "doaj", "title": _clean(b.get("title")), "year": b.get("year") or "",
            "venue": _clean((b.get("journal") or {}).get("title")), "cited_by": 0,
            "is_oa": "yes",
            "doi": next((i.get("id") for i in (b.get("identifier") or [])
                         if i.get("type") == "doi"), ""),
            "pdf_url": next((l.get("url") for l in (b.get("link") or [])
                             if l.get("type") == "fulltext"), ""),
            "language": ",".join(b.get("language") or []),
            "abstract": _clean(b.get("abstract")),
        })
    return out


def q_zenodo(q):
    u = (f"https://zenodo.org/api/records?size=50&q={urllib.parse.quote(q)}"
         "&type=publication")
    raw = _get(u, "zenodo")
    if not raw:
        return []
    out = []
    for w in (json.loads(raw).get("hits", {}).get("hits") or []):
        m = w.get("metadata") or {}
        out.append({
            "source": "zenodo", "title": _clean(m.get("title")),
            "year": _clean(m.get("publication_date"))[:4], "venue": "Zenodo",
            "cited_by": 0, "is_oa": "yes", "doi": m.get("doi") or "",
            "pdf_url": (w.get("links") or {}).get("self_html") or "",
            "language": m.get("language") or "", "abstract": _clean(m.get("description")),
        })
    return out


FETCH = {"openalex": q_openalex, "crossref": q_crossref, "openaire": q_openaire,
         "semanticscholar": q_semanticscholar, "doaj": q_doaj, "zenodo": q_zenodo}

# Relevance gate: must look archaeological AND be about the right object/region.
ARCH = re.compile(
    r"castro|castre|hillfort|hill-fort|povoado fortificad|poblado fortificad|"
    r"citania|cividade|iron age|idade do ferro|edad del hierro|gallaec|callaec|"
    r"galaic|astur|celt|tumul|mamoa|megalit|arqueolog|archaeolog|protohistor", re.I)
NOISE = re.compile(
    r"castrol|fidel castro|castro valley|castro street|\bcastro, [A-Z]|"
    r"raul castro|castro theatre", re.I)


def relevant(rec) -> bool:
    blob = f"{rec.get('title','')} {rec.get('abstract','')}"
    if not blob.strip() or len(rec.get("title", "")) < 8:
        return False
    if NOISE.search(blob):
        return False
    return bool(ARCH.search(blob))


def job(theme, query, source, total):
    global _done
    log = LOG_DIR / f"worker_{threading.current_thread().name}.log"
    recs = []
    try:
        recs = FETCH[source](query) or []
        for r in recs:
            r["theme"], r["query"] = theme, query
    except Exception as exc:
        with open(log, "a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%H:%M:%S')} FAIL {source} '{query[:40]}': {exc}\n")
    else:
        with open(log, "a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%H:%M:%S')} ok {source} '{query[:40]}' -> {len(recs)}\n")
    with _lock:
        _done += 1
        if _done % 15 == 0 or _done == total:
            print(f"  progress {_done}/{total}", flush=True)
    return recs


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--sources", default=",".join(SOURCES))
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    srcs = [s for s in args.sources.split(",") if s in FETCH]

    tasks = [(t, q, s) for t, qs in QUERIES.items() for q in qs for s in srcs]
    total = len(tasks)
    print(f"themes {len(QUERIES)} | queries {sum(len(v) for v in QUERIES.values())} "
          f"| sources {len(srcs)} | tasks {total} | workers {args.workers}", flush=True)

    raw = []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(job, t, q, s, total) for t, q, s in tasks]
        for f in as_completed(futs):
            raw.extend(f.result())

    kept, dropped, seen = [], 0, set()
    for r in raw:
        if not relevant(r):
            dropped += 1
            continue
        key = (r.get("doi") or "").lower() or re.sub(r"\W+", "", r.get("title", "").lower())[:90]
        if not key or key in seen:
            continue
        seen.add(key)
        kept.append(r)

    fields = ["theme", "query", "source", "title", "year", "venue", "cited_by",
              "is_oa", "doi", "pdf_url", "language", "abstract"]

    def dump(path, rows):
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, delimiter="\t", fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow(r)

    dump(OUT_DIR / "literature_all.tsv", kept)
    by_theme = defaultdict(list)
    for r in kept:
        by_theme[r["theme"]].append(r)
    for t, rows in by_theme.items():
        dump(OUT_DIR / f"literature_{t}.tsv", rows)

    lines = ["# Archaeology literature bank: castros and the Atlantic Iron Age", "",
             f"Unique relevant records: `{len(kept)}` (dropped `{dropped}` as off-topic "
             f"from `{len(raw)}` raw hits).", "",
             "| theme | records |", "|---|---:|"]
    for t, rows in sorted(by_theme.items(), key=lambda x: -len(x[1])):
        lines.append(f"| `{t}` | `{len(rows)}` |")
    lines += ["", "| source | records |", "|---|---:|"]
    for s, n in Counter(r["source"] for r in kept).most_common():
        lines.append(f"| `{s}` | `{n}` |")
    lines += ["", "| language reported | records |", "|---|---:|"]
    for l, n in Counter((r.get("language") or "?")[:12] for r in kept).most_common(8):
        lines.append(f"| `{l}` | `{n}` |")
    lines += ["", "## Most cited", "", "| cited | year | title | venue |", "|---:|---:|---|---|"]
    for r in sorted(kept, key=lambda r: -int(r.get("cited_by") or 0))[:25]:
        ti = r["title"][:95].replace("|", "/")
        lines.append(f"| {r.get('cited_by')} | {r.get('year')} | {ti} | {r.get('venue','')[:40]} |")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"\ndone in {(time.time()-t0)/60:.1f} min | kept {len(kept)} unique "
          f"| dropped {dropped} | out {OUT_DIR}", flush=True)
    for s, n in Counter(r["source"] for r in kept).most_common():
        print(f"   {s}: {n}", flush=True)


if __name__ == "__main__":
    main()
