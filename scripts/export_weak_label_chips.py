#!/usr/bin/env python3
"""Export RGB weak-label chips from the WMS tile manifest.

The script is intentionally conservative: it downloads official orthophoto
chips outside Git, validates that each PNG is readable, and writes a lightweight
manifest/report that can be versioned.
"""

from __future__ import annotations

import argparse
import csv
import time
import threading
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from PIL import Image, ImageStat


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = PROJECT_ROOT / "data/weak-label-splits-v1/weak_label_tile_manifest_512m.tsv"
DEFAULT_OUT_MANIFEST = PROJECT_ROOT / "data/weak-label-splits-v1/weak_label_chip_export_manifest.tsv"
DEFAULT_REPORT = PROJECT_ROOT / "reports/weak_label_chip_export_v1.md"

GENERATED_AT = "2026-08-01T00:00:00Z"
USER_AGENT = "Mozilla/5.0 castros-ia-galicia/1.0 weak-label-chip-export"
SPLIT_ORDER = {"train": 0, "val": 1, "test": 2, "test_trasancos": 3, "test_o_val": 4}

MANIFEST_FIELDS = [
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
    "tile_side_m",
    "wms_source",
    "wms_base",
    "wms_layer",
    "target_png_path",
    "training_use",
    "width_px_requested",
    "height_px_requested",
    "status",
    "image_status",
    "actual_width_px",
    "actual_height_px",
    "image_mode",
    "bytes",
    "attempts",
    "error",
    "wms_url",
    "generated_at",
]


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, dialect="excel-tab"))


