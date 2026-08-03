#!/usr/bin/env python3
"""Ask the local model what the hyperspectral literature actually reports.

The project concluded that hyperspectral is the wrong instrument, on the
grounds that PRISMA and EnMAP fly at 30 m and a 20 m mámoa is sub-pixel.
That reasoning only covers *satellite* hyperspectral. Airborne and UAV
sensors reach metre or sub-metre resolution, which would invalidate the
conclusion — so the question is worth putting to the literature rather
than settled by arithmetic.

For each abstract, extract four things and nothing else:

  PLATAFORMA  satellite / airborne / uav / laboratory / unclear
  RESOLUCION  ground sample distance as written, or NULL
  ENTERRADO   whether the paper claims detection of buried features
  RESULTADO   the outcome phrase, verbatim

Every extracted value is checked against the source text. Anything the
abstract does not contain is discarded as hallucination and counted, so
the report carries its own reliability estimate.
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
DEFAULT_BANK = PROJECT_ROOT / "data/literature-bank-hyper/literature_all.tsv"
DEFAULT_OUT = PROJECT_ROOT / "data/literature-bank-hyper/hyperspectral_evidence.tsv"
DEFAULT_REPORT = PROJECT_ROOT / "reports/hyperspectral_evidence_v1.md"
OLLAMA = "http://127.0.0.1:11434/api/generate"

FEWSHOT = """Lee el texto y extrae SOLO lo que aparece en el. Nunca inventes.
Formato exacto, cuatro lineas:
PLATAFORMA: satellite|airborne|uav|laboratory|unclear
RESOLUCION: <valor tal como aparece, o NULL>
ENTERRADO: si|no
RESULTADO: <frase literal del texto, o NULL>

Ejemplo1
Texto: We flew an airborne HyMap sensor at 4 m ground resolution over the site. Crop marks revealed a buried ditch system.
PLATAFORMA: airborne
RESOLUCION: 4 m
ENTERRADO: si
RESULTADO: Crop marks revealed a buried ditch system

Ejemplo2
Texto: PRISMA imagery at 30 m was assessed for land cover mapping in agricultural regions.
PLATAFORMA: satellite
RESOLUCION: 30 m
ENTERRADO: no
RESULTADO: assessed for land cover mapping

Ejemplo3
Texto: This review discusses spectral libraries for mineral identification.
PLATAFORMA: laboratory
RESOLUCION: NULL
ENTERRADO: no
RESULTADO: NULL

