#!/usr/bin/env python3
"""La metrica del entregable: ¿cuantas fichas hay que mirar por castro encontrado?

Todo el proyecto se mide con `F1` a umbral `0.70`, que es una cifra de paper. Pero
lo que se entrega **no es una prediccion, es una cola de revision**: un arqueologo
mira fichas por orden de puntuacion y decide. Para el, la pregunta util es otra:

    «si miro las N primeras, ¿cuantos castros encuentro?»

`F1` no responde eso. Esto si, y ademas dice **donde esta el codo**: el punto a
partir del cual mirar mas fichas ya casi no aporta hallazgos, que es donde debe
cortarse la cola que se entrega.

Ojo con la interpretacion: aqui «acierto» es *reencontrar un castro ya catalogado*,
que es lo unico verificable sin trabajo de campo. Los verdaderos hallazgos —sitios
no catalogados— estan **entre los supuestos falsos positivos**, y por eso el coste
por hallazgo que sale de aqui es una **cota superior pesimista**: cuenta como
error lo que podria ser el objetivo del proyecto.
"""
from __future__ import annotations

import csv
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "scripts")
from detection_eval import a_metros, agrupar, leer_tsv   # noqa: E402

BLOQUES = ["lugo", "coruna", "ourense", "pontevedra"]
TOL = 500.0
ENLACE = 512.0


def cola_de(modelo, bloque, suelo=0.30):
    pred = Path(f"data/sweep_val_{bloque}_{modelo}.tsv")
    truth = Path(f"data/{bloque}_fus_truth_limpia.tsv")
    if not pred.exists() or not truth.exists():
        return None
    ps = [p for p in leer_tsv(pred, ("lon", "lat", "score")) if "score" in p]
    if len(ps) < 10:
        return None
    for p in ps:
        p["score"] = float(p["score"])

    # **Suelo obligatorio antes de agrupar.** El agrupado es de enlace simple, y
    # con las `8.000` celdas de un bloque sin filtrar, cada una a `256 m` de la
    # siguiente por el solape de la rejilla, TODO se encadena en un unico grupo:
    # la primera version de esto reporto «cola de 1 ficha» en los cuatro bloques.
    # El suelo no es un umbral de decision —la curva que interesa esta muy por
    # encima—, solo evita que el ruido de fondo suelde la malla entera.
    ps = [p for p in ps if p["score"] >= suelo]
    if len(ps) < 10:
        return None
    ts = leer_tsv(truth)
    lat0 = float(np.mean([t["lat"] for t in ts]))
    px, py = a_metros([p["lon"] for p in ps], [p["lat"] for p in ps], lat0)
    tx, ty = a_metros([t["lon"] for t in ts], [t["lat"] for t in ts], lat0)

    # agrupar en sitios y quedarse con la puntuacion maxima de cada uno
    sitios = []
    for g in agrupar(px, py, ENLACE):
        cx, cy = float(np.mean(px[g])), float(np.mean(py[g]))
        sc = max(ps[i]["score"] for i in g)
        d = np.hypot(tx - cx, ty - cy)
        sitios.append((sc, int(d.argmin()) if d.min() <= TOL else None))
    sitios.sort(key=lambda s: -s[0])
    return sitios, len(ts)


def main() -> int:
    modelo = sys.argv[1] if len(sys.argv) > 1 else "v7"
    suelo = float(sys.argv[2]) if len(sys.argv) > 2 else 0.30
    print(f"modelo: {modelo} | suelo de agrupado {suelo}   («acierto» = reencontrar un castro catalogado)\n")
    tot_sitios, tot_hall, tot_conocidos = [], 0, 0
    for b in BLOQUES:
        r = cola_de(modelo, b, suelo)
        if r is None:
            print(f"{b}: sin barrido"); continue
        sitios, n_truth = r
        vistos, hall, curva = set(), 0, []
        for i, (sc, t) in enumerate(sitios, 1):
            if t is not None and t not in vistos:
                vistos.add(t); hall += 1
            curva.append(hall)
        tot_sitios.append((b, sitios, curva, n_truth))
        tot_hall += hall; tot_conocidos += n_truth
        print(f"{b:<12} cola de {len(sitios):>5} fichas | {n_truth} castros conocidos")
        for N in (25, 50, 100, 200, 500):
            if N <= len(curva):
                h = curva[N-1]
                coste = N / h if h else float("inf")
                print(f"   primeras {N:>4}: {h:>3} castros  "
                      f"({h/n_truth:>5.0%} del bloque) | {coste:>5.1f} fichas por castro")

    print(f"\n{'='*64}\nCONJUNTO: {tot_hall} castros reencontrados de {tot_conocidos}\n{'='*64}")
    # el codo: donde el rendimiento marginal cae por debajo de 1 castro cada 50 fichas
    print("\ndonde esta el codo de cada bloque (rendimiento marginal < 1 por 50 fichas):")
    for b, sitios, curva, n_truth in tot_sitios:
        codo = None
        for i in range(50, len(curva)):
            if curva[i] - curva[i-50] < 1:
                codo = i; break
        if codo:
            print(f"  {b:<12} corta en ~{codo:>4} fichas -> {curva[codo]:>3} castros "
                  f"({curva[codo]/n_truth:.0%}); las {len(curva)-codo} restantes casi no aportan")
        else:
            print(f"  {b:<12} sin codo claro en {len(curva)} fichas")
    print("\nCota superior pesimista: los hallazgos de verdad —sitios NO catalogados—")
    print("cuentan aqui como falsos positivos. El coste real por hallazgo es menor.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
