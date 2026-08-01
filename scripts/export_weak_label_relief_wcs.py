#!/usr/bin/env python3
"""Export WCS MDT/relief DEM chips for weak-label rows.

This downloads small MDT5 GeoTIFF crops from the public Spanish WCS service.
The GeoTIFFs are stored under data/external and ignored by Git; only manifests
and reports are versioned.
"""

from __future__ import annotations

import argparse
import csv
import time
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = PROJECT_ROOT / "data/weak-label-splits-v1/weak_label_chip_export_holdouts.tsv"
DEFAULT_OUT_MANIFEST = PROJECT_ROOT / "data/weak-label-relief-v1/weak_label_relief_wcs_holdouts.tsv"
DEFAULT_REPORT = PROJECT_ROOT / "reports/weak_label_relief_wcs_holdouts.md"

GENERATED_AT = "2026-08-01T00:00:00Z"
USER_AGENT = "Mozilla/5.0 castros-ia-galicia/1.0 weak-label-relief-wcs"
DEFAULT_WCS_BASE = "https://servicios.idee.es/wcs-inspire/mdt"
DEFAULT_COVERAGE_ID = "Elevacion25830_5"
DEFAULT_TARGET_CRS = "EPSG:25830"

FIELDS = [
    "export_id",
    "tile_id",
    "sample_id",
    "bank_id",
    "label_class",
    "label_role",
    "final_split",
    "country",
    "name",
    "longitude",
    "latitude",
    "bbox_epsg4326",
    "bbox_epsg25830",
    "tile_side_m",
    "coverage_id",
    "wcs_base",
    "target_dem_path",
    "status",
    "dem_status",
    "actual_width_px",
    "actual_height_px",
    "resolution_x_m",
    "resolution_y_m",
    "crs",
    "finite_fraction",
    "dem_min_m",
    "dem_max_m",
    "bytes",
    "attempts",
    "error",
    "wcs_url",
    "generated_at",
]


def require_runtime() -> None:
    missing = []
    for module in ("pyproj", "rasterio", "numpy"):
        try:
            __import__(module)
        except Exception:
            missing.append(module)
    if missing:
        raise SystemExit(f"Missing Python modules: {', '.join(missing)}")


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, dialect="excel-tab"))