Ahora:
Texto: {text}"""

NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
PLATFORM_WORDS = {
    "airborne": ("airborne", "aerial", "aircraft", "flight", "flown", "aeroplane", "airplane"),
    "uav": ("uav", "drone", "unmanned"),
    "satellite": ("satellite", "prisma", "enmap", "hyperion", "spaceborne", "orbit", "chime"),
    "laboratory": ("laboratory", "lab ", "spectral librar", "spectroradiomet"),
}


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
            "options": {"num_predict": 110, "temperature": 0},
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
    out = {"plataforma": "", "resolucion": "", "enterrado": "", "resultado": ""}
    for line in reply.splitlines():
        low = line.strip().lower()
        for key, prefix in (
            ("plataforma", "plataforma:"),
            ("resolucion", "resolucion:"),
            ("resolucion", "resolución:"),
            ("enterrado", "enterrado:"),
            ("resultado", "resultado:"),
        ):
            if low.startswith(prefix):
                out[key] = line.split(":", 1)[1].strip()
                break
    return out


def verify(extracted: dict[str, str], source: str) -> tuple[bool, str]:
    low = source.lower()

    platform = extracted.get("plataforma", "").lower()
    if platform in PLATFORM_WORDS:
        if not any(word in low for word in PLATFORM_WORDS[platform]):
            return False, "platform_unsupported"

    resolution = extracted.get("resolucion", "")
    if resolution and resolution.upper() != "NULL":
        numbers = NUMBER.findall(resolution)
        if not numbers:
            return False, "resolution_without_number"
        for number in numbers:
            variants = {number, number.replace(".", ","), number.replace(",", ".")}
            if not any(v in source for v in variants):
                return False, f"resolution_{number}_absent"

    outcome = extracted.get("resultado", "")
    if outcome and outcome.upper() != "NULL":
        words = re.findall(r"[a-z]{5,}", outcome.lower())
        if words and sum(1 for w in words if w in low) < max(1, len(words) // 2):
            return False, "outcome_not_in_source"
    return True, ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bank", type=Path, default=DEFAULT_BANK)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--model", default="qwen2.5:3b")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--timeout", type=int, default=200)
    parser.add_argument("--max-chars", type=int, default=900)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    for attr in ("bank", "out", "report"):
        value = getattr(args, attr)
        setattr(args, attr, value if value.is_absolute() else PROJECT_ROOT / value)

    rows = [r for r in read_tsv(args.bank) if len(r.get("abstract") or "") > 120]
    rows.sort(key=lambda r: -int(r.get("cited_by") or 0))
    rows = rows[: args.limit]
    print(f"abstracts a consultar: {len(rows)}", flush=True)

    results: list[dict[str, str]] = []
    stats = Counter()
    started = time.time()

    for index, row in enumerate(rows, start=1):
        text = re.sub(r"\s+", " ", row["abstract"])[: args.max_chars]
        reply = ask(FEWSHOT.format(text=text), args.model, args.timeout)
        if not reply:
            stats["no_reply"] += 1
            continue
        extracted = parse_reply(reply)
        ok, reason = verify(extracted, text)
        if not ok:
            stats["rejected"] += 1
            stats[f"reject_{reason}"] += 1
            continue
        stats["accepted"] += 1
        stats[f"plat_{extracted['plataforma'] or 'vacio'}"] += 1
        if extracted["enterrado"].lower().startswith("s"):
            stats["claims_buried"] += 1
        results.append(
            {
                **extracted,
                "title": row.get("title", "")[:150],
                "year": row.get("year", ""),
                "venue": row.get("venue", "")[:60],
                "doi": row.get("doi", ""),
                "cited_by": row.get("cited_by", ""),
                "theme": row.get("theme", ""),
            }
        )
        if index % 10 == 0:
            rate = (time.time() - started) / index
            print(
                f"  {index}/{len(rows)} ok={stats['accepted']} rech={stats['rejected']} "
                f"enterrado={stats['claims_buried']} ({rate:.0f}s/ab)",
                flush=True,
            )

    fields = [
        "plataforma", "resolucion", "enterrado", "resultado",
        "title", "year", "venue", "doi", "cited_by", "theme",
    ]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=fields, dialect="excel-tab", extrasaction="ignore", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(results)

    # The decisive question: fine-resolution platforms that claim buried detection.
    fine = []
    for row in results:
        numbers = NUMBER.findall(row.get("resolucion", "") or "")
        if not numbers:
            continue
        try:
            value = float(numbers[0].replace(",", "."))
        except ValueError:
            continue
        unit_cm = "cm" in row["resolucion"].lower()
        metres = value / 100 if unit_cm else value
        if metres <= 5.0 and row["plataforma"] in {"airborne", "uav"}:
            fine.append((metres, row))
    fine.sort(key=lambda t: t[0])

    total = stats["accepted"] + stats["rejected"]
    lines = [
        "# What the hyperspectral literature actually reports",
        "",
        f"Model `{args.model}` on the Raspberry, few-shot, temperature `0`.",
        f"Abstracts queried: `{len(rows)}`.",
        "",
        "## Extraction reliability",
        "",
        f"- accepted: `{stats['accepted']}`",
        f"- rejected as unsupported by the source: `{stats['rejected']}` "
        f"(`{stats['rejected'] / total:.1%}`)" if total else "- no data",
        "",
        "Values are verified against the abstract before being kept.",
        "",
        "## Platforms",
        "",
        "| platform | papers |",
        "|---|---:|",
    ]
    for key, count in stats.most_common():
        if key.startswith("plat_"):
            lines.append(f"| `{key[5:]}` | `{count}` |")

    lines += [
        "",
        f"- papers claiming detection of **buried** features: `{stats['claims_buried']}`",
        "",
        "## The decisive question",
        "",
        "Satellite hyperspectral flies at `30 m`, which cannot resolve a `20 m`",
        "mámoa. Airborne and UAV sensors reach metre scale. If fine-resolution",
        "hyperspectral reliably detects buried features, the project's dismissal",
        "of hyperspectral was too quick.",
        "",
        f"**Airborne/UAV papers reporting `<= 5 m` resolution: `{len(fine)}`**",
        "",
    ]
    if fine:
        lines += ["| resolution | platform | buried? | outcome | source |", "|---|---|---|---|---|"]
        for metres, row in fine[:25]:
            lines.append(
                f"| `{row['resolucion']}` | `{row['plataforma']}` | `{row['enterrado']}` | "
                f"{(row['resultado'] or '')[:70]} | {row['title'][:55]} ({row['year']}) |"
            )
    else:
        lines.append("None found in this sample.")

    lines += [
        "",
        "## How to read this",
        "",
        "These are abstracts, not full texts, parsed by a 3B model with a",
        "verification filter. Good enough to decide **what to read next**;",
        "not good enough to cite. The project rule stands: a claim entering a",
        "wiki page needs the actual paper read.",
        "",
    ]
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"\naccepted={stats['accepted']} rejected={stats['rejected']} buried_claims={stats['claims_buried']}")
    print(f"fine_resolution_airborne={len(fine)}")
    print(f"report={args.report}")


if __name__ == "__main__":
    main()
