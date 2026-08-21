#!/usr/bin/env python3
"""¿Se solapan la verdad de un bloque y su mascara de entrenamiento?

En `detection_eval.evaluar` el bucle comprueba **primero** si la deteccion cae
sobre un castro de la verdad y hace `continue`; solo si no, mira la mascara. Es
decir: **si un castro esta en las dos listas, detectarlo cuenta como acierto**,
aunque el modelo lo viera al entrenar. Eso seria memoria contada como
prospeccion, y afectaria a las cifras publicadas de todas las versiones.

El orden solo es inocuo si las dos listas son disjuntas. Esto lo comprueba.
"""
from __future__ import annotations

import csv
import math
from pathlib import Path

TOL = 500.0  # la misma tolerancia con la que evalua el script


def leer(p):
    return [r for r in csv.DictReader(p.open(encoding="utf-8"), delimiter="\t")
            if r.get("lon") and r.get("lat")]


for b in ("lugo", "coruna", "ourense", "pontevedra"):
    ft, fm = Path(f"data/{b}_fus_truth_limpia.tsv"), Path(f"data/{b}_fus_mascara_train.tsv")
    if not (ft.exists() and fm.exists()):
        continue
    truth, masc = leer(ft), leer(fm)
    lat0 = sum(float(t["lat"]) for t in truth) / len(truth)
    k = 111_320.0 * math.cos(math.radians(lat0))
    mp = [(float(m["lon"]) * k, float(m["lat"]) * 110_540.0) for m in masc]
    n = 0
    for t in truth:
        tx, ty = float(t["lon"]) * k, float(t["lat"]) * 110_540.0
        if any((mx - tx) ** 2 + (my - ty) ** 2 <= TOL * TOL for mx, my in mp):
            n += 1
    print(f"  {b:<12} verdad {len(truth):>4} | mascara {len(masc):>4} | "
          f"de la verdad, a menos de {TOL:.0f} m de la mascara: {n} "
          f"({100*n/len(truth):.0f}%)")
