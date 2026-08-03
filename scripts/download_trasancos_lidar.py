#!/usr/bin/env python3
"""Download PNOA 3rd-coverage LiDAR (LAZ) for the whole Trasancos pilot area.

The 5 m MDT5 the project has been using cannot resolve a rampart, and more than
half of the catalogued castros sit under >50% canopy, where the orthophoto sees
treetops. PNOA 2024 carries ~2 ground returns/m^2 under that canopy, which is
what a 1 m bare-earth DTM needs.

Courtesy matters more than speed here: CNIG is a free public service, so the
CNIG semaphore stays small and every failure backs off instead of retrying hot.
Resumable by design — a tile already on disk is never re-fetched, so a crash of
the external disk costs only the tile in flight.
"""
from __future__ import annotations

import argparse
import csv
import math
import os
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from query_viladonga_cnig_lidar import (  # noqa: E402
    download_file,
    init_download,
    query_archivos_serie,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT_DIR = PROJECT_ROOT / "data/lidar-trasancos-v1"
DEFAULT_LAZ_DIR = PROJECT_ROOT / "data/external/lidar-trasancos-v1"
DEFAULT_LOG_DIR = DEFAULT_OUT_DIR / "worker-logs"

# Same envelope as the dense inference grid, so labels and rasters line up.
TRASANCOS = (-8.33, 43.42, -7.99, 43.65)

CNIG_CONCURRENCY = 3          # be a good citizen on a free public service
MAX_ATTEMPTS = 4
BASE_BACKOFF = 4.0

_cnig_sem = threading.Semaphore(CNIG_CONCURRENCY)
_progress_lock = threading.Lock()
_done = 0


def utm29_grid(bbox, step_m=1000.0):
    """One query point per 1 km CNIG tile covering the bbox."""
    from pyproj import Transformer

    fwd = Transformer.from_crs("EPSG:4326", "EPSG:25829", always_xy=True)
    inv = Transformer.from_crs("EPSG:25829", "EPSG:4326", always_xy=True)
    w, s, e, n = bbox
    xs, ys = [], []
    for lon, lat in ((w, s), (w, n), (e, s), (e, n)):
        x, y = fwd.transform(lon, lat)
        xs.append(x)
        ys.append(y)
    minx = math.floor(min(xs) / step_m) * step_m
    maxx = math.ceil(max(xs) / step_m) * step_m
    miny = math.floor(min(ys) / step_m) * step_m
    maxy = math.ceil(max(ys) / step_m) * step_m

    points = []
    y = miny
    while y < maxy:
        x = minx
        while x < maxx:
            cx, cy = x + step_m / 2.0, y + step_m / 2.0
            lon, lat = inv.transform(cx, cy)
            points.append({
                "query_tile_lower_id": f"{int(x/1000)}-{int(y/1000)}",
                "query_x_utm29": f"{cx:.2f}",
                "query_y_utm29": f"{cy:.2f}",
                "query_lon_wgs84": f"{lon:.8f}",
                "query_lat_wgs84": f"{lat:.8f}",
            })
            x += step_m
        y += step_m
    return points


def with_backoff(fn, *args, what="", log=None):
    """Retry with jittered exponential backoff; never hammer on failure."""
    last = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with _cnig_sem:
                return fn(*args)
        except Exception as exc:  # network, parse, transient 5xx
            last = exc
            if attempt == MAX_ATTEMPTS:
                break
            delay = BASE_BACKOFF * (2 ** (attempt - 1)) + random.uniform(0, 2)
            if log:
                log(f"retry {attempt}/{MAX_ATTEMPTS} {what}: {exc}; sleep {delay:.1f}s")
            time.sleep(delay)
    raise RuntimeError(f"{what} failed after {MAX_ATTEMPTS}: {last}")


def load_previous(manifest: Path) -> dict:
    """What a previous run already resolved, so a resume asks CNIG nothing."""
    if not manifest.exists():
        return {}
    out = {}
    with open(manifest, encoding="utf-8") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            out[r.get("tile_id", "")] = r
    return out


def handle_tile(point, laz_dir: Path, log_dir: Path, total: int, known=None):
    global _done
    tile_id = point["query_tile_lower_id"]
    log_path = log_dir / f"worker_{threading.current_thread().name}.log"

    def log(msg):
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%H:%M:%S')} [{tile_id}] {msg}\n")

    row = {"tile_id": tile_id, **point, "file_name": "", "sec": "",
           "status": "", "path": "", "size_mb": ""}
    try:
        # Resume without re-querying. A previous run already resolved this tile
        # to a filename, so if that file is on disk there is nothing to ask
        # CNIG. Without this a restart re-queries all 756 tiles, which is rude
        # to a free public service and slow on a Pi that keeps dying mid-run.
        prev = (known or {}).get(tile_id)
        if prev:
            fn = prev.get("file_name") or ""
            if fn:
                cached = laz_dir / fn
                if cached.exists() and cached.stat().st_size > 0:
                    row.update({"file_name": fn, "sec": prev.get("sec", ""),
                                "status": "exists", "path": str(cached),
                                "size_mb": f"{cached.stat().st_size/1e6:.1f}"})
                    log("ya en disco segun manifiesto, sin consulta")
                    return row
            elif prev.get("status") == "no_tile_in_series":
                row["status"] = "no_tile_in_series"
                log("sin tesela LIDA3 segun manifiesto, sin consulta")
                return row

        _t, files = with_backoff(
            query_archivos_serie, "LIDA3",
            point["query_lon_wgs84"], point["query_lat_wgs84"],
            what="archivosSerie", log=log)
        if not files:
            row["status"] = "no_tile_in_series"
            log("no LIDA3 tile for this point")
            return row

        file_name, sec = files[0]
        row["file_name"], row["sec"] = file_name, sec

        out_path = laz_dir / file_name
        if out_path.exists() and out_path.stat().st_size > 0:
            row["status"] = "exists"
            row["path"] = str(out_path)
            row["size_mb"] = f"{out_path.stat().st_size/1e6:.1f}"
            log("already on disk, skipped")
            return row

        state = with_backoff(init_download, sec, what="initDescargaDir", log=log)
        if not state.startswith("ready"):
            row["status"] = f"init_{state}"
            log(f"init refused: {state}")
            return row

        path, status = with_backoff(
            download_file, sec, file_name, laz_dir, what="descargaDir", log=log)
        row["path"], row["status"] = path, status
        if path and Path(path).exists():
            row["size_mb"] = f"{Path(path).stat().st_size/1e6:.1f}"
        log(f"{status} {row['size_mb']} MB")
    except Exception as exc:
        row["status"] = f"error:{exc}"
        log(f"FAILED: {exc}")
    finally:
        with _progress_lock:
            _done += 1
            if _done % 10 == 0 or _done == total:
                print(f"  progress {_done}/{total}", flush=True)
    return row


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    ap.add_argument("--laz-dir", type=Path, default=DEFAULT_LAZ_DIR)
    ap.add_argument("--workers", type=int, default=CNIG_CONCURRENCY)
    ap.add_argument("--limit", type=int, default=0, help="0 = all tiles")
    ap.add_argument("--min-free-gb", type=float, default=60.0)
    args = ap.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    args.laz_dir.mkdir(parents=True, exist_ok=True)
    DEFAULT_LOG_DIR.mkdir(parents=True, exist_ok=True)

    points = utm29_grid(TRASANCOS)
    if args.limit:
        points = points[: args.limit]
    total = len(points)
    est_gb = total * 45 / 1000.0
    free_gb = os.statvfs(args.laz_dir).f_bavail * os.statvfs(args.laz_dir).f_frsize / 1e9
    print(f"tiles: {total} | estimated ~{est_gb:.0f} GB | free {free_gb:.0f} GB "
          f"| workers {args.workers}", flush=True)
    if free_gb - est_gb < args.min_free_gb:
        print("ABORT: not enough headroom on /srv/data", flush=True)
        return 1

    manifest = args.out_dir / "trasancos_lidar_manifest.tsv"
    known = load_previous(manifest)
    if known:
        print(f"manifiesto previo: {len(known)} teselas ya resueltas", flush=True)

    fields = ["tile_id", "query_tile_lower_id", "query_x_utm29", "query_y_utm29",
              "query_lon_wgs84", "query_lat_wgs84", "file_name", "sec",
              "status", "path", "size_mb"]

    def flush(rows):
        """Write the manifest atomically, merging anything a previous run knew.

        Flushed periodically rather than once at the end: this Pi's external
        disk has hung mid-run before, and a manifest that only exists after the
        last tile is a manifest that never exists.
        """
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

    rows = []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(handle_tile, p, args.laz_dir, DEFAULT_LOG_DIR, total, known)
                for p in points]
        for i, f in enumerate(as_completed(futs), 1):
            rows.append(f.result())
            if i % 25 == 0:
                flush(rows)
    flush(rows)

    ok = sum(1 for r in rows if r["status"] in {"downloaded", "exists", "ok"})
    got_mb = sum(float(r["size_mb"]) for r in rows if r["size_mb"])
    print(f"\ndone in {(time.time()-t0)/60:.1f} min | usable {ok}/{total} "
          f"| {got_mb/1000:.1f} GB | manifest {manifest}", flush=True)
    from collections import Counter
    for k, v in Counter(r["status"].split(":")[0] for r in rows).most_common():
        print(f"   {k}: {v}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
