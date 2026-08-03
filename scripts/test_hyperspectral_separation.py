#!/usr/bin/env python3
"""Does hyperspectral imagery separate castros from mámoas? Small controlled test.

The earlier dismissal of hyperspectral rested on spatial resolution: 30 m
cannot resolve a 20 m mound. That argument is sound about *shape* and wrong
about *composition*. A buried stone rampart may alter the spectral signature
of the surface — soil mineralogy, moisture, vegetation stress — without the
structure ever being resolved geometrically. Those are different questions
and only one of them was answered.

So this tests it rather than assuming. EnMAP L2A (224 bands, 30 m) over
Galicia has 145 scenes, 93 under 20% cloud, across 26 dates. Enough for a
controlled comparison on the same sites used everywhere else in the project.

Requires DLR EOC credentials (free registration). Set in the environment:

    ENMAP_USER, ENMAP_PASS

Reports separation in the same sigma units as the relief, LiDAR and
Sentinel-2 experiments, so the answer is directly comparable.
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import os
import statistics
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LABELS = PROJECT_ROOT / "data/osm-strong-labels-v1/osm_strong_labels.tsv"
DEFAULT_OUT_DIR = PROJECT_ROOT / "data/hyperspectral-test-v1"
DEFAULT_REPORT = PROJECT_ROOT / "reports/hyperspectral_separation_v1.md"

STAC_ENMAP = "https://geoservice.dlr.de/eoc/ogc/stac/v1/collections/ENMAP_HSI_L2A/items"


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, dialect="excel-tab"))


def write_tsv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=fields, dialect="excel-tab", extrasaction="ignore", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def credentials() -> tuple[str, str] | None:
    user = os.environ.get("ENMAP_USER", "").strip()
    password = os.environ.get("ENMAP_PASS", "").strip()
    return (user, password) if user and password else None


def configure_gdal_auth(creds: tuple[str, str]) -> None:
    """GDAL follows the DLR SSO redirect if given basic auth."""
    token = base64.b64encode(f"{creds[0]}:{creds[1]}".encode()).decode()
    os.environ["GDAL_HTTP_HEADERS"] = f"Authorization: Basic {token}"
    os.environ["GDAL_HTTP_UNSAFESSL"] = "YES"
    os.environ["CPL_VSIL_CURL_USE_HEAD"] = "NO"
    os.environ["GDAL_DISABLE_READDIR_ON_OPEN"] = "EMPTY_DIR"


def search_scenes(bbox: str, limit: int, max_cloud: float) -> list[dict]:
    url = f"{STAC_ENMAP}?{urllib.parse.urlencode({'bbox': bbox, 'limit': limit})}"
    request = urllib.request.Request(url, headers={"User-Agent": "castros-ia-galicia/1.0"})
    with urllib.request.urlopen(request, timeout=90) as response:
        features = json.loads(response.read()).get("features", [])
    out = []
    for feature in features:
        try:
            cloud = float(feature["properties"].get("eo:cloud_cover", 100))
        except (TypeError, ValueError):
            cloud = 100.0
        if cloud <= max_cloud:
            out.append(feature)
    out.sort(key=lambda f: float(f["properties"].get("eo:cloud_cover", 100)))
    return out


def scene_bounds(feature: dict) -> tuple[float, float, float, float] | None:
    bbox = feature.get("bbox")
    if bbox and len(bbox) >= 4:
        return bbox[0], bbox[1], bbox[2], bbox[3]
    return None


def covers(feature: dict, lon: float, lat: float) -> bool:
    bounds = scene_bounds(feature)
    if not bounds:
        return False
    return bounds[0] <= lon <= bounds[2] and bounds[1] <= lat <= bounds[3]


def spectral_window(href: str, lon: float, lat: float, half_m: float):
    """Read all bands in a small window around the point."""
    import numpy as np
    import rasterio
    from rasterio.warp import transform as warp_transform
    from rasterio.windows import from_bounds

    with rasterio.open(f"/vsicurl/{href}") as src:
        xs, ys = warp_transform("EPSG:4326", src.crs, [lon], [lat])
        window = from_bounds(
            xs[0] - half_m, ys[0] - half_m, xs[0] + half_m, ys[0] + half_m, src.transform
        )
        data = src.read(window=window).astype("float32")
    if data.size == 0:
        return None
    data[data <= 0] = np.nan
    return data


def site_spectral_features(site: dict, scenes: list[dict], args) -> dict | None:
    import numpy as np

    lon, lat = float(site["centroid_lon"]), float(site["centroid_lat"])
    usable = [s for s in scenes if covers(s, lon, lat)][: args.max_scenes]
    if not usable:
        return None

    per_scene = []
    for scene in usable:
        assets = scene.get("assets", {})
        href = (assets.get("image") or assets.get("vnir") or {}).get("href")
        if not href:
            continue
        try:
            cube = spectral_window(href, lon, lat, args.half_m)
            if cube is None or cube.shape[0] < 10:
                continue
            bands, h, w = cube.shape
            flat = cube.reshape(bands, -1)
            mean_spectrum = np.nanmean(flat, axis=1)
            if not np.isfinite(mean_spectrum).any():
                continue
            # Spectral shape descriptors that do not need band calibration.
            finite = mean_spectrum[np.isfinite(mean_spectrum)]
            brightness = float(np.nanmean(finite))
            variability = float(np.nanstd(finite) / (brightness + 1e-6))
            # Within-window spectral heterogeneity: a site with mixed
            # surfaces (rampart, ditch, interior) should look less uniform.
            per_pixel = np.nanmean(flat, axis=0)
            heterogeneity = float(np.nanstd(per_pixel) / (np.nanmean(per_pixel) + 1e-6))
            per_scene.append((brightness, variability, heterogeneity))
        except Exception:
            continue

    if not per_scene:
        return None
    brightness = [p[0] for p in per_scene]
    variability = [p[1] for p in per_scene]
    heterogeneity = [p[2] for p in per_scene]
    return {
        "osm_id": site["osm_id"],
        "site_class": site["site_class"],
        "name": site["name"][:60],
        "scenes_used": len(per_scene),
        "brightness_median": statistics.median(brightness),
        "spectral_variability": statistics.median(variability),
        "spatial_heterogeneity": statistics.median(heterogeneity),
    }


def separation(a: list[float], b: list[float]) -> float:
    if len(a) < 2 or len(b) < 2:
        return float("nan")
    pooled = statistics.pstdev(a + b)
    return abs(statistics.median(a) - statistics.median(b)) / pooled if pooled > 1e-9 else 0.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--bbox", default="-9.4,41.8,-6.7,43.9")
    parser.add_argument("--per-class", type=int, default=30)
    parser.add_argument("--half-m", type=float, default=150.0)
    parser.add_argument("--max-cloud", type=float, default=20.0)
    parser.add_argument("--max-scenes", type=int, default=3)
    parser.add_argument("--scene-limit", type=int, default=200)
    parser.add_argument("--workers", type=int, default=3)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    for attr in ("labels", "out_dir", "report"):
        value = getattr(args, attr)
        setattr(args, attr, value if value.is_absolute() else PROJECT_ROOT / value)

    creds = credentials()
    if not creds:
        raise SystemExit(
            "Faltan credenciales EnMAP.\n"
            "  1. Registro gratuito en https://sso.eoc.dlr.de (DLR EOC)\n"
            "  2. export ENMAP_USER=... ENMAP_PASS=...\n"
            "Los datos existen: 145 escenas sobre Galicia, 93 con nubes <20%, 26 fechas."
        )
    configure_gdal_auth(creds)

    print(f"buscando escenas EnMAP en {args.bbox} ...", flush=True)
    scenes = search_scenes(args.bbox, args.scene_limit, args.max_cloud)
    print(f"escenas con nubes <= {args.max_cloud}%: {len(scenes)}", flush=True)
    if not scenes:
        raise SystemExit("sin escenas utilizables")

    rows = read_tsv(args.labels)
    castros = [r for r in rows if r["site_class"] == "castro"][: args.per_class]
    mounds = [r for r in rows if r["site_class"] == "mound"][: args.per_class]
    sites = castros + mounds
    print(f"sitios: {len(castros)} castros, {len(mounds)} mamoas", flush=True)

    results: list[dict] = []
    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(site_spectral_features, s, scenes, args) for s in sites]
        for future in as_completed(futures):
            done += 1
            try:
                record = future.result()
            except Exception:
                record = None
            if record:
                results.append(record)
            if done % 10 == 0:
                print(f"  {done}/{len(sites)} con espectro: {len(results)}", flush=True)

    fields = [
        "osm_id", "site_class", "name", "scenes_used",
        "brightness_median", "spectral_variability", "spatial_heterogeneity",
    ]
    write_tsv(args.out_dir / "hyperspectral_features.tsv", results, fields)

    c = [r for r in results if r["site_class"] == "castro"]
    m = [r for r in results if r["site_class"] == "mound"]
    metrics = ["brightness_median", "spectral_variability", "spatial_heterogeneity"]
    best = 0.0
    table = []
    for metric in metrics:
        value = separation([r[metric] for r in c], [r[metric] for r in m])
        if value == value:
            best = max(best, value)
        table.append((metric, value))

    lines = [
        "# Hyperspectral (EnMAP) separation test",
        "",
        f"Sites with usable spectra: `{len(c)}` castros, `{len(m)}` mámoas.",
        f"EnMAP L2A, `224` bands, `30 m`, cloud `<= {args.max_cloud}%`.",
        "",
        "## Why this was worth testing despite 30 m",
        "",
        "The earlier objection was about spatial resolution, and it holds for",
        "*shape*: a `20 m` mound is sub-pixel at `30 m`. But hyperspectral is not",
        "a shape instrument, it is a composition one. Buried stone can alter soil",
        "mineralogy, moisture retention and vegetation stress at the surface,",
        "which is a spectral question, not a geometric one. Those are separable",
        "claims and only the geometric one had been answered.",
        "",
        "## Separation (sigmas)",
        "",
        "| feature | separation |",
        "|---|---:|",
    ]
    for metric, value in table:
        lines.append(f"| `{metric}` | `{value:.2f}` |")

    lines += [
        "",
        "## Against everything else measured on these classes",
        "",
        "| source | best separation |",
        "|---|---:|",
        "| OSM polygon radius (geometry) | `1.38` |",
        "| Sentinel-2 multitemporal NDVI | `1.24` |",
        "| MDT5 relief descriptors | `1.15` |",
        "| LiDAR 1 m relief descriptors | `0.90` |",
        f"| **EnMAP hyperspectral** | **`{best:.2f}`** |",
        "",
        "## Verdict",
        "",
    ]
    if best >= 1.24:
        lines.append("- **Best remote descriptor so far.** Hyperspectral earns a place in the feature set.")
    elif best >= 0.9:
        lines.append("- **Comparable to relief, below Sentinel-2.** Worth keeping only if complementary.")
    else:
        lines.append(
            "- **Does not separate these classes at 30 m.** The composition argument "
            "does not rescue hyperspectral here, and the project can stop treating "
            "it as an open question."
        )
    lines += [
        "",
        f"- Caveat: `30 m` means a `20 m` mámoa is sub-pixel and a `114 m` castro is",
        "  about `4x4` pixels. A negative result may reflect the mixed pixel, not the",
        "  absence of a spectral signature.",
        "",
    ]
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"\ncastros={len(c)} mounds={len(m)} best_separation={best:.2f}")
    print(f"report={args.report}")


if __name__ == "__main__":
    main()
