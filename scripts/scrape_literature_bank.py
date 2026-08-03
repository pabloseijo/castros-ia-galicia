#!/usr/bin/env python3
"""Concurrent literature harvest for the castro/mámoa problem.

Three questions drive this, and only one of them is computational:

  method      how others detect archaeology in remote sensing
  archaeology how prehistorians actually distinguish a hillfort from a
              burial mound — morphology, dimensions, siting, ditches
  spectral    whether multi/hyperspectral imagery adds anything, since
              the project has never used it

The archaeology axis matters most. Five modelling routes have failed to
separate castros from mámoas, and the reason may simply be that nobody
asked what the defining physical differences are. That answer lives in
the historiography, not in a CNN paper.

Harvests OpenAlex, Crossref and arXiv concurrently, one semaphore per
host so no service is hammered. Metadata and abstracts only: per the
project rule, deciding what enters a wiki page requires reading the
actual text, and this only produces candidates.
"""

from __future__ import annotations

import argparse
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT_DIR = PROJECT_ROOT / "data/literature-bank-v1"
DEFAULT_REPORT = PROJECT_ROOT / "reports/literature_bank_v1.md"
CONTACT = "castros-ia-galicia (research project)"

QUERIES: dict[str, list[str]] = {
    "archaeology_morphology": [
        "castro culture hillfort morphology northwest Iberia",
        "hillfort morphology Galicia Iron Age settlement",
        "Gallaecia castro settlement defensive earthwork rampart",
        "castros Noroeste peninsular morfologia poblado fortificado",
        "recinto castreno foso parapeto muralla dimensiones",
        "Iron Age hillfort size distribution enclosure area",
    ],
    "archaeology_mounds": [
        "megalithic tumulus Galicia morphology dimensions",
        "mamoa medorra tumulo megalitico noroeste peninsular",
        "burial mound diameter height Neolithic Iberia",
        "megalithic necropolis distribution Galicia landscape",
        "passage grave mound morphometry Atlantic Europe",
    ],
    "archaeology_discrimination": [
        "distinguishing burial mounds from hillforts remote sensing",
        "archaeological feature typology confusion tumulus enclosure",
        "morphometric classification archaeological earthworks",
    ],
    "method_detection": [
        "archaeological site detection deep learning LiDAR",
        "burial mound detection convolutional neural network",
        "hillfort automated detection remote sensing",
        "object detection archaeology aerial imagery deep learning",
        "semantic segmentation archaeological features LiDAR DTM",
    ],
    "method_relief": [
        "multi-scale relief model MSRM archaeological prospection",
        "local relief model visualisation LiDAR archaeology",
        "sky view factor openness archaeological topography",
    ],
    "method_validation": [
        "spatial cross validation autocorrelation remote sensing",
        "positive unlabeled learning archaeological prediction",
    ],
    "spectral": [
        "hyperspectral imagery archaeological crop marks",
        "multispectral Sentinel-2 archaeological prospection tumuli",
        "cropmark detection satellite multitemporal archaeology",
        "PRISMA EnMAP hyperspectral archaeology buried structures",
        "soil marks spectral signature buried archaeological remains",
    ],
}

RELEVANCE = re.compile(
    r"castro|hillfort|hill-fort|tumul|mound|mamoa|medorra|megalith|barrow|"
    r"archaeolog|arqueolog|lidar|remote sensing|prospection|earthwork",
    re.I,
)

_locks: dict[str, threading.Semaphore] = {}
_lock_guard = threading.Lock()


def host_semaphore(host: str, limit: int) -> threading.Semaphore:
    with _lock_guard:
        if host not in _locks:
            _locks[host] = threading.Semaphore(limit)
        return _locks[host]


def fetch_json(url: str, *, host_limit: int = 2, attempts: int = 4, timeout: int = 45):
    """GET with per-host throttling and backoff. Returns None on give-up."""
    host = urllib.parse.urlparse(url).netloc
    semaphore = host_semaphore(host, host_limit)
    delay = 2.0
    for attempt in range(attempts):
        with semaphore:
            try:
                request = urllib.request.Request(
                    url, headers={"User-Agent": CONTACT, "Accept": "application/json"}
                )
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    return json.loads(response.read().decode("utf-8", "replace"))
            except urllib.error.HTTPError as exc:
                if exc.code in (429, 500, 502, 503, 504):
                    time.sleep(delay)
                    delay *= 2
                    continue
                return None
            except Exception:
                time.sleep(delay)
                delay *= 2
    return None


