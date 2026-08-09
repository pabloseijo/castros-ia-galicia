#!/usr/bin/env python3
"""L3.3, causa 2: ¿esta el catalogo sesgado hacia lo accesible?

La sospecha declarada en la hoja de informacion del modelo: «esta catalogado lo
que alguien encontro, y se encuentra mas cerca de carreteras, en terreno despejado
y en comarcas mas estudiadas». Si es cierto, el modelo aprende a encontrar **lo
que ya se encontro**, y el barrido de Galicia heredara ese sesgo.

Se mide con lo que ya hay en disco —la cache de Overpass de `39 MB`, sin volver a
pedir nada— comparando la distancia a via mas cercana de:

  - los **castros catalogados** del maestro,
  - el **terreno aleatorio** del corpus, que es la referencia de «un sitio
    cualquiera de Galicia».

Si los castros estan sistematicamente mas cerca de una via que el terreno al azar,
el sesgo esta cuantificado. Si no, la sospecha se debilita.
"""
from __future__ import annotations

import csv
import glob
import json
import math
import random
from pathlib import Path

import numpy as np

# vias de la cache: cualquier elemento con etiqueta highway
vias = []
for f in glob.glob("data/galicia-hard-negatives-v1/overpass-cache/*.json"):
    try:
        d = json.load(open(f, encoding="utf-8"))
    except Exception:
        continue
    for e in d.get("elements", []):
        t = e.get("tags") or {}
        if "highway" not in t:
            continue
        c = e.get("center") or e
        la, lo = c.get("lat"), c.get("lon")
        if la is not None and lo is not None:
            vias.append((float(la), float(lo)))
print(f"vias en la cache: {len(vias)}")
if len(vias) < 500:
    print("  muy pocas vias cacheadas para medir esto con sentido")
    raise SystemExit(1)

V = np.array(vias)

def dist_min(la, lo):
    m = np.abs(V[:, 0] - la) < 0.05
    if not m.any():
        return None
    sub = V[m]
    dy = (sub[:, 0] - la) * 111320.0
    dx = (sub[:, 1] - lo) * 111320.0 * math.cos(math.radians(la))
    return float(np.min(np.hypot(dx, dy)))

filas = list(csv.DictReader(open("data/galicia-vignettes-v11p/index.tsv",
                                 encoding="utf-8"), delimiter="\t"))
rnd = random.Random(20260809)
def muestra(pred, n=300):
    sel = [r for r in filas if pred((r.get("group") or "").strip())]
    return rnd.sample(sel, min(n, len(sel)))

grupos = {
    "castros catalogados": muestra(lambda g: g.startswith("castro")),
    "terreno aleatorio":   muestra(lambda g: g.startswith("random_terrain")),
}
print(f"\n{'grupo':<24}{'n':>5}{'mediana m':>11}{'media m':>10}{'<200 m':>9}")
res = {}
for nom, sel in grupos.items():
    ds = []
    for r in sel:
        try:
            d = dist_min(float(r["lat"]), float(r["lon"]))
        except (TypeError, ValueError, KeyError):
            continue
        if d is not None:
            ds.append(d)
    if not ds:
        continue
    a = np.array(ds); res[nom] = a
    print(f"{nom:<24}{len(a):>5}{np.median(a):>11.0f}{a.mean():>10.0f}"
          f"{100*(a < 200).mean():>8.0f}%")

if len(res) == 2:
    a, b = res["castros catalogados"], res["terreno aleatorio"]
    from statistics import median
    print(f"\n  los castros estan a {median(b)/max(median(a),1e-9):.2f}x "
          f"la distancia del terreno al azar (mediana)")
    # Mann-Whitney sin scipy: U por conteo
    conc = sum(1 for x in a for y in b if x < y)
    U = conc / (len(a) * len(b))
    print(f"  P(un castro este mas cerca de una via que un punto al azar) = {U:.3f}")
    print(f"  (0,5 = sin sesgo | >0,5 = catalogo sesgado hacia lo accesible)")
