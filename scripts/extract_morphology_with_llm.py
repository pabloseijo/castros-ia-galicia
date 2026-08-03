#!/usr/bin/env python3
"""Pull castro/mámoa morphology facts out of harvested abstracts, with Qwen.

The local model cannot be fine-tuned on a Pi — 3B weights, no GPU, 37 s per
short answer. What it can do is few-shot extraction at temperature 0 with a
rigid output format, which is a task it is actually good at: find the number
in this paragraph, not reason about archaeology.

Every extracted figure is verified against the source text before being
kept. If the model returns a measurement that does not appear in the
abstract, the row is dropped as a hallucination and counted. That check is
the difference between using an LLM as a parser and trusting it as an
authority.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
import urllib.request
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BANKS = [
    PROJECT_ROOT / "data/literature-bank-v1/literature_all.tsv",
    PROJECT_ROOT / "data/literature-bank-es/literature_all.tsv",
]
DEFAULT_OUT = PROJECT_ROOT / "data/literature-bank-v1/morphology_facts.tsv"
DEFAULT_REPORT = PROJECT_ROOT / "reports/morphology_facts_v1.md"
OLLAMA = "http://127.0.0.1:11434/api/generate"

FEWSHOT = """Extrae SOLO datos presentes en el texto. Nunca inventes cifras.
Formato exacto, tres lineas:
TIPO: castro|mamoa|otro
DIAMETRO: <cifra+unidad tal como aparece, o NULL>
RASGO: <palabras literales del texto, o NULL>

Ejemplo1
Texto: The mounds have diameters of more than 25 m, the largest bigger than 100 m.
TIPO: mamoa
DIAMETRO: 25-100 m
RASGO: mounds

Ejemplo2
Texto: A rampart-and-ditch enclosure of 65 x 75 m on a river terrace.
TIPO: castro
DIAMETRO: 65 x 75 m
RASGO: rampart-and-ditch enclosure

Ejemplo3
Texto: This paper reviews ceramic typologies of the Late Bronze Age.
TIPO: otro
DIAMETRO: NULL
RASGO: NULL