def write_tsv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, dialect="excel-tab", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def rel_to_project(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def csv_set(value: str) -> set[str]:
    return {item.strip() for item in value.split(",") if item.strip()}


def row_sort_key(row: dict[str, str]) -> tuple:
    return (
        SPLIT_ORDER.get(row.get("final_split", ""), 99),
        row.get("label_class", ""),
        row.get("wms_source", ""),
        row.get("country", ""),
        row.get("name", ""),
        row.get("tile_id", ""),
    )


def round_robin_stratified_take(rows: list[dict[str, str]], limit: int, strata_fields: list[str]) -> list[dict[str, str]]:
    groups: dict[tuple[str, ...], list[dict[str, str]]] = defaultdict(list)
    for row in sorted(rows, key=row_sort_key):
        key = tuple(row.get(field, "") for field in strata_fields)
        groups[key].append(row)

    selected: list[dict[str, str]] = []
    keys = sorted(groups)
    while keys and len(selected) < limit:
        next_keys: list[tuple[str, ...]] = []
        for key in keys:
            group_rows = groups[key]
            if group_rows and len(selected) < limit:
                selected.append(group_rows.pop(0))
            if group_rows:
                next_keys.append(key)
        keys = next_keys
    return selected


def select_rows(rows: list[dict[str, str]], args: argparse.Namespace) -> list[dict[str, str]]:
    splits = csv_set(args.splits)
    labels = csv_set(args.labels)
    sources = csv_set(args.sources)

    selected = [
        row
        for row in rows
        if (not splits or row.get("final_split") in splits)
        and (not labels or row.get("label_class") in labels or row.get("label_role") in labels)
        and (not sources or row.get("wms_source") in sources or row.get("country") in sources)
    ]

    if args.per_split:
        grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in selected:
            grouped[row.get("final_split", "")].append(row)
        selected = []
        for split in sorted(grouped, key=lambda value: SPLIT_ORDER.get(value, 99)):
            selected.extend(round_robin_stratified_take(grouped[split], args.per_split, ["label_class", "wms_source"]))

    if args.per_source:
        grouped = defaultdict(list)
        for row in selected:
            grouped[row.get("wms_source", "")].append(row)
        selected = []
        for source in sorted(grouped):
            selected.extend(round_robin_stratified_take(grouped[source], args.per_source, ["final_split", "label_class"]))

    selected = sorted(selected, key=row_sort_key)
    if args.limit:
        selected = selected[: args.limit]
    return selected


def build_wms_url(row: dict[str, str], width: int, height: int) -> str:
    params = {
        "SERVICE": "WMS",
        "VERSION": "1.1.1",
        "REQUEST": "GetMap",
        "LAYERS": row["wms_layer"],
        "STYLES": "",
        "SRS": "EPSG:4326",
        "BBOX": row["bbox_epsg4326"],
        "WIDTH": str(width),
        "HEIGHT": str(height),
        "FORMAT": "image/png",
        "TRANSPARENT": "false",
    }
    return f"{row['wms_base']}?{urlencode(params)}"


def image_diagnostics(path: Path) -> dict[str, str]:
    if not path.exists():
        return {
            "image_status": "missing",
            "actual_width_px": "",
            "actual_height_px": "",
            "image_mode": "",
            "bytes": "0",
            "error": "file does not exist",
        }
    try:
        size = path.stat().st_size
        with Image.open(path) as image:
            image.load()
            rgb = image.convert("RGB")
            gray = image.convert("L")
            extrema = ImageStat.Stat(rgb).extrema
            max_channel_range = max(high - low for low, high in extrema)
            gray_stddev = ImageStat.Stat(gray).stddev[0]
            image_status = "valid"
            error = ""
            if max_channel_range < 3 or gray_stddev < 1.0:
                image_status = "low_information"
                error = f"very low pixel variation: channel_range={max_channel_range:.2f} gray_stddev={gray_stddev:.2f}"
            return {
                "image_status": image_status,
                "actual_width_px": str(image.width),
                "actual_height_px": str(image.height),
                "image_mode": image.mode,
                "bytes": str(size),
                "error": error,
            }
    except Exception as exc:
        return {
            "image_status": "invalid",
            "actual_width_px": "",
            "actual_height_px": "",
            "image_mode": "",
            "bytes": str(path.stat().st_size if path.exists() else 0),
            "error": str(exc),
        }


def fetch_png(url: str, path: Path, *, force: bool, timeout: float) -> tuple[str, dict[str, str], int]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        diagnostics = image_diagnostics(path)
        if diagnostics["image_status"] in {"valid", "low_information"}:
            return "exists", diagnostics, 0

    last_error = ""
    for attempt in range(1, 4):
        try:
            request = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(request, timeout=timeout) as response:
                payload = response.read()
                content_type = response.headers.get("content-type", "")
                if response.status == 200 and payload.startswith(b"\x89PNG"):
                    tmp_path = path.with_suffix(path.suffix + ".tmp")
                    tmp_path.write_bytes(payload)
                    tmp_path.replace(path)
                    diagnostics = image_diagnostics(path)
                    if diagnostics["image_status"] == "invalid":
                        return "failed", diagnostics, attempt
                    return "downloaded", diagnostics, attempt
                last_error = f"unexpected WMS response status={response.status} content_type={content_type}"
        except Exception as exc:
            last_error = str(exc)
        if attempt < 3:
            time.sleep(0.5 * attempt)

    diagnostics = image_diagnostics(path)
    diagnostics["error"] = last_error or diagnostics.get("error", "unknown fetch failure")
    return "failed", diagnostics, 3


def export_row(
    export_index: int,
    row: dict[str, str],
    *,
    width: int,
    height: int,
    force: bool,
    timeout: float,
    semaphores: dict[str, threading.Semaphore],
) -> dict[str, str]:
    url = build_wms_url(row, width, height)
    target_path = PROJECT_ROOT / row["target_png_path"]
    semaphore = semaphores.get(row.get("wms_source", ""), semaphores["default"])
    with semaphore:
        status, diagnostics, attempts = fetch_png(url, target_path, force=force, timeout=timeout)

    return {
        **row,
        "export_id": f"weak-chip-export-v1-{export_index:05d}",
        "width_px_requested": str(width),
        "height_px_requested": str(height),
        "status": status,
        "image_status": diagnostics["image_status"],
        "actual_width_px": diagnostics["actual_width_px"],
        "actual_height_px": diagnostics["actual_height_px"],
        "image_mode": diagnostics["image_mode"],
        "bytes": diagnostics["bytes"],
        "attempts": str(attempts),
        "error": diagnostics["error"],
        "wms_url": url,
        "generated_at": GENERATED_AT,
    }


def export_rows(rows: list[dict[str, str]], args: argparse.Namespace) -> list[dict[str, str]]:
    semaphores = {
        "ign_pnoa_rgb": threading.Semaphore(args.ign_parallel),
        "dgt_ortos2021_rgb": threading.Semaphore(args.dgt_parallel),
        "default": threading.Semaphore(args.default_parallel),
    }
    exported: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                export_row,
                index,
                row,
                width=args.width,
                height=args.height,
                force=args.force,
                timeout=args.timeout,
                semaphores=semaphores,
            ): row
            for index, row in enumerate(rows, start=1)
        }
        for future in as_completed(futures):
            exported.append(future.result())
    return sorted(exported, key=lambda row: row["export_id"])


def next_step_text(rows: list[dict[str, str]], args: argparse.Namespace) -> str:
    splits = {row["final_split"] for row in rows}
    if splits == {"test_o_val", "test_trasancos"} and not args.per_split and not args.limit:
        return "Export `val`, then train a minimal chip classifier/ranker and evaluate it against the already exported O Val/Trasancos holdouts."
    if args.per_split or args.limit:
        return "Run the same exporter over `test_o_val` and `test_trasancos`, then export `val` and train a minimal chip classifier/ranker before touching full train."
    if splits == {"val"}:
        return "Train the first minimal chip classifier/ranker and evaluate it against `test_o_val` and `test_trasancos` before exporting full train."
    return "Keep the output as a technical ranking dataset; do not treat model scores as archaeological discoveries without QGIS/LiDAR/source review."


