#!/usr/bin/env python3
"""Soft-NMS espacial, más el tope de tamaño. Del TFG de los pingüinos a castros.

El TFG `reTAG` (Pablo Seijo, `2026`) midió que **el postprocesado daba cuatro
veces más margen que el preprocesado**: `+6,54 pp` de `mAP` contra `+1,70`. Y
dentro del postprocesado, la mayor de todas fue **Soft-NMS con `+3,97 pp`**.

Aquí el agrupamiento es de **enlace simple**: todas las celdas a menos de `512 m`
se funden en un grupo y se reporta su centro. Eso tiene el mismo defecto que el
NMS duro del TFG —**si dos castros están cerca, uno desaparece dentro del
otro**— y está medido: el conjunto de cuatro modelos perdía `5` castros que v7
sí encontraba, por soldadura de grupos.

**Soft-NMS no absorbe: rebaja.** Se recorre por puntuación descendente; cada
detección conserva su identidad y su puntuación se atenúa según lo cerca que esté
de otra mejor:

    s_i  <-  s_i * exp( -(1 - d/R)^2 / sigma^2 )

Una detección pegada a otra mejor queda muy rebajada pero **sigue existiendo**;
una lejana no se toca. Así dos castros vecinos pueden salir los dos.

Y el **tope de tamaño**, que es la penalización por duración del TFG traducida:
un castro mide `50`-`200 m`, así que a paso de `256 m` deja `1`-`4` celdas.
Medido aquí: los aciertos no pasan de `7` celdas y los errores llegan a `18`.
"""
from __future__ import annotations

import csv
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "scripts")
from detection_eval import a_metros, agrupar  # noqa: E402

BLOQUES = ["lugo", "coruna", "ourense", "pontevedra"]
TOL, ENLACE = 500.0, 512.0
UMBRALES = [0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80]


def leer(p):
    with Path(p).open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def grupos_duros(px, py, sc, max_celdas=None):
    """Lo actual: enlace simple, centro del grupo, puntuación máxima."""
    out = []
    for g in agrupar(px, py, ENLACE, 1):
        if max_celdas is not None and len(g) > max_celdas:
            continue
        out.append((float(np.mean(px[g])), float(np.mean(py[g])),
                    float(sc[g].max()), len(g)))
    return out


def soft_nms(px, py, sc, radio=ENLACE, sigma=0.5, suelo=0.05):
    """Cada celda es una detección; las vecinas se atenúan, no se absorben."""
    orden = np.argsort(-sc)
    s = sc.copy()
    vivos = []
    for i in orden:
        if s[i] < suelo:
            continue
        vivos.append((float(px[i]), float(py[i]), float(s[i]), 1))
        d = np.hypot(px - px[i], py - py[i])
        cerca = (d < radio) & (d > 0)
        # solape espacial: 1 pegado, 0 al borde del radio
        solape = np.clip(1.0 - d[cerca] / radio, 0, 1)
        s[cerca] *= np.exp(-(solape ** 2) / sigma)
    return vivos


def evaluar(dets, truth, lat0, umbral):
    tx, ty = a_metros([t["lon"] for t in truth], [t["lat"] for t in truth], lat0)
    sel = [d for d in dets if d[2] >= umbral]
    if not sel:
        return 0.0
    hallado = set()
    tp = 0
    for cx, cy, _, _ in sel:
        d = np.hypot(tx - cx, ty - cy)
        j = int(np.argmin(d))
        if d[j] <= TOL:
            if j not in hallado:
                tp += 1
                hallado.add(j)
    prec = tp / len(sel) if sel else 0.0
    rec = len(hallado) / len(truth)
    return 2 * prec * rec / (prec + rec) if prec + rec > 0 else 0.0


CONFIGS = [("duro (LO ACTUAL)", "duro", {}),
           ("duro + tope 8 celdas", "duro", {"max_celdas": 8}),
           ("soft-nms sigma 0,25", "soft", {"sigma": 0.25}),
           ("soft-nms sigma 0,50", "soft", {"sigma": 0.50}),
           ("soft-nms sigma 1,00", "soft", {"sigma": 1.00})]

print(f"  {'configuracion':<24}" + "".join(f"{b[:9]:>10}" for b in BLOQUES)
      + f"{'media':>9}")
print("  " + "-" * (24 + 10 * 4 + 9))
for nombre, tipo, kw in CONFIGS:
    f1s = []
    for b in BLOQUES:
        pred = leer(f"data/sweep_val_{b}_v7.tsv")
        truth = leer(f"data/{b}_fus_truth_limpia.tsv")
        lat0 = sum(float(t["lat"]) for t in truth) / len(truth)
        px, py = a_metros([float(r["lon"]) for r in pred],
                          [float(r["lat"]) for r in pred], lat0)
        sc = np.array([float(r["score"]) for r in pred])
        mejor = 0.0
        for u in UMBRALES:
            m = sc >= u
            if not m.any():
                continue
            dets = (grupos_duros(px[m], py[m], sc[m], **kw) if tipo == "duro"
                    else soft_nms(px[m], py[m], sc[m], **kw))
            mejor = max(mejor, evaluar(dets, truth, lat0, u))
        f1s.append(mejor)
    print(f"  {nombre:<24}" + "".join(f"{x:>10.3f}" for x in f1s)
          + f"{sum(f1s)/len(f1s):>9.3f}")
