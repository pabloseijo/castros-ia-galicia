#!/usr/bin/env python3
"""Evaluación por agrupación: reconstruir un conjunto de prueba grande a partir de muchos pequeños.

Implementa el procedimiento de Collart et al. (2021), descrito y recomendado en
Collart, F. y Guisan, A. (2023), *Small to train, small to test: Dealing with low
sample size in model evaluation*, **Ecological Informatics** `75`, `102106`,
DOI `10.1016/j.ecoinf.2023.102106`.

## Por qué hace falta aquí

El holdout de O Val tiene `5` mámoas y `7` castros. Con esos tamaños, un recall
medido no distingue `0.5` de `0.9`, y una clase puede dar `0` por azar. El
`2026-08-05` la mámoa dio `0` de `5` y persiguiendo la causa se refutaron cuatro
hipótesis —geografía, ruido de etiqueta, regionalidad y fuga espacial— sin llegar
a conclusión, porque **el conjunto no daba para concluir**.

## La idea

En vez de un único reparto, se hacen `N` particiones espaciales distintas. Cada
una deja fuera un conjunto pequeño, pero **todas las predicciones dejadas fuera
se juntan** en un solo conjunto del tamaño del original. Si un punto cae en
varios conjuntos de prueba, se promedian sus probabilidades.

El resultado es un conjunto de evaluación con la misma cobertura que el dataset
completo, pero donde **cada predicción se hizo sobre un punto que su modelo no
había visto**. Collart y Guisan lo dan como suficiente para modelar con un mínimo
de `10-15` ocurrencias.

## Lo que NO arregla

No inventa datos. Si una clase tiene `426` ejemplos en total, la agrupación
permite evaluarlos todos honestamente, no tener más. Y el reparto sigue siendo
por bloque espacial, así que la autocorrelación se controla igual que antes.

Uso:
    python3 scripts/pooling_eval.py --vig-dir data/galicia-vignettes-v3 \\
        --out-dir data/pooling-v3 --folds 5 --epochs 8
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from honest_eval import wilson  # noqa: E402
from train_unet_multiclass import CLASS_NAMES, label_of  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vig-dir", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--epochs", type=int, default=8,
                    help="8 basta: la seleccion se aplana desde la epoca 5")
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--head", default="cls")
    ap.add_argument("--seed", type=int, default=20260805)
    args = ap.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    filas = list(csv.DictReader(open(args.vig_dir / "index.tsv", encoding="utf-8"),
                                delimiter="\t"))
    # O Val nunca entra en ningun reparto: es el holdout historico intocable.
    pool = [r for r in filas if r["split"] != "test_o_val"]
    bloques = sorted({r["block"] for r in pool})
    rng = np.random.default_rng(args.seed)
    rng.shuffle(bloques)
    reparto = {b: i % args.folds for i, b in enumerate(bloques)}
    print(f"{len(pool)} viñetas | {len(bloques)} bloques | {args.folds} particiones",
          flush=True)

    acum = defaultdict(list)   # sid -> lista de vectores de probabilidad
    campos = list(filas[0].keys())
    for k in range(args.folds):
        idx_k = args.out_dir / f"index_fold{k}.tsv"
        with open(idx_k, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=campos, delimiter="\t")
            w.writeheader()
            for r in pool:
                rr = dict(r)
                rr["split"] = "val" if reparto[r["block"]] == k else "train"
                w.writerow(rr)
        # el entrenador espera index.tsv dentro del directorio de viñetas
        enlace = args.out_dir / f"vig_fold{k}"
        enlace.mkdir(exist_ok=True)
        for nombre, destino in (("arrays", args.vig_dir / "arrays"),):
            d = enlace / nombre
            if not d.exists():
                d.symlink_to(destino.resolve())
        (enlace / "index.tsv").write_text(idx_k.read_text(encoding="utf-8"),
                                          encoding="utf-8")

        print(f"\n=== partición {k+1}/{args.folds} ===", flush=True)
        cmd = [sys.executable, str(Path(__file__).parent / "train_unet_multiclass.py"),
               "--vig-dir", str(enlace), "--out-dir", str(args.out_dir / f"fold{k}"),
               "--head", args.head, "--epochs", str(args.epochs),
               "--batch", str(args.batch), "--workers", str(args.workers),
               "--seed", str(args.seed + k)]
        subprocess.run(cmd, check=True)

        sc = args.out_dir / f"fold{k}" / "scores_val.tsv"
        if not sc.exists():
            print(f"  sin puntuaciones en la partición {k}", flush=True)
            continue
        for r in csv.DictReader(open(sc, encoding="utf-8"), delimiter="\t"):
            acum[r["sid"]].append([float(r["p_fondo"]), float(r["p_castro"]),
                                   float(r["p_mamoa"])])

    # --- agrupacion: promediar y evaluar una sola vez ---
    por_sid = {r["sid"]: r for r in filas}
    y, p = [], []
    for sid, vs in acum.items():
        y.append(label_of(por_sid[sid]))
        p.append(np.mean(vs, axis=0))
    y = np.asarray(y)
    pred = np.argmax(np.asarray(p), axis=1)
    print(f"\n=== CONJUNTO AGRUPADO: {len(y)} viñetas "
          f"(de {len(pool)} disponibles) ===")
    veces = [len(v) for v in acum.values()]
    print(f"  cada viñeta evaluada {np.mean(veces):.2f} veces de media")

    salida = {"n": int(len(y)), "folds": args.folds, "por_clase": {}}
    for c, nm in CLASS_NAMES.items():
        n = int((y == c).sum())
        if not n:
            continue
        tp = int(((pred == c) & (y == c)).sum())
        fp = int(((pred == c) & (y != c)).sum())
        rec, prec = tp / n, tp / (tp + fp) if tp + fp else 0.0
        lo, hi = wilson(tp, n)
        marca = "  <-- COLAPSADA" if rec == 0 else ""
        print(f"  {nm:8s} n={n:5d}  recall {rec:.3f} [{lo:.2f},{hi:.2f}]  "
              f"precision {prec:.3f}{marca}")
        salida["por_clase"][nm] = {"n": n, "recall": rec, "recall_ci95": [lo, hi],
                                   "precision": prec, "collapsed": rec == 0}
    (args.out_dir / "pooling_metrics.json").write_text(
        json.dumps(salida, indent=2, default=float), encoding="utf-8")
    print(f"\nguardado: {args.out_dir/'pooling_metrics.json'}")
    print("Cada predicción se hizo sobre un punto que su propio modelo no vio.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
