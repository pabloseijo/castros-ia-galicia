#!/usr/bin/env python3
"""Triaje morfológico de candidatos con los criterios que usa un arqueólogo.

Automatiza **la parte geométrica** de la revisión que Canedo et al. (2025) hacen
con dos arqueólogos. No la sustituye: la reduce.

## Los criterios, y de dónde salen

La literatura de identificación de castros en LiDAR nombra tres rasgos y tres
falsos positivos dominantes. Los tres rasgos:

1. **El par parapeto + foso**: un anillo de relieve positivo con una depresión
   inmediatamente por fuera. No basta uno de los dos.
2. **Posición dominante**: el recinto está en alto respecto a su entorno.
3. **El movimiento de tierras cierra**, siguiendo la curva de nivel.

Y los falsos positivos: **pistas forestales**, que siguen la curva de nivel pero
**no cierran**; formaciones naturales circulares en ladera; y castillos
medievales, que al pasar de modelo de superficie a modelo del terreno se parecen
a un castro. Los dos primeros son separables por geometría. **El tercero no**, y
esta herramienta no lo intenta.

## El criterio que más aporta

**El cierre angular.** Es lo que distingue un recinto de una pista o una terraza,
y es justo el falso positivo que la literatura reporta como dominante. Se mide
troceando el disco en sectores y contando en cuántos aparece la firma anular.

## Lo que NO hace

- No decide si algo es arqueología. Ordena y descarta lo geométricamente
  incompatible.
- No distingue épocas: un castillo medieval con foso puntúa como un castro.
- No sustituye la visita al campo, que en la propia literatura sigue siendo el
  paso que confirma.

Uso:
    python3 scripts/triage_morfologico.py --puntos data/cola_revision_v3.tsv \\
        --laz-dir data/external/lidar-trasancos-v1 --out data/triaje_v3.tsv
"""
from __future__ import annotations

import argparse
import csv
import math
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_trasancos_vignettes import (grid_from_points, group_samples_by_tiles,
                                       lonlat_to_utm29)

GROUND_CLASS = 2
EXTENT = 512.0
RES = 1.0
# p10-p90 del radio de los poligonos OSM de castro medidos en este proyecto
RADIOS = np.arange(30, 95, 5, dtype=float)
SECTORES = 12


def firma_anular(dem, res, radios=RADIOS, sectores=SECTORES):
    """Busca el par parapeto+foso y mide en cuántos sectores aparece."""
    h, w = dem.shape
    yy, xx = np.mgrid[0:h, 0:w]
    cy, cx = h/2.0, w/2.0
    r = np.hypot(yy-cy, xx-cx) * res
    ang = (np.arctan2(yy-cy, xx-cx) + np.pi) / (2*np.pi)
    sec = np.clip((ang*sectores).astype(int), 0, sectores-1)

    # Tendencia: mediana por anillo, para quitar la ladera
    mejor = None
    for R in radios:
        anillo = (r >= R-6) & (r <= R+6)
        foso = (r > R+6) & (r <= R+18)
        nucleo = r < R-10
        fuera = (r > R+30) & (r <= R+60)
        if not (anillo.any() and foso.any() and nucleo.any() and fuera.any()):
            continue
        base = float(np.median(dem[fuera]))
        # 1. parapeto: el anillo sobresale de su entorno inmediato
        alt_anillo = float(np.median(dem[anillo])) - float(np.median(dem[foso]))
        # 2. posicion dominante: el nucleo esta por encima del exterior
        dominancia = float(np.median(dem[nucleo])) - base
        # 3. cierre: en cuantos sectores el anillo supera a su foso
        cierre = 0
        for s in range(sectores):
            a = anillo & (sec == s)
            f = foso & (sec == s)
            if a.any() and f.any() and np.median(dem[a]) > np.median(dem[f]):
                cierre += 1
        frac = cierre / sectores
        # puntuacion: el cierre manda, porque es lo que separa recinto de pista
        score = frac * max(alt_anillo, 0.0)
        if mejor is None or score > mejor["score"]:
            mejor = {"radio_m": float(R), "parapeto_m": alt_anillo,
                     "dominancia_m": dominancia, "cierre": frac, "score": score}
    return mejor or {"radio_m": 0.0, "parapeto_m": 0.0, "dominancia_m": 0.0,
                     "cierre": 0.0, "score": 0.0}


