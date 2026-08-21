#!/usr/bin/env python3
"""Corta y dibuja el relieve de castros catalogados, para mirarlos con los ojos.

**La pregunta**: en A Coruna, `55` de `75` castros catalogados no producen ni una
celda por encima de `0,50` a `250 m`. O el catalogo registra sitios que no se
ven, o el modelo esta ciego en ese terreno. Los datos no lo separan; el terreno
si.

**El diseno, que es lo que hace que valga**: no se miran solo los malos. Se
mezclan los peor puntuados de A Coruna con **controles de puntuacion alta** del
mismo bloque y de Lugo, se barajan y se guardan con **nombre neutro**
(`sitio-00`, `sitio-01`...), de modo que al mirarlos no se sepa cual es cual. La
clave va en `CLAVE.json` y **se lee despues** de juzgar.

Sin eso, mirar treinta candidatos dudosos garantiza ver ambiguedad en todos: es
el sesgo que la propia pregunta induce.

Tres paneles por sitio: **relieve local**, que es donde un parapeto y un foso se
leen mejor; **pendiente**, donde un escarpe es un borde; y **elevacion**.
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
N_DUDOSOS, N_CONTROL = 18, 12
RADIO = 250.0
SALIDA = Path("reports/dudosos-coruna")
SALIDA.mkdir(parents=True, exist_ok=True)


def leer(p):
    with Path(p).open(encoding="utf-8") as fh:
        return [r for r in csv.DictReader(fh, delimiter="\t")
                if r.get("lon") and r.get("lat")]


def puntuar(bloque):
    """Mejor puntuacion del barrido de v7 a RADIO metros de cada castro."""
    truth = leer(f"data/{bloque}_fus_truth_limpia.tsv")
    pred = leer(f"data/sweep_val_{bloque}_v7.tsv")
    lat0 = sum(float(t["lat"]) for t in truth) / len(truth)
    k = 111_320.0 * math.cos(math.radians(lat0))
    celdas = [(float(r["lon"]) * k, float(r["lat"]) * 110_540.0,
               float(r.get("score", 0))) for r in pred]
    out = []
    for t in truth:
        tx, ty = float(t["lon"]) * k, float(t["lat"]) * 110_540.0
        cerca = [s for px, py, s in celdas
                 if (px - tx) ** 2 + (py - ty) ** 2 <= RADIO * RADIO]
        out.append((max(cerca) if cerca else 0.0, t))
    return sorted(out, key=lambda x: x[0])


def panel(canal):
    """Un canal [0,1] a imagen de 8 bits, estirada al 2-98 para que se vea."""
    a = np.asarray(canal, dtype=np.float32)
    a = np.nan_to_num(a, nan=float(np.nanmedian(a)) if np.isfinite(a).any() else 0.5)
    lo, hi = np.percentile(a, 2), np.percentile(a, 98)
    a = np.clip((a - lo) / max(hi - lo, 1e-6), 0, 1)
    return (a * 255).astype(np.uint8)


cor, lug = puntuar("coruna"), puntuar("lugo")
lote = ([("dudoso-coruna", s, t) for s, t in cor[:N_DUDOSOS]]
        + [("control-coruna", s, t) for s, t in cor[-(N_CONTROL // 2):]]
        + [("control-lugo", s, t) for s, t in lug[-(N_CONTROL // 2):]])
random.Random(20260809).shuffle(lote)

clave, por_bloque = [], {}
for i, (grupo, sc, t) in enumerate(lote):
    b = "lugo" if grupo.endswith("lugo") else "coruna"
    por_bloque.setdefault(b, []).append((i, t))
    clave.append({"n": i, "grupo": grupo, "score": round(sc, 3),
                  "nombre": t.get("name", ""), "concello": t.get("concello", ""),
                  "lon": t["lon"], "lat": t["lat"]})

hechas = 0
for b, items in por_bloque.items():
    celdas = []
    for i, t in items:
        x, y = lonlat_to_utm29(float(t["lon"]), float(t["lat"]))
        celdas.append({"id": i, "x": x, "y": y,
                       "lon": float(t["lon"]), "lat": float(t["lat"])})
    tiles = sorted(str(p) for p in Path(f"data/external/lidar-val-{b}").glob("*.laz"))
    grupos, huerf = group_samples_by_tiles(celdas, tiles, EXTENT)
    print(f"  {b}: {sum(len(v) for v in grupos.values())} con LiDAR | {huerf} fuera",
          flush=True)
    for k, v in grupos.items():
        try:
            res = cortar_grupo((list(k), v, EXTENT, RES, None))
        except Exception as e:      # una tesela mala no debe parar el lote entero
            print(f"    grupo fallido: {type(e).__name__} {str(e)[:60]}", flush=True)
            continue
        for cid, lon, lat, arr in res or []:
            a = np.asarray(arr, dtype=np.float32)
            trio = np.concatenate([panel(a[1]), panel(a[2]), panel(a[0])], axis=1)
            Image.fromarray(trio).save(SALIDA / f"sitio-{cid:02d}.png")
            hechas += 1
    print(f"    llevamos {hechas} fichas", flush=True)

(SALIDA / "CLAVE.json").write_text(json.dumps(clave, indent=1, ensure_ascii=False))
print(f"\n  {hechas} fichas en {SALIDA}  (paneles: relieve local | pendiente | elevación)")
print(f"  clave, NO abrir antes de juzgar: {SALIDA}/CLAVE.json")
