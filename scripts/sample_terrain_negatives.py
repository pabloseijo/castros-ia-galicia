#!/usr/bin/env python3
"""Negativos muestreados del propio terreno LiDAR ya descargado.

Resuelve dos problemas de una vez.

**Cantidad.** Minar negativos con nombre desde OpenStreetMap a escala gallega
choca con los límites de Overpass: `31` trozos de `210` en una hora, con `429`
y `504` constantes. Eso ya es abusar de un servicio gratuito de voluntarios.
Aquí hay `2.036 km²` de LiDAR en disco y caben decenas de miles de negativos
sin pedirle nada a nadie.

**Efecto de lote.** El `2026-08-04` un modelo separó castros de terreno con AUC
aparente perfecto, y la causa era `rgb__radial_peak_count`: valía constante `20`
en un banco y `22` en el otro, porque venían de extracciones distintas. Un
negativo recortado por el mismo cortador que el positivo no puede sufrir eso.

Los negativos con nombre de OSM siguen siendo valiosos —cada uno dice *por qué*
es difícil, y la matriz de confusión se lee por causa— así que estos no los
sustituyen: los complementan hasta la proporción que el despliegue exige.
"""
from __future__ import annotations

import argparse
import csv
import math
import os
import random
import sys
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MASTER = PROJECT_ROOT / "data/weak-label-splits-v1/weak_label_master.tsv"
HALF_M = 256.0     # media viñeta, para no salirse de la tesela


def known_sites_utm29():
    """Todo sitio catalogado, positivo o negativo: no se muestrea encima."""
    from pyproj import Transformer
    tr = Transformer.from_crs("EPSG:4326", "EPSG:25829", always_xy=True)
    pts = []
    if MASTER.exists():
        for r in csv.DictReader(open(MASTER, encoding="utf-8"), delimiter="\t"):
            try:
                lon, lat = float(r["longitude"]), float(r["latitude"])
            except (KeyError, TypeError, ValueError):
                continue
            pts.append(tr.transform(lon, lat))
    osm = PROJECT_ROOT / "data/osm-strong-labels-v1/osm_strong_labels.tsv"
    if osm.exists():
        for r in csv.DictReader(open(osm, encoding="utf-8"), delimiter="\t"):
            try:
                lon, lat = float(r["centroid_lon"]), float(r["centroid_lat"])
            except (KeyError, TypeError, ValueError):
                continue
            pts.append(tr.transform(lon, lat))
    return np.asarray(pts) if pts else np.zeros((0, 2))


def tile_bounds(path):
    import laspy
    with laspy.open(path) as rd:
        h = rd.header
        return (float(h.mins[0]), float(h.mins[1]),
                float(h.maxs[0]), float(h.maxs[1]))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--laz-dirs", nargs="+", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--per-tile", type=int, default=12,
                    help="negativos por km2 de tesela")
    ap.add_argument("--buffer-m", type=float, default=400.0,
                    help="distancia mínima a cualquier sitio catalogado")
    ap.add_argument("--min-sep-m", type=float, default=300.0,
                    help="separación mínima entre negativos, para que no")
    ap.add_argument("--seed", type=int, default=20260804)
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    from pyproj import Transformer
    inv = Transformer.from_crs("EPSG:25829", "EPSG:4326", always_xy=True)
    rng = random.Random(args.seed)

    known = known_sites_utm29()
    print(f"sitios catalogados que evitar: {len(known)}", flush=True)

    tiles = []
    for d in args.laz_dirs:
        tiles += sorted(d.glob("*.laz"))
    print(f"teselas disponibles: {len(tiles)} ({len(tiles)} km2)", flush=True)
    if not tiles:
        raise SystemExit("sin teselas LAZ")

    kept = []
    kept_xy = np.zeros((0, 2))
    for i, t in enumerate(tiles, 1):
        try:
            minx, miny, maxx, maxy = tile_bounds(t)
        except Exception:
            continue
        made, tries = 0, 0
        while made < args.per_tile and tries < args.per_tile * 30:
            tries += 1
            x = rng.uniform(minx + HALF_M, maxx - HALF_M)
            y = rng.uniform(miny + HALF_M, maxy - HALF_M)
            if len(known) and np.min(np.hypot(known[:, 0] - x,
                                              known[:, 1] - y)) < args.buffer_m:
                continue
            if len(kept_xy) and np.min(np.hypot(kept_xy[:, 0] - x,
                                                kept_xy[:, 1] - y)) < args.min_sep_m:
                continue
            lon, lat = inv.transform(x, y)
            kept.append({"negative_class": "random_terrain",
                         "name": "", "osm_tags": "",
                         "osm_type": "", "osm_id": "",
                         "longitude": lon, "latitude": lat})
            kept_xy = np.vstack([kept_xy, [x, y]])
            made += 1
        if i % 200 == 0:
            print(f"  {i}/{len(tiles)} teselas, {len(kept)} negativos", flush=True)

    fields = ["osm_type", "osm_id", "negative_class", "name", "osm_tags",
              "longitude", "latitude"]
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, delimiter="\t", fieldnames=fields,
                           extrasaction="ignore")
        w.writeheader()
        for r in kept:
            w.writerow(r)
    print(f"\n{len(kept)} negativos de terreno -> {args.out}", flush=True)
    print(f"  proporción frente a 3071 positivos: 1:{len(kept)/3071:.1f}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
