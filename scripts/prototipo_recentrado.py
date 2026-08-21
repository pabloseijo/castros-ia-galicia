#!/usr/bin/env python3
"""Buscar el castro dentro de la ficha: correlación con el prototipo, no coseno fijo.

El `2026-08-10` se midió que el prototipo espacial —la imagen media del `LRM` de
los `773` castros de entrenamiento— separa un castro de terreno corriente con
**`AUC 0,911`**, el mejor discriminador que ha producido este proyecto. Y que
contra los falsos positivos del modelo da **`0,495`**: azar.

Pero los mismos datos traen una pista que hay que perseguir:

| conjunto | centrado en | similitud media |
| --- | --- | ---: |
| control | el castro **catalogado** | **`+0,396`** |
| prueba | la **celda del modelo** | `+0,133` |

**Son los mismos castros.** Lo único que cambia es dónde se recorta: el barrido
detecta desde una celda que puede estar a `250 m` del recinto, y el prototipo,
que es una plantilla rígida, se desalinea y deja de valer.

Así que la comparación anterior no era justa con el prototipo: le pedía acertar
sobre un recorte descentrado. Esto lo corrige **buscando**: se desplaza la
plantilla por la vecindad y se queda con el mejor encaje, que es lo que hace
cualquier emparejamiento de plantillas desde siempre.

## Y por qué esto puede discriminar, y no solo mejorar la puntuación

Un castro real debería tener un **máximo local marcado**: un sitio donde la
plantilla encaja mucho mejor que en los alrededores. Una ladera que se parece a
un castro de refilón debería dar un máximo **plano y bajo**. Así que además del
máximo se mide **el contraste del máximo contra su entorno**, que es la firma
que distingue «hay un objeto ahí» de «esto se parece un poco por todas partes».

Uso:
    python3 scripts/prototipo_recentrado.py --puntos data/calib_morfo.tsv \\
        --proto data/proto_calib.proto.npy --out data/proto_rec_calib.tsv
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "scripts"))

LADO_PROTO_M = 300.0     # el del prototipo ya construido
BUSQUEDA_M = 256.0       # media celda del barrido: hasta donde puede estar
PASO_M = 16.0            # resolución de la búsqueda


def normalizar(p):
    p = p - p.mean()
    n = float(np.linalg.norm(p))
    return p / n if n > 1e-9 else p


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--puntos", type=Path, required=True)
    ap.add_argument("--proto", type=Path, required=True)
    ap.add_argument("--laz-base", type=Path, default=Path("data/external"))
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--res-m", type=float, default=1.0)
    args = ap.parse_args()

    from build_trasancos_vignettes import (channels_from_dem, grid_from_points,
                                           group_samples_by_tiles,
                                           lonlat_to_utm29)
    import laspy

    proto = np.load(args.proto)
    lp = proto.shape[0]
    print("prototipo %dx%d" % proto.shape, flush=True)

    # Recorte grande: el prototipo más el margen de búsqueda por los dos lados.
    lado_grande_m = LADO_PROTO_M + 2 * BUSQUEDA_M
    half = lado_grande_m / 2.0
    paso_px = int(round(PASO_M / args.res_m))
    busq_px = int(round(BUSQUEDA_M / args.res_m))

    filas = list(csv.DictReader(args.puntos.open(encoding="utf-8"),
                               delimiter="\t"))
    hechos = set()
    if args.out.exists():
        hechos = {(r["bloque"], r["n"]) for r in
                  csv.DictReader(args.out.open(encoding="utf-8"),
                                 delimiter="\t")}
    nuevo = not args.out.exists()
    fh = args.out.open("a", newline="", encoding="utf-8")
    w = csv.writer(fh, delimiter="\t")
    if nuevo:
        w.writerow(["bloque", "n", "etiqueta", "sim_centro", "sim_max",
                    "contraste", "desplaz_m"])

    por_bloque = {}
    for r in filas:
        if (r["bloque"], r["n"]) not in hechos:
            por_bloque.setdefault(r["bloque"], []).append(r)

    for bloque, cs in por_bloque.items():
        teselas = sorted(str(p) for p in
                         (args.laz_base / f"lidar-val-{bloque}").glob("*.laz"))
        celdas = []
        for c in cs:
            x, y = lonlat_to_utm29(float(c["lon"]), float(c["lat"]))
            celdas.append({"id": c["n"], "x": x, "y": y, "fila": c})
        grupos, _ = group_samples_by_tiles(celdas, teselas, lado_grande_m + 40)
        print("== %s: %d puntos en %d grupos" % (bloque, len(cs), len(grupos)),
              flush=True)
        for tp, cls_ in grupos.items():
            xs, ys, zs = [], [], []
            for t in tp:
                try:
                    las = laspy.read(t)
                    k = np.asarray(las.classification) == 2
                    if not k.any():
                        continue
                    xs.append(np.asarray(las.x)[k])
                    ys.append(np.asarray(las.y)[k])
                    zs.append(np.asarray(las.z)[k])
                except Exception:
                    continue
            if not xs:
                continue
            X = np.concatenate(xs); Y = np.concatenate(ys)
            Z = np.concatenate(zs)
            for c in cls_:
                b = (c["x"] - half, c["y"] - half,
                     c["x"] + half, c["y"] + half)
                m = (X >= b[0]) & (X <= b[2]) & (Y >= b[1]) & (Y <= b[3])
                if m.sum() < 4000:
                    continue
                dem = grid_from_points(X[m], Y[m], Z[m], b, args.res_m)
                if dem is None or np.ndim(dem) != 2:
                    continue
                # **El LRM se calcula sobre el recorte grande y una sola vez.**
                # Recalcularlo por desplazamiento cambiaría la normalización en
                # cada posición y la comparación dejaría de ser entre iguales.
                lrm = channels_from_dem(dem, args.res_m)[1]
                H, W = lrm.shape
                if H < lp or W < lp:
                    continue
                cy, cx = H // 2, W // 2

                mejor = (-2.0, 0, 0)
                sims = []
                for dy in range(-busq_px, busq_px + 1, paso_px):
                    for dx in range(-busq_px, busq_px + 1, paso_px):
                        y0 = cy + dy - lp // 2
                        x0 = cx + dx - lp // 2
                        if y0 < 0 or x0 < 0 or y0 + lp > H or x0 + lp > W:
                            continue
                        s = float(np.dot(
                            normalizar(lrm[y0:y0 + lp, x0:x0 + lp]).ravel(),
                            proto.ravel()))
                        sims.append(s)
                        if s > mejor[0]:
                            mejor = (s, dy, dx)
                if not sims:
                    continue
                sims = np.asarray(sims)
                y0 = cy - lp // 2
                x0 = cx - lp // 2
                s_centro = float(np.dot(
                    normalizar(lrm[y0:y0 + lp, x0:x0 + lp]).ravel(),
                    proto.ravel()))
                # Contraste del máximo contra su propia distribución: cuánto
                # sobresale el mejor encaje del resto de la vecindad.
                contraste = float((mejor[0] - sims.mean()) /
                                  (sims.std() + 1e-9))
                desp = float(np.hypot(mejor[1], mejor[2]) * args.res_m)
                w.writerow([bloque, c["id"], c["fila"].get("etiqueta", ""),
                            "%.4f" % s_centro, "%.4f" % mejor[0],
                            "%.3f" % contraste, "%.0f" % desp])
                fh.flush()
            del X, Y, Z
    fh.close()
    print("\nescrito: %s" % args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