def write_tsv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=fieldnames,
            dialect="excel-tab",
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def rel_to_project(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def csv_set(value: str) -> set[str]:
    return {item.strip() for item in value.split(",") if item.strip()}


def parse_bbox(raw_value: str) -> tuple[float, float, float, float]:
    values = [float(value) for value in raw_value.split(",")]
    if len(values) != 4:
        raise ValueError(f"invalid bbox: {raw_value}")
    return values[0], values[1], values[2], values[3]


def transform_bbox_4326_to_25830(raw_bbox: str) -> tuple[float, float, float, float]:
    from pyproj import Transformer

    min_lon, min_lat, max_lon, max_lat = parse_bbox(raw_bbox)
    transformer = Transformer.from_crs("EPSG:4326", DEFAULT_TARGET_CRS, always_xy=True)
    xs = []
    ys = []
    for lon in (min_lon, max_lon):
        for lat in (min_lat, max_lat):
            x, y = transformer.transform(lon, lat)
            xs.append(x)
            ys.append(y)
    return min(xs), min(ys), max(xs), max(ys)


def target_dem_path(row: dict[str, str]) -> Path:
    label = "positive" if row.get("label_class") == "1" else "negative"
    png_stem = Path(row.get("target_png_path", f"{row['tile_id']}-{row['bank_id']}")).stem
    rel = Path("data/external/weak-label-relief-v1") / row.get("final_split", "unknown") / label / f"{png_stem}-mdt5.tif"
    return PROJECT_ROOT / rel


def build_wcs_url(base_url: str, coverage_id: str, bbox_25830: tuple[float, float, float, float]) -> str:
    minx, miny, maxx, maxy = bbox_25830
    params = [
        ("SERVICE", "WCS"),
        ("VERSION", "2.0.1"),
        ("REQUEST", "GetCoverage"),
        ("COVERAGEID", coverage_id),
        ("FORMAT", "image/tiff"),
        ("SUBSET", f"x({minx:.2f},{maxx:.2f})"),
        ("SUBSET", f"y({miny:.2f},{maxy:.2f})"),
    ]
    return f"{base_url}?{urlencode(params)}"


def dem_diagnostics(path: Path) -> dict[str, str]:
    if not path.exists():
        return {
            "dem_status": "missing",
            "actual_width_px": "",
            "actual_height_px": "",
            "resolution_x_m": "",
            "resolution_y_m": "",
            "crs": "",
            "finite_fraction": "0.000000",
            "dem_min_m": "",
            "dem_max_m": "",
            "bytes": "0",
            "error": "file does not exist",
        }
    try:
        import numpy as np
        import rasterio

        with rasterio.open(path) as src:
            array = src.read(1).astype("float32")
            if src.nodata is not None:
                array[array == src.nodata] = np.nan
            finite = np.isfinite(array)
            finite_count = int(finite.sum())
            dem_status = "valid" if finite_count > 0 and src.width > 0 and src.height > 0 else "invalid"
            return {
                "dem_status": dem_status,
                "actual_width_px": str(src.width),
                "actual_height_px": str(src.height),
                "resolution_x_m": f"{abs(float(src.res[0])):.3f}",
                "resolution_y_m": f"{abs(float(src.res[1])):.3f}",
                "crs": str(src.crs),
                "finite_fraction": f"{(finite_count / array.size) if array.size else 0.0:.6f}",
                "dem_min_m": f"{float(np.nanmin(array)):.3f}" if finite_count else "",
                "dem_max_m": f"{float(np.nanmax(array)):.3f}" if finite_count else "",
                "bytes": str(path.stat().st_size),
                "error": "" if dem_status == "valid" else "no finite DEM pixels",
            }
    except Exception as exc:
        return {
            "dem_status": "invalid",
            "actual_width_px": "",
            "actual_height_px": "",
            "resolution_x_m": "",
            "resolution_y_m": "",
            "crs": "",
            "finite_fraction": "0.000000",
            "dem_min_m": "",
            "dem_max_m": "",
            "bytes": str(path.stat().st_size if path.exists() else 0),
            "error": str(exc),
        }


def fetch_tiff(url: str, path: Path, *, force: bool, timeout: float) -> tuple[str, dict[str, str], int]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        diagnostics = dem_diagnostics(path)
        if diagnostics["dem_status"] == "valid":
            return "exists", diagnostics, 0

    last_error = ""
    for attempt in range(1, 4):
        try:
            request = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(request, timeout=timeout) as response:
                payload = response.read()
                content_type = response.headers.get("content-type", "")
                if response.status == 200 and (payload.startswith(b"II") or payload.startswith(b"MM")):
                    tmp_path = path.with_suffix(path.suffix + ".tmp")
                    tmp_path.write_bytes(payload)
                    tmp_path.replace(path)
                    diagnostics = dem_diagnostics(path)
                    if diagnostics["dem_status"] == "valid":
                        return "downloaded", diagnostics, attempt
                    return "failed", diagnostics, attempt
                last_error = f"unexpected WCS response status={response.status} content_type={content_type}"
        except Exception as exc:
            last_error = str(exc)
        if attempt < 3:
            time.sleep(0.75 * attempt)

    diagnostics = dem_diagnostics(path)
    diagnostics["error"] = last_error or diagnostics.get("error", "unknown fetch failure")
    return "failed", diagnostics, 3


def select_rows(rows: list[dict[str, str]], args: argparse.Namespace) -> list[dict[str, str]]:
    splits = csv_set(args.splits)
    selected = [row for row in rows if not splits or row.get("final_split") in splits]
    if args.limit:
        selected = selected[: args.limit]
    return selected


def export_row(
    index: int,
    row: dict[str, str],
    *,
    args: argparse.Namespace,
    semaphore: threading.Semaphore,
) -> dict[str, str]:
    result = {field: "" for field in FIELDS}
    result.update(
        {
            "export_id": f"weak-relief-wcs-v1-{index:05d}",
            "tile_id": row.get("tile_id", ""),
            "sample_id": row.get("sample_id", ""),
            "bank_id": row.get("bank_id", ""),
            "label_class": row.get("label_class", ""),
            "label_role": row.get("label_role", ""),
            "final_split": row.get("final_split", ""),
            "country": row.get("country", ""),
            "name": row.get("name", ""),
            "longitude": row.get("longitude", ""),
            "latitude": row.get("latitude", ""),
            "bbox_epsg4326": row.get("bbox_epsg4326", ""),
            "tile_side_m": row.get("tile_side_m", ""),
            "coverage_id": args.coverage_id,
            "wcs_base": args.wcs_base,
            "generated_at": GENERATED_AT,
        }
    )
    out_path = target_dem_path(row)
    result["target_dem_path"] = rel_to_project(out_path)

    if row.get("country") != "ES":
        result.update({"status": "skipped", "dem_status": "unsupported_country", "error": "WCS MDT target currently supports Spain/EPSG:25830 only"})
        return result
    try:
        bbox_25830 = transform_bbox_4326_to_25830(row["bbox_epsg4326"])
        result["bbox_epsg25830"] = ",".join(f"{value:.2f}" for value in bbox_25830)
        url = build_wcs_url(args.wcs_base, args.coverage_id, bbox_25830)
        result["wcs_url"] = url
        with semaphore:
            status, diagnostics, attempts = fetch_tiff(url, out_path, force=args.force, timeout=args.timeout)
        result.update(
            {
                "status": status,
                "dem_status": diagnostics["dem_status"],
                "actual_width_px": diagnostics["actual_width_px"],
                "actual_height_px": diagnostics["actual_height_px"],
                "resolution_x_m": diagnostics["resolution_x_m"],
                "resolution_y_m": diagnostics["resolution_y_m"],
                "crs": diagnostics["crs"],
                "finite_fraction": diagnostics["finite_fraction"],
                "dem_min_m": diagnostics["dem_min_m"],
                "dem_max_m": diagnostics["dem_max_m"],
                "bytes": diagnostics["bytes"],
                "attempts": str(attempts),
                "error": diagnostics["error"],
            }
        )
    except Exception as exc:
        result.update({"status": "failed", "dem_status": "invalid", "error": str(exc)})
    return result


def export_rows(rows: list[dict[str, str]], args: argparse.Namespace) -> list[dict[str, str]]:
    semaphore = threading.Semaphore(args.wcs_parallel)
    out: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(export_row, index, row, args=args, semaphore=semaphore): index
            for index, row in enumerate(rows, start=1)
        }
        for future in as_completed(futures):
            out.append(future.result())
    return sorted(out, key=lambda row: row["export_id"])


