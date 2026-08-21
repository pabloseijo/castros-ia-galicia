#!/usr/bin/env python3
"""Arma el conjunto con el que se calibra la cobertura angular del anillo.

`morfologia_candidatos.py` emite `cobertura_angular` desde el `2026-08-08` con
una nota en su propia cabecera: **«sin calibrar todavía — se emite como columna
para mirarla contra los veredictos visuales, no como criterio»**. Nunca se
miró.

Es el hueco que importa. La literatura de detección de castros nombra la
**pista forestal** como falso positivo dominante, y la separa del recinto por
una sola propiedad: **la pista no cierra**. Si el descriptor mide eso, es un
filtro de postprocesado contra el confusor que limita este sistema; y si no lo
mide, hay que dejarlo escrito y dejar de mirar ahí.

Este script no mide: **construye el conjunto de prueba**. Agrupa las
detecciones de un detector en el punto de operación, las etiqueta contra la
verdad de campo, y emite el TSV que `morfologia_candidatos.py` come.

La distinción que hay que respetar: se etiqueta **el grupo**, no la celda. Un
grupo es acierto si **alguna** de sus celdas cae dentro de la tolerancia de un
castro catalogado — el mismo criterio que usa `detection_eval.py`, y por la
misma razón: una detección desplazada media celda sigue siendo la misma
detección.

Uso:
    python3 scripts/conjunto_calibracion_morfologia.py \\
        --detector v7 --out data/calib_morfo.tsv
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path

import numpy as np

BLOQUES = ["coruna", "lugo", "ourense", "pontevedra"]

# El punto de operación congelado, medido en `el-punto-de-operacion-depende-del-presupuesto`.
UMBRAL = 0.60
ENLACE = 512.0
MIN_CELDAS = 1
TOL = 500.0


def agrupar(px: np.ndarray, py: np.ndarray, enlace: float) -> list[list[int]]:
    """Enlace simple por distancia, igual que el evaluador."""
    n = len(px)
    visto = np.zeros(n, bool)
    grupos = []
    for i in range(n):
        if visto[i]:
            continue
        pila = [i]
        visto[i] = True
        g = []
        while pila:
            j = pila.pop()
            g.append(j)
            d = np.hypot(px - px[j], py - py[j])
            nuevos = np.where((d <= enlace) & (~visto))[0]
            visto[nuevos] = True
            pila.extend(nuevos.tolist())
        grupos.append(g)
    return grupos


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--detector", default="v7",
                    help="sufijo del barrido: v7, ens_max, ...")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--umbral", type=float, default=UMBRAL)
    args = ap.parse_args()

    filas_out = []
    resumen = []
    for bloque in BLOQUES:
        sw = Path(f"data/sweep_val_{bloque}_{args.detector}.tsv")
        vt = Path(f"data/{bloque}_truth_limpia.tsv")
        if not sw.exists() or not vt.exists():
            print("  falta %s o %s — bloque omitido" % (sw.name, vt.name))
            continue

        det = [r for r in csv.DictReader(open(sw, encoding="utf-8"),
                                         delimiter="\t")
               if float(r["p_castro"]) >= args.umbral]
        if not det:
            print("  %s: 0 detecciones sobre el umbral" % bloque)
            continue

        lon = np.array([float(r["lon"]) for r in det])
        lat = np.array([float(r["lat"]) for r in det])
        sco = np.array([float(r["p_castro"]) for r in det])

        # UN solo factor de longitud por bloque. Usar el de cada punto
        # desplazó los centroides 3 km en su día y produjo 179 candidatos
        # fantasma; es un error ya cometido y no se repite.
        lat0 = float(lat.mean())
        k = 111_320.0 * math.cos(math.radians(lat0))
        px = lon * k
        py = lat * 110_540.0

        verdad = list(csv.DictReader(open(vt, encoding="utf-8"),
                                     delimiter="\t"))
        tx = np.array([float(r["lon"]) for r in verdad]) * k
        ty = np.array([float(r["lat"]) for r in verdad]) * 110_540.0

        grupos = [g for g in agrupar(px, py, ENLACE) if len(g) >= MIN_CELDAS]
        n_tp = n_fp = 0
        for g in grupos:
            # el punto que representa al grupo es su celda de máxima puntuación
            i = max(g, key=lambda j: sco[j])
            # pero la etiqueta la decide CUALQUIER celda del grupo, como el
            # evaluador: un grupo que toca un castro es un acierto.
            toca = False
            if len(tx):
                for j in g:
                    if float(np.hypot(tx - px[j], ty - py[j]).min()) <= TOL:
                        toca = True
                        break
            etiqueta = "castro" if toca else "falso"
            n_tp += toca
            n_fp += (not toca)
            filas_out.append({
                "bloque": bloque,
                "n": "%s_%d" % (bloque, len(filas_out)),
                "lon": "%.6f" % lon[i],
                "lat": "%.6f" % lat[i],
                "score": "%.4f" % sco[i],
                "celdas": str(len(g)),
                "etiqueta": etiqueta,
            })
        resumen.append((bloque, len(grupos), n_tp, n_fp))
        print("  %-11s %4d grupos  %3d aciertos  %4d falsos"
              % (bloque, len(grupos), n_tp, n_fp), flush=True)

    if not filas_out:
        print("nada que escribir", file=sys.stderr)
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, delimiter="\t",
                           fieldnames=["bloque", "n", "lon", "lat", "score",
                                       "celdas", "etiqueta"])
        w.writeheader()
        w.writerows(filas_out)

    tot_tp = sum(r[2] for r in resumen)
    tot_fp = sum(r[3] for r in resumen)
    print("\nTOTAL  %d grupos: %d aciertos, %d falsos"
          % (len(filas_out), tot_tp, tot_fp))
    print("escrito: %s" % args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
