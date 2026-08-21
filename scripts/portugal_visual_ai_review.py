#!/usr/bin/env python3
"""Revision visual asistida por IA local para candidatos de Portugal.

No toca el precinto ni compara con verdad. Produce un paquete de revision:

- fichas PNG con sombreado, relieve local y apertura;
- GeoJSON de candidatos para QGIS;
- respuestas JSONL/TSV de Ollama vision.
"""
from __future__ import annotations

import argparse
import base64
import csv
import json
import math
import sys
import textwrap
import time
from pathlib import Path

import numpy as np
import requests
import rasterio
from PIL import Image, ImageDraw
from pyproj import Transformer
from rasterio.merge import merge

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "scripts"))


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def moving_mean(a: np.ndarray, k: int) -> np.ndarray:
    k = max(3, int(k) | 1)
    pad = k // 2
    b = np.pad(a, pad, mode="edge")
    c = np.cumsum(np.cumsum(b, axis=0), axis=1)
    c = np.pad(c, ((1, 0), (1, 0)))
    h, w = a.shape
    return (c[k:k + h, k:k + w] - c[:h, k:k + w]
            - c[k:k + h, :w] + c[:h, :w]) / float(k * k)


def hillshade_multi(dem: np.ndarray, res: float, alt: float = 35.0) -> np.ndarray:
    gy, gx = np.gradient(dem.astype(np.float32), res)
    slope = np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    zen = np.radians(alt)
    acc = np.zeros_like(dem, dtype=np.float32)
    for az in (315.0, 45.0, 135.0, 225.0):
        aza = np.radians(360.0 - az + 90.0)
        acc += (np.sin(zen) * np.cos(slope)
                + np.cos(zen) * np.sin(slope) * np.cos(aza - aspect))
    return acc / 4.0


def scale01(a: np.ndarray, lo_hi: tuple[float, float] | None = None) -> np.ndarray:
    finite = a[np.isfinite(a)]
    if finite.size == 0:
        return np.zeros_like(a, dtype=np.float32)
    if lo_hi is None:
        lo, hi = np.percentile(finite, (2, 98))
    else:
        lo, hi = lo_hi
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        hi = lo + 1e-6
    return np.clip((a - lo) / (hi - lo), 0, 1).astype(np.float32)


def gray(a: np.ndarray) -> Image.Image:
    v = (scale01(a) * 255).astype(np.uint8)
    return Image.fromarray(v, "L").convert("RGB")


def diverging(a: np.ndarray) -> Image.Image:
    finite = a[np.isfinite(a)]
    if finite.size == 0:
        return Image.fromarray(np.zeros((*a.shape, 3), np.uint8))
    m = float(np.nanpercentile(np.abs(finite), 98))
    if m <= 0:
        m = 1e-6
    v = np.clip(a / m, -1, 1)
    rgb = np.zeros((*a.shape, 3), np.uint8)
    pos = v >= 0
    rgb[..., 0] = np.where(pos, 255, (1 + v) * 255)
    rgb[..., 1] = np.where(pos, (1 - v * 0.55) * 255, (1 + v) * 255)
    rgb[..., 2] = np.where(pos, (1 - v) * 255, 255)
    return Image.fromarray(rgb, "RGB")


def mark_center(img: Image.Image) -> Image.Image:
    out = img.copy()
    d = ImageDraw.Draw(out)
    w, h = out.size
    cx, cy = w // 2, h // 2
    r = 10
    d.line((cx - r, cy, cx + r, cy), fill=(255, 0, 0), width=3)
    d.line((cx, cy - r, cx, cy + r), fill=(255, 0, 0), width=3)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(255, 0, 0), width=2)
    return out


def raster_index(paths: list[Path]) -> list[tuple[Path, tuple[float, float, float, float]]]:
    out = []
    for p in paths:
        with rasterio.open(p) as ds:
            b = ds.bounds
            out.append((p, (float(b.left), float(b.bottom), float(b.right), float(b.top))))
    return out


