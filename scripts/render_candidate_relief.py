#!/usr/bin/env python3
"""Renderiza el relieve de cada candidato como PNG, para poder mirarlo.

Genera dos vistas del mismo recorte, porque enseñan cosas distintas:

- **Sombreado multidireccional**: cómo se ve el terreno. Un sombreado de una sola
  dirección esconde justo los tramos de parapeto paralelos a la luz, que es un
  artefacto conocido y la razón de que la literatura use varias direcciones.
- **Relieve local (LRM)**: la altura menos su propia media en una ventana. Quita
  la ladera y deja el movimiento de tierras, que es lo que se busca.

Uso (en el nodo que tiene el LiDAR):
    python3 scripts/render_candidate_relief.py --puntos data/cola_triada_v3.tsv \\
        --laz-dir data/external/lidar-trasancos-v1 --out data/revision-visual-v1/relieve
"""
from __future__ import annotations

import argparse
import csv
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


def media_movil(a, k):
    """Media en ventana kxk por suma acumulada; k puede ser grande sin coste."""
    pad = k // 2
    b = np.pad(a, pad, mode="edge")
    c = np.cumsum(np.cumsum(b, axis=0), axis=1)
    c = np.pad(c, ((1, 0), (1, 0)))
    h, w = a.shape
    return (c[k:k+h, k:k+w] - c[0:h, k:k+w] - c[k:k+h, 0:w] + c[0:h, 0:w]) / (k*k)


def sombreado_multi(dem, res, alt=35.0):
    """Suma de cuatro azimuts. Uno solo esconde los parapetos paralelos a la luz."""
    gy, gx = np.gradient(dem, res)
    pend = np.arctan(np.hypot(gx, gy))
    asp = np.arctan2(-gx, gy)
    za = np.radians(alt)
    acc = np.zeros_like(dem)
    for az in (315.0, 45.0, 135.0, 225.0):
        aza = np.radians(360.0 - az + 90.0)
        acc += (np.sin(za)*np.cos(pend) +
                np.cos(za)*np.sin(pend)*np.cos(aza - asp))
    return acc / 4.0


def a_png(arr, destino, recorte=(2, 98)):
    import struct
    import zlib
    lo, hi = np.percentile(arr[np.isfinite(arr)], recorte)
    if hi <= lo:
        hi = lo + 1e-6
    v = np.clip((arr - lo) / (hi - lo), 0, 1)
    img = (v * 255).astype(np.uint8)
    h, w = img.shape
    crudo = b"".join(b"\x00" + img[y].tobytes() for y in range(h))

    def trozo(tipo, datos):
        c = tipo + datos
        return struct.pack(">I", len(datos)) + c + struct.pack(">I", zlib.crc32(c))

    png = (b"\x89PNG\r\n\x1a\n"
           + trozo(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
           + trozo(b"IDAT", zlib.compress(crudo, 6))
           + trozo(b"IEND", b""))
    Path(destino).write_bytes(png)


def procesar(args_t):
    tiles, puntos, out = args_t
    import laspy
    half = EXTENT / 2.0
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
    hechos = []
    for p in puntos:
        b = (p["x"]-half, p["y"]-half, p["x"]+half, p["y"]+half)
        m = (xs >= b[0]) & (xs <= b[2]) & (ys >= b[1]) & (ys <= b[3])
        if m.sum() < 2000:
            continue
        dem = grid_from_points(xs[m], ys[m], zs[m], b, RES)
        if dem is None:
            continue
        dem = np.flipud(dem)                      # norte arriba
        a_png(sombreado_multi(dem, RES), Path(out) / ("cand-%02d-sombra.png" % p["id"]))
        a_png(dem - media_movil(dem, 51), Path(out) / ("cand-%02d-lrm.png" % p["id"]))
        hechos.append(p["id"])
    return hechos


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--puntos", type=Path, required=True)
    ap.add_argument("--laz-dir", type=Path, nargs="+", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--solo-estado", default="CANDIDATO")
    ap.add_argument("--workers", type=int, default=3)
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    filas = list(csv.DictReader(open(args.puntos, encoding="utf-8"), delimiter="\t"))
    if args.solo_estado:
        filas = [r for r in filas if r.get("estado") == args.solo_estado]
    for i, r in enumerate(filas):
        r["id"] = i
        r["x"], r["y"] = lonlat_to_utm29(float(r["lon"]), float(r["lat"]))
    print("puntos: %d" % len(filas), flush=True)

    tiles = sorted({str(p) for d in args.laz_dir for p in Path(d).glob("*.laz")})
    slim = [{k: r[k] for k in ("id", "x", "y")} for r in filas]
    grupos, huerf = group_samples_by_tiles(slim, tiles, EXTENT)
    print("  con LiDAR: %d | fuera: %d"
          % (sum(len(v) for v in grupos.values()), huerf), flush=True)

    n = 0
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(procesar, (list(k), v, str(args.out)))
                for k, v in grupos.items()]
        for i, f in enumerate(as_completed(futs), 1):
            n += len(f.result())
            if i % 10 == 0 or i == len(futs):
                print("  %d/%d grupos, %d renderizados" % (i, len(futs), n), flush=True)
    print("relieve escrito en %s" % args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