Ahora:
Texto: {text}"""

# Only abstracts that plausibly carry a measurement are worth 37 s of model time.
WORTH_ASKING = re.compile(
    r"(diameter|diametro|diámetro|height|altura|width|anchura|extension|extensión|"
    r"area|superficie|size|dimension|dimensión|ha\b|hectare|metre|meter|metros|\bm\b)",
    re.I,
)
SUBJECT = re.compile(
    r"(castro|hillfort|hill-fort|oppid|tumul|túmul|mound|mamoa|mámoa|medorra|megalith|barrow|kurgan|enclosure|recinto)",
    re.I,
)
NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def read_tsv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, dialect="excel-tab"))


def ask(prompt: str, model: str, timeout: int) -> str:
    payload = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": 80, "temperature": 0},
        }
    ).encode()
    request = urllib.request.Request(
        OLLAMA, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read()).get("response", "")
    except Exception:
        return ""


def parse_reply(reply: str) -> dict[str, str]:
    out = {"tipo": "", "diametro": "", "rasgo": ""}
    for line in reply.splitlines():
        low = line.strip().lower()
        if low.startswith("tipo:"):
            out["tipo"] = line.split(":", 1)[1].strip().lower()
        elif low.startswith("diametro:") or low.startswith("diámetro:"):
            out["diametro"] = line.split(":", 1)[1].strip()
        elif low.startswith("rasgo:"):
            out["rasgo"] = line.split(":", 1)[1].strip()
    return out


def verify(extracted: dict[str, str], source: str) -> tuple[bool, str]:
    """Reject anything the source text does not actually contain."""
    value = extracted.get("diametro", "")
    if value and value.upper() != "NULL":
        numbers = NUMBER.findall(value)
        if not numbers:
            return False, "diameter_without_number"
        for number in numbers:
            # Accept either separator, since the model may normalise them.
            variants = {number, number.replace(".", ","), number.replace(",", ".")}
            if not any(v in source for v in variants):
                return False, f"number_{number}_not_in_source"
    feature = extracted.get("rasgo", "")
    if feature and feature.upper() != "NULL":
        words = [w for w in re.findall(r"[a-záéíóúñ]{5,}", feature.lower())]
        if words and not any(w in source.lower() for w in words):
            return False, "feature_not_in_source"
    return True, ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bank", type=Path, action="append", default=None)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--model", default="qwen2.5:3b")
    parser.add_argument("--limit", type=int, default=250)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--max-chars", type=int, default=900)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    banks = [b if b.is_absolute() else PROJECT_ROOT / b for b in (args.bank or DEFAULT_BANKS)]
    args.out = args.out if args.out.is_absolute() else PROJECT_ROOT / args.out
    args.report = args.report if args.report.is_absolute() else PROJECT_ROOT / args.report

    seen: set[str] = set()
    candidates: list[dict[str, str]] = []
    for bank in banks:
        for row in read_tsv(bank):
            abstract = (row.get("abstract") or "").strip()
            if len(abstract) < 120:
                continue
            if not (WORTH_ASKING.search(abstract) and SUBJECT.search(abstract)):
                continue
            key = (row.get("doi") or row.get("title", "")).lower()
            if key in seen:
                continue
            seen.add(key)
            candidates.append(row)

    candidates.sort(key=lambda r: -int(r.get("cited_by") or 0))
    candidates = candidates[: args.limit]
    print(f"abstracts que merecen consulta: {len(candidates)}", flush=True)

    results: list[dict[str, str]] = []
    stats = Counter()
    started = time.time()

    for index, row in enumerate(candidates, start=1):
        text = re.sub(r"\s+", " ", row["abstract"])[: args.max_chars]
        reply = ask(FEWSHOT.format(text=text), args.model, args.timeout)
        if not reply:
            stats["model_no_reply"] += 1
            continue
        extracted = parse_reply(reply)
        ok, reason = verify(extracted, text)
        stats[f"tipo_{extracted.get('tipo') or 'vacio'}"] += 1
        if not ok:
            stats["rejected_hallucination"] += 1
            stats[f"reject_{reason}"] += 1
        else:
            stats["accepted"] += 1
            if extracted["tipo"] in {"castro", "mamoa"} and extracted["diametro"].upper() != "NULL":
                results.append(
                    {
                        "tipo": extracted["tipo"],
                        "diametro": extracted["diametro"],
                        "rasgo": extracted["rasgo"],
                        "title": row.get("title", "")[:160],
                        "year": row.get("year", ""),
                        "venue": row.get("venue", "")[:70],
                        "doi": row.get("doi", ""),
                        "theme": row.get("theme", ""),
                        "source_span": text[:300],
                    }
                )
        if index % 10 == 0:
            rate = (time.time() - started) / index
            print(
                f"  {index}/{len(candidates)} aceptados={stats['accepted']} "
                f"rechazados={stats['rejected_hallucination']} utiles={len(results)} "
                f"({rate:.0f}s/abstract)",
                flush=True,
            )

    fields = ["tipo", "diametro", "rasgo", "title", "year", "venue", "doi", "theme", "source_span"]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=fields, dialect="excel-tab", extrasaction="ignore", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(results)

    castros = [r for r in results if r["tipo"] == "castro"]
    mounds = [r for r in results if r["tipo"] == "mamoa"]
    total_asked = stats["accepted"] + stats["rejected_hallucination"]
    hallucination_rate = stats["rejected_hallucination"] / total_asked if total_asked else 0.0

    lines = [
        "# Morphology facts extracted from the literature",
        "",
        f"Model: `{args.model}` on the Raspberry, few-shot, temperature `0`.",
        f"Abstracts queried: `{len(candidates)}`.",
        "",
        "## Reliability of the extraction",
        "",
        f"- accepted: `{stats['accepted']}`",
        f"- **rejected as hallucination: `{stats['rejected_hallucination']}` "
        f"(`{hallucination_rate:.1%}`)**",
        f"- no reply from model: `{stats['model_no_reply']}`",
        "",
        "Every figure was checked against the source abstract. A measurement the",
        "text does not contain is discarded, not reported. That rejection rate is",
        "the honest measure of how far a 3B model can be trusted here.",
        "",
        "## Usable measurements",
        "",
        f"- castro: `{len(castros)}`",
        f"- mámoa/mound: `{len(mounds)}`",
        "",
        "| tipo | diámetro | rasgo | fuente |",
        "|---|---|---|---|",
    ]
    for row in (castros + mounds)[:40]:
        lines.append(
            f"| `{row['tipo']}` | `{row['diametro']}` | {row['rasgo'][:40]} | "
            f"{row['title'][:60]} ({row['year']}) |"
        )
    lines += [
        "",
        "## Caveat",
        "",
        "These are figures reported in abstracts about sites worldwide — kurgans,",
        "Irish passage graves, Siberian enclosures. They corroborate orders of",
        "magnitude; they are not Galician measurements. The project's own OSM",
        "polygon bank (`57 m` vs `10 m` median radius, measured on Galicia) remains",
        "the more specific evidence. This literature is for justifying and framing,",
        "not for discovering the criterion.",
        "",
    ]
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"\naccepted={stats['accepted']} hallucinations={stats['rejected_hallucination']} ({hallucination_rate:.1%})")
    print(f"castros={len(castros)} mounds={len(mounds)}")
    print(f"out={args.out}")
    print(f"report={args.report}")


if __name__ == "__main__":
    main()
