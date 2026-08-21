#!/usr/bin/env python3
"""¿Están los candidatos donde suele haber castros, o repartidos al azar?

Los castros no se distribuyen uniformemente: ocupan posiciones defendibles y
forman patrones territoriales, con vecinos a pocos kilometros. Si los `419`
candidatos de `candidatos_ineditos.py` estan **mas cerca de los castros
catalogados de lo que estaria un punto al azar**, eso los apoya como sitios
plausibles. Si se reparten como el azar, pesa hacia el ruido.

**El control tiene que llevar la misma exclusion.** A los candidatos se les quito
todo lo que caia a menos de `500 m` de un castro catalogado, asi que un punto al
azar sin esa criba estaria mas cerca por construccion y la comparacion saldria
falsamente a favor del azar. Los puntos de control se sortean **dentro del mismo
bloque y con el mismo filtro de `500 m`**.

No prueba que un candidato sea un castro. Mide si la **poblacion** de candidatos
se comporta como cabria esperar de yacimientos y no de artefactos del relieve.
"""
from __future__ import annotations

import csv
import math
import random
from pathlib import Path

import numpy as np
from scipy.stats import mannwhitneyu

BLOQUES = {"lugo": "-7.375 42.625 -7.125 42.875",
           "coruna": "-8.50 43.00 -8.25 43.25",
           "ourense": "-8.25 42.25 -8.00 42.50",
           "pontevedra": "-8.875 42.125 -8.625 42.375"}
EXCL = 500.0
N_AZAR = 2000
rnd = random.Random(20260809)


def leer(p):
    with Path(p).open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


cand = leer("data/candidatos-ineditos.tsv")
d_cand, d_azar = [], []

for b, bb in BLOQUES.items():
    w, s, e, n = map(float, bb.split())
    truth = leer(f"data/{b}_fus_truth_limpia.tsv")
    lat0 = (s + n) / 2
    k = 111_320.0 * math.cos(math.radians(lat0))
    tx = np.array([float(t["lon"]) * k for t in truth])
    ty = np.array([float(t["lat"]) * 110_540.0 for t in truth])

    def dist_min(lon, lat):
        return float(np.hypot(tx - lon * k, ty - lat * 110_540.0).min())

    for c in cand:
        if c["bloque"] != b:
            continue
        d = dist_min(float(c["lon"]), float(c["lat"]))
        if d >= EXCL:                    # deberia cumplirse siempre; se comprueba
            d_cand.append(d)

    hechos = 0
    while hechos < N_AZAR:
        lon, lat = rnd.uniform(w, e), rnd.uniform(s, n)
        d = dist_min(lon, lat)
        if d >= EXCL:                    # mismo filtro que llevan los candidatos
            d_azar.append(d)
            hechos += 1

a, z = np.array(d_cand), np.array(d_azar)
print(f"  distancia al castro catalogado mas cercano, en metros")
print(f"  (los dos grupos con el mismo filtro de {EXCL:.0f} m)\n")
print(f"  {'grupo':<16}{'n':>6}{'mediana':>10}{'media':>10}{'<1 km':>8}{'<2 km':>8}")
print("  " + "-" * 58)
for nombre, v in (("candidatos", a), ("azar en el bloque", z)):
    print(f"  {nombre:<16}{len(v):>6}{np.median(v):>10.0f}{v.mean():>10.0f}"
          f"{100*(v<1000).mean():>7.0f}%{100*(v<2000).mean():>7.0f}%")

u, p = mannwhitneyu(a, z, alternative="less")
print(f"\n  P(un candidato este mas cerca que un punto al azar) = "
      f"{1 - u/(len(a)*len(z)):.3f}")
print(f"  Mann-Whitney (candidatos MAS cerca): p = {p:.4g}")
