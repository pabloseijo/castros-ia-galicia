#!/usr/bin/env python3
"""Evaluación a nivel de yacimiento, que es como mide el campo, más el VPP.

Hasta ahora este proyecto evaluaba **por celda**: cada viñeta acierta o falla y
de ahí salen recall y precisión. La literatura del dominio no hace eso, y por eso
nuestras cifras no eran comparables con las suyas.

Landauer et al. (2025) declara explícitamente que **los verdaderos negativos no
son significativos** —«el resto del paisaje puede considerarse esencialmente
TN»—, agrupa las detecciones y cuenta un acierto cuando el grupo cae a menos de
`500 m` de un yacimiento conocido. Reporta **F1 `36%`** sobre Inglaterra entera.
Canedo et al. (2025) hace lo mismo y llega a **F1 `66%`** tras minería de
negativos duros.

Este script produce las dos lecturas, porque responden preguntas distintas:

- **F1 con tolerancia de distancia**: sirve para compararnos con la literatura.
- **VPP a la tasa base real** (`1:475`): sirve para saber cuántas celdas hay que
  abrir en QGIS, que es lo que decide si el proyecto es viable para una persona.

Aplica además los cuatro filtros de despliegue de Canedo, en orden:

1. **Umbral de confianza.**
2. **Unión de detecciones solapadas**, para no contar el mismo sitio dos veces.
   Es lo que convierte «celdas» en «yacimientos candidatos».
3. **Área mínima**: descarta grupos de una sola celda, incoherentes con el tamaño
   de un castro. Es el filtro de tamaño que el plan ya había identificado como
   capaz de descartar el `96,7%` de las mámoas.
4. **Filtro de margen**: descarta detecciones pegadas al borde de la cobertura.
   Los objetos cortados por el borde de una tesela «suelen ser indicativos de
   falso positivo».

Uso:
    python3 scripts/detection_eval.py --pred barrido.tsv --truth castros.tsv
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from honest_eval import ppv_from, wilson  # noqa: E402

# Tasa base medida en el barrido propio de Trasancos: 91 castros / 43.215 celdas.
PREVALENCIA_DESPLIEGUE = 91 / 43215


def a_metros(lon, lat, lat0):
    """Proyección local rápida a metros. Suficiente para distancias de km.

    `lat0` es **obligatorio y compartido**: la primera versión lo calculaba como
    la media del array recibido, de modo que las predicciones y la verdad de
    campo acababan proyectadas a sistemas distintos y las distancias entre ambas
    no significaban nada. Se veía en que bajar el umbral perdía aciertos, lo cual
    es imposible. Un evaluador con ese fallo no da error: da cifras plausibles y
    falsas.
    """
    lon = np.asarray(lon, float)
    lat = np.asarray(lat, float)
    x = np.radians(lon) * 6371000.0 * math.cos(math.radians(lat0))
    y = np.radians(lat) * 6371000.0
    return x, y


def agrupar(x, y, enlace_m):
    """Une detecciones a menos de `enlace_m` — single linkage por rejilla.

    Rejilla y no matriz de distancias: un barrido de Galicia son millones de
    celdas y una matriz `n^2` no cabe en ninguna parte.
    """
    n = len(x)
    padre = list(range(n))

    def buscar(i):
        while padre[i] != i:
            padre[i] = padre[padre[i]]
            i = padre[i]
        return i

    def unir(i, j):
        ri, rj = buscar(i), buscar(j)
        if ri != rj:
            padre[rj] = ri

    celda = {}
    for i in range(n):
        celda.setdefault((int(x[i] // enlace_m), int(y[i] // enlace_m)), []).append(i)
    for (cx, cy), idxs in celda.items():
        vecinos = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                vecinos += celda.get((cx + dx, cy + dy), [])
        for i in idxs:
            for j in vecinos:
                if j > i and math.hypot(x[i] - x[j], y[i] - y[j]) <= enlace_m:
                    unir(i, j)
    grupos = {}
    for i in range(n):
        grupos.setdefault(buscar(i), []).append(i)
    return list(grupos.values())


def leer_tsv(path, cols=("lon", "lat")):
    filas = []
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            try:
                filas.append({c: float(r[c]) for c in cols if c in r}
                             | {k: v for k, v in r.items() if k not in cols})
            except (KeyError, TypeError, ValueError):
                continue
    return filas


def evaluar(pred, truth, umbral, enlace_m, min_celdas, margen_m, tol_m, lat0):
    sel = [p for p in pred if p["score"] >= umbral]
    if not sel:
        return {"umbral": umbral, "detecciones": 0, "tp": 0, "fp": 0,
                "fn": len(truth), "precision": 0.0, "recall": 0.0, "f1": 0.0}

    px, py = a_metros([p["lon"] for p in sel], [p["lat"] for p in sel], lat0)
    grupos = agrupar(px, py, enlace_m)

    # 3. area minima: un grupo de una sola celda no es un castro
    grupos = [g for g in grupos if len(g) >= min_celdas]

    centros = [(float(np.mean(px[g])), float(np.mean(py[g])), len(g)) for g in grupos]

    # 4. filtro de margen: fuera lo pegado al borde de la cobertura
    if margen_m > 0 and centros:
        ax, ay = a_metros([p["lon"] for p in pred], [p["lat"] for p in pred], lat0)
        x0, x1, y0, y1 = ax.min(), ax.max(), ay.min(), ay.max()
        centros = [c for c in centros
                   if x0 + margen_m <= c[0] <= x1 - margen_m
                   and y0 + margen_m <= c[1] <= y1 - margen_m]

    tx, ty = a_metros([t["lon"] for t in truth], [t["lat"] for t in truth], lat0)
    encontrado = [False] * len(truth)
    tp = 0
    for cx, cy, _ in centros:
        d = np.hypot(tx - cx, ty - cy)
        j = int(np.argmin(d)) if len(d) else -1
        if j >= 0 and d[j] <= tol_m:
            tp += 1
            encontrado[j] = True
    fp = len(centros) - tp
    fn = sum(1 for e in encontrado if not e)
    prec = tp / len(centros) if centros else 0.0
    rec = sum(encontrado) / len(truth) if truth else float("nan")
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
    return {"umbral": umbral, "detecciones": len(centros), "tp": tp, "fp": fp,
            "fn": fn, "precision": prec, "recall": rec, "f1": f1,
            "recall_ci95": list(wilson(sum(encontrado), len(truth))) if truth else [0, 1]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pred", type=Path, required=True,
                    help="TSV del barrido con columnas lon, lat, score")
    ap.add_argument("--truth", type=Path, required=True,
                    help="TSV de yacimientos conocidos con lon, lat")
    ap.add_argument("--tolerancia-m", type=float, default=500.0,
                    help="distancia de acierto; 500 m es lo que usa Landauer")
    ap.add_argument("--enlace-m", type=float, default=256.0,
                    help="distancia para unir detecciones vecinas")
    ap.add_argument("--min-celdas", type=int, default=2)
    ap.add_argument("--margen-m", type=float, default=0.0)
    ap.add_argument("--umbrales", type=float, nargs="+",
                    default=[0.5, 0.7, 0.8, 0.9, 0.95])
    ap.add_argument("--out-json", type=Path)
    args = ap.parse_args()

    pred = [p for p in leer_tsv(args.pred, ("lon", "lat", "score"))
            if "score" in p]
    for p in pred:
        p["score"] = float(p["score"])
    truth = leer_tsv(args.truth)
    print(f"predicciones: {len(pred)} | yacimientos conocidos: {len(truth)}",
          flush=True)
    if not pred or not truth:
        raise SystemExit("faltan predicciones o verdad de campo")

    # Una sola latitud de referencia para todo, o las distancias no comparan.
    lat0 = float(np.mean([t["lat"] for t in truth]))
    filas = []
    print(f"\n{'umbral':>7} {'detec':>7} {'TP':>5} {'FP':>6} {'FN':>5} "
          f"{'prec':>6} {'recall':>7} {'F1':>7} {'VPP@1:475':>10}")
    for u in args.umbrales:
        r = evaluar(pred, truth, u, args.enlace_m, args.min_celdas,
                    args.margen_m, args.tolerancia_m, lat0)
        # El VPP se recalcula a la prevalencia real, que es lo unico trasladable.
        espec = 1 - (r["fp"] / max(len(pred), 1))
        r["vpp_tasa_real"] = ppv_from(r["recall"], espec, PREVALENCIA_DESPLIEGUE) \
            if r["recall"] == r["recall"] else float("nan")
        filas.append(r)
        print(f"{u:7.2f} {r['detecciones']:7d} {r['tp']:5d} {r['fp']:6d} "
              f"{r['fn']:5d} {r['precision']:6.3f} {r['recall']:7.3f} "
              f"{r['f1']:7.3f} {r['vpp_tasa_real']:10.4f}")

    mejor = max(filas, key=lambda r: r["f1"])
    print(f"\nmejor F1: {mejor['f1']:.3f} en umbral {mejor['umbral']:.2f} "
          f"(recall {mejor['recall']:.3f} "
          f"IC95% [{mejor['recall_ci95'][0]:.2f}, {mejor['recall_ci95'][1]:.2f}])")
    print("referencias del campo: Landauer 0.36 (Inglaterra entera), "
          "Canedo 0.66 (tras minería de negativos duros)")
    if mejor["f1"] >= 0.66:
        print("  -> por encima de Canedo")
    elif mejor["f1"] >= 0.36:
        print("  -> por encima de Landauer, por debajo de Canedo")
    else:
        print("  -> por debajo de ambas referencias")

    if args.out_json:
        args.out_json.write_text(json.dumps(
            {"config": vars(args), "resultados": filas}, indent=2, default=str),
            encoding="utf-8")
        print(f"guardado: {args.out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
