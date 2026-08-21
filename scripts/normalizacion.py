#!/usr/bin/env python3
"""¿Hace la normalización por viñeta que el mismo parapeto valga distinto?

`channels_from_dem` normaliza cada canal con `mm()`, que estira entre los
percentiles `1` y `99` **de esa viñeta**. La consecuencia sospechada:

> el mismo parapeto de `1 m` satura el canal en una llanura y desaparece en una
> ladera de `40 m` de desnivel — **el modelo no ve alturas, ve contrastes
> locales**.

Se comprueba directamente: para cada castro se mide el valor del `LRM` en el
parapeto con las dos normalizaciones, y se correlaciona con el **desnivel total
del recorte**. Si la actual depende del desnivel y la física no, el defecto es
real y la corrección lo arregla.

La normalización física divide por una escala fija en metros —un parapeto son
`0,5`-`1,5 m`, asi que `±2 m` cubre el rango— y recorta. Un metro de relieve vale
lo mismo en todas partes.
"""
from __future__ import annotations

import csv
import math
import sys
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

sys.path.insert(0, "scripts")
from build_trasancos_vignettes import (boxblur, grid_from_points,  # noqa: E402
                                       group_samples_by_tiles, lonlat_to_utm29)
import laspy  # noqa: E402

EXTENT, RES, LRM_R = 512.0, 1.0, 60.0
ESCALA_M = 2.0
N = int(sys.argv[1]) if len(sys.argv) > 1 else 32


def leer(p):
    with Path(p).open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def mm_actual(a):
    lo, hi = np.nanpercentile(a, 1), np.nanpercentile(a, 99)
    if not np.isfinite(lo) or not np.isfinite(hi) or hi - lo < 1e-6:
        return np.zeros_like(a, dtype=np.float32)
    return np.clip((a - lo) / (hi - lo), 0, 1).astype(np.float32)


def mm_fisica(a, escala=ESCALA_M):
    """Escala fija en metros: 0 es -escala, 1 es +escala, y se recorta."""
    return np.clip((a + escala) / (2 * escala), 0, 1).astype(np.float32)


filas = []
for b in ("lugo", "coruna", "ourense", "pontevedra"):
    truth = leer(f"data/{b}_fus_truth_limpia.tsv")
    pred = [r for r in leer(f"data/sweep_val_{b}_v7.tsv")
            if float(r.get("score", 0)) >= 0.80]
    lat0 = sum(float(t["lat"]) for t in truth) / len(truth)
    k = 111_320.0 * math.cos(math.radians(lat0))
    pts = [(float(r["lon"]) * k, float(r["lat"]) * 110_540.0) for r in pred]
    muestras, n_b = [], 0
    for t in truth:
        if n_b >= N // 4:
            break
        tx, ty = float(t["lon"]) * k, float(t["lat"]) * 110_540.0
        if any((px - tx) ** 2 + (py - ty) ** 2 <= 250 ** 2 for px, py in pts):
            x, y = lonlat_to_utm29(float(t["lon"]), float(t["lat"]))
            muestras.append({"id": len(muestras), "x": x, "y": y})
            n_b += 1
    if not muestras:
        continue
    tiles = sorted(str(p) for p in Path(f"data/external/lidar-val-{b}").glob("*.laz"))
    grupos, _ = group_samples_by_tiles(muestras, tiles, EXTENT)
    for tt, celdas in grupos.items():
        half = EXTENT / 2
        ux0 = min(c["x"] for c in celdas) - half; ux1 = max(c["x"] for c in celdas) + half
        uy0 = min(c["y"] for c in celdas) - half; uy1 = max(c["y"] for c in celdas) + half
        xs_l, ys_l, zs_l = [], [], []
        for tp in tt:
            try:
                las = laspy.read(tp)
            except Exception:
                continue
            m0 = np.asarray(las.classification) == 2
            if not m0.any():
                continue
            x, y, z = np.asarray(las.x)[m0], np.asarray(las.y)[m0], np.asarray(las.z)[m0]
            d = (x >= ux0) & (x <= ux1) & (y >= uy0) & (y <= uy1)
            if d.any():
                xs_l.append(x[d]); ys_l.append(y[d]); zs_l.append(z[d])
        if not xs_l:
            continue
        xs = np.concatenate(xs_l); ys = np.concatenate(ys_l); zs = np.concatenate(zs_l)
        for c in celdas:
            bd = (c["x"] - half, c["y"] - half, c["x"] + half, c["y"] + half)
            m = (xs >= bd[0]) & (xs <= bd[2]) & (ys >= bd[1]) & (ys <= bd[3])
            if m.sum() < 2000:
                continue
            dem = grid_from_points(xs[m], ys[m], zs[m], bd, RES)
            if dem is None:
                continue
            lrm = dem - boxblur(dem, int(round(LRM_R / RES)))
            n = lrm.shape[0]; cc = n // 2; r = int(60 / RES)
            nucleo = slice(cc - r, cc + r)
            desnivel = float(np.percentile(dem, 99) - np.percentile(dem, 1))
            # "cuanto vale el parapeto" = rango intercuartilico del nucleo tras normalizar
            a_act = mm_actual(lrm)[nucleo, nucleo]
            a_fis = mm_fisica(lrm)[nucleo, nucleo]
            filas.append({
                "desnivel": desnivel,
                "actual": float(np.percentile(a_act, 75) - np.percentile(a_act, 25)),
                "fisica": float(np.percentile(a_fis, 75) - np.percentile(a_fis, 25)),
            })
            print(f"    desnivel {desnivel:6.1f} m   actual {filas[-1]['actual']:.4f}"
                  f"   fisica {filas[-1]['fisica']:.4f}", flush=True)

if len(filas) < 6:
    raise SystemExit("  muestras insuficientes")
d = np.array([f["desnivel"] for f in filas])
print(f"\n  === {len(filas)} castros, desnivel de {d.min():.0f} a {d.max():.0f} m ===")
for k in ("actual", "fisica"):
    v = np.array([f[k] for f in filas])
    rho, p = spearmanr(d, v)
    etiqueta = "por percentiles (ACTUAL)" if k == "actual" else "por escala fisica"
    print(f"    {etiqueta:<26} rho con el desnivel = {rho:+.3f}  (p={p:.4f})"
          f"   cv={v.std()/max(v.mean(),1e-9):.3f}")
print(f"\n  rho negativo y fuerte = el mismo parapeto vale MENOS donde hay mas desnivel")
print(f"  cv bajo = el objeto se ve igual en todas partes, que es lo que se quiere")
