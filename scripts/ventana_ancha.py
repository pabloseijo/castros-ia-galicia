#!/usr/bin/env python3
"""Los castros perdidos de A Coruna, ¿no caben en la ventana de 512 m?

La mirada a ciegas del `2026-08-09` dejo `6` de los `18` perdidos como «dudosos»,
y varios de ellos mostraban **formas redondeadas grandes que el recuadro
cortaba**. Si un castro mide mas de `512 m`, el modelo no puede verlo entero: no
es que sea invisible, es que no cabe.

Esto corta los mismos `18` sitios a **`1.024 m`**, el doble de ancho, y los dibuja
al lado del recorte original. Si al abrir el campo aparece un recinto que antes se
salia, la causa no es el catalogo: es la ventana, y eso **si** se arregla.

Se conserva el mismo nombre `sitio-NN` para poder comparar ficha con ficha.
"""
from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, "scripts")
from build_trasancos_vignettes import group_samples_by_tiles, lonlat_to_utm29  # noqa: E402
from sweep_grid_lidar import cortar_grupo  # noqa: E402

EXTENT, RES = 1024.0, 1.0
ORIG = Path("reports/dudosos-coruna")
SALIDA = Path("reports/dudosos-coruna-ancho")
SALIDA.mkdir(parents=True, exist_ok=True)

clave = json.loads((ORIG / "CLAVE.json").read_text())
perdidos = [d for d in clave if d["grupo"] == "dudoso-coruna"]
print(f"  {len(perdidos)} sitios perdidos de A Coruna, ventana {EXTENT:.0f} m", flush=True)

celdas = []
for d in perdidos:
    x, y = lonlat_to_utm29(float(d["lon"]), float(d["lat"]))
    celdas.append({"id": d["n"], "x": x, "y": y,
                   "lon": float(d["lon"]), "lat": float(d["lat"])})

tiles = sorted(str(p) for p in Path("data/external/lidar-val-coruna").glob("*.laz"))
grupos, huerf = group_samples_by_tiles(celdas, tiles, EXTENT)
print(f"  con LiDAR: {sum(len(v) for v in grupos.values())} | fuera: {huerf}", flush=True)


def panel(canal):
    a = np.nan_to_num(np.asarray(canal, dtype=np.float32), nan=0.5)
    lo, hi = np.percentile(a, 2), np.percentile(a, 98)
    return (np.clip((a - lo) / max(hi - lo, 1e-6), 0, 1) * 255).astype(np.uint8)


hechas = 0
for k, v in grupos.items():
    try:
        res = cortar_grupo((list(k), v, EXTENT, RES, None))
    except Exception as e:
        print(f"    grupo fallido: {type(e).__name__} {str(e)[:60]}", flush=True)
        continue
    for cid, lon, lat, arr in res or []:
        a = np.asarray(arr, dtype=np.float32)
        ancho = np.concatenate([panel(a[1]), panel(a[2])], axis=1)
        # el recorte de 512 m, escalado al mismo alto, para comparar de un vistazo
        vieja = ORIG / f"sitio-{cid:02d}.png"
        if vieja.exists():
            im = Image.open(vieja).convert("L")
            im = im.crop((0, 0, im.width * 2 // 3, im.height))   # solo LRM y pendiente
            im = im.resize((ancho.shape[1] // 2, ancho.shape[0]))
            comp = Image.new("L", (ancho.shape[1] + im.width, ancho.shape[0]), 0)
            comp.paste(Image.fromarray(ancho), (0, 0))
            comp.paste(im, (ancho.shape[1], 0))
        else:
            comp = Image.fromarray(ancho)
        comp.save(SALIDA / f"sitio-{cid:02d}.png")
        hechas += 1

print(f"\n  {hechas} fichas anchas en {SALIDA}")
print("  paneles: relieve 1024 m | pendiente 1024 m | el recorte de 512 m encajado")
