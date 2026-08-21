#!/usr/bin/env python3
"""¿Es el arado o es el alto? El confusor que queda de la hipótesis del suelo.

Medido el `2026-08-09`: en A Coruna los castros que el modelo pierde estan en
terreno claro y liso —labradio— y los que encuentra bajo dosel oscuro y rugoso
(`p = 0,002` sobre `75`). Pero queda una explicacion alternativa que predice lo
mismo:

> **Los castros bajo monte estan en altos que nunca compenso arar.** Si es la
> posicion topografica la que decide, el uso del suelo solo es su consecuencia.

Se separan midiendo la topografia directamente sobre el LiDAR:

- **prominencia**: elevacion del centro menos la mediana del anillo exterior. Un
  castro en un alto destaca; uno en un rellano de vega, no.
- **pendiente media** alrededor del sitio.

Dos preguntas, y la segunda es la que decide:

1. ¿Separan las medidas topograficas a hallados de perdidos?
2. **Dentro de los sitios de topografia parecida, ¿sigue separando el uso del
   suelo?** Si si, el arado tiene efecto propio. Si no, era el alto todo el rato.
"""
from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "scripts")
from build_trasancos_vignettes import group_samples_by_tiles, lonlat_to_utm29  # noqa: E402
from sweep_grid_lidar import cortar_grupo  # noqa: E402

EXTENT, RES = 512.0, 1.0
UMBRAL, RADIO = 0.70, 250.0
BLOQUES = ["lugo", "coruna", "ourense", "pontevedra"]


def leer(p):
    with Path(p).open(encoding="utf-8") as fh:
        return [r for r in csv.DictReader(fh, delimiter="\t")
                if r.get("lon") and r.get("lat")]


salida = []
for b in BLOQUES:
    truth, pred = leer(f"data/{b}_fus_truth_limpia.tsv"), leer(f"data/sweep_val_{b}_v7.tsv")
    lat0 = sum(float(t["lat"]) for t in truth) / len(truth)
    k = 111_320.0 * math.cos(math.radians(lat0))
    celdas_pred = [(float(r["lon"]) * k, float(r["lat"]) * 110_540.0,
                    float(r.get("score", 0))) for r in pred]

    celdas, meta = [], {}
    for j, t in enumerate(truth):
        tx, ty = float(t["lon"]) * k, float(t["lat"]) * 110_540.0
        cerca = [s for px, py, s in celdas_pred
                 if (px - tx) ** 2 + (py - ty) ** 2 <= RADIO * RADIO]
        sc = max(cerca) if cerca else 0.0
        x, y = lonlat_to_utm29(float(t["lon"]), float(t["lat"]))
        cid = len(celdas)
        celdas.append({"id": cid, "x": x, "y": y,
                       "lon": float(t["lon"]), "lat": float(t["lat"])})
        meta[cid] = {"bloque": b, "score": round(sc, 3), "hallado": int(sc >= UMBRAL),
                     "nombre": t.get("name", "")}

    tiles = sorted(str(p) for p in Path(f"data/external/lidar-val-{b}").glob("*.laz"))
    grupos, huerf = group_samples_by_tiles(celdas, tiles, EXTENT)
    print(f"  {b}: {sum(len(v) for v in grupos.values())} con LiDAR | {huerf} fuera",
          flush=True)
    hechas = 0
    for kk, vv in grupos.items():
        try:
            res = cortar_grupo((list(kk), vv, EXTENT, RES, None))
        except Exception as e:
            print(f"    grupo fallido: {type(e).__name__} {str(e)[:50]}", flush=True)
            continue
        for cid, lon, lat, arr in res or []:
            a = np.asarray(arr, dtype=np.float32)
            dtm, slope = a[0], a[2]           # canal 0 normalizado, canal 2 pendiente
            n = dtm.shape[0]
            c = n // 2
            r_in, r_out = n // 8, n // 2 - 4  # nucleo de 64 m, anillo al borde
            yy, xx = np.ogrid[:n, :n]
            d = np.hypot(yy - c, xx - c)
            nucleo = dtm[d <= r_in]
            anillo = dtm[(d >= r_out - 20) & (d <= r_out)]
            if nucleo.size < 10 or anillo.size < 10:
                continue
            salida.append({**meta[cid],
                           # el DTM viene normalizado por viñeta: la prominencia
                           # es relativa dentro de su propio recuadro, que es
                           # justo lo que interesa aqui
                           "prominencia": round(float(np.median(nucleo) -
                                                      np.median(anillo)), 4),
                           "pendiente": round(float(np.mean(slope)), 4)})
            hechas += 1
    print(f"    {hechas} medidos", flush=True)

Path("data/topografia_214.json").write_text(json.dumps(salida))
print(f"\n  {len(salida)} castros con topografia -> data/topografia_214.json")
