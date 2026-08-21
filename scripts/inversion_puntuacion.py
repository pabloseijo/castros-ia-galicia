#!/usr/bin/env python3
"""¿Puntúa la red los errores más alto que los aciertos?

Es la comprobacion que el TFG de los pinguinos (`reTAG`, 2026) identifico como el
mayor bloqueo de su sistema: **la red daba scores mas altos a las detecciones
incorrectas que a las correctas** —*score inversion*—, y corregirlo con
*temperature scaling*, sin reentrenar nada, valio `+0,78 pp` de `mAP`.

Aqui nunca se ha mirado. Y si existe, es la explicacion de por que subir el
umbral no siempre mejora: se estarian tirando aciertos antes que errores.

Se mide sobre los grupos ya formados: para cada uno, si cae sobre un castro
catalogado es acierto y si no, error. Y se compara el reparto de sus
puntuaciones.
"""
from __future__ import annotations

import csv
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "scripts")
from detection_eval import a_metros, agrupar  # noqa: E402

BLOQUES = ["lugo", "coruna", "ourense", "pontevedra"]
TOL, ENLACE, UMBRAL = 500.0, 512.0, 0.50


def leer(p):
    with Path(p).open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


aciertos, errores = [], []
tam_ac, tam_er = [], []
for b in BLOQUES:
    pred = [r for r in leer(f"data/sweep_val_{b}_v7.tsv")
            if float(r.get("score", 0)) >= UMBRAL]
    if not pred:
        continue
    truth = leer(f"data/{b}_fus_truth_limpia.tsv")
    lat0 = sum(float(t["lat"]) for t in truth) / len(truth)
    px, py = a_metros([float(r["lon"]) for r in pred],
                      [float(r["lat"]) for r in pred], lat0)
    sc = np.array([float(r["score"]) for r in pred])
    tx, ty = a_metros([t["lon"] for t in truth], [t["lat"] for t in truth], lat0)
    for g in agrupar(px, py, ENLACE, 1):
        cx, cy = float(np.mean(px[g])), float(np.mean(py[g]))
        pico = float(sc[g].max())
        d = float(np.hypot(tx - cx, ty - cy).min())
        (aciertos if d <= TOL else errores).append(pico)
        (tam_ac if d <= TOL else tam_er).append(len(g))

a, e = np.array(aciertos), np.array(errores)
print(f"  grupos a umbral {UMBRAL}: {len(a)} aciertos | {len(e)} errores\n")
print(f"  {'':<22}{'aciertos':>10}{'errores':>10}")
print("  " + "-" * 42)
for nombre, fa, fe in (("media", a.mean(), e.mean()),
                       ("mediana", np.median(a), np.median(e)),
                       ("percentil 90", np.percentile(a, 90), np.percentile(e, 90)),
                       ("maximo", a.max(), e.max())):
    print(f"  puntuacion {nombre:<11}{fa:>10.3f}{fe:>10.3f}")
print()
u = sum(1 for x in a for y in e if x > y) / (len(a) * len(e))
print(f"  P(un acierto puntue mas que un error) = {u:.3f}")
print(f"  (0,5 = la puntuacion no discrimina | <0,5 = INVERSION)")

print(f"\n  {'':<22}{'aciertos':>10}{'errores':>10}")
print("  " + "-" * 42)
ta, te = np.array(tam_ac), np.array(tam_er)
for nombre, fa, fe in (("mediana", np.median(ta), np.median(te)),
                       ("percentil 90", np.percentile(ta, 90), np.percentile(te, 90)),
                       ("maximo", ta.max(), te.max())):
    print(f"  celdas por grupo {nombre:<6}{fa:>10.0f}{fe:>10.0f}")
ut = sum(1 for x in ta for y in te if x > y) / (len(ta) * len(te))
print(f"\n  P(un acierto sea mas grande que un error) = {ut:.3f}")
