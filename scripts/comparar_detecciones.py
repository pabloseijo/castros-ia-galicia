#!/usr/bin/env python3
"""Que castros gana y cuales pierde un modelo nuevo respecto a v7, uno a uno.

Un `F1` mejor puede esconder un intercambio malo: encontrar cinco castros nuevos
y perder cuatro de los que ya salian sube la cifra y **empeora el trabajo**, si
los que se pierden son los faciles y los que se ganan son dudosos.

Por eso el plan exige, antes de dar por buena cualquier version que bata a v7,
comprobar que **no pierde ninguno de los castros que v7 si detectaba**.

Emparejamiento: un castro cuenta como encontrado si hay alguna prediccion por
encima del umbral a menos de `tol_m`. Es el mismo criterio de distancia que usa
`detection_eval.py`, pero **esto no sustituye a `detection_eval.py`**: las cifras
oficiales salen de alli, con su enlace, su `min-celdas` y su margen. Esto sirve
para lo que aquella no dice, que es **quien** cambia.
"""
from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path


def leer(p: Path, cols=("lon", "lat")):
    with p.open(encoding="utf-8") as fh:
        return [r for r in csv.DictReader(fh, delimiter="\t") if all(r.get(c) for c in cols)]


def a_metros(lon, lat, lat0):
    return (lon * 111_320.0 * math.cos(math.radians(lat0)), lat * 110_540.0)


def encontrados(pred, truth, umbral, tol_m, lat0):
    """Devuelve el conjunto de indices de `truth` que el barrido si detecta."""
    pts = [a_metros(float(r["lon"]), float(r["lat"]), lat0)
           for r in pred if float(r.get("score", 0)) >= umbral]
    out = set()
    for i, t in enumerate(truth):
        tx, ty = a_metros(float(t["lon"]), float(t["lat"]), lat0)
        for px, py in pts:
            if (px - tx) ** 2 + (py - ty) ** 2 <= tol_m * tol_m:
                out.add(i)
                break
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--nuevo", required=True, help="version candidata, p.ej. v12")
    ap.add_argument("--referencia", default="v7")
    ap.add_argument("--bloques", default="lugo,coruna,ourense,pontevedra")
    ap.add_argument("--umbral", type=float, default=0.70)
    ap.add_argument("--tol-m", type=float, default=500.0)
    args = ap.parse_args()

    tot_gana = tot_pierde = tot_ambos = 0
    for b in args.bloques.split(","):
        fn = Path(f"data/sweep_val_{b}_{args.nuevo}.tsv")
        fr = Path(f"data/sweep_val_{b}_{args.referencia}.tsv")
        ft = Path(f"data/{b}_fus_truth_limpia.tsv")
        if not (fn.exists() and fr.exists() and ft.exists()):
            print(f"  {b}: falta {[str(p) for p in (fn, fr, ft) if not p.exists()]}")
            continue
        truth = leer(ft)
        lat0 = sum(float(t["lat"]) for t in truth) / len(truth)
        en = encontrados(leer(fn), truth, args.umbral, args.tol_m, lat0)
        er = encontrados(leer(fr), truth, args.umbral, args.tol_m, lat0)

        gana, pierde, ambos = en - er, er - en, en & er
        tot_gana += len(gana); tot_pierde += len(pierde); tot_ambos += len(ambos)
        print(f"\n  {b}: {len(truth)} castros catalogados")
        print(f"    los dos:            {len(ambos)}")
        print(f"    solo {args.nuevo:<14} {len(gana)}")
        print(f"    solo {args.referencia:<14} {len(pierde)}   <-- los que se PIERDEN")
        for i in sorted(pierde)[:8]:
            print(f"        {(truth[i].get('name') or '?')[:48]}")

    print(f"\n  === {args.nuevo} contra {args.referencia}, los cuatro bloques ===")
    print(f"    los dos: {tot_ambos} | gana {tot_gana} | PIERDE {tot_pierde}")
    if tot_pierde == 0:
        print("    OK: no pierde ninguno de los que la referencia si detectaba")
    else:
        print(f"    *** pierde {tot_pierde}: hay que mirarlos antes de dar por buena "
              f"la version ***")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
