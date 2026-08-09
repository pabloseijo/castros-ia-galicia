#!/usr/bin/env python3
"""Combina las puntuaciones de dos barridos sobre la misma rejilla.

**Por que tiene sentido aqui.** Medido el 2026-08-09 al umbral preregistrado:

| bloque | v7 | v11p |
| --- | ---: | ---: |
| Lugo | `0,697` | `0,618` |
| A Coruna | `0,396` | **`0,425`** |
| Ourense | `0,535` | `0,359` |

v7 es **preciso** y v11p tiene **recall** —en A Coruna `0,613` contra `0,333`—.
Un conjunto puede quedarse con las dos cosas: la media penaliza a quien dispara
solo, el maximo suma coberturas.

**Lo que NO se hace aqui, y es importante.** Elegir por bloque el modelo que
mejor `F1` da en ese bloque **es elegir mirando el examen**, y no se puede
trasladar a Galicia entera: alli no hay etiquetas para decidir. El mismo error se
midio con los umbrales y, hecho honestamente —dejando el bloque fuera—, daba
`-0,001`. Combinar puntuaciones, en cambio, no mira ni una etiqueta.

Uso:
    python3 scripts/ensamblar.py --a data/sweep_val_lugo_v7.tsv \\
        --b data/sweep_val_lugo_v11p.tsv --modo media --out data/sweep_lugo_ens.tsv
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path


def leer(p: Path):
    d = {}
    with p.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            try:
                k = (round(float(r["lon"]), 6), round(float(r["lat"]), 6))
                d[k] = r
            except (KeyError, TypeError, ValueError):
                continue
    return d


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--a", type=Path, required=True)
    ap.add_argument("--b", type=Path, required=True)
    ap.add_argument("--modo", choices=["media", "max", "min", "geom"], default="media")
    ap.add_argument("--peso-a", type=float, default=0.5)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    A, B = leer(args.a), leer(args.b)
    comunes = set(A) & set(B)
    print(f"  {args.a.name}: {len(A)} celdas | {args.b.name}: {len(B)} | "
          f"comunes: {len(comunes)}")
    if len(comunes) < 0.5 * min(len(A), len(B)):
        print("  *** las rejillas no coinciden: no se puede combinar ***")
        return 2

    filas = []
    for k in comunes:
        ra, rb = A[k], B[k]
        try:
            sa, sb = float(ra["score"]), float(rb["score"])
        except (KeyError, TypeError, ValueError):
            continue
        if args.modo == "media":
            s = args.peso_a * sa + (1 - args.peso_a) * sb
        elif args.modo == "max":
            s = max(sa, sb)
        elif args.modo == "min":
            s = min(sa, sb)
        else:
            s = (max(sa, 1e-9) * max(sb, 1e-9)) ** 0.5
        filas.append((ra.get("id", ""), k[0], k[1], s,
                      ra.get("p_fondo", ""), ra.get("p_castro", ""),
                      ra.get("p_mamoa", "")))

    with args.out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter="\t")
        w.writerow(["id", "lon", "lat", "score", "p_fondo", "p_castro", "p_mamoa"])
        w.writerows(filas)
    print(f"  escrito {args.out} ({len(filas)} celdas, modo {args.modo})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
