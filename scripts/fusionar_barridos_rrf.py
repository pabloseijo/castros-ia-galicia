#!/usr/bin/env python3
"""Fusiona barridos de varios modelos con Reciprocal Rank Fusion.

Entrada: varios TSV de `sweep_grid_lidar.py` sobre la misma rejilla.
Salida: un TSV con `score` RRF y las puntuaciones originales como columnas
extra. No evalúa contra verdad de campo.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path


def leer(path: Path) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            if row.get("id") and row.get("p_castro"):
                out[row["id"]] = row
    return out


def escribir(path: Path, rows: list[dict[str, object]], model_names: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["id", "lon", "lat", "score", "p_castro"] + [
        f"p_castro_{m}" for m in model_names
    ]
    with path.open("w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=fields, delimiter="\t")
        wr.writeheader()
        for row in rows:
            wr.writerow(row)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred", nargs="+", type=Path, required=True)
    ap.add_argument("--names", nargs="+", required=True)
    ap.add_argument("--out-full", type=Path, required=True)
    ap.add_argument("--out-top", type=Path)
    ap.add_argument("--top-k", type=int, default=100)
    ap.add_argument("--rrf-k", type=float, default=60.0)
    args = ap.parse_args()

    if len(args.pred) != len(args.names):
        raise SystemExit("--pred y --names deben tener la misma longitud")

    preds = [leer(p) for p in args.pred]
    common = sorted(set.intersection(*(set(p) for p in preds)))
    if not common:
        raise SystemExit("no hay celdas comunes entre barridos")

    ranks: list[dict[str, int]] = []
    for pred in preds:
        ordered = sorted(common, key=lambda cid: -float(pred[cid]["p_castro"]))
        ranks.append({cid: rank for rank, cid in enumerate(ordered)})

    fused: list[dict[str, object]] = []
    for cid in common:
        base = preds[0][cid]
        score = sum(1.0 / (args.rrf_k + r[cid]) for r in ranks)
        row: dict[str, object] = {
            "id": cid,
            "lon": base["lon"],
            "lat": base["lat"],
            "score": f"{score:.12f}",
            "p_castro": f"{score:.12f}",
        }
        for name, pred in zip(args.names, preds):
            row[f"p_castro_{name}"] = pred[cid]["p_castro"]
        fused.append(row)

    fused.sort(key=lambda r: -float(r["score"]))
    escribir(args.out_full, fused, args.names)
    print(f"full: {args.out_full} ({len(fused)} celdas)", flush=True)

    if args.out_top:
        escribir(args.out_top, fused[: args.top_k], args.names)
        print(f"top{args.top_k}: {args.out_top}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
