#!/usr/bin/env python3
"""LiDAR sampled around the labels, instead of blanket-covering one comarca.

Covering Trasancos costs 756 tiles (~34 GB) and yields 68 usable positives,
which under the diagnostic-accuracy sample-size formula gives a +-0.109
interval on sensitivity. Galicia holds 3071 trainable positives; they are just
not under any downloaded LiDAR. Choosing tiles by how many labels they complete
buys far more statistical power per gigabyte:

    tiles    GB    positives    CI95 width
      600    27          330         0.098
      900    40          496         0.080
     1500    68          781         0.064

A vignette is 512 m and CNIG ships 1 km tiles, so a label needs every tile its
extent touches: 2.27 on average, and a label only counts once all of them are
present. The selection is greedy on that coverage, but capped per spatial block
so it does not collapse into whichever corner of Galicia happens to be densest
-- geographic spread is what the model-drift question needs.

Reuses the manifest-based resume and per-worker logging of
download_trasancos_lidar.py, so an interrupted run costs zero CNIG queries on
restart.
"""
from __future__ import annotations

import argparse
import collections
import csv
import math
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from download_trasancos_lidar import (  # noqa: E402
    DEFAULT_LOG_DIR as _UNUSED_LOG,
    handle_tile,
    load_previous,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MASTER = PROJECT_ROOT / "data/weak-label-splits-v1/weak_label_master.tsv"
OUT_DIR = PROJECT_ROOT / "data/lidar-positives-v1"
LAZ_DIR = PROJECT_ROOT / "data/external/lidar-positives-v1"
LOG_DIR = OUT_DIR / "worker-logs"

HALF_M = 256.0        # media viñeta de 512 m
TILE_M = 1000.0       # unidad de descarga del CNIG
BLOCK_M = 10000.0     # bloque de estratificación espacial


def load_positives():
    from pyproj import Transformer
    tr = Transformer.from_crs("EPSG:4326", "EPSG:25829", always_xy=True)
    out = []
    for r in csv.DictReader(open(MASTER, encoding="utf-8"), delimiter="\t"):
        if r.get("label_class") != "1":
            continue
        # excluded_review es el ruido toponimico que el proyecto ya filtró:
        # calles, edificios y capillas llamadas "Castro".
        if r.get("final_split") == "excluded_review":
            continue
        try:
            lon, lat = float(r["longitude"]), float(r["latitude"])
        except (KeyError, TypeError, ValueError):
            continue
        x, y = tr.transform(lon, lat)
        out.append({"sample_id": r.get("sample_id", ""), "name": r.get("name", ""),
                    "municipality": r.get("municipality", ""),
                    "lon": lon, "lat": lat, "x": x, "y": y})
    return out


def tiles_touched(x, y):
    t = set()
    for dx in (-HALF_M, HALF_M):
        for dy in (-HALF_M, HALF_M):
            t.add((int((x + dx) // TILE_M), int((y + dy) // TILE_M)))
    return frozenset(t)


def select_tiles(positives, budget, per_block_cap):
    """Greedy by labels completed, capped per 10 km block for spatial spread."""
    need = {p["sample_id"] or i: tiles_touched(p["x"], p["y"])
            for i, p in enumerate(positives)}
    cover = collections.defaultdict(set)
    for pid, ts in need.items():
        for t in ts:
            cover[t].add(pid)

    block_of = lambda t: (int(t[0] * TILE_M // BLOCK_M), int(t[1] * TILE_M // BLOCK_M))
    per_block = collections.Counter()
    chosen = set()
    for tile, _ in sorted(cover.items(), key=lambda kv: -len(kv[1])):
        if len(chosen) >= budget:
            break
        b = block_of(tile)
        if per_block[b] >= per_block_cap:
            continue
        chosen.add(tile)
        per_block[b] += 1

    complete = [pid for pid, ts in need.items() if ts <= chosen]
    return chosen, complete, need


def ci_width(n, p=0.70, z=1.96):
    if n <= 0:
        return 1.0
    d = 1 + z * z / n
    return 2 * z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--budget", type=int, default=900, help="teselas a descargar")
    ap.add_argument("--per-block-cap", type=int, default=12,
                    help="máximo de teselas por bloque de 10 km")
    ap.add_argument("--laz-dir", type=Path, default=LAZ_DIR)
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--min-free-gb", type=float, default=80.0)
    ap.add_argument("--plan-only", action="store_true")
    args = ap.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    args.laz_dir.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    pos = load_positives()
    chosen, complete, need = select_tiles(pos, args.budget, args.per_block_cap)
    est_gb = len(chosen) * 45 / 1000.0
    print(f"positivos entrenables: {len(pos)}", flush=True)
    print(f"teselas elegidas: {len(chosen)} (~{est_gb:.0f} GB) | "
          f"positivos completos: {len(complete)} | "
          f"IC95% sobre sensibilidad 0.70: ±{ci_width(len(complete))/2:.3f}", flush=True)

    blocks = collections.Counter(
        (int(t[0] * TILE_M // BLOCK_M), int(t[1] * TILE_M // BLOCK_M)) for t in chosen)
    print(f"reparto espacial: {len(blocks)} bloques de 10 km, "
          f"máx {max(blocks.values())} teselas por bloque", flush=True)

    with open(args.out_dir / "selected_positives.tsv", "w", newline="",
              encoding="utf-8") as fh:
        w = csv.DictWriter(fh, delimiter="\t",
                           fieldnames=["sample_id", "name", "municipality", "lon", "lat"])
        w.writeheader()
        done = set(complete)
        for i, p in enumerate(pos):
            if (p["sample_id"] or i) in done:
                w.writerow({k: p[k] for k in
                            ("sample_id", "name", "municipality", "lon", "lat")})

    if args.plan_only:
        print("plan-only: no se descarga nada", flush=True)
        return 0

    free_gb = (os.statvfs(args.laz_dir).f_bavail *
               os.statvfs(args.laz_dir).f_frsize / 1e9)
    print(f"espacio libre: {free_gb:.0f} GB", flush=True)
    if free_gb - est_gb < args.min_free_gb:
        print("ABORTADO: margen de disco insuficiente", flush=True)
        return 1

    from pyproj import Transformer
    inv = Transformer.from_crs("EPSG:25829", "EPSG:4326", always_xy=True)
    points = []
    for tx, ty in sorted(chosen):
        cx, cy = tx * TILE_M + TILE_M / 2, ty * TILE_M + TILE_M / 2
        lon, lat = inv.transform(cx, cy)
        points.append({"query_tile_lower_id": f"{tx}-{ty}",
                       "query_x_utm29": f"{cx:.2f}", "query_y_utm29": f"{cy:.2f}",
                       "query_lon_wgs84": f"{lon:.8f}", "query_lat_wgs84": f"{lat:.8f}"})

    manifest = args.out_dir / "positives_lidar_manifest.tsv"
    known = load_previous(manifest)
    if known:
        print(f"manifiesto previo: {len(known)} teselas ya resueltas", flush=True)

    fields = ["tile_id", "query_tile_lower_id", "query_x_utm29", "query_y_utm29",
              "query_lon_wgs84", "query_lat_wgs84", "file_name", "sec",
              "status", "path", "size_mb"]

    def flush(rows):
        merged = dict(known)
        for r in rows:
            merged[r["tile_id"]] = r
        tmp = manifest.with_suffix(".tsv.tmp")
        with open(tmp, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, delimiter="\t", fieldnames=fields,
                               extrasaction="ignore")
            w.writeheader()
            for r in sorted(merged.values(), key=lambda r: r.get("tile_id", "")):
                w.writerow(r)
        os.replace(tmp, manifest)

    rows, t0 = [], time.time()
    total = len(points)
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(handle_tile, p, args.laz_dir, LOG_DIR, total, known)
                for p in points]
        for i, f in enumerate(as_completed(futs), 1):
            rows.append(f.result())
            if i % 25 == 0:
                flush(rows)
                print(f"  progress {i}/{total}", flush=True)
    flush(rows)

    ok = sum(1 for r in rows if r["status"] in {"downloaded", "exists", "ok"})
    got = sum(float(r["size_mb"]) for r in rows if r["size_mb"])
    print(f"\nlisto en {(time.time()-t0)/60:.1f} min | usables {ok}/{total} | "
          f"{got/1000:.1f} GB", flush=True)
    for k, v in collections.Counter(r["status"].split(":")[0] for r in rows).most_common():
        print(f"   {k}: {v}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
