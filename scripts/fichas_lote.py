#!/usr/bin/env python3
"""Corta el relieve de N candidatos para poder mirarlos en tandas.

La revisión del `2026-08-09` fue de `14` candidatos con `6` controles, y dejó
`11` ambiguos. Con `419` en la lista, mirar catorce no dice gran cosa: hace falta
volumen para saber **qué fracción de la cola merece la pena**, que es el número
que decide si el entregable sirve.

Se cortan por puntuación descendente y **con controles intercalados** —castros
catalogados que el modelo detecta— para poder medirse: si en una tanda los
controles no se distinguen, el juicio de esa tanda no vale.

Uso: fichas_lote.py [cuantos] [cuantos_controles]
"""
from __future__ import annotations

import csv
import json
import math
import random
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, "scripts")
from build_trasancos_vignettes import group_samples_by_tiles, lonlat_to_utm29  # noqa: E402
from sweep_grid_lidar import cortar_grupo  # noqa: E402

EXTENT, RES = 512.0, 1.0
N_CAND = int(sys.argv[1]) if len(sys.argv) > 1 else 60
N_CTRL = int(sys.argv[2]) if len(sys.argv) > 2 else 12
SALIDA = Path("reports/lote-candidatos")
SALIDA.mkdir(parents=True, exist_ok=True)


def leer(p):
    with Path(p).open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


cand = leer("data/candidatos-ineditos.tsv")[:N_CAND]
lote = [("candidato", c["bloque"], float(c["lon"]), float(c["lat"]),
         float(c["score"]), "") for c in cand]

# controles: catalogados que el modelo detecta con holgura, repartidos por bloque
rnd = random.Random(20260810)
por_bloque = max(1, N_CTRL // 4)
for b in ("lugo", "coruna", "ourense", "pontevedra"):
    truth = leer(f"data/{b}_fus_truth_limpia.tsv")
    pred = [r for r in leer(f"data/sweep_val_{b}_v7.tsv")
            if float(r.get("score", 0)) >= 0.85]
    lat0 = sum(float(t["lat"]) for t in truth) / len(truth)
    k = 111_320.0 * math.cos(math.radians(lat0))
    pts = [(float(r["lon"]) * k, float(r["lat"]) * 110_540.0) for r in pred]
    buenos = []
    for t in truth:
        tx, ty = float(t["lon"]) * k, float(t["lat"]) * 110_540.0
        if any((px - tx) ** 2 + (py - ty) ** 2 <= 250 ** 2 for px, py in pts):
            buenos.append(t)
    for t in rnd.sample(buenos, min(por_bloque, len(buenos))):
        lote.append(("control", b, float(t["lon"]), float(t["lat"]), 0.0,
                     t.get("name", "")))

rnd.shuffle(lote)
clave, agrupado = [], {}
for i, (grupo, b, lon, lat, sc, nombre) in enumerate(lote):
    agrupado.setdefault(b, []).append((i, lon, lat))
    clave.append({"n": i, "grupo": grupo, "bloque": b, "score": sc,
                  "nombre": nombre, "lon": lon, "lat": lat})


def panel(c):
    a = np.nan_to_num(np.asarray(c, dtype=np.float32), nan=0.5)
    lo, hi = np.percentile(a, 2), np.percentile(a, 98)
    return (np.clip((a - lo) / max(hi - lo, 1e-6), 0, 1) * 255).astype(np.uint8)


hechas = 0
for b, items in agrupado.items():
    celdas = []
    for i, lon, lat in items:
        x, y = lonlat_to_utm29(lon, lat)
        celdas.append({"id": i, "x": x, "y": y, "lon": lon, "lat": lat})
    tiles = sorted(str(p) for p in Path(f"data/external/lidar-val-{b}").glob("*.laz"))
    grupos, huerf = group_samples_by_tiles(celdas, tiles, EXTENT)
    print(f"  {b}: {sum(len(v) for v in grupos.values())} con LiDAR | {huerf} fuera",
          flush=True)
    for k_, v in grupos.items():
        try:
            res = cortar_grupo((list(k_), v, EXTENT, RES, None))
        except Exception as e:
            print(f"    grupo fallido: {type(e).__name__} {str(e)[:50]}", flush=True)
            continue
        for cid, lon, lat, arr in res or []:
            a = np.asarray(arr, dtype=np.float32)
            # solo relieve local y pendiente: son los dos donde se ve el recinto,
            # y con dos paneles caben más fichas por hoja
            Image.fromarray(np.concatenate([panel(a[1]), panel(a[2])], axis=1)) \
                 .save(SALIDA / f"f-{cid:03d}.png")
            hechas += 1
    print(f"    llevamos {hechas}", flush=True)

(SALIDA / "CLAVE.json").write_text(json.dumps(clave, indent=1, ensure_ascii=False))
print(f"\n  {hechas} fichas en {SALIDA} ({len(cand)} candidatos + "
      f"{len(lote)-len(cand)} controles)")
