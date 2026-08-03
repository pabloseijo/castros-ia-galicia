#!/usr/bin/env python3
"""Literature aimed at the nine measured bottlenecks of the castro detector.

Not a general survey. Each theme maps to one bottleneck quantified on this
project's own data, so the bank can be read as "what does the field do about
*our* problem" instead of "what is published about archaeology and CNNs".

The ordering follows severity as measured:

  1. base_rate            1 castro per 474 cells forces precision ~0.25
  2. measurement          68 positives give a +-0.21 CI on recall
  3. prior_shift          trained at 25:1, deployed at 474:1
  4. review_budget        Galicia's top 1% is 241 h of expert time
  5. spatial_validation   52 blocks, median 1 positive each
  6. spatial_leakage      12 of 68 positives sit within 512 m of another
  7. weak_supervision     no masks, so segmentation is blocked
  8. label_noise          the toponymic filter still leaks ~16%
  9. data_efficiency      few labels, no domain-pretrained weights available

Reuses the fetchers of scrape_archaeology_bank.py; only the queries and the
relevance gate differ, because here the subject is method, not castros.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import scrape_archaeology_bank as base  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = PROJECT_ROOT / "data/literature-bank-bottlenecks-v2"
REPORT = PROJECT_ROOT / "reports/literature_bank_bottlenecks_v2.md"

QUERIES: dict[str, list[str]] = {
    "1_base_rate": [
        # El angulo util no es "class imbalance" en abstracto sino REDUCIR EL
        # ESPACIO DE BUSQUEDA antes del modelo fino. Los campos maduros en esto
        # son susceptibilidad de deslizamientos y distribucion de especies.
        "archaeological predictive model site location sensitivity map GIS",
        "landslide susceptibility mapping pseudo absence sampling rare events",
        "species distribution model background points prevalence sampling bias",
        "two stage cascade detector screening stage recall preservation",
        "coarse to fine detection pipeline candidate filtering aerial survey",
        "terrain masking exclusion criteria survey area reduction archaeology",
        "false positive reduction hard negative mining detection remote sensing",
        "prospectividad arqueologica modelo predictivo localizacion asentamientos",
    ],
    "2_measurement": [
        # No queremos teoria del bootstrap: queremos como se evalua un DETECTOR
        # con pocos positivos sin engañarse.
        "average precision variance uncertainty object detection evaluation",
        "reliability of benchmark rankings few test examples deep learning",
        "how many test samples needed reliable model comparison",
        "evaluation metrics rare class detection precision recall pitfalls",
        "repeated cross validation variance model comparison significance test",
        "confidence interval average precision detection benchmark",
        "sample size determination diagnostic accuracy sensitivity specificity",
    ],
}

# Method-oriented gate: the paper must be about learning/statistics/detection,
# not about castros. Archaeology terms are welcome but not required.
METHOD = re.compile(
    r"machine learning|deep learning|neural|classifier|classification|detection|"
    r"segmentation|calibration|cross[- ]validation|sampling|active learning|"
    r"label|annotation|imbalance|precision|recall|bayes|probabilit|estimat|"
    r"remote sensing|lidar|satellite|aerial|geospatial|spatial", re.I)
JUNK = re.compile(r"retracted|erratum|corrigendum", re.I)


def relevant(rec) -> bool:
    blob = f"{rec.get('title','')} {rec.get('abstract','')}"
    if len(rec.get("title", "")) < 12:
        return False
    if JUNK.search(blob):
        return False
    return bool(METHOD.search(blob))


_done = 0


def job(theme, query, source, total, lock):
    global _done
    recs = []
    try:
        recs = base.FETCH[source](query) or []
        for r in recs:
            r["theme"], r["query"] = theme, query
    except Exception:
        pass
    with lock:
        _done += 1
        if _done % 20 == 0 or _done == total:
            print(f"  progress {_done}/{total}", flush=True)
    return recs


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--sources", default="openalex,crossref,openaire")
    args = ap.parse_args()

    import threading
    lock = threading.Lock()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    srcs = [s for s in args.sources.split(",") if s in base.FETCH]

    tasks = [(t, q, s) for t, qs in QUERIES.items() for q in qs for s in srcs]
    total = len(tasks)
    print(f"temas {len(QUERIES)} | consultas {sum(len(v) for v in QUERIES.values())} "
          f"| fuentes {len(srcs)} | tareas {total} | workers {args.workers}", flush=True)

    raw = []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(job, t, q, s, total, lock) for t, q, s in tasks]
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
    by = defaultdict(list)
    for r in kept:
        by[r["theme"]].append(r)
    for t, rows in by.items():
        dump(OUT_DIR / f"literature_{t}.tsv", rows)

    withabs = [r for r in kept if len((r.get("abstract") or "").strip()) >= 120]
    lines = ["# Literatura por cuello de botella", "",
             f"`{len(kept)}` registros únicos relevantes de `{len(raw)}` brutos "
             f"(descartados `{dropped}`). Con abstract usable: `{len(withabs)}` "
             f"(`{100*len(withabs)/max(len(kept),1):.0f}%`). Con PDF abierto: "
             f"`{sum(1 for r in kept if r.get('pdf_url'))}`.", "",
             "Cada tema corresponde a un cuello medido sobre los datos del proyecto.",
             "", "| cuello | registros | con abstract |", "|---|---:|---:|"]
    for t, rows in sorted(by.items()):
        wa = sum(1 for r in rows if len((r.get("abstract") or "").strip()) >= 120)
        lines.append(f"| `{t}` | `{len(rows)}` | `{wa}` |")

    for t, rows in sorted(by.items()):
        lines += ["", f"## {t}", "", "| cit | año | título | revista |", "|---:|---:|---|---|"]
        for r in sorted(rows, key=lambda r: -int(r.get("cited_by") or 0))[:12]:
            ti = (r.get("title") or "")[:88].replace("|", "/")
            lines.append(f"| {r.get('cited_by')} | {r.get('year')} | {ti} | "
                         f"{(r.get('venue') or '')[:34]} |")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"\nlisto en {(time.time()-t0)/60:.1f} min | {len(kept)} únicos "
          f"| {len(withabs)} con abstract | salida {OUT_DIR}", flush=True)
    for t, rows in sorted(by.items()):
        print(f"   {t}: {len(rows)}", flush=True)


if __name__ == "__main__":
    main()
