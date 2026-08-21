#!/usr/bin/env python3
"""¿Cuánto se desalinean la ortofoto y el relieve? La causa candidata de v9.

v9 —la ortofoto como canal de entrada— se refutó con `F1 0,222` en Lugo, y su
página dejó escritas dos causas candidatas. La primera:

> «Sus ortofotos son del mismo vuelo y resolución que su modelo del terreno. Aquí
> se pegan `32.442` recortes JPEG de un servicio distinto, con otra fecha y otro
> registro geométrico. Un desalineamiento de pocos metros entre el canal de
> relieve y el de color enseña a la red a desconfiar de ambos.»

**Estaba diagnosticado y nunca medido.** Y es medible: los dos canales comparten
rasgos lineales —bordes de parcela, caminos, muros—, que en el relieve salen como
pendiente alta y en la ortofoto como bordes de intensidad. La correlación cruzada
entre los dos mapas de bordes, desplazando uno sobre el otro, dice **cuántos
metros hay de desfase y en qué dirección**.

Si el desfase mediano es de `0` a `1 m`, el diagnóstico cae y la causa de v9 hay
que buscarla en la otra hipótesis —que un castro bajo dosel no tiene firma
espectral—. Si son varios metros, v9 merece repetirse con la corrección.
"""
from __future__ import annotations

import csv
import glob
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, "scripts")
from build_trasancos_vignettes import group_samples_by_tiles, lonlat_to_utm29  # noqa: E402
from sweep_grid_lidar import cortar_grupo  # noqa: E402

EXTENT, RES = 512.0, 1.0
MAX_DESP = 12          # metros que se exploran en cada dirección
N = int(sys.argv[1]) if len(sys.argv) > 1 else 24


def bordes(a):
    """Mapa de bordes normalizado: gradiente y fuera la media."""
    gy, gx = np.gradient(a.astype(np.float32))
    m = np.hypot(gx, gy)
    m = m - m.mean()
    s = m.std()
    return m / s if s > 1e-6 else m


def mejor_desplazamiento(A, B, maxd=MAX_DESP):
    """Desplazamiento (dx, dy) que maximiza la correlación de los bordes."""
    n = A.shape[0]
    c = slice(maxd, n - maxd)
    base = A[c, c]
    mejor, arg = -9e9, (0, 0)
    for dy in range(-maxd, maxd + 1):
        for dx in range(-maxd, maxd + 1):
            sub = B[maxd + dy:n - maxd + dy, maxd + dx:n - maxd + dx]
            v = float((base * sub).mean())
            if v > mejor:
                mejor, arg = v, (dx, dy)
    return arg, mejor


# --- viñetas del corpus de v7 que además tengan ortofoto --------------------
idx = list(csv.DictReader(open("data/galicia-vignettes-v7/index.tsv",
                               encoding="utf-8"), delimiter="\t"))
orto_dir = Path("data/ortofotos-corpus")
disponibles = {p.stem for p in orto_dir.glob("*.jpg")}
cand = [r for r in idx if (r.get("group") or "").startswith("castro")
        and r["sid"] in disponibles]
print(f"  {len(cand)} castros del corpus con ortofoto descargada")
if not cand:
    print(f"  (ejemplos de nombres en {orto_dir}): "
          f"{[p.name for p in list(orto_dir.glob('*.jpg'))[:3]]}")
    raise SystemExit(1)

import random  # noqa: E402
sel = random.Random(20260810).sample(cand, min(N, len(cand)))

por_bloque = {}
for r in sel:
    b = (r.get("block") or "").strip()
    por_bloque.setdefault(b, []).append(r)

desps = []
for b, rs in por_bloque.items():
    # el LiDAR está por bloque de validación, no por bloque del corpus: se busca
    # en los cuatro directorios cuál contiene cada viñeta
    for r in rs:
        x, y = lonlat_to_utm29(float(r["lon"]), float(r["lat"]))
        celda = [{"id": 0, "x": x, "y": y,
                  "lon": float(r["lon"]), "lat": float(r["lat"])}]
        hecho = False
        for zona in ("lugo", "coruna", "ourense", "pontevedra"):
            tiles = sorted(str(p) for p in
                           Path(f"data/external/lidar-val-{zona}").glob("*.laz"))
            grupos, huerf = group_samples_by_tiles(celda, tiles, EXTENT)
            if huerf or not grupos:
                continue
            for k, v in grupos.items():
                try:
                    res = cortar_grupo((list(k), v, EXTENT, RES, None))
                except Exception:
                    continue
                for _, _, _, arr in res or []:
                    a = np.asarray(arr, dtype=np.float32)
                    relieve = a[2]                     # pendiente: bordes duros
                    im = Image.open(orto_dir / f"{r['sid']}.jpg").convert("L")
                    if im.size != relieve.shape[::-1]:
                        im = im.resize(relieve.shape[::-1])
                    foto = np.asarray(im, dtype=np.float32)
                    (dx, dy), v_ = mejor_desplazamiento(bordes(relieve), bordes(foto))
                    desps.append((dx, dy, v_, r["sid"]))
                    print(f"    {r['sid'][:22]:<24} desfase ({dx:+3d}, {dy:+3d}) m"
                          f"   corr {v_:+.3f}", flush=True)
                    hecho = True
            if hecho:
                break

if not desps:
    raise SystemExit("  no se pudo cortar ninguna viñeta")

dx = np.array([d[0] for d in desps]); dy = np.array([d[1] for d in desps])
mod = np.hypot(dx, dy)
print(f"\n  === desalineamiento sobre {len(desps)} castros ===")
print(f"    desfase en x:  mediana {np.median(dx):+.1f} m   "
      f"[{np.percentile(dx,10):+.0f}, {np.percentile(dx,90):+.0f}]")
print(f"    desfase en y:  mediana {np.median(dy):+.1f} m   "
      f"[{np.percentile(dy,10):+.0f}, {np.percentile(dy,90):+.0f}]")
print(f"    modulo:        mediana {np.median(mod):.1f} m   "
      f"p90 {np.percentile(mod,90):.1f} m")
print(f"\n  un desfase SISTEMATICO (mediana lejos de 0) se corrige desplazando;")
print(f"  uno ALEATORIO (mediana ~0 pero modulo alto) no tiene arreglo simple.")
