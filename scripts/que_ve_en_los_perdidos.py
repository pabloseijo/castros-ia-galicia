#!/usr/bin/env python3
"""En los castros que pierde, ¿el modelo ve algo o no ve nada?

**La ultima hipotesis en pie para A Coruna**, tras descartar densidad LiDAR,
umbral, posicion de la ventana y desplazamiento costa-interior: que alli haya
castros **catalogados pero arrasados** —documentados en papel y sin relieve que
detectar—. A Coruna es la provincia mas urbanizada de Galicia.

Se distingue con la puntuacion que el modelo da **en la celda del castro**:

- puntuacion **cercana a cero** -> no hay nada que ver. El sitio esta destruido,
  o enterrado, o el catalogo lo situa mal. No es un fallo del modelo.
- puntuacion **intermedia** -> el modelo ve algo y no le da bastante. Eso si es
  un fallo del modelo, y se arregla con umbral o con mas ejemplos.

La diferencia importa mucho: en el primer caso el techo de recall de A Coruna es
mas bajo que `1` y perseguirlo es perseguir un fantasma.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "scripts")
from detection_eval import a_metros, agrupar, leer_tsv  # noqa: E402

M = sys.argv[1] if len(sys.argv) > 1 else "v7"
U = float(sys.argv[2]) if len(sys.argv) > 2 else 0.70

for B in ("coruna", "lugo", "ourense", "pontevedra"):
    p = Path(f"data/sweep_val_{B}_{M}.tsv")
    if not p.exists():
        continue
    pred = [x for x in leer_tsv(p, ("lon", "lat", "score")) if "score" in x]
    for x in pred:
        x["score"] = float(x["score"])
    truth = leer_tsv(Path(f"data/{B}_fus_truth_limpia.tsv"))
    lat0 = float(np.mean([t["lat"] for t in truth]))
    cx, cy = a_metros([x["lon"] for x in pred], [x["lat"] for x in pred], lat0)
    sc = np.array([x["score"] for x in pred])
    tx, ty = a_metros([t["lon"] for t in truth], [t["lat"] for t in truth], lat0)

    sel = [x for x in pred if x["score"] >= U]
    hall = set()
    if len(sel) >= 3:
        sx, sy = a_metros([x["lon"] for x in sel], [x["lat"] for x in sel], lat0)
        for g in agrupar(sx, sy, 512.0):
            gx, gy = float(np.mean(sx[g])), float(np.mean(sy[g]))
            d = np.hypot(tx - gx, ty - gy)
            if d.min() <= 500:
                hall.add(int(d.argmin()))

    # puntuacion maxima en un radio de 256 m del castro: lo que el modelo ve alli
    smax_h, smax_p = [], []
    for i in range(len(tx)):
        d = np.hypot(cx - tx[i], cy - ty[i])
        cerca = d <= 256.0
        s = float(sc[cerca].max()) if cerca.any() else 0.0
        (smax_h if i in hall else smax_p).append(s)

    p_ = np.array(smax_p)
    print(f"\n{B} ({len(truth)} castros, {len(hall)} hallados, {len(p_)} perdidos)")
    if len(p_):
        print(f"  puntuacion maxima del modelo EN los castros perdidos:")
        print(f"    mediana {np.median(p_):.3f} | p25 {np.percentile(p_,25):.3f} "
              f"| p75 {np.percentile(p_,75):.3f}")
        print(f"    por debajo de 0,10 (no ve NADA): {100*(p_<0.10).mean():>4.0f}%")
        print(f"    entre 0,10 y {U:.2f} (ve algo y no basta): {100*((p_>=0.10)&(p_<U)).mean():>4.0f}%")
