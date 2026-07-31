#!/usr/bin/env python3
"""Export PNOA chips and segmentation masks for the Viladonga pilot."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "configs/viladonga_pilot.json"
DEFAULT_OUT_DIR = PROJECT_ROOT / "data/viladonga-pilot/chips/pnoa"
DEFAULT_MANIFEST = PROJECT_ROOT / "data/viladonga-pilot/pnoa_chip_manifest.tsv"
DEFAULT_REPORT = PROJECT_ROOT / "reports/viladonga_pnoa_chips.md"
DEFAULT_WMS_BASE = "https://www.ign.es/wms-inspire/pnoa-ma"
DEFAULT_WMS_LAYER = "OI.OrthoimageCoverage"
GENERATED_AT = "2026-07-31"
USER_AGENT = "castros-ia-galicia/0.1 viladonga-pnoa-pilot"


FIELDS = [
    "chip_id",
    "feature_id",
    "label_class",
    "label_kind",
    "tile_side_m",
    "width_px",
    "height_px",
    "center_x",
    "center_y",
    "bbox_raster_crs",
    "raster_crs",
    "image_source",
    "image_path",
    "mask_path",
    "status",
    "error",
]


def require_runtime() -> None:
    missing = []
    for module in ("numpy", "PIL", "pyproj", "rasterio", "shapely"):
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


def safe_slug(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value.strip()).strip("-")
    return cleaned.lower() or "unlabeled"


def rel_to_project(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def load_features(path: Path):
    from shapely.geometry import shape

    payload = json.loads(path.read_text(encoding="utf-8"))
    features = []
    for raw in payload.get("features", []):
        properties = raw.get("properties", {})
        geom = shape(raw.get("geometry"))
        label_class = str(properties.get("class", ""))
        if label_class not in {"0", "1"}:
            continue
        features.append(
            {
                "feature_id": str(properties.get("fid", len(features) + 1)),
                "label_class": label_class,
                "label_kind": "positive" if label_class == "1" else "negative",
                "geometry": geom,
            }
        )
    return features


def stretch_to_uint8(array):
    import numpy as np

    if array.dtype == np.uint8:
        return array
    out = np.zeros(array.shape, dtype=np.uint8)
    for idx in range(array.shape[0]):
        band = array[idx].astype("float32")
        valid = band[np.isfinite(band)]
        if valid.size == 0:
            continue
        lo, hi = np.percentile(valid, [2, 98])
        if hi <= lo:
            hi = lo + 1.0
        out[idx] = np.clip((band - lo) * 255.0 / (hi - lo), 0, 255).astype("uint8")
    return out


def save_png(array, path: Path) -> None:
    from PIL import Image

    if array.shape[0] == 1:
        image = Image.fromarray(array[0], mode="L")
    else:
        image = Image.fromarray(array[:3].transpose(1, 2, 0), mode="RGB")
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


def build_wms_url(base_url: str, layer: str, bbox: tuple[float, float, float, float], width: int, height: int) -> str:
    params = {
        "SERVICE": "WMS",
        "VERSION": "1.1.1",
        "REQUEST": "GetMap",
        "LAYERS": layer,
        "STYLES": "",
        "SRS": "EPSG:25829",
        "BBOX": ",".join(f"{value:.2f}" for value in bbox),
        "WIDTH": str(width),
        "HEIGHT": str(height),
        "FORMAT": "image/png",
        "TRANSPARENT": "false",
    }
    return f"{base_url}?{urlencode(params)}"


def fetch_wms_png(url: str, path: Path) -> None:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=60) as response:
        payload = response.read()
        content_type = response.headers.get("content-type", "")
        if response.status != 200 or not payload.startswith(b"\x89PNG"):
            raise RuntimeError(f"unexpected WMS response: status={response.status} content_type={content_type}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def write_tsv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, dialect="excel-tab")
        writer.writeheader()
        writer.writerows(rows)


def write_report(path: Path, rows: list[dict[str, str]], source_root: Path, image_source: str, image_reference: str) -> None:
    status_counts: dict[str, int] = {}
    for row in rows:
        status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1
    status = "failed" if status_counts.get("failed", 0) else ("ready" if rows else "empty")
    lines = [
        "# Viladonga PNOA chips",
        "",
        f"Generated: {GENERATED_AT}",
        "",
        f"- Source root: `{source_root}`",
        f"- Image source: `{image_source}`",
        f"- Image reference: `{image_reference}`",
        f"- Chip rows: {len(rows)}",
        f"- Exported chips: {status_counts.get('exported', 0)}",
        f"- Failed chips: {status_counts.get('failed', 0)}",
        f"- Status: `{status}`",
        "",
        "## Status Counts",
        "",
    ]
    if status_counts:
        for status_name, count in sorted(status_counts.items()):
            lines.append(f"- {status_name}: {count}")
    else:
        lines.append("- none: 0")
    failed = [row for row in rows if row["status"] == "failed"]
    if failed:
        lines.extend(["", "## Errors", ""])
        for row in failed:
            lines.append(f"- `{row['chip_id']}`: {row['error']}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export Viladonga PNOA chips and masks.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--source-root")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--tile-side-m", type=float)
    parser.add_argument("--pixels", type=int)
    parser.add_argument("--image-source", choices=("auto", "raster", "wms"), default="auto")
    parser.add_argument("--wms-base", default=DEFAULT_WMS_BASE)
    parser.add_argument("--wms-layer", default=DEFAULT_WMS_LAYER)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    require_runtime()

    import numpy as np
    import rasterio
    from pyproj import Transformer
    from rasterio.enums import Resampling
    from rasterio.features import rasterize
    from rasterio.transform import from_bounds
    from rasterio.windows import from_bounds as window_from_bounds
    from shapely.ops import transform as transform_geom

    args = parse_args()
    config = load_config(args.config)
    source_root = resolve_source_root(config, args.source_root)
    label_path = source_root / config["label_geojson"]
    raster_path = source_root / config["pnoa_ortho"]
    if not label_path.exists():
        raise SystemExit(f"Missing label GeoJSON: {label_path}")
    use_raster = args.image_source == "raster" or (args.image_source == "auto" and raster_path.exists())
    if args.image_source == "raster" and not raster_path.exists():
        raise SystemExit(f"Missing PNOA raster: {raster_path}")

    tile_side_m = float(args.tile_side_m or config["tile_side_m"])
    pixels = int(args.pixels or config["chip_pixels"])
    half_side = tile_side_m / 2.0
    out_dir = args.out_dir if args.out_dir.is_absolute() else PROJECT_ROOT / args.out_dir
    image_dir = out_dir / "images"
    mask_dir = out_dir / "masks"

    rows: list[dict[str, str]] = []
    features = load_features(label_path)

    if use_raster:
        image_reference = str(raster_path)
        image_source = "raster"
        raster_context = rasterio.open(raster_path)
    else:
        image_reference = args.wms_base
        image_source = "wms"
        raster_context = None

    if raster_context:
        src = raster_context.__enter__()
        transformer = Transformer.from_crs(config["label_crs"], src.crs, always_xy=True)
        band_indexes = list(range(1, min(src.count, 3) + 1))
        raster_crs = str(src.crs)
    else:
        src = None
        transformer = Transformer.from_crs(config["label_crs"], config["target_crs"], always_xy=True)
        band_indexes = []
        raster_crs = config["target_crs"]

    try:
        for feature in features:
            chip_id = f"viladonga-pnoa-{feature['label_kind']}-{safe_slug(feature['feature_id'])}"
            image_path = image_dir / f"{chip_id}.png"
            mask_path = mask_dir / f"{chip_id}.png"
            status = "pending"
            error = ""
            bbox = (0.0, 0.0, 0.0, 0.0)
            center_x = 0.0
            center_y = 0.0
            try:
                geom = transform_geom(transformer.transform, feature["geometry"])
                center = geom.centroid
                center_x = center.x
                center_y = center.y
                bbox = (center.x - half_side, center.y - half_side, center.x + half_side, center.y + half_side)
                if image_path.exists() and mask_path.exists() and not args.force:
                    status = "exists"
                else:
                    out_transform = from_bounds(*bbox, width=pixels, height=pixels)
                    if src is not None:
                        window = window_from_bounds(*bbox, transform=src.transform)
                        chip = src.read(
                            band_indexes,
                            window=window,
                            out_shape=(len(band_indexes), pixels, pixels),
                            boundless=True,
                            fill_value=0,
                            resampling=Resampling.bilinear,
                        )
                        chip = stretch_to_uint8(chip)
                        save_png(chip, image_path)
                    else:
                        url = build_wms_url(args.wms_base, args.wms_layer, bbox, pixels, pixels)
                        fetch_wms_png(url, image_path)
                    if feature["label_class"] == "1":
                        mask = rasterize(
                            [(geom, 1)],
                            out_shape=(pixels, pixels),
                            transform=out_transform,
                            fill=0,
                            dtype="uint8",
                        )
                    else:
                        mask = np.zeros((pixels, pixels), dtype="uint8")
                    save_png(mask.reshape(1, pixels, pixels), mask_path)
                    status = "exported"
            except Exception as exc:
                status = "failed"
                error = str(exc)
            rows.append(
                {
                    "chip_id": chip_id,
                    "feature_id": feature["feature_id"],
                    "label_class": feature["label_class"],
                    "label_kind": feature["label_kind"],
                    "tile_side_m": f"{tile_side_m:.2f}",
                    "width_px": str(pixels),
                    "height_px": str(pixels),
                    "center_x": f"{center_x:.2f}",
                    "center_y": f"{center_y:.2f}",
                    "bbox_raster_crs": ",".join(f"{value:.2f}" for value in bbox),
                    "raster_crs": raster_crs,
                    "image_source": image_source,
                    "image_path": rel_to_project(image_path),
                    "mask_path": rel_to_project(mask_path),
                    "status": status,
                    "error": error,
                }
            )
    finally:
        if raster_context:
            raster_context.__exit__(None, None, None)

    write_tsv(args.manifest, rows, FIELDS)
    write_report(args.report, rows, source_root, image_source, image_reference)
    failed = sum(1 for row in rows if row["status"] == "failed")
    print(f"source_root={source_root}")
    print(f"chip_rows={len(rows)}")
    print(f"failed_chips={failed}")
    print(f"manifest={args.manifest}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
