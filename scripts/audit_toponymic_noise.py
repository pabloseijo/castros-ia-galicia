#!/usr/bin/env python3
"""Audita el ruido toponímico entre los positivos (cuello 8).

El barrido denso midió que `17` de `108` positivos de Trasancos no eran castros:
`4` mámoas con «Castro» en el nombre y `13` elementos modernos («Edificio na rúa
Castro 10», «Pontella sobre o río Castro»). Un `16%` que contamina numerador y
denominador a la vez: infla el recall aparente y ensucia la precisión.

Este script lo cuantifica sobre el catálogo entero, con una regla que peca de
**conservadora a propósito**. El proyecto ya se quemó una vez marcando de más:
«Castro das Medorras» es un castro con ese topónimo, no una mámoa, y una regex
amplia lo habría excluido. Así que aquí se separan tres niveles:

  - `seguro_no_castro`: patrones que no admiten duda (calle, edificio, puente,
    río, iglesia + número, arboleda...). Se recomienda excluir.
  - `dudoso`: contiene un término sospechoso pero podría ser un castro con ese
    topónimo. Se marca para revisión humana, NO se excluye.
  - `limpio`: sin señal de ruido.

No modifica el catálogo. Escribe un informe y un TSV con la clasificación y el
motivo de cada marca, para que la decisión de exclusión la tome un humano por
lotes de fiabilidad, no una regex a ciegas.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter
from pathlib import Path

csv.field_size_limit(sys.maxsize)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
MASTER = PROJECT_ROOT / "data/weak-label-splits-v1/weak_label_master.tsv"

# Patrones que un castro real nunca tendría en el nombre. Anclados con límites
# de palabra y, donde importa, exigiendo que el término encabece o vaya con
# número, para no marcar «Castro de la Iglesia» (un castro) como iglesia.
SEGURO = [
    (r"\b(r[uú]a|calle|avenida|avda|travesía|estrada)\b", "vía urbana"),
    (r"\bedificio\b", "edificio"),
    (r"\b(n[º°]|nº|número)\s*\d+", "dirección con número"),
    (r"\b\d{1,3}\s*$", "termina en número (portal)"),
    (r"\b(pontella|ponte|puente)\b", "puente"),
    (r"\b(r[ií]o|regato|rego|arroyo)\b", "hidrónimo"),
    (r"\b(arboredo|arboreda|conxunto de|xardín|jardín|parque)\b", "vegetación/parque"),
    (r"\b(rosal[ií]a de castro|fidel castro)\b", "antropónimo Castro"),
    (r"\b(colexio|colegio|escola|escuela|instituto|ceip|ies)\b", "centro educativo"),
    (r"\b(capela|capilla|ermida|ermita)\b", "capilla"),
]
# Términos que sugieren otra tipología pero NO son concluyentes: se marcan
# dudosos porque pueden ser un topónimo heredado sobre un castro real.
DUDOSO_MEGALITICO = re.compile(
    r"\b(m[aá]moa|medorra|medoña|arca|dolmen|anta|t[uú]mulo)\b", re.I)
DUDOSO_RELIGIOSO = re.compile(
    r"\b(igrexa|iglesia|santo|santa|san |são |cruceiro|cruz)\b", re.I)


def classify(name: str):
    n = (name or "").strip().lower()
    if not n:
        return "limpio", ""
    for pat, why in SEGURO:
        if re.search(pat, n):
            return "seguro_no_castro", why
    # El término megalítico solo cuenta como dudoso si ENCABEZA el nombre;
    # «Castro das Medorras» empieza por Castro y es un castro.
    m = DUDOSO_MEGALITICO.search(n)
    if m and m.start() <= 2:
        return "dudoso", f"empieza por término megalítico ({m.group(0)})"
    if DUDOSO_RELIGIOSO.search(n) and not n.startswith(("castro", "croa", "cividade")):
        return "dudoso", "término religioso sin 'castro' delante"
    return "limpio", ""


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--master", type=Path, default=MASTER)
    ap.add_argument("--out", type=Path,
                    default=PROJECT_ROOT / "data/toponymic-audit-v1")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    rows = list(csv.DictReader(open(args.master, encoding="utf-8"), delimiter="\t"))
    pos = [r for r in rows if r.get("label_class") == "1"]
    print(f"positivos en el catálogo: {len(pos)}", flush=True)

    marked = []
    for r in pos:
        cls, why = classify(r.get("name", ""))
        if cls != "limpio":
            marked.append({"sample_id": r.get("sample_id"),
                           "name": r.get("name"), "municipality": r.get("municipality"),
                           "final_split": r.get("final_split"),
                           "verdict": cls, "reason": why})

    counts = Counter(m["verdict"] for m in marked)
    # De los ya excluidos, ¿cuántos captura la regla? (control de cordura)
    already_excl = {r.get("sample_id") for r in pos
                    if r.get("final_split") == "excluded_review"}
    caught_excl = sum(1 for m in marked if m["sample_id"] in already_excl)

    seguros = [m for m in marked if m["verdict"] == "seguro_no_castro"]
    seguros_entrenables = [m for m in seguros
                           if m["sample_id"] not in already_excl]

    with open(args.out / "toponymic_marks.tsv", "w", newline="",
              encoding="utf-8") as fh:
        w = csv.DictWriter(fh, delimiter="\t",
                           fieldnames=["sample_id", "name", "municipality",
                                       "final_split", "verdict", "reason"])
        w.writeheader()
        for m in sorted(marked, key=lambda x: (x["verdict"], x["name"] or "")):
            w.writerow(m)

    L = ["# Auditoría de ruido toponímico en los positivos", "",
         f"Sobre `{len(pos)}` positivos del catálogo. Regla **conservadora**: solo",
         "se recomienda excluir lo que no admite duda; lo ambiguo se marca para",
         "revisión, no se borra. «Castro das Medorras» es un castro, no una mámoa.",
         "", "| veredicto | n |", "|---|---:|"]
    for v, n in counts.most_common():
        L.append(f"| `{v}` | `{n}` |")
    L += ["",
          f"De los `{len(seguros)}` marcados como seguro-no-castro, `{caught_excl}` ya",
          f"estaban en `excluded_review`. Quedan **`{len(seguros_entrenables)}` que",
          "siguen entrenables** y deberían excluirse.", "",
          "## Muestra de seguros no-castro aún entrenables", "",
          "| nombre | concello | split | motivo |", "|---|---|---|---|"]
    for m in seguros_entrenables[:25]:
        L.append(f"| {(m['name'] or '')[:40]} | {(m['municipality'] or '')[:16]} | "
                 f"`{m['final_split']}` | {m['reason']} |")
    L += ["", "## Dudosos (revisar, no excluir)", "",
          "| nombre | concello | motivo |", "|---|---|---|"]
    for m in [x for x in marked if x["verdict"] == "dudoso"][:20]:
        L.append(f"| {(m['name'] or '')[:44]} | {(m['municipality'] or '')[:16]} | "
                 f"{m['reason']} |")
    (PROJECT_ROOT / "reports/toponymic_audit_v1.md").write_text(
        "\n".join(L) + "\n", encoding="utf-8")

    print(f"marcados: {dict(counts)}", flush=True)
    print(f"seguros ya excluidos: {caught_excl}/{len(seguros)}", flush=True)
    print(f"seguros AÚN entrenables (excluir): {len(seguros_entrenables)}", flush=True)
    print(f"informe: reports/toponymic_audit_v1.md", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
