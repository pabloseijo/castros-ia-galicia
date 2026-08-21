#!/usr/bin/env python3
"""¿Está el paisaje de A Coruña representado en el entrenamiento?

**La hipotesis viva.** A Coruna tiene la mejor precision (`0,769`), la mayor
densidad LiDAR de los cuatro bloques (`2,62 pt/m²`) y pierde `55` de `75` castros.
Tres causas ya descartadas con medida: densidad, umbral y posicion de la ventana.

Queda la incomoda: que **sus castros sean distintos** y el entrenamiento no tenga
ejemplos parecidos. A Coruna es costa; si los positivos de entrenamiento son casi
todos de interior, el modelo nunca ha visto un castro costero.

**Como se mide sin modelo ni GPU**: por la geografia de los positivos. Distancia
al mar y altitud son las dos variables que separan costa de interior, y las dos
salen del propio indice —la altitud, del DEM ya cortado—.

Se compara la distribucion de los positivos de `train` con la de los castros de
cada bloque de validacion. Si la de A Coruna cae fuera del rango de `train`, el
modelo se examina de algo que no ha visto.
"""
from __future__ import annotations

import csv
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

# Costa atlantica gallega, muy simplificada: el meridiano del cabo Fisterra y la
# linea norte. Sirve para ordenar, no para navegar.
def dist_costa_km(lat, lon):
    # distancia al oeste (Atlantico) y al norte (Cantabrico), la menor
    d_oeste = (lon - (-9.30)) * 111.32 * math.cos(math.radians(lat))
    d_norte = (43.79 - lat) * 111.32
    return max(0.0, min(d_oeste, d_norte))

idx = Path("data/galicia-vignettes-v7/index.tsv")
filas = list(csv.DictReader(idx.open(encoding="utf-8"), delimiter="\t"))
por_grupo = defaultdict(list)
for r in filas:
    g = (r.get("group") or "").strip()
    s = (r.get("split") or "").strip()
    if not g.startswith(("castro", "mamoa")):
        continue
    try:
        la, lo = float(r["lat"]), float(r["lon"])
    except (TypeError, ValueError, KeyError):
        continue
    por_grupo[s].append(dist_costa_km(la, lo))

print(f"  {'conjunto':<14}{'n':>5}{'dist. a la costa (km)':>34}")
for s in ("train", "val", "test_o_val"):
    v = np.array(por_grupo.get(s, []))
    if len(v):
        print(f"  {s:<14}{len(v):>5}   p10 {np.percentile(v,10):>5.0f} | "
              f"mediana {np.median(v):>5.0f} | p90 {np.percentile(v,90):>5.0f}")

# los castros de cada bloque de validacion
BLOQ = {"lugo": (-7.375, 42.625, -7.125, 42.875),
        "coruna": (-8.50, 43.00, -8.25, 43.25),
        "ourense": (-8.25, 42.25, -8.00, 42.50),
        "pontevedra": (-8.875, 42.125, -8.625, 42.375)}
print(f"\n  {'bloque':<12}{'castros':>8}{'dist. a la costa (km)':>32}")
tr = np.array(por_grupo.get("train", []))
for b, (w, s_, e, n) in BLOQ.items():
    p = Path(f"data/{b}_fus_truth_limpia.tsv")
    if not p.exists():
        continue
    ds = []
    with p.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            try:
                ds.append(dist_costa_km(float(r["lat"]), float(r["lon"])))
            except (TypeError, ValueError, KeyError):
                pass
    if not ds:
        continue
    d = np.array(ds)
    # ¿que fraccion de train esta en el rango de este bloque?
    lo_, hi_ = np.percentile(d, 10), np.percentile(d, 90)
    dentro = float(((tr >= lo_) & (tr <= hi_)).mean()) if len(tr) else 0.0
    print(f"  {b:<12}{len(d):>8}   mediana {np.median(d):>5.0f} | "
          f"train en su rango: {100*dentro:>4.0f}%")
