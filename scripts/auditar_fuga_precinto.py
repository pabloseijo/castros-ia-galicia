#!/usr/bin/env python3
"""¿Hay castros del PRECINTO dentro de los corpus de entrenamiento?

Aparecio al preparar el test del consejo: los indices de vinetas de v11p tienen
filas a 0 m de castros que estan en `data/precinto-portugal.tsv`, que es el
fichero YA corregido el 2026-08-10 (los 282 que quedaron tras apartar 71
gallegos). Si esas vinetas entraron en el entrenamiento de un modelo CONGELADO,
la medicion del precinto quedaria invalidada antes de hacerse.

Comprueba TODOS los indices de vinetas que encuentre, no solo el de v11p.
"""
import csv
import math
from pathlib import Path


def dist_m(a, b):
    dx = (a[0] - b[0]) * 111320 * math.cos(math.radians((a[1] + b[1]) / 2))
    dy = (a[1] - b[1]) * 110540
    return math.hypot(dx, dy)


prec = []
with open("data/precinto-portugal.tsv", encoding="utf-8") as fh:
    for r in csv.DictReader(fh, delimiter="\t"):
        try:
            prec.append((float(r["lon"]), float(r["lat"]),
                         r.get("name") or r.get("nombre") or "?"))
        except Exception:
            pass
print(f"castros precintados: {len(prec)}\n")

indices = sorted(Path("data").glob("*vignettes*/index*.tsv"))
indices += sorted(Path("data").glob("*chips*/index*.tsv"))
if not indices:
    print("no se encontro ningun indice de vinetas")

for f in indices:
    try:
        filas = list(csv.DictReader(open(f, encoding="utf-8"), delimiter="\t"))
    except Exception as e:
        print(f"{f}: ilegible ({e})")
        continue
    hits = []
    for r in filas:
        try:
            lon, lat = float(r["lon"]), float(r["lat"])
        except Exception:
            continue
        if not (40.9 <= lat <= 42.3):
            continue
        for q in prec:
            d = dist_m((lon, lat), q)
            if d < 500:
                hits.append((d, r.get("split", "?"), r.get("label", "?"),
                             r.get("group", "?"), str(r.get("name"))[:38], str(q[2])[:34]))
                break
    print(f"=== {f} — {len(filas)} filas — {len(hits)} a menos de 500 m del precinto")
    for d, sp, lb, gr, nm, qn in sorted(hits)[:12]:
        print(f"    {d:6.0f} m  split={sp:6} label={lb:3} grupo={gr:8} {nm:38} -> {qn}")
    print()