def decode_abstract(inverted: dict | None) -> str:
    """OpenAlex ships abstracts as an inverted index."""
    if not inverted:
        return ""
    positions: list[tuple[int, str]] = []
    for word, spots in inverted.items():
        for spot in spots:
            positions.append((spot, word))
    positions.sort()
    return " ".join(word for _spot, word in positions)[:4000]


def search_openalex(query: str, per_query: int) -> list[dict]:
    url = (
        "https://api.openalex.org/works?"
        + urllib.parse.urlencode(
            {"search": query, "per-page": min(per_query, 200), "mailto": "research@example.org"}
        )
    )
    data = fetch_json(url, host_limit=3)
    if not data:
        return []
    out = []
    for work in data.get("results", []):
        oa = work.get("open_access") or {}
        out.append(
            {
                "source": "openalex",
                "id": work.get("id", ""),
                "doi": (work.get("doi") or "").replace("https://doi.org/", ""),
                "title": work.get("title") or "",
                "year": str(work.get("publication_year") or ""),
                "venue": ((work.get("primary_location") or {}).get("source") or {}).get("display_name", "") or "",
                "cited_by": str(work.get("cited_by_count") or 0),
                "is_oa": "yes" if oa.get("is_oa") else "no",
                "pdf_url": oa.get("oa_url") or "",
                "abstract": decode_abstract(work.get("abstract_inverted_index")),
                "language": work.get("language") or "",
            }
        )
    return out


def search_crossref(query: str, per_query: int) -> list[dict]:
    url = "https://api.crossref.org/works?" + urllib.parse.urlencode(
        {"query": query, "rows": min(per_query, 100), "mailto": "research@example.org"}
    )
    data = fetch_json(url, host_limit=2)
    if not data:
        return []
    out = []
    for item in (data.get("message") or {}).get("items", []):
        out.append(
            {
                "source": "crossref",
                "id": item.get("DOI", ""),
                "doi": item.get("DOI", ""),
                "title": " ".join(item.get("title") or []),
                "year": str((item.get("issued") or {}).get("date-parts", [[""]])[0][0] or ""),
                "venue": " ".join(item.get("container-title") or []),
                "cited_by": str(item.get("is-referenced-by-count") or 0),
                "is_oa": "",
                "pdf_url": "",
                "abstract": re.sub(r"<[^>]+>", " ", item.get("abstract") or "")[:4000],
                "language": item.get("language") or "",
            }
        )
    return out


def search_arxiv(query: str, per_query: int) -> list[dict]:
    url = "http://export.arxiv.org/api/query?" + urllib.parse.urlencode(
        {"search_query": f"all:{query}", "max_results": min(per_query, 50)}
    )
    host = "export.arxiv.org"
    semaphore = host_semaphore(host, 1)  # arXiv asks for gentle serial access
    with semaphore:
        try:
            request = urllib.request.Request(url, headers={"User-Agent": CONTACT})
            with urllib.request.urlopen(request, timeout=45) as response:
                text = response.read().decode("utf-8", "replace")
        except Exception:
            return []
        time.sleep(3.0)
    out = []
    for entry in re.findall(r"<entry>(.*?)</entry>", text, re.S):
        def tag(name: str) -> str:
            match = re.search(rf"<{name}[^>]*>(.*?)</{name}>", entry, re.S)
            return re.sub(r"\s+", " ", match.group(1)).strip() if match else ""
        link = re.search(r'<link[^>]*title="pdf"[^>]*href="([^"]+)"', entry)
        out.append(
            {
                "source": "arxiv",
                "id": tag("id"),
                "doi": "",
                "title": tag("title"),
                "year": tag("published")[:4],
                "venue": "arXiv",
                "cited_by": "0",
                "is_oa": "yes",
                "pdf_url": link.group(1) if link else "",
                "abstract": tag("summary")[:4000],
                "language": "en",
            }
        )
    return out


