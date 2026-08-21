#!/usr/bin/env python3
"""¿Cuántos candidatos están cerca de algo que el propio repositorio ya conoce?

Es la mitad de `verificar_todos.py` que **no depende de Overpass**, y por tanto
la que se puede tener ya. Cruza los `419` contra todos los puntos con `lon/lat`
de `data/` —verdades de bloque, máscaras de entrenamiento, maestros, censos,
mámoas, negativos con nombre— y dice a qué distancia está lo más cercano.

Sirve para dos cosas distintas:

· **Cazar colados.** Un candidato a `<300 m` de un castro catalogado es, casi
  seguro, ese castro. Ya pasó una vez con «Castro do Monte da Guía», a `77 m`.
· **Ordenar la revisión.** Lo que está lejos de todo lo conocido es lo que, si
  resulta ser un castro, es de verdad un hallazgo.

Se excluyen del cruce los ficheros de barrido y los de candidatos: cruzar la
lista consigo misma no dice nada.
"""
from __future__ import annotations

import csv
import glob
import math
from collections import Counter
from pathlib import Path

import numpy as np


def leer(p):
    with Path(p).open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


puntos, origen = [], []
for f in sorted(set(glob.glob("data/**/*.tsv", recursive=True))):
    b = Path(f).name
    if any(x in b for x in ("sweep", "candidatos")) or "tmp-union" in f or "orto" in f:
        continue
    try:
        rs = leer(f)
    except Exception:
        continue
    if not rs or not ({"lon", "lat"} <= set(rs[0])):
        continue
    for r in rs:
        try:
            puntos.append((float(r["lon"]), float(r["lat"])))
            origen.append((b, (r.get("name") or r.get("nombre") or "?")[:40]))
        except (TypeError, ValueError):
            pass

print(f"  catálogo interno: {len(puntos)} puntos de "
      f"{len({o[0] for o in origen})} ficheros")

cand = leer("data/candidatos-ineditos.tsv")
P = np.array(puntos)
filas = []
for c in cand:
    lon, lat = float(c["lon"]), float(c["lat"])
    k = 111_320.0 * math.cos(math.radians(lat))
    dx = (P[:, 0] - lon) * k
    dy = (P[:, 1] - lat) * 110_540.0
    d = np.hypot(dx, dy)
    i = int(np.argmin(d))
    filas.append({**c, "d_conocido": float(d[i]),
                  "fichero": origen[i][0], "nombre": origen[i][1]})

filas.sort(key=lambda r: -r["d_conocido"])
tramos = Counter()
for r in filas:
    d = r["d_conocido"]
    tramos["<300 m (probable colado)" if d < 300 else
           "300-600 m" if d < 600 else
           "600 m - 1,5 km" if d < 1500 else
           ">1,5 km (aislado)"] += 1

print()
for t in ("<300 m (probable colado)", "300-600 m", "600 m - 1,5 km", ">1,5 km (aislado)"):
    print(f"  {t:<28} {tramos[t]:>4}")

print(f"\n  los 10 más aislados de todo lo conocido:")
for r in filas[:10]:
    print(f"    {r['d_conocido']:>7.0f} m  {r['score']}  {r['bloque']:<11} "
          f"{r['lat']},{r['lon']}")

print(f"\n  los que casi seguro ya están catalogados:")
for r in [x for x in filas if x["d_conocido"] < 300][:8]:
    print(f"    {r['d_conocido']:>5.0f} m  {r['bloque']:<11} -> {r['nombre'][:34]:<34} "
          f"({r['fichero']})")

dest = Path("data/candidatos-aislamiento.tsv")
with dest.open("w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=list(filas[0].keys()), delimiter="\t")
    w.writeheader()
    for r in filas:
        r["d_conocido"] = f"{r['d_conocido']:.0f}"
        w.writerow(r)
print(f"\n  -> {dest}")
