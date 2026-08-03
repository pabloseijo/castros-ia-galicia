#!/usr/bin/env python3
"""Named hard negatives for the Trasancos pilot, from OpenStreetMap.

The pilot's catalogued negatives are 97.8% megalithic mounds and contain zero
modern or natural noise, so any score measured against them answers "castro or
mound?" rather than "castro or anything else?". Landauer et al. (2025) report
what actually generates false positives at continental scale: forest tracks,
field terraces, medieval structures, modern hilltop villages, mining features
and natural landforms. This script goes and gets exactly those, by name.

Sampling named OSM features beats random terrain because each negative carries
the reason it is hard, so a confusion matrix can be read by cause instead of
just counted. Random terrain mostly teaches "empty ground", which the landscape
negatives already cover.

Overpass is a free volunteer service: one query at a time, generous timeouts,
and the whole run is a handful of requests rather than thousands.

Output is ODbL-derived; attribution is required if anything downstream ships.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = PROJECT_ROOT / "data/trasancos-hard-negatives-v1"
REPORT = PROJECT_ROOT / "reports/trasancos_hard_negatives_v1.md"

ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
UA = "castros-ia-galicia/0.1 (archaeological research; contact via repo)"

# Generous envelope over the six Trasancos councils; the council filter below
# is what actually decides membership.
BBOX = (43.42, -8.40, 43.72, -7.95)          # S, W, N, E for Overpass
BBOX_GALICIA = (41.80, -9.40, 43.85, -6.70)  # toda Galicia

# Overpass rechaza o agota una consulta que cubra Galicia entera para clases
# densas como highway=track, asi que el area grande se trocea y cada trozo se
# cachea por separado: si una peticion falla solo se reintenta ese trozo.
SUBTILE_DEG = 0.5

TRASANCOS = {"Ferrol", "Narón", "Naron", "Neda", "Fene", "Valdoviño",
             "Valdovino", "San Sadurniño", "San Sadurnino"}

# Each class maps to the Landauer false-positive taxonomy.
CLASSES: dict[str, list[str]] = {
    "mining_quarry": [
        'way["landuse"="quarry"]',
        'way["man_made"="mineshaft"]',
        'node["man_made"="mineshaft"]',
    ],
    "forest_track": [
        'way["highway"="track"]["surface"~"ground|dirt|unpaved|gravel"]',
    ],
    "medieval_structure": [
        'way["historic"="ruins"]',
        'node["historic"="ruins"]',
        'way["historic"="castle"]',
        'node["historic"="castle"]',
        'way["historic"="church"]',
        'way["building"="church"]',
    ],
    "hilltop_settlement": [
        'node["place"~"hamlet|village|isolated_dwelling"]',
    ],
    "natural_landform": [
        'node["natural"="peak"]',
        'way["natural"="rock"]',
        'node["natural"="rock"]',
        'way["natural"="cliff"]',
    ],
    "modern_infrastructure": [
        'way["man_made"="water_tower"]',
        'node["man_made"="water_tower"]',
        'way["man_made"="storage_tank"]',
        'way["landuse"="reservoir"]',
        'node["junction"="roundabout"]',
        'way["junction"="roundabout"]',
        'node["power"="tower"]',
    ],
    "agricultural_enclosure": [
        'way["landuse"="orchard"]',
        'way["landuse"="vineyard"]',
        'way["barrier"="hedge"]',
    ],
}


def overpass(query: str, attempts: int = 3, timeout: int = 180) -> dict | None:
    body = urllib.parse.urlencode({"data": query}).encode()
    for i in range(attempts):
        ep = ENDPOINTS[i % len(ENDPOINTS)]
        try:
            req = urllib.request.Request(
                ep, data=body,
                headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except Exception as exc:
            wait = 20 * (i + 1)
            print(f"    overpass {ep.split('/')[2]} failed ({exc}); "
                  f"retry in {wait}s", flush=True)
            if i < attempts - 1:
                time.sleep(wait)
    return None


def build_query(selectors: list[str], bbox) -> str:
    s, w, n, e = bbox
    parts = "".join(f"  {sel}({s},{w},{n},{e});\n" for sel in selectors)
    return f"[out:json][timeout:180];\n(\n{parts});\nout center tags;\n"


def subtiles(bbox, step=SUBTILE_DEG):
    """Trocea un bbox grande en cuadros manejables para Overpass."""
    s, w, n, e = bbox
    if (n - s) <= step and (e - w) <= step:
        return [bbox]
    out = []
    lat = s
    while lat < n:
        lon = w
        while lon < e:
            out.append((lat, lon, min(lat + step, n), min(lon + step, e)))
            lon += step
        lat += step
    return out


def centroid(el: dict):
    if el.get("type") == "node":
        return el.get("lon"), el.get("lat")
    c = el.get("center") or {}
    return c.get("lon"), c.get("lat")


def haversine_m(lon1, lat1, lon2, lat2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(a))


def load_known_sites() -> list[tuple[float, float]]:
    """Catalogued castros, so a negative is never sampled on top of one."""
    pts = []
    master = PROJECT_ROOT / "data/weak-label-splits-v1/weak_label_master.tsv"
    if master.exists():
        for r in csv.DictReader(open(master, encoding="utf-8"), delimiter="\t"):
            if r.get("label_class") != "1":
                continue
            try:
                pts.append((float(r["longitude"]), float(r["latitude"])))
            except (KeyError, TypeError, ValueError):
                continue
    osm = PROJECT_ROOT / "data/osm-strong-labels-v1/osm_strong_labels.tsv"
    if osm.exists():
        for r in csv.DictReader(open(osm, encoding="utf-8"), delimiter="\t"):
            if r.get("site_class") != "castro":
                continue
            try:
                pts.append((float(r["centroid_lon"]), float(r["centroid_lat"])))
            except (KeyError, TypeError, ValueError):
                continue
    return pts


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    ap.add_argument("--per-class", type=int, default=400,
                    help="cap per class, so tracks do not swamp the set")
    ap.add_argument("--buffer-m", type=float, default=250.0,
                    help="minimum distance from any catalogued castro")
    ap.add_argument("--min-sep-m", type=float, default=120.0,
                    help="minimum distance between two negatives")
    ap.add_argument("--seed", type=int, default=20260803)
    ap.add_argument("--scope", choices=("trasancos", "galicia"), default="trasancos")
    args = ap.parse_args()
    args.bbox = BBOX_GALICIA if args.scope == "galicia" else BBOX

    args.out_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)

    known = load_known_sites()
    print(f"catalogued castros to avoid: {len(known)}", flush=True)

    # Cache each class's raw response. Overpass is a volunteer service and it
    # rate-limits hard; without this, an interrupted run throws away every
    # query it already paid for and the retry hammers them again for nothing.
    cache_dir = args.out_dir / "overpass-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    for cls, selectors in CLASSES.items():
        cache = cache_dir / f"{cls}.json"
        if cache.exists():
            data = json.loads(cache.read_text(encoding="utf-8"))
            print(f"[{cls}] from cache", flush=True)
        else:
            tiles = subtiles(args.bbox)
            print(f"[{cls}] {len(selectors)} selectores x {len(tiles)} trozos...",
                  flush=True)
            elements, failed = [], 0
            for i, tb in enumerate(tiles, 1):
                sub = cache_dir / f"{cls}__{i:03d}.json"
                if sub.exists():
                    elements += json.loads(sub.read_text(encoding="utf-8")).get("elements", [])
                    continue
                d = overpass(build_query(selectors, tb))
                if not d:
                    failed += 1
                    continue
                sub.write_text(json.dumps(d), encoding="utf-8")
                elements += d.get("elements", [])
                time.sleep(2)
            if failed:
                print(f"[{cls}] {failed}/{len(tiles)} trozos fallaron; relanzar "
                      f"para reintentar solo esos", flush=True)
            if not elements:
                print(f"[{cls}] sin elementos, se salta", flush=True)
                continue
            data = {"elements": elements}
            cache.write_text(json.dumps(data), encoding="utf-8")
        els = data.get("elements") or []
        cand = []
        for el in els:
            lon, lat = centroid(el)
            if lon is None or lat is None:
                continue
            tags = el.get("tags") or {}
            cand.append({
                "osm_type": el.get("type"), "osm_id": el.get("id"),
                "negative_class": cls,
                "name": tags.get("name", ""),
                "osm_tags": ";".join(f"{k}={v}" for k, v in sorted(tags.items())
                                     if k in ("landuse", "highway", "historic",
                                              "natural", "man_made", "place",
                                              "junction", "power", "barrier",
                                              "building", "surface"))[:180],
                "longitude": lon, "latitude": lat,
            })
        rng.shuffle(cand)
        print(f"[{cls}] {len(els)} elements -> {len(cand)} with coordinates",
              flush=True)
        rows.extend(cand[: args.per_class * 3])  # trim later after filtering
        time.sleep(3)  # courtesy gap between Overpass queries

    # Filter: away from castros, and spatially separated from each other.
    kept: list[dict] = []
    per_class = Counter()
    for r in rows:
        if per_class[r["negative_class"]] >= args.per_class:
            continue
        lon, lat = r["longitude"], r["latitude"]
        if any(haversine_m(lon, lat, kx, ky) < args.buffer_m for kx, ky in known):
            continue
        if any(haversine_m(lon, lat, k["longitude"], k["latitude"]) < args.min_sep_m
               for k in kept):
            continue
        kept.append(r)
        per_class[r["negative_class"]] += 1

    fields = ["osm_type", "osm_id", "negative_class", "name", "osm_tags",
              "longitude", "latitude"]
    out_tsv = args.out_dir / "trasancos_hard_negatives.tsv"
    with open(out_tsv, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, delimiter="\t", fieldnames=fields,
                           extrasaction="ignore")
        w.writeheader()
        for r in kept:
            w.writerow(r)

    gj = {"type": "FeatureCollection", "features": [
        {"type": "Feature",
         "geometry": {"type": "Point", "coordinates": [r["longitude"], r["latitude"]]},
         "properties": {k: r[k] for k in fields if k not in ("longitude", "latitude")}}
        for r in kept]}
    (args.out_dir / "trasancos_hard_negatives.geojson").write_text(
        json.dumps(gj), encoding="utf-8")

    lines = ["# Trasancos hard negatives from OpenStreetMap", "",
             f"Kept `{len(kept)}` negatives, `{args.buffer_m:.0f} m` clear of any "
             f"catalogued castro and `{args.min_sep_m:.0f} m` apart from each other.",
             "", "Classes follow the false-positive taxonomy reported by Landauer "
             "et al. (2025) for continental-scale hillfort search.", "",
             "| class | n |", "|---|---:|"]
    for c, n in per_class.most_common():
        lines.append(f"| `{c}` | `{n}` |")
    lines += ["", "Source: OpenStreetMap contributors, ODbL. Attribution and "
              "share-alike apply to anything derived from this set.", ""]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"\nkept {len(kept)} negatives -> {out_tsv}", flush=True)
    for c, n in per_class.most_common():
        print(f"   {c}: {n}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
