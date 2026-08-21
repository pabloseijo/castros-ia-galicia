#!/usr/bin/env python3
"""La lista de candidatos a castro inedito: el entregable, no la metrica.

Todo lo que este proyecto mide —`F1`, recall, precision— es instrumental. **Lo
que se busca son sitios que el catalogo no conoce.** Esos, en la evaluacion,
cuentan como falsos positivos; en el objetivo real, son el producto.

Se construye con lo medido el `2026-08-09`:

- **Union de detectores** en vez del mejor solo. v7 y v11p encuentran castros
  distintos —`28` y `27` que el otro no ve—, asi que la union halla `158` de
  `214` donde la mejor sola halla `119`. Se fusiona por **maximo por celda**.
- **Umbral `0,60`**, que es donde la union rinde mas por ficha revisada. A `0,50`
  el enlace simple encadena todo en grupos cuyo centro ya no cae sobre nada.

Y se quita lo que no es hallazgo:

- lo que cae sobre un **castro catalogado** (a `500 m`): ya se conoce;
- lo que cae sobre la **mascara de entrenamiento**: el modelo lo vio, es memoria;
- lo que toca el **margen** del bloque, donde la cobertura es parcial.

Sale ordenado por puntuacion, que es el orden en que conviene revisarlo: el coste
de revision es el entregable y se gasta de arriba abajo.
"""
from __future__ import annotations

import csv
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, "scripts")
from detection_eval import a_metros, agrupar  # noqa: E402

BLOQUES = ["lugo", "coruna", "ourense", "pontevedra"]
# **Los cuatro, no dos.** Medido el `2026-08-10` con los barridos de v12 y v14
# cerrados: la unión de los cuatro a `0,60` encuentra `173` de los `214` castros
# catalogados (`recall 0,808`) contra los `95` de v7 sola. v12 y v14 están
# refutados como modelos —`0,459` y `0,431` de `F1`— y aun así suman aquí, porque
# **encuentran castros que v7 no ve**: `25` y `26` respectivamente.
MODELOS = ["v7", "v11p", "v12", "v14"]
# **Los mismos valores con los que se evaluo, no otros.** El primer intento puso
# `enlace 120 m` y `min_celdas 2`, y salieron **cero candidatos en los cuatro
# bloques**: la rejilla del barrido es de `256 m`, asi que con un enlace de `120`
# ninguna celda puede unirse a ninguna y todos los grupos quedan de una sola
# celda, que el minimo de dos elimina. Un cero por parametros mal puestos es
# indistinguible de un cero real, y por eso se copian del evaluador.
UMBRAL, ENLACE, MIN_CELDAS, TOL = 0.60, 512.0, 1, 500.0
# El margen si es una eleccion propia: en el borde del bloque la cobertura es
# parcial y un grupo de ahi no es revisable. La evaluacion usa `0` por defecto.
MARGEN = 300.0
SALIDA = Path("data/candidatos-ineditos.tsv")


def leer(p):
    with Path(p).open(encoding="utf-8") as fh:
        return [r for r in csv.DictReader(fh, delimiter="\t")
                if r.get("lon") and r.get("lat")]


filas = []
for b in BLOQUES:
    # union = maximo por celda; una celda pasa el umbral si algun modelo la pasa
    mejor = {}
    for m in MODELOS:
        p = Path(f"data/sweep_val_{b}_{m}.tsv")
        if not p.exists():
            continue
        for r in leer(p):
            cid = r.get("id") or f"{r['lon']},{r['lat']}"
            s = float(r.get("score", 0))
            if cid not in mejor or s > mejor[cid][2]:
                mejor[cid] = (float(r["lon"]), float(r["lat"]), s)
    if not mejor:
        continue
    todas = list(mejor.values())
    lat0 = sum(v[1] for v in todas) / len(todas)
    sel = [v for v in todas if v[2] >= UMBRAL]
    if not sel:
        continue

    px, py = a_metros([v[0] for v in sel], [v[1] for v in sel], lat0)
    grupos = [g for g in agrupar(px, py, ENLACE, 1) if len(g) >= MIN_CELDAS]

    ax, ay = a_metros([v[0] for v in todas], [v[1] for v in todas], lat0)
    x0, x1, y0, y1 = ax.min(), ax.max(), ay.min(), ay.max()

    truth = leer(f"data/{b}_fus_truth_limpia.tsv")
    masc = leer(f"data/{b}_fus_mascara_train.tsv")
    tx, ty = a_metros([t["lon"] for t in truth], [t["lat"] for t in truth], lat0)
    mx, my = a_metros([m["lon"] for m in masc], [m["lat"] for m in masc], lat0)

    n_cat = n_masc = n_borde = 0
    for g in grupos:
        # **La exclusion se mide donde se va a reportar, y ademas sobre TODAS las
        # celdas del grupo.** El primer intento comprobaba el centroide y
        # reportaba la celda de puntuacion maxima: en un grupo alargado el
        # centroide cae lejos del castro catalogado, el grupo no se excluye, y la
        # celda maxima resulta ser el castro. Paso de verdad — el unico candidato
        # que parecia un recinto claro al mirarlo a ciegas era «Castro do Monte da
        # Guia», a `77 m`, ya catalogado. Un fallo asi no produce ruido: produce
        # un falso hallazgo, que es mucho peor.
        i = max(g, key=lambda j: sel[j][2])
        cx, cy = float(px[i]), float(py[i])
        gx, gy = px[g], py[g]
        if not (x0 + MARGEN <= cx <= x1 - MARGEN and y0 + MARGEN <= cy <= y1 - MARGEN):
            n_borde += 1
            continue
        if min(float(np.hypot(tx - a, ty - b).min()) for a, b in zip(gx, gy)) <= TOL:
            n_cat += 1
            continue
        if len(mx) and min(float(np.hypot(mx - a, my - b).min())
                           for a, b in zip(gx, gy)) <= TOL:
            n_masc += 1
            continue
        filas.append({"bloque": b, "lon": f"{sel[i][0]:.6f}", "lat": f"{sel[i][1]:.6f}",
                      "score": f"{sel[i][2]:.3f}", "celdas": len(g)})
    print(f"  {b}: {len(grupos)} grupos | {n_cat} ya catalogados | "
          f"{n_masc} vistos al entrenar | {n_borde} en el margen | "
          f"{sum(1 for f in filas if f['bloque']==b)} CANDIDATOS", flush=True)

filas.sort(key=lambda r: -float(r["score"]))
with SALIDA.open("w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=["bloque", "lon", "lat", "score", "celdas"],
                       delimiter="\t")
    w.writeheader()
    w.writerows(filas)

print(f"\n  {len(filas)} candidatos a castro inedito -> {SALIDA}")
print(f"  los 10 mejores:")
for r in filas[:10]:
    print(f"    {r['score']}  {r['bloque']:<11} {r['lat']}, {r['lon']}  "
          f"({r['celdas']} celdas)")
