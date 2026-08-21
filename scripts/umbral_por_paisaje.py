#!/usr/bin/env python3
"""Umbral adaptado al paisaje, elegido SIN mirar las etiquetas.

**El diagnostico que lo motiva.** Medido el 2026-08-09 sobre v7, los dos bloques
flojos tienen problemas opuestos:

| bloque | precision | recall | le pasa |
| --- | ---: | ---: | --- |
| A Coruna | `0,769` | `0,267` | no encuentra: pierde `55` de `75` |
| Pontevedra | `0,391` | `0,450` | alucina sobre obra moderna |

Un umbral unico no puede servir a los dos. Y elegirlo **por bloque mirando su
`F1`** es hacer trampa: en Galicia entera no hay etiquetas para decidir.

**La via legitima**: que el umbral dependa de una propiedad del paisaje
**medible sin etiquetas**, como la densidad de edificios de OSM. Eso se puede
calcular en cualquier tesela de Galicia y del norte de Portugal, asi que se
traslada; el `F1` del bloque, no.

Este guion mide si existe esa relacion antes de construir nada encima: densidad
de edificacion por bloque contra el umbral que le habria venido bien.
"""
from __future__ import annotations

import glob
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "scripts")
from detection_eval import a_metros, agrupar, leer_tsv  # noqa: E402

BLOQUES = {"lugo": (-7.375, 42.625, -7.125, 42.875),
           "coruna": (-8.50, 43.00, -8.25, 43.25),
           "ourense": (-8.25, 42.25, -8.00, 42.50),
           "pontevedra": (-8.875, 42.125, -8.625, 42.375)}
M = sys.argv[1] if len(sys.argv) > 1 else "v7"

# densidad de edificacion desde la cache de Overpass: sin pedir nada nuevo
edif = []
for f in glob.glob("data/galicia-hard-negatives-v1/overpass-cache/*.json"):
    try:
        d = json.load(open(f, encoding="utf-8"))
    except Exception:
        continue
    for e in d.get("elements", []):
        t = e.get("tags") or {}
        if "building" not in t and t.get("landuse") not in ("residential", "industrial"):
            continue
        c = e.get("center") or e
        if c.get("lat") is not None:
            edif.append((float(c["lat"]), float(c["lon"])))
E = np.array(edif) if edif else np.zeros((0, 2))
print(f"edificaciones en la cache: {len(E)}")

print(f"\n  {'bloque':<12}{'edif/km2':>10}{'u* propio':>11}{'F1 a u*':>9}{'F1 a 0,70':>11}")
datos = []
for b, (w, s, e, n) in BLOQUES.items():
    p = Path(f"data/sweep_val_{b}_{M}.tsv")
    if not p.exists():
        continue
    dens = 0.0
    if len(E):
        m = (E[:, 0] >= s) & (E[:, 0] <= n) & (E[:, 1] >= w) & (E[:, 1] <= e)
        km2 = (n - s) * 111.32 * (e - w) * 111.32 * math.cos(math.radians((n + s) / 2))
        dens = float(m.sum()) / max(km2, 1e-9)

    pred_all = [x for x in leer_tsv(p, ("lon", "lat", "score")) if "score" in x]
    for x in pred_all:
        x["score"] = float(x["score"])
    truth = leer_tsv(Path(f"data/{b}_fus_truth_limpia.tsv"))
    lat0 = float(np.mean([t["lat"] for t in truth]))
    tx, ty = a_metros([t["lon"] for t in truth], [t["lat"] for t in truth], lat0)

    mejor, u_mejor, f70 = -1.0, None, None
    for u in np.arange(0.40, 0.90, 0.05):
        sel = [x for x in pred_all if x["score"] >= u]
        if len(sel) < 3:
            continue
        px, py = a_metros([x["lon"] for x in sel], [x["lat"] for x in sel], lat0)
        tp, fp, vistos = 0, 0, set()
        for g in agrupar(px, py, 512.0):
            cx, cy = float(np.mean(px[g])), float(np.mean(py[g]))
            d = np.hypot(tx - cx, ty - cy)
            if d.min() <= 500:
                tp += 1; vistos.add(int(d.argmin()))
            else:
                fp += 1
        rec = len(vistos) / max(len(truth), 1)
        pre = tp / max(tp + fp, 1)
        f = 2*pre*rec/max(pre+rec, 1e-9)
        if abs(u - 0.70) < 0.001:
            f70 = f
        if f > mejor:
            mejor, u_mejor = f, u
    datos.append((b, dens, u_mejor, mejor))
    print(f"  {b:<12}{dens:>10.1f}{u_mejor:>11.2f}{mejor:>9.3f}{(f70 or 0):>11.3f}")

if len(datos) >= 3:
    d = np.array([[x[1], x[2]] for x in datos], dtype=float)
    r = float(np.corrcoef(d[:, 0], d[:, 1])[0, 1])
    print(f"\n  correlacion densidad de edificacion / umbral optimo: {r:+.3f} (n={len(datos)})")
    if abs(r) > 0.8:
        print("  -> hay relacion: un umbral funcion de la densidad SI se traslada")
    else:
        print("  -> sin relacion con n=4; no hay base para un umbral por paisaje")
