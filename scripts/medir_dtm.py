#!/usr/bin/env python3
"""Fase A del preregistro: ¿conservan más señal los arreglos del DTM?

Cada arreglo propuesto afirma lo mismo —**que conserva relieve de parapeto que
hoy se pierde**— y eso se puede medir sobre el DTM directamente, sin entrenar
nada. Si un cambio no mejora la relacion entre el relieve del objeto y el ruido
del fondo, no hay razon para gastar seis horas de nodo reentrenando con el.

Se comparan cuatro construcciones del DTM sobre los mismos puntos:

  · **min** — lo actual: el retorno mas bajo de cada celda.
  · **p10** — percentil `10` de los retornos de la celda.
  · **min+tin** — el minimo, pero rellenando huecos por interpolacion lineal.
  · **p10+tin** — las dos cosas.

Y la medida que decide, para cada castro:

  · **senal**: rango intercuartilico del `LRM` en el nucleo (`120 m` centrales),
    que es donde esta el recinto;
  · **ruido**: desviacion tipica del `LRM` en el anillo exterior, terreno de
    fondo;
  · **razon senal/ruido**, que es lo que decide si el objeto se ve.

Uso: medir_dtm.py [n_castros]
"""
from __future__ import annotations

import csv
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "scripts")
from build_trasancos_vignettes import (GROUND_CLASS, boxblur,  # noqa: E402
                                       group_samples_by_tiles, lonlat_to_utm29)

EXTENT, RES = 512.0, 1.0
N = int(sys.argv[1]) if len(sys.argv) > 1 else 40
LRM_R = 60.0


def leer(p):
    with Path(p).open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def rasterizar(xs, ys, zs, bounds, res, estimador, relleno):
    minx, miny, maxx, maxy = bounds
    w = int(round((maxx - minx) / res))
    h = int(round((maxy - miny) / res))
    ix = np.clip(((xs - minx) / res).astype(np.int64), 0, w - 1)
    iy = np.clip(((maxy - ys) / res).astype(np.int64), 0, h - 1)
    flat = iy * w + ix

    if estimador == "min":
        dem = np.full(w * h, np.inf)
        np.minimum.at(dem, flat, zs)
        dem[~np.isfinite(dem)] = np.nan
    else:
        # percentil por celda: se agrupa por indice y se toma el cuantil
        orden = np.argsort(flat, kind="stable")
        f_ord, z_ord = flat[orden], zs[orden]
        cortes = np.searchsorted(f_ord, np.unique(f_ord))
        dem = np.full(w * h, np.nan)
        limites = list(cortes) + [len(f_ord)]
        for a, b in zip(limites[:-1], limites[1:]):
            dem[f_ord[a]] = np.quantile(z_ord[a:b], 0.10)
    dem = dem.reshape(h, w)

    valid = np.isfinite(dem)
    if valid.mean() < 0.30:
        return None
    if not valid.all():
        if relleno == "tin":
            from scipy.interpolate import griddata
            yy, xx = np.nonzero(valid)
            hy, hx = np.nonzero(~valid)
            rell = griddata((yy, xx), dem[valid], (hy, hx), method="linear")
            # los que quedan fuera del casco convexo no los cubre la lineal
            malos = ~np.isfinite(rell)
            if malos.any():
                rell[malos] = griddata((yy, xx), dem[valid],
                                       (hy[malos], hx[malos]), method="nearest")
            dem[hy, hx] = rell
        else:
            from scipy import ndimage
            idx = ndimage.distance_transform_edt(
                ~valid, return_distances=False, return_indices=True)
            dem = dem[tuple(idx)]
    return dem.astype(np.float32)


def suavizar_dem(dem, sigma_m=1.5, res=RES):
    """Suavizado gaussiano del DEM antes de derivar canales.

    **Nace de refutar la hipotesis anterior.** Medido el `2026-08-10`: con
    `1,4`-`4,1 pt/m2` y celdas de `1 m` hay **uno o dos puntos por celda**, asi
    que el percentil `10` *es* el minimo y cambiar de estimador no puede hacer
    nada. El DTM no esta limitado por el estimador sino **por el muestreo**.

    Contra el ruido de muestreo lo que sirve es filtrar a la escala donde el
    objeto no esta: un parapeto mide `5`-`15 m` de ancho, asi que un suavizado de
    `1,5 m` quita ruido de celda sin tocar el parapeto.
    """
    from scipy.ndimage import gaussian_filter
    return gaussian_filter(dem, sigma=sigma_m / res).astype(np.float32)


