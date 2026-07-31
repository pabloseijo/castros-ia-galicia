#!/usr/bin/env python3
"""Fetch a WCS MDT crop for the Viladonga pilot."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "configs/viladonga_pilot.json"
DEFAULT_OUT = PROJECT_ROOT / "data/viladonga-pilot/lidar/viladonga_mdt5_wcs.tif"
DEFAULT_REPORT = PROJECT_ROOT / "reports/viladonga_mdt_wcs.md"
DEFAULT_MANIFEST = PROJECT_ROOT / "data/viladonga-pilot/wcs_dem_manifest.tsv"
DEFAULT_WCS_BASE = "https://servicios.idee.es/wcs-inspire/mdt"
DEFAULT_COVERAGE_ID = "Elevacion25830_5"
DEFAULT_WCS_CRS = "EPSG:25830"
GENERATED_AT = "2026-07-31"
USER_AGENT = "castros-ia-galicia/0.1 viladonga-mdt-wcs"


FIELDS = ["product", "path", "coverage_id", "wcs_crs", "bbox_wcs_crs", "size_bytes", "status", "error"]


def require_runtime() -> None:
    missing = []
    for module in ("pyproj",):
        try:
            __import__(module)
        except Exception:
            missing.append(module)
    if missing:
        raise SystemExit(f"Missing Python modules: {', '.join(missing)}")


def load_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_source_root(config: dict[str, Any], override: str | None) -> Path:
    if override:
        return Path(override).expanduser()
    for key in ("source_root_local", "source_root_raspberry"):
        candidate = Path(config[key]).expanduser()
        if candidate.exists():
            return candidate
    return Path(config["source_root_local"]).expanduser()


def label_bounds(path: Path) -> tuple[float, float, float, float]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    xs = []
    ys = []
    for feature in payload.get("features", []):
        geometry = feature.get("geometry") or {}
        if geometry.get("type") != "Polygon":
            continue
        for ring in geometry.get("coordinates") or []:
            for x, y, *_rest in ring:
                xs.append(float(x))
                ys.append(float(y))
    if not xs:
        raise RuntimeError(f"No polygon coordinates found in {path}")
    return min(xs), min(ys), max(xs), max(ys)


def transform_bounds(bounds: tuple[float, float, float, float], source_crs: str, target_crs: str) -> tuple[float, float, float, float]:
    from pyproj import Transformer

    transformer = Transformer.from_crs(source_crs, target_crs, always_xy=True)
    minx, miny, maxx, maxy = bounds
    xs = []
    ys = []
    for x in (minx, maxx):
        for y in (miny, maxy):
            tx, ty = transformer.transform(x, y)
            xs.append(tx)
            ys.append(ty)
    return min(xs), min(ys), max(xs), max(ys)


def build_wcs_url(base_url: str, coverage_id: str, bbox: tuple[float, float, float, float]) -> str:
    minx, miny, maxx, maxy = bbox
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


def fetch(url: str, out_path: Path, force: bool) -> tuple[str, str]:
    if out_path.exists() and not force:
        return "exists", ""
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=90) as response:
        payload = response.read()
        content_type = response.headers.get("content-type", "")
        if response.status != 200 or not (payload.startswith(b"II") or payload.startswith(b"MM")):
            return "failed", f"unexpected WCS response: status={response.status} content_type={content_type}"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(payload)
    return "downloaded", ""


def rel_to_project(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def write_tsv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, dialect="excel-tab")
        writer.writeheader()
        writer.writerows(rows)


def write_report(path: Path, row: dict[str, str], url: str) -> None:
    lines = [
        "# Viladonga WCS MDT",
        "",
        f"Generated: {GENERATED_AT}",
        "",
        f"- Coverage: `{row['coverage_id']}`",
        f"- CRS: `{row['wcs_crs']}`",
        f"- BBOX: `{row['bbox_wcs_crs']}`",
        f"- Output: `{row['path']}`",
        f"- Size bytes: {row['size_bytes']}",
        f"- Status: `{row['status']}`",
        "",
        "## Source",
        "",
        "- Service: `https://servicios.idee.es/wcs-inspire/mdt`",
        "- Product family: MDT from PNOA-LiDAR, WCS service.",
        "",
        "## Request",
        "",
        f"`{url}`",
    ]
    if row["error"]:
        lines.extend(["", "## Error", "", row["error"]])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch a WCS MDT crop for Viladonga.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--source-root")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--wcs-base", default=DEFAULT_WCS_BASE)
    parser.add_argument("--coverage-id", default=DEFAULT_COVERAGE_ID)
    parser.add_argument("--wcs-crs", default=DEFAULT_WCS_CRS)
    parser.add_argument("--buffer-m", type=float)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    require_runtime()
    args = parse_args()
    config = load_config(args.config)
    source_root = resolve_source_root(config, args.source_root)
    label_path = source_root / config["label_geojson"]
    out_path = args.out if args.out.is_absolute() else PROJECT_ROOT / args.out
    buffer_m = float(args.buffer_m if args.buffer_m is not None else config["dem_buffer_m"])

    minx, miny, maxx, maxy = label_bounds(label_path)
    buffered = (minx - buffer_m, miny - buffer_m, maxx + buffer_m, maxy + buffer_m)
    wcs_bbox = transform_bounds(buffered, config["label_crs"], args.wcs_crs)
    url = build_wcs_url(args.wcs_base, args.coverage_id, wcs_bbox)
    status, error = fetch(url, out_path, args.force)
    size_bytes = out_path.stat().st_size if out_path.exists() else 0
    row = {
        "product": "mdt_wcs",
        "path": rel_to_project(out_path),
        "coverage_id": args.coverage_id,
        "wcs_crs": args.wcs_crs,
        "bbox_wcs_crs": ",".join(f"{value:.2f}" for value in wcs_bbox),
        "size_bytes": str(size_bytes),
        "status": status,
        "error": error,
    }
    write_tsv(args.manifest, [row], FIELDS)
    write_report(args.report, row, url)
    print(f"status={status}")
    print(f"out={out_path}")
    print(f"size_bytes={size_bytes}")
    return 1 if status == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
