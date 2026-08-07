#!/usr/bin/env python3
"""Junta el triaje de los cuatro bloques en una sola cola de revisión.

**Es el entregable del proyecto.** Decidido el `2026-08-07`: confirmar sobre el
terreno queda fuera de alcance, así que lo que se entrega es una **cola
priorizada y explicada**, y la medida de éxito no son castros confirmados sino
la calidad de esa cola — precisión en los primeros puestos y un motivo escrito
que aguante que un arqueólogo lo lea.

## Por qué no se ordena por la puntuación cruda

Porque no es comparable entre bloques. La calibración de la prominencia sale de
los castros conocidos **del propio bloque** —`10,8 m` en Ourense, `5,6 m` en
Lugo, `4,0 m` en A Coruña— así que el mismo candidato saca notas distintas según
dónde caiga. Ordenar los cuatro bloques juntos por esa cifra mezclaría cuatro
reglas distintas y pondría arriba a los del bloque más generoso.

Se ordena por **posición relativa dentro de su bloque** —el percentil de su
puntuación entre los candidatos de su propio bloque— y el número crudo se
conserva al lado. Así «el mejor de Ourense» y «el mejor de Lugo» compiten de
igual a igual, que es lo que una cola de revisión necesita.

## Lo que la cola dice y lo que no

Cada candidato lleva **por qué está donde está**, en palabras. Lo que no lleva
es un veredicto: ninguna de las comprobaciones automáticas confirma nada, solo
descartan barato y ordenan. Las columnas `veredicto`, `revisor` y `notas` van
vacías a propósito para que se rellenen al revisar, y ese resultado vuelva al
corpus (Bickler y colegas, `2023`, `10.1038/s41598-023-36015-5`).

Uso:
    python3 scripts/informe_candidatos.py --triaje data/triaje-v7e \\
        --out data/informe_candidatos.md
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np


def f(r, k, d=0.0):
    try:
        return float(r.get(k) or d)
    except (TypeError, ValueError):
        return d


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--triaje", type=Path, required=True,
                    help="directorio con los *_triaje.csv de los cuatro bloques")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--tsv", type=Path, default=None,
                    help="además, la misma cola en TSV para llevar a un SIG")
    args = ap.parse_args()

    todos = []
    for f_ in sorted(args.triaje.glob("*_triaje.csv")):
        # `candidatos_lugo_v7_triaje.csv` -> `lugo`
        bloque = f_.stem.split("_")[1]
        filas = list(csv.DictReader(open(f_, encoding="utf-8")))
        if not filas:
            continue
        revisables = [r for r in filas
                      if (r.get("veredicto") or "") != "YA CATALOGADO"]
        ya = len(filas) - len(revisables)
        if not revisables:
            print(f"{bloque}: {len(filas)} candidatos, todos ya catalogados")
            continue
        v = np.array([f(r, "triaje") for r in revisables])
        for r in revisables:
            # Percentil dentro de SU bloque: es lo unico comparable entre
            # bloques calibrados con reglas distintas.
            r["_pct"] = float((v <= f(r, "triaje")).mean()) * 100
            r["_bloque"] = bloque
        todos += revisables
        print(f"{bloque}: {len(revisables)} revisables"
              + (f" ({ya} descartados por el guardián)" if ya else ""))

    if not todos:
        print("no hay candidatos revisables"); return 1
    todos.sort(key=lambda r: (-r["_pct"], -f(r, "triaje")))

    L = []
    L.append("# Cola de revisión de candidatos a castro\n")
    L.append(f"**{len(todos)} candidatos sin catalogar** en cuatro bloques de "
             f"validación de Galicia, ordenados por su posición **dentro de su "
             f"propio bloque**.\n")
    L.append("La puntuación cruda no es comparable entre bloques: la "
             "calibración de la prominencia sale de los castros conocidos de "
             "cada uno, así que el mismo candidato saca notas distintas según "
             "dónde caiga. Por eso manda el percentil y el número va al lado.\n")
    L.append("Ninguna comprobación de aquí confirma nada. Descartan barato y "
             "ordenan la cola; el veredicto lo pone quien revise.\n")

    L.append("\n## Reparto por bloque\n")
    L.append("| bloque | candidatos |")
    L.append("|---|---:|")
    for b in sorted({r["_bloque"] for r in todos}):
        L.append(f"| {b} | {sum(1 for r in todos if r['_bloque']==b)} |")

    L.append("\n## La cola\n")
    for i, r in enumerate(todos, 1):
        conf = r.get("confusor_relieve") or ""
        L.append(f"\n### {i}. {r['_bloque'].capitalize()} — "
                 f"{r.get('concello') or 'concello desconocido'}\n")
        L.append(f"- **Dónde**: `{r['lat']}, {r['lon']}`")
        L.append(f"- **Posición en su bloque**: percentil {r['_pct']:.0f} "
                 f"(triaje {r.get('triaje')})")
        L.append(f"- **Confianza del modelo**: {r.get('score_modelo')}")
        prom = r.get("prominencia_m") or "?"
        tip = r.get("tipicidad") or ""
        extra = f", tipicidad {tip}" if tip else ""
        L.append(f"- **Forma**: prominencia {prom} m{extra}, domina el "
                 f"{r.get('pct_domina') or '?'}% de su entorno")
        L.append(f"- **Castro conocido más próximo**: {r.get('d_castro_m')} m "
                 f"({r.get('castro_proximo') or '—'})")
        if r.get("obra_moderna"):
            L.append(f"- **Obra moderna encima**: {r['obra_moderna']}")
        if conf and conf not in ("ninguno",):
            marca = ("**sin comprobar** — OSM no tiene uso del suelo mapeado "
                     "aquí, así que la ausencia de viñedo no dice nada"
                     if conf == "SIN COMPROBAR" else f"**{conf}**")
            L.append(f"- **Confusor del relieve**: {marca}")
        if r.get("densidad_suelo"):
            L.append(f"- **LiDAR**: {r['densidad_suelo']} pt/m² de suelo")
        if r.get("toponimo"):
            L.append(f"- **Topónimo**: «{r['toponimo']}»")
        L.append(f"- **Por qué está aquí**: {r.get('motivos') or '—'}")

    L.append("\n---\n")
    L.append("Generado por `scripts/informe_candidatos.py`. Las columnas "
             "`veredicto`, `revisor` y `notas` de los CSV de triaje van vacías "
             "a propósito: se rellenan al revisar y ese resultado vuelve al "
             "corpus.\n")
    args.out.write_text("\n".join(L), encoding="utf-8")
    print(f"\nescrito: {args.out}  ({len(todos)} candidatos)")

    if args.tsv:
        cols = ["_bloque", "_pct", "lon", "lat", "triaje", "score_modelo",
                "concello", "prominencia_m", "tipicidad", "pct_domina",
                "d_castro_m", "obra_moderna", "confusor_relieve", "toponimo",
                "motivos"]
        with open(args.tsv, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh, delimiter="\t")
            w.writerow([c.lstrip("_") for c in cols])
            for r in todos:
                w.writerow([f"{r[c]:.0f}" if c == "_pct" else r.get(c, "")
                            for c in cols])
        print(f"escrito: {args.tsv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
