#!/usr/bin/env python3
"""Stage 1: cut 1 m relief vignettes for the Trasancos classifier.

Landauer et al. (2025) swept 180.000 km2 with a *classifier* over 768x768 m
LiDAR vignettes, not a segmenter. That matters here: a classifier needs one
point and one label per sample, while segmentation needs drawn masks, and
Trasancos only has 8 OSM polygons. So the classifier is the route that is
actually unblocked today.

Three channels, all from the bare-earth point cloud, chosen to be what a
model pretrained on natural images can still read:

  0. normalised DTM   - min/max scaled height. Landauer found raw normalised
                        elevation beat hillshade, which is worth respecting.
  1. local relief     - DTM minus a smoothed DTM, so the hillside is removed
                        and the rampart survives. This is the channel that
                        works under canopy.
  2. slope            - degrees; ditches and scarps read as edges here.

Runs on the Raspberry: needs only laspy and numpy, no torch and no GPU. Output
is a compact .npz cache that the training stage consumes anywhere.

Concurrent over LAZ tiles with progress, because reading a 45 MB tile is slow
and there are ~700 of them.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

# El paralelismo util aqui es de proceso, no de hilo: cada viñeta son arrays de
# 512x512, demasiado pequeños para que BLAS multihilo compense su coordinacion.
# Sin fijar esto, 3 workers x 5 hilos sobre 4 nucleos dan carga 7.8 y se pelean
# entre si. Debe ir antes de importar numpy.
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
           "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LAZ_DIR = PROJECT_ROOT / "data/external/lidar-trasancos-v1"
OUT_DIR = PROJECT_ROOT / "data/trasancos-vignettes-v1"
MASTER = PROJECT_ROOT / "data/weak-label-splits-v1/weak_label_master.tsv"
HARD_NEG = PROJECT_ROOT / "data/trasancos-hard-negatives-v1/trasancos_hard_negatives.tsv"

TRASANCOS = {"Ferrol", "Narón", "Naron", "Neda", "Fene", "Valdoviño",
             "Valdovino", "San Sadurniño", "San Sadurnino"}
# O Val is the untouched final holdout: it carries Pena Lopesa, the project's
# historical control case, and it must never be trained on.
O_VAL = (-8.2411, 43.5346, -8.1932, 43.5890)  # W, S, E, N

GROUND_CLASS = 2
EXTENT_M = 512.0      # vignette side; a 114 m castro fills ~22% of the frame
PIXEL_M = 1.0
BLOCK_M = 2000.0      # spatial block size for the train/val split


_TRANSFORMER = None


def lonlat_to_utm29(lon, lat):
    """Convierte a UTM 29N reutilizando el transformador y aceptando secuencias.

    Antes construia un `Transformer` nuevo en cada llamada, y como se llamaba una
    vez por muestra, a escala Galicia eran `41.259` construcciones: cada una abre
    `proj.db` y cuesta milisegundos, asi que la carga de muestras se comia varios
    minutos al `100%` de un nucleo antes de imprimir la primera linea. Construirlo
    una vez y pasarle los arrays completos deja eso en milisegundos.
    """
    global _TRANSFORMER
    if _TRANSFORMER is None:
        from pyproj import Transformer
        _TRANSFORMER = Transformer.from_crs("EPSG:4326", "EPSG:25829",
                                            always_xy=True)
    return _TRANSFORMER.transform(lon, lat)


def in_bbox(lon, lat, bbox):
    w, s, e, n = bbox
    return w <= lon <= e and s <= lat <= n


def load_samples(scope: str = "trasancos", extra_negatives=None):
    """Positives, mound hard negatives and named modern/natural negatives.

    `scope="trasancos"` keeps the six-council pilot. `scope="galicia"` opens it
    to every trainable positive in the catalogue, which is what the
    label-centred LiDAR sampling exists to serve: 747 positives spread over 286
    blocks instead of 68 in one comarca, and a +-0.033 interval on sensitivity
    instead of +-0.109.
    """
    samples = []
    if MASTER.exists():
        for r in csv.DictReader(open(MASTER, encoding="utf-8"), delimiter="\t"):
            if scope == "trasancos" and (r.get("municipality") or "") not in TRASANCOS:
                continue
            try:
                lon, lat = float(r["longitude"]), float(r["latitude"])
            except (KeyError, TypeError, ValueError):
                continue
            split = r.get("final_split") or ""
            if r.get("label_class") == "1":
                # excluded_review holds the toponymic noise the project already
                # flagged: streets, buildings and chapels named "Castro".
                if split == "excluded_review":
                    continue
                samples.append({"label": 1, "group": "castro",
                                "name": r.get("name", ""), "lon": lon, "lat": lat})
            elif "megalithic" in (r.get("negative_type") or ""):
                samples.append({"label": 0, "group": "mamoa",
                                "name": r.get("name", ""), "lon": lon, "lat": lat})
    # Los negativos con nombre se extrajeron sobre el bbox de Trasancos, asi que
    # en alcance galicia entran igual pero solo cubriran esa zona. El resto de
    # Galicia aporta por ahora negativos de catalogo (mamoas), y hara falta una
    # pasada de Overpass a escala gallega antes de entrenar en serio.
    neg_files = [HARD_NEG] + [Path(p) for p in (extra_negatives or [])]
    for nf in neg_files:
        if not Path(nf).exists():
            continue
        for r in csv.DictReader(open(nf, encoding="utf-8"), delimiter="\t"):
            try:
                lon, lat = float(r["longitude"]), float(r["latitude"])
            except (KeyError, TypeError, ValueError):
                continue
            samples.append({"label": 0, "group": r.get("negative_class", "other"),
                            "name": r.get("name", ""), "lon": lon, "lat": lat})

    # Una sola llamada con los arrays completos, no una por muestra.
    if samples:
        xs, ys = lonlat_to_utm29([s["lon"] for s in samples],
                                 [s["lat"] for s in samples])
        for smp, x, y in zip(samples, xs, ys):
            smp["x"], smp["y"] = x, y
    for smp in samples:
        # O Val permanece intocable en ambos alcances: lleva Pena Lopesa, el caso
        # de control historico del proyecto, y nunca debe entrar en entrenamiento.
        smp["split"] = "test_o_val" if in_bbox(smp["lon"], smp["lat"], O_VAL) else "pool"
    return samples


def grid_from_points(xs, ys, zs, bounds, res):
    """Lowest ground return per cell, then fill gaps by nearest valid neighbour."""
    minx, miny, maxx, maxy = bounds
    w = int(round((maxx - minx) / res))
    h = int(round((maxy - miny) / res))
    if w < 8 or h < 8:
        return None
    ix = np.clip(((xs - minx) / res).astype(np.int64), 0, w - 1)
    iy = np.clip(((maxy - ys) / res).astype(np.int64), 0, h - 1)
    flat = iy * w + ix
    dem = np.full(w * h, np.inf, dtype=np.float64)
    np.minimum.at(dem, flat, zs)
    dem = dem.reshape(h, w)
    valid = np.isfinite(dem)
    if valid.mean() < 0.30:
        return None
    if not valid.all():
        from scipy import ndimage  # optional; fall back to median fill
        try:
            idx = ndimage.distance_transform_edt(
                ~valid, return_distances=False, return_indices=True)
            dem = dem[tuple(idx)]
        except Exception:
            dem[~valid] = np.median(dem[valid])
    return dem.astype(np.float32)


def boxblur(a, radius):
    """Separable mean filter via summed-area table; no scipy dependency."""
    if radius < 1:
        return a
    pad = np.pad(a, radius, mode="edge")
    c = np.cumsum(np.cumsum(pad, axis=0), axis=1)
    c = np.pad(c, ((1, 0), (1, 0)))
    k = 2 * radius + 1
    h, w = a.shape
    tot = (c[k:k + h, k:k + w] - c[0:h, k:k + w]
           - c[k:k + h, 0:w] + c[0:h, 0:w])
    return (tot / (k * k)).astype(np.float32)


def channels_from_dem(dem, res, lrm_radius_m=60.0):
    """Normalised DTM, local relief and slope, each scaled to [0, 1]."""
    def mm(a):
        lo, hi = np.nanpercentile(a, 1), np.nanpercentile(a, 99)
        if not np.isfinite(lo) or not np.isfinite(hi) or hi - lo < 1e-6:
            return np.zeros_like(a, dtype=np.float32)
        return np.clip((a - lo) / (hi - lo), 0, 1).astype(np.float32)

    ndtm = mm(dem)
    lrm = dem - boxblur(dem, int(round(lrm_radius_m / res)))
    lrm = mm(lrm)
    gy, gx = np.gradient(dem, res)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    slope = np.clip(slope / 45.0, 0, 1).astype(np.float32)
    return np.stack([ndtm, lrm, slope], axis=0)


_BOUNDS_CACHE: dict[str, tuple] = {}


def laz_bounds(path):
    import laspy
    key = str(path)
    if key not in _BOUNDS_CACHE:
        with laspy.open(path) as rd:
            h = rd.header
            _BOUNDS_CACHE[key] = (float(h.mins[0]), float(h.mins[1]),
                                  float(h.maxs[0]), float(h.maxs[1]))
    return _BOUNDS_CACHE[key]


def process_group(args_tuple):
    """Cut every vignette in a group that needs the same set of LAZ tiles.

    CNIG ships 1 km tiles and a vignette is 512 m, so a site anywhere but the
    middle of a tile straddles two or four of them. Requiring the extent to sit
    inside a single tile silently drops about three quarters of the samples,
    so the tiles are unioned per group instead.
    """
    tile_paths, samples, extent, res, out_dir = args_tuple
    import laspy
    half = extent / 2.0

    # Si el grupo entero ya esta cortado, ni se abren los LAZ: son ~45 MB cada
    # uno y un grupo puede tocar cuatro.
    pending = [s for s in samples
               if not (Path(out_dir) / f"{s['sid']}.npz").exists()]
    if not pending:
        return len(samples), len(samples)

    xs_l, ys_l, zs_l = [], [], []
    for tp in tile_paths:
        las = laspy.read(tp)
        keep = np.asarray(las.classification) == GROUND_CLASS
        if not keep.any():
            continue
        xs_l.append(np.asarray(las.x)[keep])
        ys_l.append(np.asarray(las.y)[keep])
        zs_l.append(np.asarray(las.z)[keep])
    if not xs_l:
        return 0, len(samples)
    xs = np.concatenate(xs_l)
    ys = np.concatenate(ys_l)
    zs = np.concatenate(zs_l)

    written = 0
    for s in samples:
        # Reanudacion: esta maquina ha perdido el disco tres veces hoy, asi que
        # recalcular una viñeta ya escrita es tiempo regalado. Comprobar el
        # fichero cuesta un stat; recortarla cuesta leer decenas de MB de LAZ.
        out_npz = Path(out_dir) / f"{s['sid']}.npz"
        if out_npz.exists() and out_npz.stat().st_size > 0:
            written += 1
            continue
        b = (s["x"] - half, s["y"] - half, s["x"] + half, s["y"] + half)
        m = (xs >= b[0]) & (xs <= b[2]) & (ys >= b[1]) & (ys <= b[3])
        if m.sum() < 2000:
            continue
        dem = grid_from_points(xs[m], ys[m], zs[m], b, res)
        if dem is None:
            continue
        arr = channels_from_dem(dem, res)
        np.savez_compressed(Path(out_dir) / f"{s['sid']}.npz",
                            x=arr.astype(np.float16), label=s["label"])
        written += 1
    return written, len(samples)


def group_samples_by_tiles(samples, tiles, extent):
    """Map each sample to the tiles its vignette overlaps, then group by that set."""
    half = extent / 2.0
    bounds = {t: laz_bounds(t) for t in tiles}
    groups = defaultdict(list)
    orphans = 0
    for s in samples:
        b = (s["x"] - half, s["y"] - half, s["x"] + half, s["y"] + half)
        need = tuple(sorted(
            t for t, (mnx, mny, mxx, mxy) in bounds.items()
            if not (b[2] < mnx or b[0] > mxx or b[3] < mny or b[1] > mxy)))
        if not need:
            orphans += 1
            continue
        groups[need].append(s)
    return groups, orphans


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    # Varios directorios, y no uno, porque las teselas viven separadas por cómo
    # se descargaron —`lidar-positives-v1` centrado en positivos, `lidar-trasancos-v1`
    # cubriendo la comarca— y usar solo el primero dejaba fuera el 93% de los
    # negativos con nombre. La cobertura es la union de todos.
    ap.add_argument("--laz-dir", type=Path, nargs="+", default=[LAZ_DIR])
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    ap.add_argument("--extent-m", type=float, default=EXTENT_M)
    ap.add_argument("--res-m", type=float, default=PIXEL_M)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--scope", choices=("trasancos", "galicia"), default="trasancos")
    ap.add_argument("--extra-negatives", nargs="*", default=None,
                    help="TSV adicionales de negativos (mismo formato)")
    ap.add_argument("--val-every", type=int, default=5,
                    help="1 de cada N bloques espaciales va a validacion")
    args = ap.parse_args()

    arr_dir = args.out_dir / "arrays"
    arr_dir.mkdir(parents=True, exist_ok=True)

    samples = load_samples(args.scope, args.extra_negatives)
    # El identificador se deriva de las coordenadas, no del índice en la lista.
    # Con el índice, añadir una fuente de negativos desplaza a todos los demás
    # y la reanudación empieza a saltar ficheros que corresponden a otro sitio:
    # datos corruptos en silencio, que es peor que recalcular.
    for s in samples:
        key = f"{s['lon']:.6f},{s['lat']:.6f}".encode()
        s["sid"] = (f"{s['label']}_{s['group']}_"
                    f"{hashlib.sha1(key).hexdigest()[:10]}")
    seen = set()
    unique = []
    for s in samples:
        if s["sid"] in seen:
            continue
        seen.add(s["sid"])
        unique.append(s)
    if len(unique) != len(samples):
        print(f"  {len(samples)-len(unique)} duplicados por coordenada descartados",
              flush=True)
    samples = unique
    pos = sum(1 for s in samples if s["label"] == 1)
    print(f"samples: {len(samples)} ({pos} positives, {len(samples)-pos} negatives)",
          flush=True)
    for g, n in Counter(s["group"] for s in samples).most_common():
        print(f"   {g}: {n}", flush=True)

    tiles = sorted({str(p) for d in args.laz_dir for p in Path(d).glob("*.laz")})
    if not tiles:
        print(f"no LAZ tiles in {args.laz_dir}; run download_trasancos_lidar.py first")
        return 1
    for d in args.laz_dir:
        print(f"   {d}: {len(list(Path(d).glob('*.laz')))} teselas", flush=True)
    print(f"tiles: {len(tiles)} | workers {args.workers}", flush=True)

    slim = [{k: s[k] for k in ("sid", "x", "y", "label")} for s in samples]
    groups, orphans = group_samples_by_tiles(slim, tiles, args.extent_m)
    covered = sum(len(v) for v in groups.values())
    print(f"groups: {len(groups)} | samples covered by LiDAR: {covered} "
          f"| outside coverage: {orphans}", flush=True)

    tasks = [(list(k), v, args.extent_m, args.res_m, str(arr_dir))
             for k, v in groups.items()]

    written = 0
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(process_group, t): t for t in tasks}
        for i, f in enumerate(as_completed(futs), 1):
            try:
                w, tried = f.result()
                written += w
            except Exception as exc:
                print(f"  FAIL group of {len(futs[f][1])}: {exc}", flush=True)
            if i % 25 == 0 or i == len(tasks):
                print(f"  progress {i}/{len(tasks)} groups, {written} vignettes",
                      flush=True)

    # Spatial blocks, so train and val never share a hillside. O Val stays out.
    made = {p.stem for p in arr_dir.glob("*.npz")}
    index = []
    for s in samples:
        if s["sid"] not in made:
            continue
        blk = f"{int(s['x'] // BLOCK_M)}_{int(s['y'] // BLOCK_M)}"
        index.append({"sid": s["sid"], "label": s["label"], "group": s["group"],
                      "name": s["name"], "lon": s["lon"], "lat": s["lat"],
                      "block": blk, "split": s["split"]})

    blocks = sorted({r["block"] for r in index if r["split"] == "pool"})
    val_blocks = set(blocks[::args.val_every])  # 1 de cada N bloques
    for r in index:
        if r["split"] == "pool":
            r["split"] = "val" if r["block"] in val_blocks else "train"

    with open(args.out_dir / "index.tsv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, delimiter="\t",
                           fieldnames=["sid", "label", "group", "name",
                                       "lon", "lat", "block", "split"])
        w.writeheader()
        for r in index:
            w.writerow(r)

    stats = defaultdict(Counter)
    for r in index:
        stats[r["split"]][r["label"]] += 1
    meta = {"extent_m": args.extent_m, "res_m": args.res_m,
            "channels": ["normalised_dtm", "local_relief", "slope"],
            "blocks": len(blocks), "val_blocks": len(val_blocks),
            "counts": {k: dict(v) for k, v in stats.items()}}
    (args.out_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print(f"\ndone in {(time.time()-t0)/60:.1f} min | {len(index)} vignettes indexed",
          flush=True)
    for sp in ("train", "val", "test_o_val"):
        c = stats[sp]
        print(f"   {sp}: {c[1]} positives, {c[0]} negatives", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