def overlaps(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    return not (a[2] <= b[0] or a[0] >= b[2] or a[3] <= b[1] or a[1] >= b[3])


def read_dem(index, center_x: float, center_y: float, side_m: float, res_m: float) -> np.ndarray:
    half = side_m / 2.0
    bounds = (center_x - half, center_y - half, center_x + half, center_y + half)
    selected = [p for p, b in index if overlaps(bounds, b)]
    if not selected:
        raise RuntimeError("sin MDT para la ventana")
    datasets = [rasterio.open(p) for p in selected]
    try:
        arr, _ = merge(datasets, bounds=bounds, res=(res_m, res_m),
                       nodata=np.nan, dtype="float32")
    finally:
        for ds in datasets:
            ds.close()
    dem = arr[0].astype(np.float32)
    if not np.isfinite(dem).any():
        raise RuntimeError("MDT vacio")
    med = float(np.nanmedian(dem))
    return np.nan_to_num(dem, nan=med)


def render_chip(row: dict[str, str], rank: int, dem: np.ndarray, res_m: float,
                out_png: Path, side_m: float) -> None:
    from openness import canal_rapido

    hs = hillshade_multi(dem, res_m)
    lrm = dem - moving_mean(dem, int(round(51.0 / res_m)))
    opn = canal_rapido(dem, res=res_m, radio_m=30.0, direcciones=8)

    panels = [
        ("SOMBRA", gray(hs)),
        ("LRM", diverging(lrm)),
        ("APERTURA", gray(opn)),
    ]
    target = 420
    margin = 12
    label_h = 62
    header_h = 82
    w = len(panels) * target + (len(panels) + 1) * margin
    h = header_h + target + label_h + margin
    canvas = Image.new("RGB", (w, h), (245, 245, 245))
    d = ImageDraw.Draw(canvas)
    title = (
        f"PT orden 1 rank {rank:02d} id {row.get('id', '')}  "
        f"lon {float(row['lon']):.6f} lat {float(row['lat']):.6f}"
    )
    scores = (
        f"RRF {float(row.get('score', 0)):.6f} | "
        f"v7 {float(row.get('p_castro_v7', 0)):.3f} "
        f"v7last {float(row.get('p_castro_v7last', 0)):.3f} "
        f"v8 {float(row.get('p_castro_v8', 0)):.3f} "
        f"v12 {float(row.get('p_castro_v12', 0)):.3f} | "
        f"ventana {side_m:.0f} m"
    )
    d.text((margin, 12), title, fill=(0, 0, 0))
    d.text((margin, 38), scores, fill=(40, 40, 40))
    for i, (label, panel) in enumerate(panels):
        x = margin + i * (target + margin)
        p = mark_center(panel.resize((target, target), Image.Resampling.BILINEAR))
        canvas.paste(p, (x, header_h))
        d.text((x + 4, header_h + target + 12), label, fill=(0, 0, 0))
    out_png.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_png)


def make_contact_sheet(chips: list[Path], out: Path, cols: int = 1) -> None:
    if not chips:
        return
    imgs = [Image.open(p).convert("RGB") for p in chips]
    w = max(i.width for i in imgs)
    h = max(i.height for i in imgs)
    rows = math.ceil(len(imgs) / cols)
    canvas = Image.new("RGB", (cols * w, rows * h), (255, 255, 255))
    for i, img in enumerate(imgs):
        x = (i % cols) * w
        y = (i // cols) * h
        canvas.paste(img, (x, y))
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out)


def call_ollama(url: str, model: str, prompt: str, image_path: Path,
                timeout_s: int) -> dict:
    data = base64.b64encode(image_path.read_bytes()).decode("ascii")
    payload = {
        "model": model,
        "prompt": prompt,
        "images": [data],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
    }
    resp = requests.post(url.rstrip("/") + "/api/generate", json=payload,
                         timeout=timeout_s)
    resp.raise_for_status()
    raw = resp.json().get("response", "")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {"visual_class": "parse_error", "raw": raw}
    parsed["_raw_response"] = raw
    return parsed