def job(theme: str, query: str, engine: str, per_query: int) -> tuple[str, str, str, list[dict]]:
    fn = {"openalex": search_openalex, "crossref": search_crossref, "arxiv": search_arxiv}[engine]
    try:
        return theme, query, engine, fn(query, per_query)
    except Exception:
        return theme, query, engine, []


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--per-query", type=int, default=100)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--engines", default="openalex,crossref,arxiv")
    parser.add_argument("--themes", default="")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.out_dir = args.out_dir if args.out_dir.is_absolute() else PROJECT_ROOT / args.out_dir
    args.report = args.report if args.report.is_absolute() else PROJECT_ROOT / args.report
    args.out_dir.mkdir(parents=True, exist_ok=True)
    log_dir = args.out_dir / "worker-logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    engines = [e.strip() for e in args.engines.split(",") if e.strip()]
    themes = [t.strip() for t in args.themes.split(",") if t.strip()] or list(QUERIES)

    tasks = [
        (theme, query, engine)
        for theme in themes
        for query in QUERIES.get(theme, [])
        for engine in engines
    ]
    print(f"{len(tasks)} búsquedas en {len(themes)} temas, {args.workers} workers", flush=True)

    by_theme: dict[str, dict[str, dict]] = defaultdict(dict)
    stats = Counter()
    done = 0

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(job, t, q, e, args.per_query) for t, q, e in tasks]
        for future in as_completed(futures):
            theme, query, engine, results = future.result()
            done += 1
            kept = 0
            for record in results:
                blob = f"{record['title']} {record['abstract']}"
                if not RELEVANCE.search(blob):
                    stats["filtered_irrelevant"] += 1
                    continue
                key = (record.get("doi") or record.get("id") or record["title"]).lower().strip()
                if not key:
                    continue
                if key in by_theme[theme]:
                    stats["duplicate"] += 1
                    continue
                record["query"] = query
                record["theme"] = theme
                by_theme[theme][key] = record
                kept += 1
            stats[f"engine_{engine}"] += len(results)
            # One log line per worker task, so a failing query is findable.
            with (log_dir / f"{theme}.log").open("a", encoding="utf-8") as fh:
                fh.write(f"[{engine}] {query} -> {len(results)} raw, {kept} kept\n")
            print(f"  {done}/{len(tasks)} [{engine}] {theme}: +{kept}", flush=True)

    fields = [
        "theme", "query", "source", "title", "year", "venue", "cited_by",
        "is_oa", "doi", "pdf_url", "language", "abstract",
    ]
    import csv

    all_rows: list[dict] = []
    for theme, records in by_theme.items():
        rows = sorted(records.values(), key=lambda r: -int(r.get("cited_by") or 0))
        all_rows.extend(rows)
        path = args.out_dir / f"literature_{theme}.tsv"
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(
                fh, fieldnames=fields, dialect="excel-tab", extrasaction="ignore", lineterminator="\n"
            )
            writer.writeheader()
            writer.writerows(rows)

    master = args.out_dir / "literature_all.tsv"
    with master.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=fields, dialect="excel-tab", extrasaction="ignore", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(sorted(all_rows, key=lambda r: -int(r.get("cited_by") or 0)))

    lines = [
        "# Literature bank v1",
        "",
        f"Harvested `{len(all_rows)}` unique relevant records across `{len(by_theme)}` themes.",
        "",
        "| theme | records | open access | with abstract |",
        "|---|---:|---:|---:|",
    ]
    for theme in sorted(by_theme):
        rows = list(by_theme[theme].values())
        lines.append(
            f"| `{theme}` | `{len(rows)}` | "
            f"`{sum(1 for r in rows if r['is_oa'] == 'yes')}` | "
            f"`{sum(1 for r in rows if r['abstract'])}` |"
        )
    lines += [
        "",
        "## Most cited per theme",
        "",
    ]
    for theme in sorted(by_theme):
        rows = sorted(by_theme[theme].values(), key=lambda r: -int(r.get("cited_by") or 0))[:6]
        lines.append(f"### `{theme}`")
        lines.append("")
        for row in rows:
            lines.append(
                f"- **{row['title'][:120]}** ({row['year']}, {row['venue'][:50]}) — "
                f"cited `{row['cited_by']}`{', OA' if row['is_oa'] == 'yes' else ''}"
            )
        lines.append("")
    lines += [
        "## How to use this",
        "",
        "This is a **candidate list**, not a reading. The project rule is explicit:",
        "citing a paper requires having read its abstract or full text, not its",
        "bibliographic metadata. Titles and citation counts pick what to open;",
        "they do not justify what goes into a wiki page.",
        "",
    ]
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"\nunique={len(all_rows)} filtered={stats['filtered_irrelevant']} dupes={stats['duplicate']}")
    print(f"master={master}")
    print(f"report={args.report}")


if __name__ == "__main__":
    main()
