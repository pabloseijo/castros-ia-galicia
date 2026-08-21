#!/usr/bin/env python3
"""¿Es A Coruna peor para el modelo, o es su catalogo distinto?

Sexta hipotesis caida (`2026-08-09`): los castros que A Coruna pierde **no estan
destruidos**. Queda la septima, y es la unica que no culpa al modelo:

> A Coruna tiene `75` castros catalogados en su bloque contra los `36` de
> Ourense. Si su catalogo es **mas exhaustivo** —si registra sitios mas
> marginales que otros concellos ni anotaron—, entonces el modelo no va peor
> alli: **le estan pidiendo algo mas dificil**.

Como se comprueba sin verdad de campo: **puntuando el terreno donde esta cada
castro catalogado**. Si los de A Coruna reciben puntuaciones sistematicamente
mas bajas que los de Lugo, es que se parecen menos a un castro — y eso apunta al
catalogo, no a la red.

Es la misma tecnica que refuto la hipotesis de los positivos nuevos, y tiene la
misma limitacion honesta: mide **parecido a lo que el modelo aprendio**, no
autenticidad arqueologica. Un catalogo con sitios mas sutiles y un modelo ciego a
esa zona dan la misma senal. Lo que si distingue es **la densidad**: si ademas
A Coruna tiene el doble de castros por km2, las dos piezas juntas apuntan al
catalogo.
"""
from __future__ import annotations

import csv
import math
import statistics as st
from pathlib import Path

BLOQUES = {"lugo": "-7.375 42.625 -7.125 42.875",
           "coruna": "-8.50 43.00 -8.25 43.25",
           "ourense": "-8.25 42.25 -8.00 42.50",
           "pontevedra": "-8.875 42.125 -8.625 42.375"}
RADIO = 250.0   # se coge la mejor celda a menos de esto del castro


def leer(p):
    with Path(p).open(encoding="utf-8") as fh:
        return [r for r in csv.DictReader(fh, delimiter="\t")
                if r.get("lon") and r.get("lat")]


print(f"  {'bloque':<12}{'castros':>8}{'km2':>8}{'por km2':>9}"
      f"{'mediana':>9}{'media':>8}{'>0,70':>8}{'>0,50':>8}")
print("  " + "-" * 70)
res = {}
for b, bb in BLOQUES.items():
    w, s, e, n = map(float, bb.split())
    lat0 = (s + n) / 2
    km2 = (e - w) * 111.32 * math.cos(math.radians(lat0)) * (n - s) * 110.54
    truth = leer(f"data/{b}_fus_truth_limpia.tsv")
    pred = leer(f"data/sweep_val_{b}_v7.tsv")
    k = 111_320.0 * math.cos(math.radians(lat0))
    celdas = [(float(r["lon"]) * k, float(r["lat"]) * 110_540.0,
               float(r.get("score", 0))) for r in pred]
    mejores = []
    for t in truth:
        tx, ty = float(t["lon"]) * k, float(t["lat"]) * 110_540.0
        cerca = [sc for px, py, sc in celdas
                 if (px - tx) ** 2 + (py - ty) ** 2 <= RADIO * RADIO]
        if cerca:
            mejores.append(max(cerca))
    if not mejores:
        continue
    res[b] = mejores
    print(f"  {b:<12}{len(truth):>8}{km2:>8.0f}{len(truth)/km2:>9.3f}"
          f"{st.median(mejores):>9.3f}{st.mean(mejores):>8.3f}"
          f"{100*sum(x > 0.70 for x in mejores)/len(mejores):>7.0f}%"
          f"{100*sum(x > 0.50 for x in mejores)/len(mejores):>7.0f}%")

if "coruna" in res and "lugo" in res:
    a, c = res["lugo"], res["coruna"]
    u = sum(1 for x in a for y in c if x > y) / (len(a) * len(c))
    print(f"\n  P(un castro de Lugo puntue mas alto que uno de A Coruna) = {u:.3f}")
    print("  (0,5 = los catalogos piden lo mismo | >0,6 = el de A Coruna es mas exigente)")
