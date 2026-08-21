#!/usr/bin/env python3
"""¿Cuántos castros encuentras en las primeras N fichas revisadas?

La pregunta «¿202 fichas para 95 castros o 1.448 para 180?» está mal planteada:
con una lista **ordenada** nadie revisa todo, se revisa de arriba abajo hasta que
se acaba el tiempo. Así que lo que decide no es el total sino **el rendimiento de
las primeras N fichas**, y eso se mide.

Para cada configuración se ordenan las detecciones por puntuación y se cuenta
cuántos castros catalogados distintos aparecen en las primeras `N`. La que más
encuentre a un `N` dado es la que hay que congelar para ese presupuesto.

Se cuentan **castros distintos**: dos detecciones sobre el mismo sitio no son dos
hallazgos, y no descontarlo fue lo que infló el `F1` de Lugo de `0,667` a `0,754`
en su día.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "scripts")
from detection_eval import a_metros, agrupar  # noqa: E402

BLOQUES = ["lugo", "coruna", "ourense", "pontevedra"]
TOL, ENLACE, MIN_CELDAS = 500.0, 512.0, 1
CORTES = (100, 200, 350, 500, 750, 1000, 1500)

CONFIGS = [
    ("v7 sola, 0,70", ["v7"], 0.70, 1),
    ("v7 sola, 0,60", ["v7"], 0.60, 1),
    ("conjunto 0,65", ["v7", "v11p", "v12", "v14"], 0.65, 1),
    ("conjunto 0,60", ["v7", "v11p", "v12", "v14"], 0.60, 1),
    ("conjunto 0,60 dens3", ["v7", "v11p", "v12", "v14"], 0.60, 3),
    ("conjunto 0,50 dens3", ["v7", "v11p", "v12", "v14"], 0.50, 3),
]


def leer(p):
    with Path(p).open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def detecciones(modelos, umbral, bloque, mv):
    """Grupos ordenados por su mejor puntuación, con su centro."""
    mejor = {}
    for m in modelos:
        p = Path(f"data/sweep_val_{bloque}_{m}.tsv")
        if not p.exists():
            continue
        for r in leer(p):
            cid = r.get("id") or f"{r['lon']},{r['lat']}"
            s = float(r.get("score", 0))
            if cid not in mejor or s > mejor[cid][2]:
                mejor[cid] = (float(r["lon"]), float(r["lat"]), s)
    sel = [v for v in mejor.values() if v[2] >= umbral]
    if not sel:
        return []
    truth = leer(f"data/{bloque}_fus_truth_limpia.tsv")
    lat0 = sum(float(t["lat"]) for t in truth) / len(truth)
    px, py = a_metros([v[0] for v in sel], [v[1] for v in sel], lat0)
    grupos = [g for g in agrupar(px, py, ENLACE, mv) if len(g) >= MIN_CELDAS]
    tx, ty = a_metros([t["lon"] for t in truth], [t["lat"] for t in truth], lat0)
    out = []
    for g in grupos:
        cx, cy = float(np.mean(px[g])), float(np.mean(py[g]))
        pico = max(sel[i][2] for i in g)
        d = np.hypot(tx - cx, ty - cy)
        j = int(np.argmin(d))
        out.append((pico, bloque, j if d[j] <= TOL else -1))
    return out


print(f"  castros distintos hallados en las primeras N fichas revisadas")
print(f"  (los cuatro bloques juntos, {sum(len(leer(f'data/{b}_fus_truth_limpia.tsv')) for b in BLOQUES)} castros catalogados)\n")
cab = "".join(f"{n:>8}" for n in CORTES)
print(f"  {'configuracion':<22}{cab}{'total':>8}")
print("  " + "-" * (22 + 8 * len(CORTES) + 8))

for nombre, modelos, umbral, mv in CONFIGS:
    todas = []
    for b in BLOQUES:
        todas += detecciones(modelos, umbral, b, mv)
    todas.sort(key=lambda t: -t[0])
    vistos, curva = set(), []
    for i, (_, b, j) in enumerate(todas, 1):
        if j >= 0:
            vistos.add((b, j))
        if i in CORTES:
            curva.append(len(vistos))
    while len(curva) < len(CORTES):
        curva.append(len(vistos))       # la lista se acabó antes del corte
    fila = "".join(f"{c:>8}" for c in curva)
    print(f"  {nombre:<22}{fila}{len(todas):>8}")
