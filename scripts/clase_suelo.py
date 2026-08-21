#!/usr/bin/env python3
"""¿Se pierde parapeto al fiarse de la clasificación de suelo del PNOA?

El corpus usa `classification == 2` y nada más. Esa clasificación la hace el
vuelo cartográfico, con un algoritmo afinado para **quitar vegetación y dejar
terreno**, no para conservar microrrelieve arqueológico. Un parapeto bajo tojo
puede quedar etiquetado como vegetacion baja (clase `3`) y desaparecer entero.

Es un problema conocido en LiDAR arqueologico y **aqui nunca se ha comprobado**.
Se mide sobre castros conocidos:

  · cuantos puntos anade la clase `3`;
  · si el relieve del parapeto sube o baja al incluirla;
  · y la razon senal/ruido, que es lo que decide.

**Cuidado con la trampa evidente**: incluir vegetacion sube el terreno donde hay
matorral, asi que puede *fabricar* relieve. Por eso no basta con ver si el
relieve crece — hay que mirar si crece **mas en el nucleo que en el fondo**.
"""
from __future__ import annotations

import csv
import math
import sys
from pathlib import Path

import laspy
import numpy as np

sys.path.insert(0, "scripts")
from build_trasancos_vignettes import (boxblur, grid_from_points,  # noqa: E402
                                       group_samples_by_tiles, lonlat_to_utm29)

EXTENT, RES, LRM_R = 512.0, 1.0, 60.0
N = int(sys.argv[1]) if len(sys.argv) > 1 else 24


def leer(p):
    with Path(p).open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def senal_ruido(dem):
    lrm = dem - boxblur(dem, int(round(LRM_R / RES)))
    n = lrm.shape[0]; c = n // 2
    r_n, r_b = int(60 / RES), int(40 / RES)
    nucleo = lrm[c - r_n:c + r_n, c - r_n:c + r_n]
    anillo = np.concatenate([lrm[:r_b, :].ravel(), lrm[-r_b:, :].ravel(),
                             lrm[:, :r_b].ravel(), lrm[:, -r_b:].ravel()])
    s = float(np.percentile(nucleo, 75) - np.percentile(nucleo, 25))
    r = float(np.std(anillo))
    return s, r, (s / r if r > 1e-6 else np.nan)


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
            muestras.append({"id": len(muestras), "x": x, "y": y,
                             "nombre": (t.get("name") or "?")[:26]})
            n_b += 1
    if not muestras:
        continue
    tiles = sorted(str(p) for p in Path(f"data/external/lidar-val-{b}").glob("*.laz"))
    grupos, _ = group_samples_by_tiles(muestras, tiles, EXTENT)
    for tt, celdas in grupos.items():
        half = EXTENT / 2
        ux0 = min(c["x"] for c in celdas) - half; ux1 = max(c["x"] for c in celdas) + half
        uy0 = min(c["y"] for c in celdas) - half; uy1 = max(c["y"] for c in celdas) + half
        acc = {2: [[], [], []], 23: [[], [], []]}
        for tp in tt:
            try:
                las = laspy.read(tp)
            except Exception:
                continue
            cl = np.asarray(las.classification)
            x, y, z = np.asarray(las.x), np.asarray(las.y), np.asarray(las.z)
            d = (x >= ux0) & (x <= ux1) & (y >= uy0) & (y <= uy1)
            for clave, m in ((2, (cl == 2) & d), (23, ((cl == 2) | (cl == 3)) & d)):
                if m.any():
                    acc[clave][0].append(x[m]); acc[clave][1].append(y[m])
                    acc[clave][2].append(z[m])
        if not acc[2][0]:
            continue
        P = {k2: tuple(np.concatenate(v) for v in acc[k2]) for k2 in acc if acc[k2][0]}
        for c in celdas:
            bd = (c["x"] - half, c["y"] - half, c["x"] + half, c["y"] + half)
            fila = {"nombre": c["nombre"]}
            ok = True
            for clave in (2, 23):
                if clave not in P:
                    ok = False; break
                xs, ys, zs = P[clave]
                m = (xs >= bd[0]) & (xs <= bd[2]) & (ys >= bd[1]) & (ys <= bd[3])
                if m.sum() < 2000:
                    ok = False; break
                dem = grid_from_points(xs[m], ys[m], zs[m], bd, RES)
                if dem is None:
                    ok = False; break
                s, r, sr = senal_ruido(dem)
                fila[f"n{clave}"] = int(m.sum())
                fila[f"s{clave}"], fila[f"r{clave}"], fila[f"sr{clave}"] = s, r, sr
            if not ok:
                continue
            filas.append(fila)
            print(f"    {fila['nombre']:<28} pts {fila['n2']:>6}->{fila['n23']:>6}"
                  f"  s/r {fila['sr2']:.2f} -> {fila['sr23']:.2f}", flush=True)

if not filas:
    raise SystemExit("  sin datos")
import numpy as np2  # noqa: E402
sr2 = np.array([f["sr2"] for f in filas]); sr23 = np.array([f["sr23"] for f in filas])
n2 = np.array([f["n2"] for f in filas]); n23 = np.array([f["n23"] for f in filas])
print(f"\n  === {len(filas)} castros ===")
print(f"    puntos: clase 2 = {n2.sum():,} | clase 2+3 = {n23.sum():,} "
      f"(+{100*(n23.sum()-n2.sum())/n2.sum():.0f}%)")
print(f"    senal/ruido mediana: {np.median(sr2):.3f} (clase 2) -> "
      f"{np.median(sr23):.3f} (clase 2+3)")
mej = sr23 / np.where(sr2 > 1e-6, sr2, np.nan)
print(f"    mejora pareada mediana: x{np.nanmedian(mej):.3f}")
print(f"    castros que mejoran: {int(np.nansum(mej > 1))}/{len(filas)}")
