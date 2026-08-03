#!/usr/bin/env python3
"""Discovery-bias test: are catalogued castros systematically in open ground?

For every OSM castro/mamoa polygon falling inside the 24 PNOA-2024 LAZ tiles of
Trasancos, measure canopy cover and ground-return density from the point cloud,
and compare against random control locations drawn from the same tiles.

If catalogued sites sit under significantly less canopy than random terrain, the
catalogue is biased toward visible sites, and any model trained on it inherits
that bias. Concurrent over tiles, progress to stdout.
"""
from __future__ import annotations
import csv, glob, json, math, os, random, sys, time
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np
import laspy
from pyproj import Transformer

W = "/srv/data/castros-ia-galicia-current"
LAZ_DIR = f"{W}/data/external/lidar-mamoa-test-v1"
LABELS = f"{W}/data/lidar-mamoa-test-v1/test_sites.tsv"
OUT = f"{W}/data/canopy-bias-v1"
RADIUS = 40.0          # m, sampling disc around a site centre
N_CONTROL_PER_TILE = 120
VEG_CLASSES = (3, 4, 5)   # low / medium / high vegetation
GROUND = 2
SEED = 20260803


def load_sites():
    """Holdout castros/mamoas that the LiDAR tiles actually cover."""
    tr = Transformer.from_crs("EPSG:4326", "EPSG:25829", always_xy=True)
    out = []
    with open(LABELS, encoding="utf-8") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            try:
                lon = float(r["longitude"]); lat = float(r["latitude"])
            except (TypeError, ValueError):
                continue
            x, y = tr.transform(lon, lat)
            out.append({
                "osm_id": r.get("sample_id"),
                "label_class": (r.get("site_class") or "").strip(),
                "name": r.get("name"),
                "x": x, "y": y,
            })
    return out


def disc_stats(cls: np.ndarray, xs: np.ndarray, ys: np.ndarray,
               cx: float, cy: float, radius: float):
    m = (np.abs(xs - cx) <= radius) & (np.abs(ys - cy) <= radius)
    if not m.any():
        return None
    sx = xs[m]; sy = ys[m]; sc = cls[m]
    d2 = (sx - cx) ** 2 + (sy - cy) ** 2
    inside = d2 <= radius * radius
    if inside.sum() < 50:
        return None
    c = sc[inside]
    area = math.pi * radius * radius
    n_ground = int(np.isin(c, [GROUND]).sum())
    n_veg = int(np.isin(c, VEG_CLASSES).sum())
    denom = n_ground + n_veg
    if denom < 30:
        return None
    return {
        "n_points": int(c.size),
        "ground_density": n_ground / area,
        "veg_density": n_veg / area,
        "canopy_fraction": n_veg / denom,
    }


def process_tile(path: str):
    t0 = time.time()
    name = os.path.basename(path)
    las = laspy.read(path)
    xs = np.asarray(las.x); ys = np.asarray(las.y)
    cls = np.asarray(las.classification)
    minx, maxx = xs.min(), xs.max()
    miny, maxy = ys.min(), ys.max()

    sites = load_sites()
    rows = []
    for s in sites:
        if not (minx + RADIUS <= s["x"] <= maxx - RADIUS):
            continue
        if not (miny + RADIUS <= s["y"] <= maxy - RADIUS):
            continue
        st = disc_stats(cls, xs, ys, s["x"], s["y"], RADIUS)
        if st:
            rows.append({**st, "group": s["label_class"], "tile": name,
                         "name": s["name"], "osm_id": s["osm_id"]})

    rng = random.Random(SEED + hash(name) % 10000)
    site_xy = [(s["x"], s["y"]) for s in sites]
    made = 0
    tries = 0
    while made < N_CONTROL_PER_TILE and tries < N_CONTROL_PER_TILE * 25:
        tries += 1
        cx = rng.uniform(minx + RADIUS, maxx - RADIUS)
        cy = rng.uniform(miny + RADIUS, maxy - RADIUS)
        # keep controls away from any known site
        if any((cx - sx) ** 2 + (cy - sy) ** 2 < 250.0 ** 2 for sx, sy in site_xy):
            continue
        st = disc_stats(cls, xs, ys, cx, cy, RADIUS)
        if st:
            rows.append({**st, "group": "control", "tile": name,
                         "name": "", "osm_id": ""})
            made += 1

    print(f"[{name}] sites+controls={len(rows)} in {time.time()-t0:.1f}s", flush=True)
    return rows


def summarise(rows):
    def stats(g):
        v = [r["canopy_fraction"] for r in rows if r["group"] == g]
        d = [r["ground_density"] for r in rows if r["group"] == g]
        if not v:
            return None
        return {
            "n": len(v),
            "canopy_median": float(np.median(v)),
            "canopy_mean": float(np.mean(v)),
            "ground_density_median": float(np.median(d)),
            "frac_over_50pct_canopy": float(np.mean([x > 0.5 for x in v])),
        }
    return {g: stats(g) for g in ("castro", "mamoa", "control")}


def sigmas(rows, a, b):
    va = np.array([r["canopy_fraction"] for r in rows if r["group"] == a])
    vb = np.array([r["canopy_fraction"] for r in rows if r["group"] == b])
    if len(va) < 3 or len(vb) < 3:
        return float("nan")
    pooled = math.sqrt((va.var(ddof=1) + vb.var(ddof=1)) / 2)
    if pooled == 0:
        return 0.0
    return abs(np.median(va) - np.median(vb)) / pooled


def main():
    os.makedirs(OUT, exist_ok=True)
    tiles = sorted(glob.glob(f"{LAZ_DIR}/*.laz"))
    print(f"tiles: {len(tiles)}, workers: 3", flush=True)
    rows = []
    with ProcessPoolExecutor(max_workers=3) as ex:
        futs = {ex.submit(process_tile, t): t for t in tiles}
        done = 0
        for f in as_completed(futs):
            done += 1
            try:
                rows.extend(f.result())
            except Exception as e:
                print(f"FAIL {futs[f]}: {e}", flush=True)
            print(f"  progress {done}/{len(tiles)}", flush=True)

    with open(f"{OUT}/canopy_bias_rows.tsv", "w", newline="", encoding="utf-8") as fh:
        wcsv = csv.DictWriter(fh, delimiter="\t", fieldnames=[
            "tile", "group", "osm_id", "name", "n_points",
            "ground_density", "veg_density", "canopy_fraction"])
        wcsv.writeheader()
        for r in rows:
            wcsv.writerow(r)

    summary = summarise(rows)
    summary["separation_sigmas"] = {
        "castro_vs_control": sigmas(rows, "castro", "control"),
        "mamoa_vs_control": sigmas(rows, "mamoa", "control"),
    }
    with open(f"{OUT}/canopy_bias_summary.json", "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
