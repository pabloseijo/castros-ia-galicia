#!/usr/bin/env python3
"""Umbral por PERCENTIL del propio bloque, no por puntuacion absoluta.

**El hallazgo que lo motiva.** Medido el 2026-08-09 sobre v7: en los castros que
el modelo pierde, la puntuacion mediana es `0,394` en A Coruna y `0,589` en
Ourense. **El modelo ve los castros en los cuatro bloques** —ninguno puntua cerca
de cero— pero **la escala de sus puntuaciones se desplaza con el paisaje**.

Un umbral absoluto de `0,70` es por tanto mas exigente en A Coruna que en Ourense,
sin que nadie lo haya decidido.

**Por que el percentil es legitimo y el umbral por bloque no.** Elegir el umbral
que maximiza el `F1` de cada bloque exige mirar sus etiquetas, y en Galicia entera
no las hay. El percentil se calcula **de la propia distribucion de puntuaciones**,
sin etiqueta ninguna, asi que se puede aplicar a cualquier tesela nueva.

Es ademas lo que un revisor humano hace de forma natural: mira las `N` mejores de
lo que tiene delante, no las que pasan un numero fijo.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "scripts")
from detection_eval import a_metros, agrupar, leer_tsv  # noqa: E402

M = sys.argv[1] if len(sys.argv) > 1 else "v7"
BLOQUES = ("lugo", "coruna", "ourense", "pontevedra")


def evaluar(B, corte):
    p = Path(f"data/sweep_val_{B}_{M}.tsv")
    pred = [x for x in leer_tsv(p, ("lon", "lat", "score")) if "score" in x]
    for x in pred:
        x["score"] = float(x["score"])
    truth = leer_tsv(Path(f"data/{B}_fus_truth_limpia.tsv"))
    lat0 = float(np.mean([t["lat"] for t in truth]))
    tx, ty = a_metros([t["lon"] for t in truth], [t["lat"] for t in truth], lat0)
    sel = [x for x in pred if x["score"] >= corte]
    if len(sel) < 3:
        return 0.0, 0.0, 0.0, len(sel)
    sx, sy = a_metros([x["lon"] for x in sel], [x["lat"] for x in sel], lat0)
    tp = fp = 0
    vistos = set()
    for g in agrupar(sx, sy, 512.0):
        gx, gy = float(np.mean(sx[g])), float(np.mean(sy[g]))
        d = np.hypot(tx - gx, ty - gy)
        if d.min() <= 500:
            tp += 1; vistos.add(int(d.argmin()))
        else:
            fp += 1
    rec = len(vistos) / max(len(truth), 1)
    pre = tp / max(tp + fp, 1)
    return 2*pre*rec/max(pre+rec, 1e-9), pre, rec, len(sel)


# a que percentil equivale 0,70 en cada bloque
print(f"  {'bloque':<12}{'u=0,70 es el percentil':>26}")
pcts = {}
for B in BLOQUES:
    pred = [float(x["score"]) for x in
            leer_tsv(Path(f"data/sweep_val_{B}_{M}.tsv"), ("lon", "lat", "score"))
            if "score" in x]
    a = np.array(pred)
    pcts[B] = float((a < 0.70).mean() * 100)
    print(f"  {B:<12}{pcts[B]:>25.2f}%")

print(f"\n  {'percentil':<12}" + "".join(f"{b[:6]:>9}" for b in BLOQUES) + f"{'media':>9}")
mejor = (None, -1)
for pc in (97.0, 98.0, 98.5, 99.0, 99.3, 99.5, 99.7):
    fs = []
    for B in BLOQUES:
        pred = [float(x["score"]) for x in
                leer_tsv(Path(f"data/sweep_val_{B}_{M}.tsv"), ("lon", "lat", "score"))
                if "score" in x]
        corte = float(np.percentile(np.array(pred), pc))
        f, _, _, _ = evaluar(B, corte)
        fs.append(f)
    m = float(np.mean(fs))
    if m > mejor[1]:
        mejor = (pc, m)
    print(f"  p{pc:<11.1f}" + "".join(f"{f:>9.3f}" for f in fs) + f"{m:>9.3f}")

print(f"\n  referencia, umbral absoluto 0,70: media 0.512")
print(f"  mejor percentil: p{mejor[0]} con media {mejor[1]:.3f} "
      f"({mejor[1]-0.512:+.3f})")
print("\n  El percentil se calcula sin etiquetas, asi que SI se traslada a")
print("  territorio nuevo. Elegir el umbral por bloque mirando su F1, no.")
