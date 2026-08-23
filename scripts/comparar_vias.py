#!/usr/bin/env python3
"""Compara la via de la NUBE (LAZ diezmada a 2 pt/m2) con la via del RASTER
(MDT-50cm de la DGT remuestreado a 1 m) sobre la misma peticion.

**El criterio no es la correlacion de canales, es la cola.** Lo que este
proyecto entrega es una lista de fichas que alguien va a mirar; si las dos vias
puntuan parecido pero ordenan distinto, el raster no sirve aunque la
correlacion salga alta. Por eso se mide el solapamiento del top-K ademas de la
correlacion.

Y se compara SOLO sobre celdas comunes: dos barridos con distinta cobertura no
son comparables, que es el error que invalido seis cifras del proyecto.
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path


def carga(p: Path) -> dict[tuple[float, float], dict]:
    d = {}
    with open(p, encoding="utf-8") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            try:
                k = (round(float(r["lon"]), 5), round(float(r["lat"]), 5))
                d[k] = {"score": float(r["score"]),
                        "p_castro": float(r.get("p_castro", r["score"]))}
            except (KeyError, ValueError):
                continue
    return d


def pearson(x, y):
    n = len(x)
    if n < 3:
        return float("nan")
    mx, my = sum(x) / n, sum(y) / n
    sx = math.sqrt(sum((a - mx) ** 2 for a in x))
    sy = math.sqrt(sum((b - my) ** 2 for b in y))
    if sx == 0 or sy == 0:
        return float("nan")
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / (sx * sy)


def rangos(v):
    orden = sorted(range(len(v)), key=lambda i: v[i])
    r = [0.0] * len(v)
    i = 0
    while i < len(orden):
        j = i
        while j + 1 < len(orden) and v[orden[j + 1]] == v[orden[i]]:
            j += 1
        medio = (i + j) / 2.0 + 1
        for k in range(i, j + 1):
            r[orden[k]] = medio
        i = j + 1
    return r


def spearman(x, y):
    return pearson(rangos(x), rangos(y))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--nube", type=Path, required=True)
    ap.add_argument("--raster", type=Path, nargs="+", required=True)
    ap.add_argument("--topk", type=int, nargs="+", default=[20, 50, 100, 200])
    a = ap.parse_args()

    nube = carga(a.nube)
    print(f"NUBE   {a.nube.name}: {len(nube)} celdas")

    for rp in a.raster:
        ras = carga(rp)
        comunes = sorted(set(nube) & set(ras))
        solo_n = len(nube) - len(comunes)
        solo_r = len(ras) - len(comunes)
        print(f"\n{'='*66}\nRASTER {rp.name}: {len(ras)} celdas")
        print(f"  comunes: {len(comunes)}  | solo en nube: {solo_n} | solo en raster: {solo_r}")
        if len(comunes) < 10:
            print("  *** muy pocas celdas comunes: la rejilla no coincide ***")
            continue

        xn = [nube[k]["p_castro"] for k in comunes]
        xr = [ras[k]["p_castro"] for k in comunes]
        difs = [abs(p - q) for p, q in zip(xn, xr)]
        difs_ord = sorted(difs)

        print(f"  Pearson  p_castro : {pearson(xn, xr):.4f}")
        print(f"  Spearman p_castro : {spearman(xn, xr):.4f}")
        print(f"  |dif| media       : {sum(difs)/len(difs):.4f}")
        print(f"  |dif| mediana     : {difs_ord[len(difs_ord)//2]:.4f}")
        print(f"  |dif| p95         : {difs_ord[int(0.95*len(difs_ord))]:.4f}")
        print(f"  |dif| maxima      : {max(difs):.4f}")

        print("  --- la cola, que es el entregable ---")
        for k in a.topk:
            if k > len(comunes):
                continue
            tn = {c for c, _ in sorted(((c, nube[c]["p_castro"]) for c in comunes),
                                       key=lambda t: -t[1])[:k]}
            tr = {c for c, _ in sorted(((c, ras[c]["p_castro"]) for c in comunes),
                                       key=lambda t: -t[1])[:k]}
            inter = len(tn & tr)
            print(f"    top-{k:<4} coinciden {inter:4}/{k}  ({100*inter/k:5.1f}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
