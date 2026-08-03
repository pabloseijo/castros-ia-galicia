#!/usr/bin/env python3
"""Extract the full RGB+relief+MSRM feature vector for any chip manifest.

Two jobs depend on this:

- adding new rows (landscape negatives) to the training bank
- scaling to Galicia, where 1.71M cells would need ~926 GB of PNG/GeoTIFF.
  Features are ~1/100 the size of the imagery, so with --delete-chips-after
  a province can be processed within a disk budget the machine actually has.

Output columns match the fusion trainer's feature schema, so the resulting
TSV can be concatenated onto the existing bank without translation.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_trasancos_inference_ranking import (  # noqa: E402
    msrm_features_for,
    relief_features_for,
)
from evaluate_weak_label_msrm_features import parse_scale_list  # noqa: E402
from evaluate_weak_label_relief_score_variants import VARIANT_NAMES  # noqa: E402
from train_weak_label_rgb_baseline import (  # noqa: E402
    FEATURE_NAMES as RGB_FEATURE_NAMES,
    extract_features as extract_rgb_features,
    read_tsv,
    rel_to_project,
    write_tsv,
)
from train_weak_label_rgb_relief_baseline import (  # noqa: E402
    MSRM_FEATURE_NAMES,
    RELIEF_FEATURE_NAMES,
    fit_variant_scaler,
    variant_scores,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TRAIN_RELIEF = PROJECT_ROOT / "data/weak-label-relief-v1/weak_label_relief_features_train.tsv"

META_FIELDS = [
    "dataset",
    "tile_id",
    "sample_id",
    "bank_id",
    "label_class",
    "label_role",
    "final_split",
    "country",
    "name",
    "municipality",
    "parish",
    "morphology_proxy",
    "negative_type",
]

FUSION_FEATURE_NAMES = (
    [f"rgb__{name}" for name in RGB_FEATURE_NAMES]
    + [f"relief__{name}" for name in RELIEF_FEATURE_NAMES]
    + [f"relief_variant__{name}" for name in VARIANT_NAMES]
    + [f"msrm__{name}" for name in MSRM_FEATURE_NAMES]
)

OUT_FIELDS = META_FIELDS + FUSION_FEATURE_NAMES + ["error", "status"]

_STATE: dict[str, object] = {}


def _init(scaler: dict, scales_m: list[float], ring_radii_m: list[float], opts: dict) -> None:
    _STATE["scaler"] = scaler
    _STATE["scales_m"] = scales_m
    _STATE["ring_radii_m"] = ring_radii_m
    _STATE["opts"] = opts


def _run(payload: tuple[dict, str, str]) -> dict[str, str]:
    row, png_path, dem_path = payload
    opts = _STATE["opts"]  # type: ignore[assignment]
    result = {key: row.get(key, "") for key in META_FIELDS}
    result["dataset"] = opts["dataset"]  # type: ignore[index]
    result["status"] = "failed"
    result["error"] = ""

    png = Path(png_path)
    dem = Path(dem_path)
    if not png.exists():
        result["error"] = "missing_rgb"
        return result
    if not dem.exists():
        result["error"] = "missing_dem"
        return result
    try:
        rgb = extract_rgb_features(png, opts["fixed_radius_m"], opts["image_size"])  # type: ignore[index]
        relief = relief_features_for(dem, opts["fixed_radius_m"])  # type: ignore[index]
        msrm = msrm_features_for(
            dem, _STATE["scales_m"], _STATE["ring_radii_m"]  # type: ignore[arg-type]
        )
        variants = variant_scores(
            {k: f"{v:.8f}" for k, v in relief.items()}, _STATE["scaler"]  # type: ignore[arg-type]
        )
        for name in RGB_FEATURE_NAMES:
            result[f"rgb__{name}"] = f"{float(rgb.get(name, 0.0)):.8f}"
        for name in RELIEF_FEATURE_NAMES:
            result[f"relief__{name}"] = f"{float(relief.get(name, 0.0)):.8f}"
        for name in VARIANT_NAMES:
            result[f"relief_variant__{name}"] = f"{float(variants.get(name, 0.0)):.8f}"
        for name in MSRM_FEATURE_NAMES:
            result[f"msrm__{name}"] = f"{float(msrm.get(name, 0.0)):.8f}"
        result["status"] = "ok"
    except Exception as exc:
        result["error"] = str(exc)[:200]
    return result


def dem_path_for_row(row: dict[str, str], dem_by_tile: dict[str, str]) -> str:
    tile_id = row.get("tile_id", "")
    if tile_id in dem_by_tile:
        return dem_by_tile[tile_id]
    return ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rgb-manifest", type=Path, required=True)
    parser.add_argument("--dem-manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--dataset", default="landscape_negatives")
    parser.add_argument("--train-relief", type=Path, default=DEFAULT_TRAIN_RELIEF)
    parser.add_argument("--scales-m", default="15,30,60,120,240")
    parser.add_argument("--ring-radii-m", default="40,60,80,100,120,150,180,220")
    parser.add_argument("--fixed-radius-m", type=float, default=120.0)
    parser.add_argument("--image-size", type=int, default=256)
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    parser.add_argument("--progress-every", type=int, default=500)
    parser.add_argument(
        "--delete-chips-after",
        action="store_true",
        help="Remove PNG/GeoTIFF once features are extracted. Required to fit Galicia on disk.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    for attr in ("rgb_manifest", "dem_manifest", "out", "train_relief"):
        value = getattr(args, attr)
        setattr(args, attr, value if value.is_absolute() else PROJECT_ROOT / value)

    scaler = fit_variant_scaler(
        [row for row in read_tsv(args.train_relief) if row.get("status") == "ok"]
    )
    scales_m = parse_scale_list(args.scales_m)
    ring_radii_m = parse_scale_list(args.ring_radii_m)

    rgb_rows = read_tsv(args.rgb_manifest)
    dem_by_tile = {
        row.get("tile_id", ""): row.get("target_dem_path", "")
        for row in read_tsv(args.dem_manifest)
        if row.get("dem_status") == "valid"
    }

    payloads = []
    for row in rgb_rows:
        if row.get("status") not in {"downloaded", "ok", "cached"}:
            continue
        png = row.get("target_png_path", "")
        dem = dem_path_for_row(row, dem_by_tile)
        if not png or not dem:
            continue
        payloads.append(
            (
                row,
                str(PROJECT_ROOT / png if not Path(png).is_absolute() else png),
                str(PROJECT_ROOT / dem if not Path(dem).is_absolute() else dem),
            )
        )

    opts = {
        "dataset": args.dataset,
        "fixed_radius_m": args.fixed_radius_m,
        "image_size": args.image_size,
    }

    out_rows: list[dict[str, str]] = []
    total = len(payloads)
    print(f"extracting {total} rows with {args.workers} workers", flush=True)

    workers = max(1, args.workers)
    if workers == 1:
        _init(scaler, scales_m, ring_radii_m, opts)
        for index, payload in enumerate(payloads, start=1):
            out_rows.append(_run(payload))
            if index % args.progress_every == 0 or index == total:
                print(f"extracted {index}/{total}", flush=True)
    else:
        with ProcessPoolExecutor(
            max_workers=workers, initializer=_init, initargs=(scaler, scales_m, ring_radii_m, opts)
        ) as pool:
            for index, result in enumerate(pool.map(_run, payloads, chunksize=8), start=1):
                out_rows.append(result)
                if index % args.progress_every == 0 or index == total:
                    print(f"extracted {index}/{total}", flush=True)

    write_tsv(args.out, out_rows, OUT_FIELDS)
    ok = sum(1 for row in out_rows if row["status"] == "ok")
    print(f"rows_ok={ok} rows_failed={len(out_rows) - ok}")
    print(f"features={rel_to_project(args.out)}")

    if args.delete_chips_after:
        freed = 0
        for _row, png, dem in payloads:
            for path in (Path(png), Path(dem)):
                try:
                    if path.exists():
                        freed += path.stat().st_size
                        path.unlink()
                except OSError:
                    pass
        print(f"deleted_chips_bytes={freed} ({freed / 1e9:.2f} GB freed)")


if __name__ == "__main__":
    main()
