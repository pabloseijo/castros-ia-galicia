#!/usr/bin/env python3
"""¿Los castros que el modelo NO encuentra caen en el borde de la ventana?

**El problema que investiga.** A Coruna tiene buena precision (`0,769`) y pierde
`55` de `75` castros. Antes de tocar el modelo hay que descartar una causa mucho
mas tonta: que el barrido los vea **de refilon**.

La ventana es de `512 m` y el paso de `256 m`, o sea `50%` de solape. Un castro
justo en la esquina de cuatro ventanas aparece **en el borde de las cuatro** y en
el centro de ninguna. Si eso pesa, se arregla con mas solape —un parametro—, no
con otro modelo.

**Como se mide sin gastar GPU**: para cada castro conocido, la distancia al centro
de la ventana mas cercana. Si los perdidos estan sistematicamente mas lejos del
centro que los encontrados, el mecanismo existe.

Uso:  python3 scripts/castros_en_el_borde.py coruna v7 0.70
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "scripts")
from detection_eval import a_metros, agrupar, leer_tsv  # noqa: E402

B = sys.argv[1] if len(sys.argv) > 1 else "coruna"
M = sys.argv[2] if len(sys.argv) > 2 else "v7"
U = float(sys.argv[3]) if len(sys.argv) > 3 else 0.70

pred = [p for p in leer_tsv(Path(f"data/sweep_val_{B}_{M}.tsv"), ("lon", "lat", "score"))
        if "score" in p]
for p in pred:
    p["score"] = float(p["score"])
truth = leer_tsv(Path(f"data/{B}_fus_truth_limpia.tsv"))
lat0 = float(np.mean([t["lat"] for t in truth]))

# TODAS las celdas del barrido son centros de ventana
cx, cy = a_metros([p["lon"] for p in pred], [p["lat"] for p in pred], lat0)
tx, ty = a_metros([t["lon"] for t in truth], [t["lat"] for t in truth], lat0)

sel = [p for p in pred if p["score"] >= U]
sx, sy = a_metros([p["lon"] for p in sel], [p["lat"] for p in sel], lat0)
hallados = set()
if len(sx):
    for g in agrupar(sx, sy, 512.0):
        gx, gy = float(np.mean(sx[g])), float(np.mean(sy[g]))
        d = np.hypot(tx - gx, ty - gy)
        if d.min() <= 500:
            hallados.add(int(d.argmin()))

d_centro, clase = [], []
for i in range(len(tx)):
    d = np.hypot(cx - tx[i], cy - ty[i])
    d_centro.append(float(d.min()))
    clase.append("hallado" if i in hallados else "perdido")
d_centro = np.array(d_centro); clase = np.array(clase)

print(f"{B} / {M} a umbral {U}: {len(truth)} castros, "
      f"{(clase=='hallado').sum()} hallados, {(clase=='perdido').sum()} perdidos")
print(f"\n  {'grupo':<12}{'n':>5}{'dist. al centro de ventana':>30}")
for c in ("hallado", "perdido"):
    v = d_centro[clase == c]
    if len(v):
        print(f"  {c:<12}{len(v):>5}      mediana {np.median(v):>6.0f} m | "
              f"media {v.mean():>6.0f} m | max {v.max():>6.0f} m")

a = d_centro[clase == "hallado"]; b = d_centro[clase == "perdido"]
if len(a) and len(b):
    U_ = sum(1 for x in a for y in b if x < y) / (len(a)*len(b))
    print(f"\n  P(un hallado este mas cerca del centro que un perdido) = {U_:.3f}")
    print("  (0,5 = el borde no influye | >0,6 = el solape importa)")
    print(f"\n  paso de la rejilla: 256 m -> un punto cualquiera esta como mucho")
    print(f"  a {256/2*1.415:.0f} m del centro mas cercano. Medido: max {d_centro.max():.0f} m")