def procesar(args_tuple):
    tiles, puntos, extent, res = args_tuple
    import laspy
    half = extent/2.0
    ux0 = min(p["x"] for p in puntos)-half; ux1 = max(p["x"] for p in puntos)+half
    uy0 = min(p["y"] for p in puntos)-half; uy1 = max(p["y"] for p in puntos)+half
    xs_l, ys_l, zs_l = [], [], []
    for tp in tiles:
        las = laspy.read(tp)
        keep = np.asarray(las.classification) == GROUND_CLASS
        if not keep.any():
            del las; continue
        x = np.asarray(las.x)[keep]; y = np.asarray(las.y)[keep]; z = np.asarray(las.z)[keep]
        del las
        d = (x >= ux0) & (x <= ux1) & (y >= uy0) & (y <= uy1)
        if d.any():
            xs_l.append(x[d].astype(np.float32)); ys_l.append(y[d].astype(np.float32))
            zs_l.append(z[d].astype(np.float32))
    if not xs_l:
        return []
    xs = np.concatenate(xs_l); ys = np.concatenate(ys_l); zs = np.concatenate(zs_l)
    out = []
    for p in puntos:
        b = (p["x"]-half, p["y"]-half, p["x"]+half, p["y"]+half)
        m = (xs >= b[0]) & (xs <= b[2]) & (ys >= b[1]) & (ys <= b[3])
        if m.sum() < 2000:
            continue
        dem = grid_from_points(xs[m], ys[m], zs[m], b, res)
        if dem is None:
            continue
        f = firma_anular(dem, res)
        f["id"] = p["id"]
        out.append(f)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--puntos", type=Path, required=True)
    ap.add_argument("--laz-dir", type=Path, nargs="+", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--workers", type=int, default=3)
    args = ap.parse_args()

    filas = list(csv.DictReader(open(args.puntos, encoding="utf-8"), delimiter="\t"))
    for i, r in enumerate(filas):
        r["id"] = i
        r["x"], r["y"] = lonlat_to_utm29(float(r["lon"]), float(r["lat"]))
    print(f"puntos: {len(filas)}", flush=True)

    tiles = sorted({str(p) for d in args.laz_dir for p in Path(d).glob("*.laz")})
    slim = [{k: r[k] for k in ("id", "x", "y")} for r in filas]
    grupos, huerf = group_samples_by_tiles(slim, tiles, EXTENT)
    print(f"  con LiDAR: {sum(len(v) for v in grupos.values())} | fuera: {huerf}",
          flush=True)

    res = {}
    tareas = [(list(k), v, EXTENT, RES) for k, v in grupos.items()]
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(procesar, t) for t in tareas]
        for i, f in enumerate(as_completed(futs), 1):
            for r in f.result():
                res[r["id"]] = r
            if i % 10 == 0 or i == len(tareas):
                print(f"  {i}/{len(tareas)} grupos", flush=True)

    campos = list(filas[0].keys()) + ["radio_m", "parapeto_m", "dominancia_m",
                                      "cierre", "score_morfo"]
    campos = [c for c in campos if c not in ("x", "y", "id")]
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=campos, delimiter="\t",
                           extrasaction="ignore")
        w.writeheader()
        for r in filas:
            m = res.get(r["id"])
            if m:
                r.update({"radio_m": round(m["radio_m"], 1),
                          "parapeto_m": round(m["parapeto_m"], 2),
                          "dominancia_m": round(m["dominancia_m"], 2),
                          "cierre": round(m["cierre"], 3),
                          "score_morfo": round(m["score"], 3)})
            w.writerow(r)
    print(f"\nescrito: {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
