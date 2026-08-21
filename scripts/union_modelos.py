#!/usr/bin/env python3
"""¿Cuantos castros encuentra la UNION de los modelos que ya tenemos?

El objetivo del proyecto no es maximizar `F1`: es **encontrar castros ineditos**.
Y para eso los dos errores no cuestan lo mismo. Un falso positivo son cinco
minutos de alguien mirando una ficha; un castro que no se detecta **no se
encuentra nunca**.

`comparar_detecciones.py` mostro que v11p halla `28` castros que v7 no ve, y v7
`27` que v11p no ve. Si cada modelo mira distinto, la union encuentra mas que
cualquiera de ellos por separado — y los checkpoints ya existen, asi que no
cuesta ni un entrenamiento.

Esto lo mide: recall y numero de candidatos a revisar, para cada modelo suelto,
para la union, y bajando el umbral.
"""
from __future__ import annotations

import csv
import math
from itertools import combinations
from pathlib import Path

BLOQUES = ["lugo", "coruna", "ourense", "pontevedra"]
TOL = 500.0


def leer(p: Path):
    with p.open(encoding="utf-8") as fh:
        return [r for r in csv.DictReader(fh, delimiter="\t")
                if r.get("lon") and r.get("lat")]


def detectados(pred, truth, umbral, k):
    """Indices de `truth` con alguna prediccion sobre umbral a menos de TOL."""
    pts = [(float(r["lon"]) * k, float(r["lat"]) * 110_540.0)
           for r in pred if float(r.get("score", 0)) >= umbral]
    out = set()
    for i, t in enumerate(truth):
        tx, ty = float(t["lon"]) * k, float(t["lat"]) * 110_540.0
        if any((px - tx) ** 2 + (py - ty) ** 2 <= TOL * TOL for px, py in pts):
            out.add(i)
    return out, len(pts)


def barrer(modelos, umbral):
    hall = cand = tot = 0
    por_modelo = {m: 0 for m in modelos}
    for b in BLOQUES:
        ft = Path(f"data/{b}_fus_truth_limpia.tsv")
        if not ft.exists():
            continue
        truth = leer(ft)
        lat0 = sum(float(t["lat"]) for t in truth) / len(truth)
        k = 111_320.0 * math.cos(math.radians(lat0))
        union, celdas = set(), 0
        for m in modelos:
            p = Path(f"data/sweep_val_{b}_{m}.tsv")
            if not p.exists():
                continue
            d, n = detectados(leer(p), truth, umbral, k)
            union |= d
            por_modelo[m] += len(d)
            celdas += n
        hall += len(union); cand += celdas; tot += len(truth)
    return hall, tot, cand, por_modelo


print("  recall = castros catalogados hallados / total (214 en 2.284 km2)")
print("  celdas = cuantas celdas hay que revisar (antes de agrupar)\n")
print(f"  {'conjunto':<26}{'umbral':>7}{'recall':>9}{'hallados':>10}{'celdas':>10}")
print("  " + "-" * 62)
for umbral in (0.70, 0.50):
    for modelos in (["v7"], ["v11p"], ["v7", "v11p"],
                    ["v7", "v11p", "v8"], ["v7", "v11p", "v8", "v6focal"]):
        h, t, c, _ = barrer(modelos, umbral)
        print(f"  {'+'.join(modelos):<26}{umbral:>7.2f}{h/t:>9.3f}{h:>10}{c:>10}")
    print()