def write_geojson(rows: list[dict[str, str]], out: Path) -> None:
    features = []
    for rank, r in enumerate(rows, 1):
        props = {k: v for k, v in r.items() if k not in ("lon", "lat")}
        props["rank"] = rank
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [float(r["lon"]), float(r["lat"])],
            },
            "properties": props,
        })
    out.write_text(json.dumps({"type": "FeatureCollection", "features": features},
                              ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--candidatos", type=Path, default=Path("data/sweep_test_portugal_1.tsv"))
    ap.add_argument("--dem-dir", type=Path, default=Path("data/entrada-portugal/1"))
    ap.add_argument("--morpho", type=Path, default=None)
    ap.add_argument("--out-dir", type=Path, default=Path("data/revision-portugal/orden-1"))
    ap.add_argument("--top-n", type=int, default=20)
    ap.add_argument("--crs", default="EPSG:3763")
    ap.add_argument("--side-m", type=float, default=600.0)
    ap.add_argument("--res-m", type=float, default=1.0)
    ap.add_argument("--model", default="qwen2.5vl:7b")
    ap.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    ap.add_argument("--ollama-timeout", type=int, default=240)
    ap.add_argument("--skip-ai", action="store_true")
    args = ap.parse_args()

    rows = read_tsv(args.candidatos)[:args.top_n]
    if not rows:
        raise SystemExit("sin candidatos")
    args.out_dir.mkdir(parents=True, exist_ok=True)

    tifs = sorted(args.dem_dir.rglob("*.tif")) + sorted(args.dem_dir.rglob("*.tiff"))
    if not tifs:
        raise SystemExit(f"no hay GeoTIFF en {args.dem_dir}")
    idx = raster_index(tifs)
    to_crs = Transformer.from_crs("EPSG:4326", args.crs, always_xy=True)

    write_geojson(rows, args.out_dir / "candidatos_top.geojson")
    chips = []
    meta_path = args.out_dir / "candidatos_top_manifest.tsv"
    with meta_path.open("w", newline="", encoding="utf-8") as fh:
        fields = ["rank", "id", "lon", "lat", "score", "chip"]
        w = csv.DictWriter(fh, fieldnames=fields, delimiter="\t")
        w.writeheader()
        for rank, row in enumerate(rows, 1):
            x, y = to_crs.transform(float(row["lon"]), float(row["lat"]))
            dem = read_dem(idx, x, y, args.side_m, args.res_m)
            chip = args.out_dir / "chips" / f"rank-{rank:02d}-id-{row.get('id', 'na')}.png"
            render_chip(row, rank, dem, args.res_m, chip, args.side_m)
            chips.append(chip)
            w.writerow({
                "rank": rank,
                "id": row.get("id", ""),
                "lon": row["lon"],
                "lat": row["lat"],
                "score": row.get("score", ""),
                "chip": str(chip),
            })
            print(f"chip {rank}/{len(rows)} {chip}", flush=True)

    make_contact_sheet(chips, args.out_dir / "contact_sheet_top.png", cols=1)

    prompt = textwrap.dedent("""
        You are helping with archaeological LiDAR triage in northern Portugal.
        The image has three LiDAR-derived panels for the same 600 m window:
        SOMBRA is multidirectional hillshade, LRM is local relief, APERTURA is
        topographic openness. The red cross is the model cell center.

        Decide whether the image visually supports a hillfort/castro-like
        enclosed earthwork. Be conservative. Reject forest tracks, terraces,
        roads, quarries, field boundaries, drainage, and natural slope texture.
        This is not ground truth and must not be treated as evaluation.

        Return strict JSON with keys:
        visual_class: one of "castro_like", "possible", "weak", "reject";
        confidence: number from 0 to 1;
        ring_closure: number from 0 to 1;
        rampart_ditch: number from 0 to 1;
        false_positive_risk: one of "low", "medium", "high";
        likely_false_positive: short string;
        reasons: array of 2-5 short strings in Spanish;
        recommended_action: one of "prioridad_qgis", "mirar_qgis", "baja_prioridad", "descartar_por_ahora".
    """).strip()

    if args.skip_ai:
        print("AI saltada por --skip-ai", flush=True)
        return 0

    jsonl = args.out_dir / "ollama_qwen25vl_review.jsonl"
    tsv = args.out_dir / "ollama_qwen25vl_review.tsv"
    with jsonl.open("w", encoding="utf-8") as jf, tsv.open("w", newline="", encoding="utf-8") as tf:
        fields = [
            "rank", "id", "lon", "lat", "score", "visual_class", "confidence",
            "ring_closure", "rampart_ditch", "false_positive_risk",
            "likely_false_positive", "recommended_action", "reasons", "chip",
        ]
        tw = csv.DictWriter(tf, fieldnames=fields, delimiter="\t")
        tw.writeheader()
        for rank, (row, chip) in enumerate(zip(rows, chips), 1):
            t0 = time.time()
            try:
                verdict = call_ollama(args.ollama_url, args.model, prompt, chip,
                                      args.ollama_timeout)
            except Exception as exc:
                verdict = {
                    "visual_class": "error",
                    "confidence": 0,
                    "ring_closure": 0,
                    "rampart_ditch": 0,
                    "false_positive_risk": "high",
                    "likely_false_positive": type(exc).__name__,
                    "recommended_action": "mirar_qgis",
                    "reasons": [str(exc)[:200]],
                }
            rec = {
                "rank": rank,
                "id": row.get("id", ""),
                "lon": row["lon"],
                "lat": row["lat"],
                "score": row.get("score", ""),
                "chip": str(chip),
                **verdict,
            }
            jf.write(json.dumps(rec, ensure_ascii=False) + "\n")
            tw.writerow({
                "rank": rec["rank"],
                "id": rec["id"],
                "lon": rec["lon"],
                "lat": rec["lat"],
                "score": rec["score"],
                "visual_class": rec.get("visual_class", ""),
                "confidence": rec.get("confidence", ""),
                "ring_closure": rec.get("ring_closure", ""),
                "rampart_ditch": rec.get("rampart_ditch", ""),
                "false_positive_risk": rec.get("false_positive_risk", ""),
                "likely_false_positive": rec.get("likely_false_positive", ""),
                "recommended_action": rec.get("recommended_action", ""),
                "reasons": " | ".join(map(str, rec.get("reasons", []))),
                "chip": rec["chip"],
            })
            tf.flush()
            jf.flush()
            print(
                f"ai {rank}/{len(rows)} {rec.get('visual_class')} "
                f"{rec.get('confidence')} {time.time() - t0:.1f}s",
                flush=True,
            )
    print(f"revision escrita en {args.out_dir}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
