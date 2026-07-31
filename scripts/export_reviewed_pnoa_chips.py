#!/usr/bin/env python3
"""Export PNOA image chips for accepted reviewed annotations only."""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ANNOTATION_GPKG = PROJECT_ROOT / "data/annotations/castros_annotations.gpkg"
TRAINING_LABELS = PROJECT_ROOT / "data/training/training_labels_manifest.tsv"
TRAINING_NEGATIVES = PROJECT_ROOT / "data/training/training_negatives_manifest.tsv"
DEFAULT_OUT_DIR = PROJECT_ROOT / "data/raster-chips/pnoa"
DEFAULT_MANIFEST = PROJECT_ROOT / "data/training/pnoa_chip_manifest.tsv"
DEFAULT_REPORT = PROJECT_ROOT / "reports/pnoa_chip_export.md"
DEFAULT_WMS_BASE = "https://www.ign.es/wms-inspire/pnoa-ma"
DEFAULT_LAYER = "OI.OrthoimageCoverage"
GENERATED_AT = "2026-07-31"
USER_AGENT = "castros-ia-galicia/0.1 reviewed-pnoa-chip-export"


FIELDS = [
    "chip_id",
    "label_kind",
    "label_id",
    "final_split",
    "source_layer",
    "source_fid",
    "source_basis",
    "confidence",
    "center_easting_utm29",
    "center_northing_utm29",
    "bbox_utm29",
    "width_px",
    "height_px",
    "product",
    "chip_path",
    "status",
    "error",
]


def read_tsv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, dialect="excel-tab"))


def write_tsv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, dialect="excel-tab")
        writer.writeheader()
        writer.writerows(rows)


def safe_slug(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value.strip()).strip("-")
    return cleaned.lower() or "unlabeled"


def count_accepted_manifests() -> tuple[int, int]:
    positive = [row for row in read_tsv(TRAINING_LABELS) if row.get("review_status") == "accepted"]
    negative = [row for row in read_tsv(TRAINING_NEGATIVES) if row.get("review_status") == "accepted"]
    return len(positive), len(negative)


def build_wms_url(base_url: str, layer: str, bbox_utm29: tuple[float, float, float, float], width: int, height: int) -> str:
    params = {
        "SERVICE": "WMS",
        "VERSION": "1.1.1",
        "REQUEST": "GetMap",
        "LAYERS": layer,
        "STYLES": "",
        "SRS": "EPSG:25829",
        "BBOX": ",".join(f"{value:.2f}" for value in bbox_utm29),
        "WIDTH": str(width),
        "HEIGHT": str(height),
        "FORMAT": "image/png",
        "TRANSPARENT": "false",
    }
    return f"{base_url}?{urlencode(params)}"


