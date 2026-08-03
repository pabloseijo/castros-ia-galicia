#!/usr/bin/env python3
"""Does multitemporal Sentinel-2 separate castros from mámoas?

The project has never used optical multispectral data. Berganzo-Besga and
Orengo (2021) detected ~10k tumuli in NW Iberia partly with multitemporal
Sentinel-2, and the mechanism is worth stating plainly: satellites do not
see underground. What they see are crop and soil marks — vegetation over a
buried wall runs short of water and senesces early, vegetation over a
filled ditch stays green longer. The signal is indirect and appears only
under the right moisture and phenology, which is exactly why *many dates*
matter more than *many bands*.

That is also why hyperspectral is the wrong instrument here: PRISMA and
EnMAP carry hundreds of bands at 30 m, where a 114 m castro is 3x3 pixels.
Sentinel-2 gives 10 m and a revisit every 5 days, which is the trade that
suits this problem.

Measures per-site NDVI statistics across many dates and reports whether
they separate the classes, using the same sigma metric as the relief work.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import urllib.parse
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LABELS = PROJECT_ROOT / "data/osm-strong-labels-v1/osm_strong_labels.tsv"
DEFAULT_OUT_DIR = PROJECT_ROOT / "data/sentinel2-test-v1"
DEFAULT_REPORT = PROJECT_ROOT / "reports/sentinel2_separation_v1.md"

STAC = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
SAS = "https://planetarycomputer.microsoft.com/api/sas/v1/token/sentinel-2-l2a"


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


def http_json(url: str, payload: dict | None = None, timeout: int = 60):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"User-Agent": "castros-ia-galicia/1.0"}
    if data:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


_token_cache: dict[str, object] = {}


def sas_token() -> str:
    """SAS tokens expire hourly; refresh a few minutes before they do."""
    import time as _time

    if _token_cache.get("expires_at", 0) < _time.time() + 300:
        data = http_json(SAS)
        _token_cache["t"] = data.get("token", "")
        _token_cache["expires_at"] = _time.time() + 3300
    return str(_token_cache.get("t", ""))


def search_scenes(lon: float, lat: float, start: str, end: str, cloud: int, limit: int) -> list[dict]:
    body = {
        "collections": ["sentinel-2-l2a"],
        "intersects": {"type": "Point", "coordinates": [lon, lat]},
        "datetime": f"{start}/{end}",
        "query": {"eo:cloud_cover": {"lt": cloud}},
        "limit": limit,
    }
    try:
        return http_json(STAC, body).get("features", [])
    except Exception:
        return []


def read_window(href: str, lon: float, lat: float, half_m: float):
    """Read a small window around a point from a COG, without full download."""
    import numpy as np
    import rasterio
    from rasterio.warp import transform as warp_transform
    from rasterio.windows import from_bounds

    url = f"{href}?{sas_token()}"
    with rasterio.open(url) as src:
        xs, ys = warp_transform("EPSG:4326", src.crs, [lon], [lat])
        x, y = xs[0], ys[0]
        window = from_bounds(x - half_m, y - half_m, x + half_m, y + half_m, src.transform)
        arr = src.read(1, window=window).astype("float32")
    return arr if arr.size else None


def site_ndvi_series(site: dict, args: argparse.Namespace) -> dict | None:
    """NDVI stats for one site across available dates."""
    import numpy as np

    lon, lat = float(site["centroid_lon"]), float(site["centroid_lat"])
    scenes = search_scenes(lon, lat, args.start, args.end, args.max_cloud, args.max_scenes)
    if not scenes:
        return None

    values: list[float] = []
    contrasts: list[float] = []
    spectra: list[list[float]] = []
    for scene in scenes[: args.max_scenes]:
        assets = scene.get("assets", {})
        if "B04" not in assets or "B08" not in assets:
            continue
        if args.all_bands:
            # The hyperspectral question is about composition, not shape.
            # Twelve bands at 10-20 m is the best spectral sampling available
            # without credentials, and finer than EnMAP's 30 m.
            bands = ["B02", "B03", "B04", "B05", "B06", "B07", "B08", "B8A", "B11", "B12"]
            vector = []
            for band in bands:
                if band not in assets:
                    vector = []
                    break
                arr = read_window(assets[band]["href"], lon, lat, args.half_m)
                if arr is None or arr.size < 4:
                    vector = []
                    break
                finite = arr[np.isfinite(arr)]
                vector.append(float(np.median(finite)) if finite.size else float("nan"))
            if vector and all(v == v for v in vector):
                spectra.append(vector)
        try:
            red = read_window(assets["B04"]["href"], lon, lat, args.half_m)
            nir = read_window(assets["B08"]["href"], lon, lat, args.half_m)
            if red is None or nir is None or red.shape != nir.shape or red.size < 9:
                continue
            denom = nir + red
            ndvi = np.where(denom > 0, (nir - red) / np.where(denom == 0, 1, denom), np.nan)
            finite = ndvi[np.isfinite(ndvi)]
            if finite.size < 9:
                continue
            values.append(float(np.median(finite)))
            # Core versus surround: a crop mark shows as the middle differing.
            h, w = ndvi.shape
            ch, cw = h // 3, w // 3
            core = ndvi[ch:2 * ch, cw:2 * cw]
            core = core[np.isfinite(core)]
            if core.size >= 4:
                contrasts.append(float(np.median(core) - np.median(finite)))
        except Exception:
            continue

    if len(values) < args.min_dates:
        return None
    spectral_extra = {}
    if spectra:
        arr = np.array(spectra, dtype="float64")
        mean_spec = np.nanmean(arr, axis=0)
        total = float(np.nansum(mean_spec)) or 1.0
        shape = mean_spec / total
        spectral_extra = {
            "spec_brightness": float(np.nanmean(mean_spec)),
            "spec_shape_std": float(np.nanstd(shape)),
            "spec_swir_vis_ratio": float((mean_spec[8] + mean_spec[9]) / (mean_spec[0] + mean_spec[2] + 1e-6)),
            "spec_rededge_slope": float(mean_spec[5] - mean_spec[3]),
            "spec_dates": float(len(spectra)),
        }
    return {
        **spectral_extra,
        "osm_id": site["osm_id"],
        "site_class": site["site_class"],
        "name": site["name"][:60],
        "dates_used": len(values),
        "ndvi_median": statistics.median(values),
        "ndvi_std_over_time": statistics.pstdev(values) if len(values) > 1 else 0.0,
        "ndvi_min": min(values),
        "ndvi_max": max(values),
        "ndvi_range": max(values) - min(values),
        "core_contrast_median": statistics.median(contrasts) if contrasts else 0.0,
        "core_contrast_abs_max": max((abs(c) for c in contrasts), default=0.0),
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
    parser.add_argument("--per-class", type=int, default=40)
    parser.add_argument("--half-m", type=float, default=120.0)
    parser.add_argument("--start", default="2022-01-01")
    parser.add_argument("--end", default="2025-12-31")
    parser.add_argument("--max-cloud", type=int, default=25)
    parser.add_argument("--max-scenes", type=int, default=14)
    parser.add_argument("--min-dates", type=int, default=4)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--all-bands", action="store_true",
                        help="Read 10 bands to test spectral composition, not just NDVI.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    for attr in ("labels", "out_dir", "report"):
        value = getattr(args, attr)
        setattr(args, attr, value if value.is_absolute() else PROJECT_ROOT / value)

    rows = read_tsv(args.labels)
    castros = [r for r in rows if r["site_class"] == "castro"][: args.per_class]
    mounds = [r for r in rows if r["site_class"] == "mound"][: args.per_class]
    sites = castros + mounds
    print(f"sitios: {len(castros)} castros, {len(mounds)} mamoas", flush=True)

    results: list[dict] = []
    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(site_ndvi_series, s, args): s for s in sites}
        for future in as_completed(futures):
            done += 1
            try:
                record = future.result()
            except Exception:
                record = None
            if record:
                results.append(record)
            if done % 10 == 0:
                print(f"  {done}/{len(sites)} con serie: {len(results)}", flush=True)

    fields = [
        "spec_brightness", "spec_shape_std", "spec_swir_vis_ratio",
        "spec_rededge_slope", "spec_dates",
        "osm_id", "site_class", "name", "dates_used", "ndvi_median",
        "ndvi_std_over_time", "ndvi_min", "ndvi_max", "ndvi_range",
        "core_contrast_median", "core_contrast_abs_max",
    ]
    write_tsv(args.out_dir / "sentinel2_ndvi_features.tsv", results, fields)

    c = [r for r in results if r["site_class"] == "castro"]
    m = [r for r in results if r["site_class"] == "mound"]
    metrics = [
        "ndvi_median", "ndvi_std_over_time", "ndvi_range",
        "core_contrast_median", "core_contrast_abs_max",
    ]
    if args.all_bands and results and "spec_brightness" in results[0]:
        metrics += ["spec_brightness", "spec_shape_std", "spec_swir_vis_ratio", "spec_rededge_slope"]

    lines = [
        "# Multitemporal Sentinel-2: does it separate castros from mámoas?",
        "",
        f"Sites with usable series: `{len(c)}` castros, `{len(m)}` mámoas "
        f"(from `{len(sites)}` attempted).",
        f"Window: `{args.start}` to `{args.end}`, cloud `< {args.max_cloud}%`, "
        f"up to `{args.max_scenes}` dates per site, `10 m` bands B04/B08.",
        "",
        "## What this measures",
        "",
        "Satellites do not see underground. They see crop and soil marks: plants",
        "over a buried wall run short of water and senesce early, plants over a",
        "filled ditch stay green longer. The mark only appears under the right",
        "moisture and phenology, so the informative variable is **time**, not band",
        "count. This is why Sentinel-2 at `10 m` beats hyperspectral at `30 m`",
        "for features of this size.",
        "",
        "## Separation (sigmas, higher is better)",
        "",
        "| feature | separation |",
        "|---|---:|",
    ]
    best = 0.0
    for metric in metrics:
        value = separation([r[metric] for r in c], [r[metric] for r in m])
        if value == value:
            best = max(best, value)
        lines.append(f"| `{metric}` | `{value:.2f}` |")

    lines += [
        "",
        "## Reference points from the same project",
        "",
        "| source | best separation |",
        "|---|---:|",
        "| OSM polygon radius (geometry) | `1.38` |",
        "| MDT5 relief descriptors | `1.15` |",
        "| LiDAR 1 m relief descriptors | `0.90` |",
        f"| **Sentinel-2 multitemporal NDVI** | **`{best:.2f}`** |",
        "",
        "## Verdict",
        "",
    ]
    if best >= 1.15:
        lines.append(
            "- **Adds real signal.** Sentinel-2 matches or beats the relief "
            "descriptors and is worth folding into the feature set."
        )
    elif best >= 0.7:
        lines.append(
            "- **Adds some signal, weaker than relief.** Only worth including if "
            "it is complementary rather than redundant — check correlation with "
            "the relief features before adding it."
        )
    else:
        lines.append(
            "- **Does not separate these classes.** Optical vegetation response "
            "is not the discriminator here, and the project should not claim it is."
        )
    lines += [
        "",
        "- Caveat: at `10 m`, a `20 m` mámoa is about `2x2` pixels. Weak separation",
        "  may reflect that mámoas are simply too small for this sensor, not that",
        "  crop marks are uninformative in general.",
        "",
    ]
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"\ncastros={len(c)} mounds={len(m)} best_separation={best:.2f}")
    print(f"report={args.report}")


if __name__ == "__main__":
    main()
