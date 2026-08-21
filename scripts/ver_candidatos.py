#!/usr/bin/env python3
"""Dibuja el relieve de los mejores candidatos a castro inedito, para mirarlos.

`candidatos_ineditos.py` da `427` sitios que el modelo señala y el catalogo no
conoce. Esto corta los `14` de puntuacion mas alta y **mezcla `6` castros
catalogados de los que el modelo si detecta**, barajados y con nombre neutro.

Los controles no son decoracion: sin ellos, mirar catorce candidatos con la
esperanza de que sean castros es la receta de ver anillos donde no los hay. Con
ellos, si los controles se distinguen y los candidatos no, la respuesta es que
los candidatos no valen — y si se confunden, es que valen.

La clave va aparte y **no se abre hasta emitir los juicios**.
"""
from __future__ import annotations

import csv
import json
import random
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, "scripts")
from build_trasancos_vignettes import group_samples_by_tiles, lonlat_to_utm29  # noqa: E402
from sweep_grid_lidar import cortar_grupo  # noqa: E402

EXTENT, RES = 512.0, 1.0
N_CAND, N_CTRL = 14, 6
SALIDA = Path("reports/candidatos")
SALIDA.mkdir(parents=True, exist_ok=True)


def leer(p):
    with Path(p).open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


cand = leer("data/candidatos-ineditos.tsv")[:N_CAND]
lote = [("candidato", c["bloque"], float(c["lon"]), float(c["lat"]),
         float(c["score"]), "") for c in cand]

# controles: castros catalogados que el modelo SI detecta, uno por bloque a lo sumo
vistos = 0
for b in ("lugo", "coruna", "ourense", "pontevedra"):
    truth = leer(f"data/{b}_fus_truth_limpia.tsv")
    pred = [r for r in leer(f"data/sweep_val_{b}_v7.tsv")
            if float(r.get("score", 0)) >= 0.85]
    import math
    lat0 = sum(float(t["lat"]) for t in truth) / len(truth)
    k = 111_320.0 * math.cos(math.radians(lat0))
    pts = [(float(r["lon"]) * k, float(r["lat"]) * 110_540.0) for r in pred]
    for t in truth:
        if vistos >= N_CTRL:
            break
        tx, ty = float(t["lon"]) * k, float(t["lat"]) * 110_540.0
        if any((px - tx) ** 2 + (py - ty) ** 2 <= 250 ** 2 for px, py in pts):
            lote.append(("control", b, float(t["lon"]), float(t["lat"]), 0.0,
                         t.get("name", "")))
            vistos += 1
            break
    # segundo del mismo bloque si aun faltan
    if vistos < N_CTRL:
        for t in truth[::-1]:
            tx, ty = float(t["lon"]) * k, float(t["lat"]) * 110_540.0
            if any((px - tx) ** 2 + (py - ty) ** 2 <= 250 ** 2 for px, py in pts):
                lote.append(("control", b, float(t["lon"]), float(t["lat"]), 0.0,
                             t.get("name", "")))
                vistos += 1
                break

random.Random(20260809).shuffle(lote)
clave, por_bloque = [], {}
for i, (grupo, b, lon, lat, sc, nombre) in enumerate(lote):
    por_bloque.setdefault(b, []).append((i, lon, lat))
    clave.append({"n": i, "grupo": grupo, "bloque": b, "score": sc,
                  "nombre": nombre, "lon": lon, "lat": lat})


def panel(c):
    a = np.nan_to_num(np.asarray(c, dtype=np.float32), nan=0.5)
    lo, hi = np.percentile(a, 2), np.percentile(a, 98)
    return (np.clip((a - lo) / max(hi - lo, 1e-6), 0, 1) * 255).astype(np.uint8)


hechas = 0
for b, items in por_bloque.items():
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
            print(f"    grupo fallido: {type(e).__name__} {str(e)[:60]}", flush=True)
            continue
        for cid, lon, lat, arr in res or []:
            a = np.asarray(arr, dtype=np.float32)
            trio = np.concatenate([panel(a[1]), panel(a[2]), panel(a[0])], axis=1)
            Image.fromarray(trio).save(SALIDA / f"c-{cid:02d}.png")
            hechas += 1

(SALIDA / "CLAVE.json").write_text(json.dumps(clave, indent=1, ensure_ascii=False))
print(f"\n  {hechas} fichas en {SALIDA} | clave sin abrir en CLAVE.json")