def write_report(path: Path, source_manifest: Path, rows: list[dict[str, str]], args: argparse.Namespace) -> None:
    status_counts = Counter(row["status"] for row in rows)
    image_counts = Counter(row["image_status"] for row in rows)
    split_counts = Counter((row["final_split"], row["label_role"]) for row in rows)
    source_counts = Counter(row["wms_source"] for row in rows)
    total_bytes = sum(int(row.get("bytes") or 0) for row in rows)
    failures = [row for row in rows if row["status"] == "failed" or row["image_status"] == "invalid"]

    lines = [
        "# Weak-label chip export",
        "",
        f"Generated: {GENERATED_AT}",
        "",
        "## Scope",
        "",
        f"- Source manifest: `{rel_to_project(source_manifest)}`",
        f"- Rows selected: {len(rows)}",
        f"- Requested size: {args.width}x{args.height}px",
        f"- Splits filter: `{args.splits or 'all'}`",
        f"- Labels filter: `{args.labels or 'all'}`",
        f"- Sources filter: `{args.sources or 'all'}`",
        f"- Per split cap: `{args.per_split or 'none'}`",
        f"- Per source cap: `{args.per_source or 'none'}`",
        f"- Global limit: `{args.limit or 'none'}`",
        "",
        "## Files",
        "",
        f"- Export manifest: `{rel_to_project(args.out_manifest)}`",
        "- PNG chips: `data/external/weak-label-chips-v1/` (ignored by Git)",
        "",
        "## Download Status",
        "",
    ]
    for status, count in sorted(status_counts.items()):
        lines.append(f"- {status}: {count}")
    lines.extend(["", "## Image Status", ""])
    for status, count in sorted(image_counts.items()):
        lines.append(f"- {status}: {count}")
    lines.extend(["", "## By Source", ""])
    for source, count in sorted(source_counts.items()):
        lines.append(f"- {source}: {count}")
    lines.extend(["", "## By Split And Role", ""])
    for (split, role), count in sorted(split_counts.items(), key=lambda item: (SPLIT_ORDER.get(item[0][0], 99), item[0][1])):
        lines.append(f"- {split}/{role}: {count}")
    lines.extend(
        [
            "",
            "## Size",
            "",
            f"- Total local PNG bytes represented by this manifest: {total_bytes}",
            "",
            "## Failures",
            "",
        ]
    )
    if failures:
        for row in failures[:20]:
            lines.append(f"- {row['tile_id']} `{row['wms_source']}`: {row['error']}")
        if len(failures) > 20:
            lines.append(f"- ... {len(failures) - 20} more failures not shown.")
    else:
        lines.append("- None.")
    lines.extend(
        [
            "",
            "## Next Step",
            "",
            next_step_text(rows, args),
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--out-manifest", type=Path, default=DEFAULT_OUT_MANIFEST)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--splits", default="", help="Comma-separated final_split values.")
    parser.add_argument("--labels", default="", help="Comma-separated labels: 1,0,positive,hard_negative.")
    parser.add_argument("--sources", default="", help="Comma-separated WMS sources or countries: ign_pnoa_rgb,dgt_ortos2021_rgb,ES,PT.")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--per-split", type=int, default=0)
    parser.add_argument("--per-source", type=int, default=0)
    parser.add_argument("--width", type=int, default=512)
    parser.add_argument("--height", type=int, default=512)
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--ign-parallel", type=int, default=6)
    parser.add_argument("--dgt-parallel", type=int, default=2)
    parser.add_argument("--default-parallel", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source_manifest = args.input if args.input.is_absolute() else PROJECT_ROOT / args.input
    args.out_manifest = args.out_manifest if args.out_manifest.is_absolute() else PROJECT_ROOT / args.out_manifest
    args.report = args.report if args.report.is_absolute() else PROJECT_ROOT / args.report

    rows = read_tsv(source_manifest)
    selected = select_rows(rows, args)
    exported = export_rows(selected, args)
    write_tsv(args.out_manifest, exported, MANIFEST_FIELDS)
    write_report(args.report, source_manifest, exported, args)

    status_counts = Counter(row["status"] for row in exported)
    image_counts = Counter(row["image_status"] for row in exported)
    print(f"source_rows={len(rows)}")
    print(f"selected_rows={len(selected)}")
    print(f"status_counts={dict(sorted(status_counts.items()))}")
    print(f"image_status_counts={dict(sorted(image_counts.items()))}")
    print(f"wrote={rel_to_project(args.out_manifest)}")
    print(f"report={rel_to_project(args.report)}")


if __name__ == "__main__":
    main()
