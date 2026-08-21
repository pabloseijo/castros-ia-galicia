#!/usr/bin/env python3
"""Aumento en test: promediar las ventanas que ven el mismo sitio.

El barrido puntua cada celda **una vez**, con el sitio en una posicion arbitraria
dentro del recuadro de `512 m`. Pero con paso de `256 m` cada punto del terreno
cae dentro de **varias ventanas**, cada una viendolo desde un desplazamiento
distinto — y solo se usa una de esas puntuaciones.

Promediarlas es aumento en test clasico, y aqui no cuesta reentrenar ni volver a
barrer: las puntuaciones ya estan. Se prueba con tres agregaciones:

- **media** de las ventanas vecinas — el aumento en test de manual;
- **media ponderada** por cercania al centro, que pesa mas la vista mejor
  centrada;
- **maximo**, que es lo que ya hace el sistema de facto y sirve de control.

Se evalua con `detection_eval.py` sobre los cuatro bloques y se compara con el
`F1` publicado. **No puede empeorar el sistema**: si no sube, no se aplica.
"""
from __future__ import annotations

import csv
import math
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

BLOQUES = ["lugo", "coruna", "ourense", "pontevedra"]
PASO = 256.0
TMP = Path("data/tmp-tta")
TMP.mkdir(exist_ok=True)


def leer(p):
    with Path(p).open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def suavizar(filas, modo, radio=PASO * 1.05):
    """Reagrega la puntuacion de cada celda con la de las ventanas que la ven."""
    lat0 = sum(float(r["lat"]) for r in filas) / len(filas)
    k = 111_320.0 * math.cos(math.radians(lat0))
    X = np.array([float(r["lon"]) * k for r in filas])
    Y = np.array([float(r["lat"]) * 110_540.0 for r in filas])
    S = np.array([float(r["score"]) for r in filas])

    # rejilla de cubos del tamano del paso: evita el O(n^2) de comparar todas
    # las celdas con todas, que en un bloque son 8.500 y en Galicia serian millones
    cx = np.floor(X / PASO).astype(np.int64)
    cy = np.floor(Y / PASO).astype(np.int64)
    cubos = {}
    for i, (a, b) in enumerate(zip(cx, cy)):
        cubos.setdefault((a, b), []).append(i)

    nueva = np.empty_like(S)
    for i in range(len(S)):
        vecinos = []
        for da in (-1, 0, 1):
            for db in (-1, 0, 1):
                vecinos += cubos.get((cx[i] + da, cy[i] + db), [])
        v = np.array(vecinos)
        d = np.hypot(X[v] - X[i], Y[v] - Y[i])
        m = d <= radio
        v, d = v[m], d[m]
        if modo == "media":
            nueva[i] = S[v].mean()
        elif modo == "ponderada":
            w = 1.0 - d / (radio + 1e-9)
            nueva[i] = float((S[v] * w).sum() / w.sum())
        else:
            nueva[i] = S[v].max()
    return nueva


UMBRALES = [0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80]


def evaluar(ruta, bloque):
    """El mejor F1 sobre un barrido de umbrales, no a uno fijo.

    **Corrige el primer intento**, que evaluaba todo a `0,70`: promediar baja
    todas las puntuaciones, asi que un umbral fijo penaliza a las variantes por
    construccion — la media salia `nan` porque casi nada superaba el corte. Un
    cambio que reescala las puntuaciones **tiene que compararse a su propio
    umbral optimo**, o se esta midiendo el reescalado y no el metodo.
    """
    mejor = float("nan")
    for u in UMBRALES:
        r = subprocess.run(
            [".venv-gpu/bin/python", "scripts/detection_eval.py", "--pred", str(ruta),
             "--truth", f"data/{bloque}_fus_truth_limpia.tsv",
             "--mascara", f"data/{bloque}_fus_mascara_train.tsv", "--umbral", str(u)],
            capture_output=True, text=True, timeout=600).stdout
        m = re.findall(r"mejor F1: ([0-9.]+)", r)
        if m:
            v = float(m[-1])
            if not (mejor == mejor) or v > mejor:
                mejor = v
    return mejor


MODOS = ["original", "media", "ponderada", "maximo"]
print("  el mejor F1 de cada modo sobre 11 umbrales (0,30 a 0,80)\n")
print(f"  {'modo':<12}" + "".join(f"{b[:10]:>11}" for b in BLOQUES) + f"{'media':>10}")
print("  " + "-" * (12 + 11 * 4 + 10))
for modo in MODOS:
    f1s = []
    for b in BLOQUES:
        orig = Path(f"data/sweep_val_{b}_v7.tsv")
        filas = leer(orig)
        if modo == "original":
            ruta = orig
        else:
            nueva = suavizar(filas, modo)
            ruta = TMP / f"{b}_{modo}.tsv"
            with ruta.open("w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=list(filas[0].keys()), delimiter="\t")
                w.writeheader()
                for r, s in zip(filas, nueva):
                    r["score"] = f"{s:.6f}"
                    w.writerow(r)
        f1s.append(evaluar(ruta, b))
    print(f"  {modo:<12}" + "".join(f"{x:>11.3f}" for x in f1s)
          + f"{sum(f1s)/len(f1s):>10.3f}")