def fetch_png(url: str, path: Path) -> None:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=45) as response:
        payload = response.read()
        content_type = response.headers.get("content-type", "")
        if response.status != 200 or not payload.startswith(b"\x89PNG"):
            raise RuntimeError(f"unexpected WMS response: status={response.status} content_type={content_type}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def load_accepted_geodata():
    try:
        import geopandas as gpd
    except ImportError as exc:  # pragma: no cover - depends on optional environment
        raise SystemExit("Missing geopandas; install the raster/vector environment before exporting chips.") from exc

    positives = gpd.read_file(ANNOTATION_GPKG, layer="labels_reviewed")
    negatives = gpd.read_file(ANNOTATION_GPKG, layer="negative_areas_reviewed")
    positives = positives[positives["review_status"] == "accepted"].copy()
    negatives = negatives[negatives["review_status"] == "accepted"].copy()
    if not positives.empty and positives.crs is None:
        positives = positives.set_crs("EPSG:4326")
    if not negatives.empty and negatives.crs is None:
        negatives = negatives.set_crs("EPSG:4326")
    return positives, negatives


def rows_from_layer(gdf, label_kind: str, source_layer: str, args: argparse.Namespace) -> list[dict[str, str]]:
    if gdf.empty:
        return []
    projected = gdf.to_crs("EPSG:25829")
    chip_root = args.out_dir if args.out_dir.is_absolute() else PROJECT_ROOT / args.out_dir
    try:
        rel_root = chip_root.relative_to(PROJECT_ROOT)
    except ValueError:
        rel_root = chip_root
    rows = []
    for idx, feature in projected.iterrows():
        geom = feature.geometry
        label_id_field = "label_id" if label_kind == "positive" else "negative_label_id"
        raw_label_id = str(feature.get(label_id_field) or f"{label_kind}-{feature.get('fid', idx)}")
        chip_id = f"pnoa-{label_kind}-{safe_slug(raw_label_id)}"
        center = geom.centroid
        half_side = args.tile_side_m / 2
        bbox_utm29 = (center.x - half_side, center.y - half_side, center.x + half_side, center.y + half_side)
        final_split = str(feature.get("final_split") or "unsplit")
        rel_path = rel_root / safe_slug(final_split) / f"{chip_id}.png"
        out_path = chip_root / safe_slug(final_split) / f"{chip_id}.png"
        status = "pending"
        error = ""
        if args.dry_run:
            status = "dry_run"
        elif out_path.exists() and not args.force:
            status = "exists"
        else:
            try:
                url = build_wms_url(args.wms_base, args.layer, bbox_utm29, args.width, args.height)
                fetch_png(url, out_path)
                status = "exported"
            except Exception as exc:  # pragma: no cover - depends on network/service
                status = "failed"
                error = str(exc)
        rows.append(
            {
                "chip_id": chip_id,
                "label_kind": label_kind,
                "label_id": raw_label_id,
                "final_split": final_split,
                "source_layer": source_layer,
                "source_fid": str(feature.get("fid") or ""),
                "source_basis": str(feature.get("source_basis") or ""),
                "confidence": str(feature.get("confidence") or ""),
                "center_easting_utm29": f"{center.x:.2f}",
                "center_northing_utm29": f"{center.y:.2f}",
                "bbox_utm29": ",".join(f"{value:.2f}" for value in bbox_utm29),
                "width_px": str(args.width),
                "height_px": str(args.height),
                "product": "pnoa_rgb",
                "chip_path": str(rel_path),
                "status": status,
                "error": error,
            }
        )
    return rows


def write_report(path: Path, rows: list[dict[str, str]], accepted_positive: int, accepted_negative: int) -> None:
    status_counts: dict[str, int] = {}
    for row in rows:
        status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1
    blocked = accepted_positive == 0 or accepted_negative == 0
    failed = status_counts.get("failed", 0)
    lines = [
        "# PNOA chip export",
        "",
        f"Generated: {GENERATED_AT}",
        "",
        f"- Accepted positive polygons: {accepted_positive}",
        f"- Accepted negative areas: {accepted_negative}",
        f"- Chip rows: {len(rows)}",
        f"- Failed chips: {failed}",
        f"- Status: {'blocked_no_accepted_labels' if blocked else ('failed' if failed else 'ready')}",
        "",
        "## Rule",
        "",
        "Only accepted reviewed annotations are eligible for chip export. Candidate points, PBA rows and toponymic hints are ignored.",
        "",
        "## Status Counts",
        "",
    ]
    if status_counts:
        for status, count in sorted(status_counts.items()):
            lines.append(f"- {status}: {count}")
    else:
        lines.append("- none: 0")
    if failed:
        lines.extend(["", "## Errors", ""])
        for row in rows:
            if row["status"] == "failed":
                lines.append(f"- {row['chip_id']}: {row['error']}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export PNOA chips for accepted reviewed annotations.")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--wms-base", default=DEFAULT_WMS_BASE)
    parser.add_argument("--layer", default=DEFAULT_LAYER)
    parser.add_argument("--tile-side-m", type=float, default=512.0)
    parser.add_argument("--width", type=int, default=512)
    parser.add_argument("--height", type=int, default=512)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    accepted_positive, accepted_negative = count_accepted_manifests()
    rows: list[dict[str, str]] = []
    if accepted_positive and accepted_negative:
        positives, negatives = load_accepted_geodata()
        rows.extend(rows_from_layer(positives, "positive", "labels_reviewed", args))
        rows.extend(rows_from_layer(negatives, "negative", "negative_areas_reviewed", args))
    write_tsv(args.manifest, rows, FIELDS)
    write_report(args.report, rows, accepted_positive, accepted_negative)
    print(f"accepted_positive_polygons={accepted_positive}")
    print(f"accepted_negative_areas={accepted_negative}")
    print(f"pnoa_chip_rows={len(rows)}")
    print(f"pnoa_chip_status={'blocked_no_accepted_labels' if not rows else 'written'}")
    return 1 if any(row["status"] == "failed" for row in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
