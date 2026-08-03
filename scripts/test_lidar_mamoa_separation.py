#!/usr/bin/env python3
"""Does 1 m LiDAR separate castros from mámoas where MDT5 cannot?

Four modelling routes have failed to move the dominant false positive
(mámoas hold 23-24 of the top 25). The measured cause is physical overlap
at 5 m: `best_ring_coverage` separates the classes by 1.5 sigma and
`dominant_scale_m` by none at all. The standing claim is that finer relief
would fix it — this tests that claim instead of assuming it.

Takes matched castros and mámoas from the Trasancos holdout, fetches the
CNIG PNOA LiDAR tiles covering them, builds 1 m DEMs, extracts the same
MSRM features, and reports separation at 1 m against separation at 5 m
on exactly the same sites.

If separation does not improve, LiDAR is not the answer either and the
project should stop citing it as the way out.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from query_viladonga_cnig_lidar import (  # noqa: E402
    build_rows as cnig_build_rows,
    utm29_to_lonlat,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MASTER = PROJECT_ROOT / "data/weak-label-splits-v1/weak_label_master.tsv"
DEFAULT_MSRM = PROJECT_ROOT / "data/weak-label-msrm-v1/weak_label_msrm_features_full.tsv"
DEFAULT_OUT_DIR = PROJECT_ROOT / "data/lidar-mamoa-test-v1"
DEFAULT_LAZ_DIR = PROJECT_ROOT / "data/external/lidar-mamoa-test-v1"
DEFAULT_REPORT = PROJECT_ROOT / "reports/lidar_mamoa_separation_v1.md"

COMPARE_FEATURES = [
    "best_ring_coverage",
    "msrm_core_delta",
    "msrm_abs_ratio",
    "best_ring_balance",
    "dominant_scale_ratio",
]


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, dialect="excel-tab"))


def write_tsv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=fields, dialect="excel-tab", extrasaction="ignore", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def lonlat_to_utm29(lon: float, lat: float) -> tuple[float, float]:
    from pyproj import Transformer

    transformer = Transformer.from_crs("EPSG:4326", "EPSG:25829", always_xy=True)
    return transformer.transform(lon, lat)


def separation_sigmas(a: list[float], b: list[float]) -> float:
    """Absolute median gap in units of the pooled spread."""
    if len(a) < 2 or len(b) < 2:
        return float("nan")
    pooled = statistics.pstdev(a + b)
    if pooled < 1e-9:
        return 0.0
    return abs(statistics.median(a) - statistics.median(b)) / pooled


def pick_sites(args: argparse.Namespace) -> list[dict[str, str]]:
    """Matched castros and mámoas from the holdout, closest together first."""
    master = {r["sample_id"]: r for r in read_tsv(args.master)}
    rows = [r for r in read_tsv(args.msrm) if r.get("status") == "ok"]
    hold = [r for r in rows if r.get("final_split") in {"test_trasancos", "test_o_val"}]

    castros, mamoas = [], []
    for row in hold:
        meta = master.get(row.get("sample_id", ""), {})
        try:
            lon, lat = float(meta["longitude"]), float(meta["latitude"])
        except (KeyError, ValueError):
            continue
        item = dict(row)
        item["longitude"], item["latitude"] = str(lon), str(lat)
        item["site_class"] = (
            "castro"
            if str(row.get("label_class", "")).strip() == "1"
            else ("mamoa" if "megalithic" in (row.get("negative_type") or "") else "other")
        )
        if item["site_class"] == "castro":
            castros.append(item)
        elif item["site_class"] == "mamoa":
            mamoas.append(item)

    castros = castros[: args.per_class]
    mamoas = mamoas[: args.per_class]
    return castros + mamoas


def tiles_for_sites(sites: list[dict[str, str]]) -> list[dict[str, str]]:
    """One CNIG query point per distinct 1 km tile covering the sites."""
    seen: dict[str, dict[str, str]] = {}
    for site in sites:
        x, y = lonlat_to_utm29(float(site["longitude"]), float(site["latitude"]))
        tile_x, tile_y = int(x // 1000), int(y // 1000)
        key = f"{tile_x}-{tile_y}"
        if key in seen:
            continue
        cx, cy = tile_x * 1000 + 500.0, tile_y * 1000 + 500.0
        lon, lat = utm29_to_lonlat(cx, cy)
        seen[key] = {
            "query_tile_lower_id": key,
            "query_x_utm29": f"{cx:.2f}",
            "query_y_utm29": f"{cy:.2f}",
            "query_lon_wgs84": f"{lon:.8f}",
            "query_lat_wgs84": f"{lat:.8f}",
        }
    return list(seen.values())


def build_dem_for_site(
    laz_paths: list[Path], lon: float, lat: float, half_m: float, resolution: float
):
    """1 m DEM crop centred on the site, from ground returns."""
    from build_viladonga_lidar_derivatives import build_dem_from_laz

    x, y = lonlat_to_utm29(lon, lat)
    bounds = (x - half_m, y - half_m, x + half_m, y + half_m)
    # Only hand over the tiles that actually overlap this site; reading all
    # 24 LAZ files per site would be minutes of wasted IO each time.
    relevant = [p for p in laz_paths if laz_overlaps(p, bounds)]
    if not relevant:
        raise RuntimeError("no LAZ tile covers this site")
    dem, _total, _used = build_dem_from_laz(relevant, bounds, resolution)
    return dem


_LAZ_BOUNDS: dict[str, tuple] = {}


def laz_overlaps(path: Path, bounds: tuple[float, float, float, float]) -> bool:
    """Cheap header-only bbox test, cached per file."""
    import laspy

    key = str(path)
    if key not in _LAZ_BOUNDS:
        with laspy.open(path) as reader:
            header = reader.header
            _LAZ_BOUNDS[key] = (
                float(header.mins[0]), float(header.mins[1]),
                float(header.maxs[0]), float(header.maxs[1]),
            )
    minx, miny, maxx, maxy = _LAZ_BOUNDS[key]
    return not (bounds[2] < minx or bounds[0] > maxx or bounds[3] < miny or bounds[1] > maxy)


def msrm_from_array(dem, resolution: float, scales_m: list[float], ring_radii_m: list[float]) -> dict:
    import numpy as np

    from evaluate_weak_label_msrm_features import (
        build_multiscale_relief,
        geometry_cache,
        mask_mean,
        ring_masks,
        ring_sector_metrics,
        safe_ratio,
    )

    finite = np.isfinite(dem)
    dem = dem.astype("float32", copy=True)
    if not finite.all():
        dem[~finite] = float(np.nanmean(dem)) if finite.any() else 0.0

    _layers, msrm = build_multiscale_relief(dem, resolution, scales_m)
    distance, sectors = geometry_cache(dem.shape)
    msrm_abs = np.abs(msrm)

    sweep = []
    for radius_m in ring_radii_m:
        core, annulus, context = ring_masks(distance, dem.shape, radius_m, resolution)
        if int(annulus.sum()) < 8 or int(context.sum()) < 8:
            continue
        coverage, balance = ring_sector_metrics(msrm_abs, annulus, context, sectors)
        sweep.append(
            {
                "coverage": coverage,
                "balance": balance,
                "ratio": safe_ratio(mask_mean(msrm_abs[annulus]), mask_mean(msrm_abs[context])),
            }
        )
    if not sweep:
        return {}
    best = max(sweep, key=lambda item: item["coverage"] * item["balance"])

    core, annulus, context = ring_masks(distance, dem.shape, 120.0, resolution)
    coverage, balance = ring_sector_metrics(msrm_abs, annulus, context, sectors)
    return {
        "best_ring_coverage": best["coverage"],
        "best_ring_balance": best["balance"],
        "msrm_abs_ratio": safe_ratio(mask_mean(msrm_abs[annulus]), mask_mean(msrm_abs[context])),
        "msrm_core_delta": mask_mean(msrm[core]) - mask_mean(msrm[context]),
        "dominant_scale_ratio": best["ratio"],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--master", type=Path, default=DEFAULT_MASTER)
    parser.add_argument("--msrm", type=Path, default=DEFAULT_MSRM)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--laz-dir", type=Path, default=DEFAULT_LAZ_DIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--per-class", type=int, default=20)
    parser.add_argument("--half-m", type=float, default=256.0)
    parser.add_argument("--resolution", type=float, default=1.0)
    parser.add_argument("--scales-m", default="4,8,15,30,60,120,240")
    parser.add_argument("--ring-radii-m", default="20,40,60,80,100,120,150,180,220")
    parser.add_argument("--stage", choices=["query", "extract", "all"], default="all")
    parser.add_argument("--max-tiles", type=int, default=60)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    for attr in ("master", "msrm", "out_dir", "laz_dir", "report"):
        value = getattr(args, attr)
        setattr(args, attr, value if value.is_absolute() else PROJECT_ROOT / value)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    args.laz_dir.mkdir(parents=True, exist_ok=True)

    sites = pick_sites(args)
    castros = [s for s in sites if s["site_class"] == "castro"]
    mamoas = [s for s in sites if s["site_class"] == "mamoa"]
    print(f"sites: {len(castros)} castros, {len(mamoas)} mamoas", flush=True)

    sites_path = args.out_dir / "test_sites.tsv"
    write_tsv(
        sites_path,
        sites,
        ["sample_id", "tile_id", "name", "site_class", "longitude", "latitude", "final_split"],
    )

    tiles = tiles_for_sites(sites)[: args.max_tiles]
    print(f"distinct 1 km LiDAR tiles needed: {len(tiles)}", flush=True)

    if args.stage in {"query", "all"}:
        rows = cnig_build_rows(["LIDA3"], tiles, args.laz_dir)
        write_tsv(
            args.out_dir / "cnig_lidar_tiles.tsv",
            rows,
            list(rows[0].keys()) if rows else ["series_code"],
        )
        downloaded = [r for r in rows if r.get("download_status") in {"downloaded", "cached"}]
        print(f"laz rows={len(rows)} downloaded={len(downloaded)}", flush=True)

    if args.stage in {"extract", "all"}:
        laz_paths = sorted(args.laz_dir.glob("*.laz"))
        print(f"laz files on disk: {len(laz_paths)}", flush=True)
        if not laz_paths:
            print("no LAZ available; stopping before extraction", flush=True)
            return

        scales = [float(v) for v in args.scales_m.split(",")]
        radii = [float(v) for v in args.ring_radii_m.split(",")]
        results: list[dict[str, str]] = []
        for site in sites:
            row = {
                "sample_id": site.get("sample_id", ""),
                "name": site.get("name", ""),
                "site_class": site["site_class"],
            }
            try:
                dem = build_dem_for_site(
                    laz_paths, float(site["longitude"]), float(site["latitude"]),
                    args.half_m, args.resolution,
                )
                feats = msrm_from_array(dem, args.resolution, scales, radii)
                if not feats:
                    row["status"] = "failed"
                    row["error"] = "no_valid_rings"
                else:
                    for key, value in feats.items():
                        row[f"lidar_{key}"] = f"{value:.8f}"
                    row["status"] = "ok"
            except Exception as exc:
                row["status"] = "failed"
                row["error"] = str(exc)[:180]
            results.append(row)
            print(f"  {row['status']:<7} {row['site_class']:<7} {row['name'][:44]}", flush=True)

        fields = ["sample_id", "name", "site_class"] + [
            f"lidar_{f}" for f in COMPARE_FEATURES
        ] + ["status", "error"]
        write_tsv(args.out_dir / "lidar_features.tsv", results, fields)

        # Compare 1 m LiDAR against the 5 m MDT on the very same sites.
        mdt = {r["sample_id"]: r for r in read_tsv(args.msrm) if r.get("status") == "ok"}
        lines = [
            "# Does 1 m LiDAR separate castros from mámoas?",
            "",
            f"Sites: `{len(castros)}` castros vs `{len(mamoas)}` mámoas from the Trasancos holdout.",
            f"LiDAR: CNIG PNOA 3rd coverage, {args.resolution:.0f} m grid from ground returns.",
            "",
            "Separation is the absolute gap between class medians, in pooled standard",
            "deviations. Higher is better; the same sites are measured both ways.",
            "",
            "| feature | MDT5 (5 m) | LiDAR (1 m) | change |",
            "|---|---:|---:|---:|",
        ]
        ok = [r for r in results if r["status"] == "ok"]
        improved = 0
        for feature in COMPARE_FEATURES:
            l_c = [float(r[f"lidar_{feature}"]) for r in ok if r["site_class"] == "castro" and r.get(f"lidar_{feature}")]
            l_m = [float(r[f"lidar_{feature}"]) for r in ok if r["site_class"] == "mamoa" and r.get(f"lidar_{feature}")]
            ids_c = {r["sample_id"] for r in ok if r["site_class"] == "castro"}
            ids_m = {r["sample_id"] for r in ok if r["site_class"] == "mamoa"}
            m_c = [float(mdt[i][feature]) for i in ids_c if i in mdt and mdt[i].get(feature)]
            m_m = [float(mdt[i][feature]) for i in ids_m if i in mdt and mdt[i].get(feature)]
            s_mdt, s_lidar = separation_sigmas(m_c, m_m), separation_sigmas(l_c, l_m)
            delta = s_lidar - s_mdt
            if delta > 0.1:
                improved += 1
            lines.append(
                f"| `{feature}` | `{s_mdt:.2f}` | `{s_lidar:.2f}` | `{delta:+.2f}` |"
            )

        lines += [
            "",
            "## Verdict",
            "",
        ]
        if improved >= 3:
            lines.append(
                f"- **LiDAR helps**: `{improved}` of `{len(COMPARE_FEATURES)}` features separate "
                "the classes better at 1 m. Finer relief is a real route out of the mámoa problem."
            )
        elif improved >= 1:
            lines.append(
                f"- **Mixed**: only `{improved}` of `{len(COMPARE_FEATURES)}` features improve. "
                "LiDAR is not a clean fix; the overlap is partly intrinsic."
            )
        else:
            lines.append(
                "- **LiDAR does not help on these features.** The claim that finer relief "
                "solves the mámoa confusion is not supported, and the project should stop "
                "citing it as the way out without further evidence."
            )
        lines += [
            "",
            f"- sites successfully processed: `{len(ok)}` of `{len(results)}`",
            "- Caveat: ground-return DEMs under dense canopy are themselves interpolated,",
            "  so 1 m nominal resolution is not 1 m of real information everywhere.",
            "",
        ]
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("\n".join(lines[-8:]))
        print(f"report={args.report}")


if __name__ == "__main__":
    main()
