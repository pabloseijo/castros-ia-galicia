#!/usr/bin/env python3
"""Sweep Galicia province by province within a fixed disk budget.

A 128 m grid over Galicia is ~1.71M cells: ~3.4M WMS/WCS requests, ~79 h of
download and ~926 GB of imagery. The machine has ~561 GB free, so the naive
approach does not fit on disk at all.

This runs one bounded batch at a time — download, extract features, score,
delete the chips — so peak disk is one batch, not one province. Features are
roughly 1/100 the size of the imagery, so what survives is small.

Everything is resumable: completed batches are recorded and skipped, which
matters because the full sweep spans days and will be interrupted.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = Path("/srv/data/castros-ia-logs")
DEFAULT_STATE = LOG_DIR / "province_batch_state.json"
DEFAULT_OUT_DIR = PROJECT_ROOT / "data/galicia-sweep-v1"

# Rough mainland envelopes. Batches falling entirely in the sea cost one
# cheap DEM probe each and are then skipped, so loose boxes are acceptable.
PROVINCES = {
    "a_coruna": (-9.31, 42.70, -7.86, 43.79),
    "lugo": (-7.95, 42.35, -6.75, 43.70),
    "ourense": (-8.35, 41.81, -6.75, 42.60),
    "pontevedra": (-9.05, 41.85, -7.90, 42.85),
}


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(message: str) -> None:
    print(f"[{now()}] {message}", flush=True)


def load_state(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            return {}
    return {}


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=1), encoding="utf-8")


def free_gb(path: Path) -> float:
    usage = shutil.disk_usage(path)
    return usage.free / 1e9


def run(cmd: list[str], timeout: int) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=timeout
        )
        tail = "\n".join((result.stdout or "").strip().splitlines()[-6:])
        if result.returncode != 0:
            tail += "\n" + "\n".join((result.stderr or "").strip().splitlines()[-4:])
        return result.returncode == 0, tail
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except Exception as exc:
        return False, str(exc)[:300]


def coarse_land_mask(box: tuple, cache_dir: Path, coarse_res: int = 25):
    """One 25 m WCS request for the whole batch, used as a land pre-mask.

    Batch 0 spent 407 s and 5.568 DEM requests to discover it was entirely
    sea. A single coarse raster answers that for the whole box, so the
    expensive 5 m per-cell fetch only ever runs on land.
    """
    import numpy as np
    import rasterio
    from pyproj import Transformer
    from urllib.parse import urlencode
    from urllib.request import Request, urlopen

    min_lon, min_lat, max_lon, max_lat = box
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:25830", always_xy=True)
    xs, ys = [], []
    for lon, lat in ((min_lon, min_lat), (min_lon, max_lat), (max_lon, min_lat), (max_lon, max_lat)):
        x, y = transformer.transform(lon, lat)
        xs.append(x)
        ys.append(y)
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)

    params = [
        ("SERVICE", "WCS"), ("VERSION", "2.0.1"), ("REQUEST", "GetCoverage"),
        ("COVERAGEID", f"Elevacion25830_{coarse_res}"), ("FORMAT", "image/tiff"),
        ("SUBSET", f"x({minx:.2f},{maxx:.2f})"), ("SUBSET", f"y({miny:.2f},{maxy:.2f})"),
    ]
    url = f"https://servicios.idee.es/wcs-inspire/mdt?{urlencode(params)}"
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"coarse_{minx:.0f}_{miny:.0f}.tif"
    try:
        if not path.exists():
            request = Request(url, headers={"User-Agent": "castros-ia-galicia/1.0 coarse-mask"})
            with urlopen(request, timeout=120) as response:
                path.write_bytes(response.read())
        with rasterio.open(path) as src:
            dem = src.read(1).astype("float32")
            if src.nodata is not None:
                dem[dem == src.nodata] = np.nan
            return dem, src.transform, src.crs, transformer
    except Exception:
        return None, None, None, None


def prefilter_by_coarse_mask(
    grid_manifest: Path, out_manifest: Path, box: tuple, cache_dir: Path, min_elev_m: float
) -> tuple[int, int]:
    """Drop cells whose coarse elevation says sea, before any 5 m request."""
    import numpy as np

    dem, transform, _crs, transformer = coarse_land_mask(box, cache_dir)
    rows = read_tsv_local(grid_manifest)
    if dem is None or not rows:
        return len(rows), 0

    inv = ~transform
    keep = []
    dropped = 0
    height, width = dem.shape
    for row in rows:
        try:
            lon, lat = float(row["longitude"]), float(row["latitude"])
        except (KeyError, ValueError):
            keep.append(row)
            continue
        x, y = transformer.transform(lon, lat)
        col, line = inv * (x, y)
        c, r = int(col), int(line)
        if 0 <= r < height and 0 <= c < width:
            # Sample a small window: a single pixel on a coastline is noisy.
            window = dem[max(0, r - 1):r + 2, max(0, c - 1):c + 2]
            finite = window[np.isfinite(window)]
            if finite.size and float(np.nanmax(finite)) < min_elev_m:
                dropped += 1
                continue
        keep.append(row)

    if keep:
        out_manifest.parent.mkdir(parents=True, exist_ok=True)
        with out_manifest.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(
                fh, fieldnames=list(rows[0].keys()), dialect="excel-tab",
                extrasaction="ignore", lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(keep)
    return len(keep), dropped


def _dem_spread(payload: tuple[str, str]) -> tuple[str, float]:
    import numpy as np
    import rasterio

    tile_id, path = payload
    try:
        full = Path(path) if Path(path).is_absolute() else PROJECT_ROOT / path
        with rasterio.open(full) as src:
            dem = src.read(1).astype("float32")
            if src.nodata is not None:
                dem[dem == src.nodata] = np.nan
        return tile_id, float(np.nanstd(dem))
    except Exception:
        return tile_id, -1.0


def filter_land_cells(
    grid_manifest: Path, dem_manifest: Path, out_manifest: Path, flat_std_m: float
) -> tuple[int, int]:
    """Keep only cells whose DEM shows real relief; drop sea and estuary.

    Reads each downloaded MDT crop once and measures its spread. Flat, near
    constant elevation means water, which has no landform to rank and no
    reason to cost an orthophoto request.
    """
    dem_rows = {r.get("tile_id", ""): r for r in read_tsv_local(dem_manifest)}
    keep_ids: set[str] = set()
    dropped = 0

    payloads = [
        (tile_id, row.get("target_dem_path", ""))
        for tile_id, row in dem_rows.items()
        if row.get("dem_status") == "valid"
    ]
    dropped += len(dem_rows) - len(payloads)

    # Reading thousands of GeoTIFFs one at a time was the hidden serial step.
    workers = max(1, (os.cpu_count() or 2) - 1)
    if len(payloads) < 64 or workers == 1:
        results = [_dem_spread(item) for item in payloads]
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(_dem_spread, payloads, chunksize=32))
    for tile_id, spread in results:
        if spread < 0 or not math.isfinite(spread) or spread < flat_std_m:
            dropped += 1
        else:
            keep_ids.add(tile_id)

    grid_rows = read_tsv_local(grid_manifest)
    kept_rows = [r for r in grid_rows if r.get("tile_id", "") in keep_ids]
    if kept_rows:
        out_manifest.parent.mkdir(parents=True, exist_ok=True)
        with out_manifest.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(
                fh, fieldnames=list(grid_rows[0].keys()), dialect="excel-tab",
                extrasaction="ignore", lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(kept_rows)
    return len(kept_rows), dropped


def read_tsv_local(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, dialect="excel-tab"))


def batch_boxes(bbox: tuple[float, float, float, float], batch_deg: float) -> list[tuple]:
    min_lon, min_lat, max_lon, max_lat = bbox
    boxes = []
    lat = min_lat
    while lat < max_lat:
        lon = min_lon
        while lon < max_lon:
            boxes.append((lon, lat, min(lon + batch_deg, max_lon), min(lat + batch_deg, max_lat)))
            lon += batch_deg
        lat += batch_deg
    return boxes


def process_batch(
    province: str, index: int, box: tuple, args: argparse.Namespace, state: dict
) -> dict:
    key = f"{province}:{index}"
    tag = f"{province}-{index:04d}"
    out_dir = args.out_dir / province
    chip_root = PROJECT_ROOT / f"data/external/galicia-sweep-tmp/{tag}"
    grid_manifest = out_dir / f"grid_{tag}.tsv"
    features_out = out_dir / f"features_{tag}.tsv"
    grid_split = f"sweep_{tag}"
    python = sys.executable
    record = {"box": box, "started_at": now()}

    bbox_arg = f"--bbox={box[0]:.5f},{box[1]:.5f},{box[2]:.5f},{box[3]:.5f}"

    ok, out = run(
        [
            python, "scripts/build_trasancos_inference_ranking.py",
            "--stage", "grid", bbox_arg,
            "--step-m", str(args.step_m),
            "--known-match-m", "128",
            "--tile-prefix", f"sw-{tag}",
            "--grid-split", grid_split,
            "--out-dir", str(out_dir),
            "--chip-root", str(chip_root),
            "--grid-manifest", str(grid_manifest),
        ],
        timeout=3600,
    )
    if not ok:
        record.update({"ok": False, "stage": "grid", "detail": out})
        return record

    cells = max(0, sum(1 for _ in grid_manifest.open(encoding="utf-8")) - 1)
    record["cells"] = cells
    if cells == 0:
        record.update({"ok": True, "skipped": "empty_grid", "finished_at": now()})
        return record

    # One coarse 25 m raster for the whole box first: it answers "is this sea"
    # in a single request instead of 5.568. Batch 0 spent 407 s discovering
    # that the hard way.
    coarse_manifest = out_dir / f"grid_coarse_{tag}.tsv"
    kept, dropped = prefilter_by_coarse_mask(
        grid_manifest, coarse_manifest, box,
        PROJECT_ROOT / "data/external/galicia-sweep-tmp/coarse", args.min_elev_m,
    )
    record["cells_after_coarse"] = kept
    record["cells_coarse_dropped"] = dropped
    log(f"  coarse mask: dropped {dropped} of {kept + dropped} before any 5 m request")
    if kept == 0:
        record.update({"ok": True, "skipped": "all_sea_coarse", "finished_at": now()})
        return record
    dem_input = coarse_manifest if dropped else grid_manifest

    # DEM before RGB: a MDT5 crop is ~24 KB against ~500 KB for an orthophoto.
    ok, out = run(
        [
            python, "scripts/export_weak_label_relief_wcs.py",
            "--input", str(dem_input),
            "--out-manifest", str(out_dir / f"dem_{tag}.tsv"),
            "--report", str(PROJECT_ROOT / f"reports/sweep_dem_{tag}.md"),
            "--workers", str(args.download_workers),
            "--wcs-parallel", str(args.wcs_parallel),
        ],
        timeout=args.batch_timeout,
    )
    record["dem_ok"] = ok
    if not ok:
        record.update({"ok": False, "stage": "dem", "detail": out})
        return record

    land_manifest = out_dir / f"grid_land_{tag}.tsv"
    kept, dropped = filter_land_cells(
        dem_input, out_dir / f"dem_{tag}.tsv", land_manifest, args.flat_dem_std_m
    )
    record["cells_land"] = kept
    record["cells_sea_skipped"] = dropped
    log(f"  sea/flat skipped before RGB: {dropped} of {kept + dropped}")
    if kept == 0:
        record.update({"ok": True, "skipped": "all_sea", "finished_at": now()})
        relief_dir = PROJECT_ROOT / "data/external/weak-label-relief-v1" / grid_split
        if relief_dir.exists():
            shutil.rmtree(relief_dir, ignore_errors=True)
        return record

    ok, out = run(
        [
            python, "scripts/export_weak_label_chips.py",
            "--input", str(land_manifest),
            "--out-manifest", str(out_dir / f"rgb_{tag}.tsv"),
            "--report", str(PROJECT_ROOT / f"reports/sweep_rgb_{tag}.md"),
            "--workers", str(args.download_workers),
            "--ign-parallel", str(args.ign_parallel),
        ],
        timeout=args.batch_timeout,
    )
    record["rgb_ok"] = ok
    if not ok:
        record.update({"ok": False, "stage": "rgb", "detail": out})
        return record

    # Extract, then delete the imagery. This is what keeps Galicia on disk.
    ok, out = run(
        [
            python, "scripts/extract_feature_bank.py",
            "--rgb-manifest", str(out_dir / f"rgb_{tag}.tsv"),
            "--dem-manifest", str(out_dir / f"dem_{tag}.tsv"),
            "--out", str(features_out),
            "--dataset", f"sweep_{province}",
            "--workers", str(args.workers),
            "--progress-every", "2000",
            "--delete-chips-after",
        ],
        timeout=args.batch_timeout,
    )
    record.update({"ok": ok, "stage": "features" if not ok else "done", "detail": out})
    if chip_root.exists():
        shutil.rmtree(chip_root, ignore_errors=True)
    relief_dir = PROJECT_ROOT / "data/external/weak-label-relief-v1" / grid_split
    if relief_dir.exists():
        shutil.rmtree(relief_dir, ignore_errors=True)
    record["finished_at"] = now()
    record["free_gb_after"] = round(free_gb(PROJECT_ROOT), 1)
    return record


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provinces", default="a_coruna")
    parser.add_argument("--batch-deg", type=float, default=0.10)
    parser.add_argument("--step-m", type=float, default=128.0)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    parser.add_argument("--download-workers", type=int, default=6)
    parser.add_argument("--ign-parallel", type=int, default=5)
    parser.add_argument("--wcs-parallel", type=int, default=4)
    parser.add_argument("--batch-timeout", type=int, default=10800)
    parser.add_argument("--max-batches", type=int, default=0, help="0 = no limit")
    parser.add_argument("--min-free-gb", type=float, default=60.0)
    parser.add_argument("--flat-dem-std-m", type=float, default=1.5)
    parser.add_argument("--min-elev-m", type=float, default=2.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.out_dir = args.out_dir if args.out_dir.is_absolute() else PROJECT_ROOT / args.out_dir
    state = load_state(args.state)
    state.setdefault("batches", {})
    state.setdefault("started_at", now())

    names = [p.strip() for p in args.provinces.split(",") if p.strip()]
    planned: list[tuple[str, int, tuple]] = []
    for province in names:
        if province not in PROVINCES:
            log(f"unknown province {province}, skipping")
            continue
        for index, box in enumerate(batch_boxes(PROVINCES[province], args.batch_deg)):
            planned.append((province, index, box))

    log(f"planned batches: {len(planned)} across {names}")
    done = 0
    for province, index, box in planned:
        key = f"{province}:{index}"
        if state["batches"].get(key, {}).get("ok"):
            continue
        if free_gb(PROJECT_ROOT) < args.min_free_gb:
            log(f"STOP: free disk below {args.min_free_gb} GB")
            break
        if args.max_batches and done >= args.max_batches:
            log(f"reached --max-batches {args.max_batches}")
            break

        log(f"BATCH {key} bbox={box}")
        started = time.time()
        record = process_batch(province, index, box, args, state)
        record["seconds"] = round(time.time() - started, 1)
        state["batches"][key] = record
        save_state(args.state, state)
        status = "ok" if record.get("ok") else f"FAILED at {record.get('stage')}"
        log(f"  {status} cells={record.get('cells','?')} free={record.get('free_gb_after','?')} GB")
        done += 1

    ok_batches = sum(1 for v in state["batches"].values() if v.get("ok"))
    cells = sum(int(v.get("cells", 0)) for v in state["batches"].values() if v.get("ok"))
    log(f"finished: {ok_batches} batches ok, {cells} cells featurised, free {free_gb(PROJECT_ROOT):.0f} GB")


if __name__ == "__main__":
    main()