def write_report(path: Path, source_manifest: Path, rows: list[dict[str, str]], args: argparse.Namespace) -> None:
    status_counts = Counter(row["status"] for row in rows)
    dem_counts = Counter(row["dem_status"] for row in rows)
    split_counts = Counter((row["final_split"], row["label_role"]) for row in rows)
    total_bytes = sum(int(row.get("bytes") or 0) for row in rows)
    failures = [row for row in rows if row["status"] == "failed" or row["dem_status"] == "invalid"]
    lines = [
        "# Weak-label relief WCS export",
        "",
        f"Generated: {GENERATED_AT}",
        "",
        "## Scope",
        "",
        f"- Source manifest: `{rel_to_project(source_manifest)}`",
        f"- Rows selected: {len(rows)}",
        f"- Coverage: `{args.coverage_id}`",
        f"- WCS base: `{args.wcs_base}`",
        f"- Splits filter: `{args.splits or 'all'}`",
        "",
        "## Files",
        "",
        f"- Export manifest: `{rel_to_project(args.out_manifest)}`",
        "- DEM chips: `data/external/weak-label-relief-v1/` (ignored by Git)",
        "",
        "## Download Status",
        "",
    ]
    for status, count in sorted(status_counts.items()):
        lines.append(f"- {status}: {count}")
    lines.extend(["", "## DEM Status", ""])
    for status, count in sorted(dem_counts.items()):
        lines.append(f"- {status}: {count}")
    lines.extend(["", "## By Split And Role", ""])
    for (split, role), count in sorted(split_counts.items()):
        lines.append(f"- {split}/{role}: {count}")
    lines.extend(["", "## Size", "", f"- Total local DEM bytes represented by this manifest: {total_bytes}", "", "## Failures", ""])
    if failures:
        for row in failures[:20]:
            lines.append(f"- {row['tile_id']} `{row['name']}`: {row['error']}")
        if len(failures) > 20:
            lines.append(f"- ... {len(failures) - 20} more failures not shown.")
    else:
        lines.append("- None.")
    lines.extend(["", "## Next Step", "", "Run the relief baseline over this manifest and compare it with the RGB ranking, especially the O Val failure on `Castro de Pena Lopesa`."])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--out-manifest", type=Path, default=DEFAULT_OUT_MANIFEST)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--splits", default="", help="Comma-separated final_split values.")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--wcs-parallel", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--wcs-base", default=DEFAULT_WCS_BASE)
    parser.add_argument("--coverage-id", default=DEFAULT_COVERAGE_ID)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> None:
    require_runtime()
    args = parse_args()
    source_manifest = args.input if args.input.is_absolute() else PROJECT_ROOT / args.input
    args.out_manifest = args.out_manifest if args.out_manifest.is_absolute() else PROJECT_ROOT / args.out_manifest
    args.report = args.report if args.report.is_absolute() else PROJECT_ROOT / args.report
    rows = select_rows(read_tsv(source_manifest), args)
    exported = export_rows(rows, args)
    write_tsv(args.out_manifest, exported, FIELDS)
    write_report(args.report, source_manifest, exported, args)
    print(f"selected_rows={len(rows)}")
    print(f"status_counts={dict(sorted(Counter(row['status'] for row in exported).items()))}")
    print(f"dem_status_counts={dict(sorted(Counter(row['dem_status'] for row in exported).items()))}")
    print(f"wrote={rel_to_project(args.out_manifest)}")
    print(f"report={rel_to_project(args.report)}")


if __name__ == "__main__":
    main()