def senal_ruido(dem, res=RES):
    """Relieve local en el nucleo contra el del anillo exterior."""
    lrm = dem - boxblur(dem, int(round(LRM_R / res)))
    n = lrm.shape[0]
    c = n // 2
    r_nuc = int(60 / res)          # nucleo de 120 m de lado
    r_bor = int(40 / res)
    nucleo = lrm[c - r_nuc:c + r_nuc, c - r_nuc:c + r_nuc]
    anillo = np.concatenate([lrm[:r_bor, :].ravel(), lrm[-r_bor:, :].ravel(),
                             lrm[:, :r_bor].ravel(), lrm[:, -r_bor:].ravel()])
    senal = float(np.percentile(nucleo, 75) - np.percentile(nucleo, 25))
    ruido = float(np.std(anillo))
    return senal, ruido, (senal / ruido if ruido > 1e-6 else np.nan)


# --- castros que el modelo detecta, repartidos por bloque -------------------
import laspy  # noqa: E402

muestras, tiles_por_bloque = [], {}
for b in ("lugo", "coruna", "ourense", "pontevedra"):
    truth = leer(f"data/{b}_fus_truth_limpia.tsv")
    pred = [r for r in leer(f"data/sweep_val_{b}_v7.tsv")
            if float(r.get("score", 0)) >= 0.80]
    lat0 = sum(float(t["lat"]) for t in truth) / len(truth)
    k = 111_320.0 * math.cos(math.radians(lat0))
    pts = [(float(r["lon"]) * k, float(r["lat"]) * 110_540.0) for r in pred]
    n_b = 0
    for t in truth:
        if n_b >= N // 4:
            break
        tx, ty = float(t["lon"]) * k, float(t["lat"]) * 110_540.0
        if any((px - tx) ** 2 + (py - ty) ** 2 <= 250 ** 2 for px, py in pts):
            x, y = lonlat_to_utm29(float(t["lon"]), float(t["lat"]))
            muestras.append({"id": len(muestras), "x": x, "y": y, "bloque": b,
                             "nombre": (t.get("name") or "?")[:30]})
            n_b += 1
    tiles_por_bloque[b] = sorted(str(p) for p in
                                 Path(f"data/external/lidar-val-{b}").glob("*.laz"))

print(f"  {len(muestras)} castros detectados, repartidos por bloque\n")

filas = []
for b in tiles_por_bloque:
    de_este = [m for m in muestras if m["bloque"] == b]
    if not de_este:
        continue
    grupos, _ = group_samples_by_tiles(de_este, tiles_por_bloque[b], EXTENT)
    for tiles, celdas in grupos.items():
        half = EXTENT / 2
        ux0 = min(c["x"] for c in celdas) - half
        ux1 = max(c["x"] for c in celdas) + half
        uy0 = min(c["y"] for c in celdas) - half
        uy1 = max(c["y"] for c in celdas) + half
        xs_l, ys_l, zs_l = [], [], []
        for tp in tiles:
            try:
                las = laspy.read(tp)
            except Exception:
                continue
            keep = np.asarray(las.classification) == GROUND_CLASS
            if not keep.any():
                continue
            x, y, z = (np.asarray(las.x)[keep], np.asarray(las.y)[keep],
                       np.asarray(las.z)[keep])
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
            fila = {"nombre": c["nombre"], "bloque": b,
                    "pt_m2": float(m.sum()) / (EXTENT * EXTENT)}
            base = rasterizar(xs[m], ys[m], zs[m], bd, RES, "min", "vecino")
            if base is None:
                continue
            fila["min_vecino"] = senal_ruido(base)[2]
            for sig in (1.0, 1.5, 2.5, 4.0):
                fila[f"suave{sig}"] = senal_ruido(suavizar_dem(base, sig))[2]
            filas.append(fila)
            print(f"    {fila['nombre'][:26]:<28} {fila['pt_m2']:.1f}pt  "
                  + " ".join(f"{k}={fila[k]:.2f}" for k in
                             ("min_vecino", "suave1.0", "suave1.5", "suave2.5",
                              "suave4.0") if k in fila), flush=True)

print(f"\n  === razon senal/ruido, mediana de {len(filas)} castros ===")
base = np.array([f["min_vecino"] for f in filas if np.isfinite(f.get("min_vecino", np.nan))])
for k in ("min_vecino", "suave1.0", "suave1.5", "suave2.5", "suave4.0"):
    v = np.array([f[k] for f in filas if k in f and np.isfinite(f[k])])
    if not len(v):
        continue
    etiqueta = "sin suavizar (LO ACTUAL)" if k == "min_vecino" else f"suavizado {k[5:]} m"
    # mejora por castro, no diferencia de medianas: es pareado y aguanta mas
    pares = np.array([f[k] / f["min_vecino"] for f in filas
                      if k in f and np.isfinite(f[k]) and f.get("min_vecino", 0) > 1e-6])
    print(f"    {etiqueta:<26} {np.median(v):>6.3f}   "
          f"mejora mediana x{np.median(pares):.3f}   (n={len(v)})")
