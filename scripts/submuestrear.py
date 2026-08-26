#!/usr/bin/env python3
"""Baja la proporcion de positivos en `train` sin cortar una sola viñeta nueva.

**Reutiliza todo**: los arrays del corpus de origen se dejan donde estan y solo
se escribe un `index.tsv` nuevo que mueve el exceso de positivos a un split
inerte. Cero minutos de CPU en cortar.

Hipotesis que prueba (`docs/preregistros/PREREGISTRO-v13-proporcion.md`): v11p fallo por la
PROPORCION de positivos (`26,7%` contra el `8,9%` de v7, desplegando en `0,73%`),
no por la cantidad. Si es cierto, con la proporcion de v7 debe recuperar su
rendimiento usando mas positivos que el.

El submuestreo es **estratificado por bloque espacial**, no aleatorio puro: si se
sortearan sin mas, unos bloques quedarian sin positivos y otros con todos, y eso
cambiaria la cobertura geografica ademas de la proporcion —dos variables a la vez,
que es justo el error que este experimento viene a deshacer—.
"""
from __future__ import annotations

import argparse
import csv
import random
from collections import defaultdict
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--origen", type=Path, required=True)
    ap.add_argument("--salida", type=Path, required=True)
    ap.add_argument("--proporcion", type=float, default=0.089,
                    help="fraccion de positivos en train (v7 = 0.089)")
    ap.add_argument("--semilla", type=int, default=20260809)
    args = ap.parse_args()

    filas = list(csv.DictReader((args.origen / "index.tsv").open(encoding="utf-8"),
                                delimiter="\t"))
    for r in filas:
        r["split"] = (r.get("split") or "").strip()
        r["group"] = (r.get("group") or "").strip()

    tren = [r for r in filas if r["split"] == "train"]
    pos = [r for r in tren if r["group"].startswith(("castro", "mamoa"))]
    fondo = len(tren) - len(pos)
    print(f"  origen: {len(tren)} en train | {len(pos)} positivos "
          f"({100*len(pos)/len(tren):.1f}%) | {fondo} de fondo")

    # con el fondo fijo, cuantos positivos caben a la proporcion pedida
    objetivo = int(round(args.proporcion * fondo / (1 - args.proporcion)))
    if objetivo >= len(pos):
        print(f"  nada que hacer: ya hay {len(pos)} y caben {objetivo}")
        return 0

    porbloque = defaultdict(list)
    for r in pos:
        porbloque[r.get("block", "?")].append(r)
    rnd = random.Random(args.semilla)

    # reparto proporcional por bloque, con al menos uno donde haya alguno
    quedan, elegidos = objetivo, []
    bloques = sorted(porbloque, key=lambda b: -len(porbloque[b]))
    for b in bloques:
        cuota = max(1, round(objetivo * len(porbloque[b]) / len(pos)))
        cuota = min(cuota, len(porbloque[b]), quedan)
        elegidos += rnd.sample(porbloque[b], cuota)
        quedan -= cuota
        if quedan <= 0:
            break
    mantener = {id(r) for r in elegidos}

    fuera = 0
    for r in pos:
        if id(r) not in mantener:
            r["split"] = "excluido_proporcion"
            fuera += 1

    args.salida.mkdir(parents=True, exist_ok=True)
    with (args.salida / "index.tsv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, delimiter="\t", fieldnames=list(filas[0].keys()))
        w.writeheader(); w.writerows(filas)

    tren2 = [r for r in filas if r["split"] == "train"]
    pos2 = [r for r in tren2 if r["group"].startswith(("castro", "mamoa"))]
    print(f"  salida: {len(tren2)} en train | {len(pos2)} positivos "
          f"({100*len(pos2)/len(tren2):.1f}%) | {fuera} apartados")
    print(f"  bloques con positivos: {len({r.get('block') for r in pos2})} "
          f"de {len(porbloque)}")
    print(f"\n  escrito {args.salida}/index.tsv "
          f"(los arrays se reutilizan de {args.origen}/arrays)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
