#!/usr/bin/env python3
"""¿En cuántos modelos independientes coincide cada candidato?

La pregunta que importa de la lista de `419` es cuáles merecen que alguien vaya a
mirarlos. Mirar la ficha uno a uno es lento; hay una señal más barata y bastante
buena: **cuántos detectores distintos señalan el mismo sitio**.

No es redundancia: v7, v11p, v12 y v13 se entrenaron con **corpus distintos** y
`comparar_detecciones.py` midió que ven castros distintos —v11p encuentra `28`
que v7 no ve, v12 otros `25`—. Que cuatro modelos entrenados con datos
diferentes coincidan en un punto que **el catálogo no conoce** es mucho más
difícil de explicar por un artefacto del relieve que si lo dice uno solo.

Es la lógica de un comité, y aquí sale gratis: los barridos ya están hechos.

Cautela declarada: los cuatro comparten arquitectura y canales, así que un
artefacto que engañe a la U-Net los engañará a todos. **El consenso reduce el
ruido aleatorio, no el sesgo compartido.**
"""
from __future__ import annotations

import csv
import math
from pathlib import Path

MODELOS = ["v7", "v11p", "v12", "v14", "v13", "v8", "v6focal"]
UMBRAL = 0.60
RADIO = 400.0     # dos detecciones a menos de esto son el mismo sitio


def leer(p):
    with Path(p).open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


cand = leer("data/candidatos-ineditos.tsv")
por_bloque = {}
for c in cand:
    por_bloque.setdefault(c["bloque"], []).append(c)

# **Un solo factor de longitud por bloque, y el mismo para nube y candidato.**
# La primera versión calculaba `k` con la latitud de cada candidato pero había
# construido la nube con la del primer punto del bloque. Dentro de un bloque la
# latitud varía `0,25°`, así que `cos(lat)` cambia un `0,5%` — que sobre una `x`
# de `585 km` son casi **`3 km` de desfase**. El síntoma fue imposible y por eso
# se vio: `179` candidatos con `0` votos, cuando por construcción salen de la
# unión de v7 y v11p y al menos uno tenía que votar siempre.
K = {b: 111_320.0 * math.cos(math.radians(
        sum(float(c["lat"]) for c in cs) / len(cs))) for b, cs in por_bloque.items()}

nubes = {}
for b in por_bloque:
    for m in MODELOS:
        p = Path(f"data/sweep_val_{b}_{m}.tsv")
        if not p.exists() or p.stat().st_size < 50_000:
            continue     # barridos incompletos: no cuentan como voto
        nubes[(b, m)] = [(float(r["lon"]) * K[b], float(r["lat"]) * 110_540.0)
                         for r in leer(p) if float(r.get("score", 0)) >= UMBRAL]

salida = []
for c in cand:
    b = c["bloque"]
    cx, cy = float(c["lon"]) * K[b], float(c["lat"]) * 110_540.0
    votos = []
    for m in MODELOS:
        nube = nubes.get((b, m))
        if nube is None:
            continue
        if any((px - cx) ** 2 + (py - cy) ** 2 <= RADIO * RADIO for px, py in nube):
            votos.append(m)
    salida.append({**c, "votos": len(votos), "quienes": ",".join(votos)})

salida.sort(key=lambda r: (-r["votos"], -float(r["score"])))
dest = Path("data/candidatos-consenso.tsv")
with dest.open("w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=list(salida[0].keys()), delimiter="\t")
    w.writeheader()
    w.writerows(salida)

reparto = {}
for r in salida:
    reparto[r["votos"]] = reparto.get(r["votos"], 0) + 1
disponibles = len({m for (_, m) in nubes})
print(f"  {len(salida)} candidatos | {disponibles} modelos con barrido completo\n")
print(f"  {'votos':>6}  {'candidatos':>11}")
for v in sorted(reparto, reverse=True):
    print(f"  {v:>6}  {reparto[v]:>11}   {'#' * min(reparto[v] // 3, 40)}")
print(f"\n  los 12 de mayor consenso:")
for r in salida[:12]:
    print(f"    {r['votos']} votos  {r['score']}  {r['bloque']:<11} "
          f"{r['lat']},{r['lon']}  [{r['quienes']}]")
print(f"\n  -> {dest}")
