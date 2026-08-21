#!/usr/bin/env python3
"""¿El conjunto pierde algún castro que v7 sí encontraba?

El plan lo exige antes de dar por buena cualquier configuración: **un recall
medio mejor puede esconder un intercambio malo**. Y aquí no basta el argumento
teórico de que la unión a `0,60` contiene las celdas de v7 a `0,70`, porque entre
las celdas y el resultado hay un **agrupamiento**: al bajar el umbral entran más
celdas, los grupos se sueldan, y el centro de un grupo grande puede alejarse del
castro hasta dejar de contarlo. Pasó de verdad a umbral `0,50`, donde el recall
BAJÓ respecto a `0,60`.

Así que se comprueba castro a castro y no por la media.
"""
from __future__ import annotations

import csv
import math
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "scripts")
from detection_eval import a_metros, agrupar  # noqa: E402

BLOQUES = ["lugo", "coruna", "ourense", "pontevedra"]
TOL, ENLACE, MIN_CELDAS = 500.0, 512.0, 1


def leer(p):
    with Path(p).open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def hallados(modelos, umbral, bloque, truth, lat0, min_vecinos=1):
    """Índices de `truth` que esta configuración detecta, tras agrupar."""
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
        return set()
    px, py = a_metros([v[0] for v in sel], [v[1] for v in sel], lat0)
    grupos = [g for g in agrupar(px, py, ENLACE, min_vecinos) if len(g) >= MIN_CELDAS]
    tx, ty = a_metros([t["lon"] for t in truth], [t["lat"] for t in truth], lat0)
    out = set()
    for g in grupos:
        cx, cy = float(np.mean(px[g])), float(np.mean(py[g]))
        d = np.hypot(tx - cx, ty - cy)
        j = int(np.argmin(d))
        if d[j] <= TOL:
            out.add(j)
    # el número de grupos es el número de fichas que alguien tendrá que mirar
    return out, len(grupos)


# **Se prueban varios agrupamientos**, porque la pérdida no viene del modelo sino
# de cómo se juntan las celdas: con enlace simple (`min_vecinos = 1`) un reguero
# de puntos suelda dos sitios, el grupo crece y su centro se va del castro. La
# alternativa documentada es **DB-NMS** (Yang et al., `10.1007/s00521-021-06628-w`):
# un punto solo une a sus vecinos si él mismo es núcleo.
CONFIGS = [("v7 sola, 0,70, enlace simple", ["v7"], 0.70, 1),
           ("conjunto 0,60, enlace simple", ["v7", "v11p", "v12", "v14"], 0.60, 1),
           ("conjunto 0,60, densidad 2", ["v7", "v11p", "v12", "v14"], 0.60, 2),
           ("conjunto 0,60, densidad 3", ["v7", "v11p", "v12", "v14"], 0.60, 3),
           ("conjunto 0,65, enlace simple", ["v7", "v11p", "v12", "v14"], 0.65, 1)]

base = {}
print(f"  {'configuracion':<32}{'hallados':>10}{'pierde de v7':>14}"
      f"{'fichas':>9}{'f/castro':>9}")
print("  " + "-" * 76)
for nombre, modelos, umbral, mv in CONFIGS:
    tot, perd, fichas, nombres = 0, 0, 0, []
    for b in BLOQUES:
        truth = leer(f"data/{b}_fus_truth_limpia.tsv")
        lat0 = sum(float(t["lat"]) for t in truth) / len(truth)
        h, n_grupos = hallados(modelos, umbral, b, truth, lat0, mv)
        if nombre.startswith("v7 sola"):
            base[b] = h
        tot += len(h)
        fichas += n_grupos
        falta = base.get(b, set()) - h
        perd += len(falta)
        nombres += [(truth[j].get("name") or "?")[:38] for j in sorted(falta)]
    print(f"  {nombre:<32}{tot:>10}{perd:>14}{fichas:>9}"
          f"{fichas/max(tot,1):>9.1f}")
    for n in nombres[:5]:
        print(f"        pierde: {n}")
