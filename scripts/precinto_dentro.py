#!/usr/bin/env python3
"""¿Cae algún castro sellado DENTRO de una viñeta de entrenamiento?

**El control anterior medía mal.** Excluía las muestras a menos de `300 m` del
centro de un sellado, pero la viñeta es un **cuadrado de `512 m` de lado**: llega
a `256 m` por el eje y a `362 m` por la esquina. Un sellado entre `300` y `362 m`
en diagonal **está dentro de la imagen que ve la red** y el control lo daba por
seguro.

Esto lo comprueba como debe hacerse: **contención geométrica real**, no distancia
a un punto. Es la ultima verificación antes de que el precinto signifique algo.
"""
from __future__ import annotations

import csv
import math
import sys
from pathlib import Path

EXTENT = 512.0
MEDIO = EXTENT / 2.0


def leer(p, latc=("lat", "latitude"), lonc=("lon", "longitude")):
    out = []
    with open(p, encoding="utf-8") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            la = next((r[c] for c in latc if c in r and r[c]), None)
            lo = next((r[c] for c in lonc if c in r and r[c]), None)
            try:
                out.append((float(la), float(lo), r))
            except (TypeError, ValueError):
                pass
    return out


corpus = sys.argv[1] if len(sys.argv) > 1 else "data/galicia-vignettes-v13"
sellados = leer("data/portugal-test_truth_limpia.tsv")
idx = [r for r in leer(f"{corpus}/index.tsv")
       if (r[2].get("split") or "").strip() in ("train", "val")]
print(f"sellados: {len(sellados)} | viñetas de train/val: {len(idx)}")

dentro, cerca = [], []
for sla, slo, sr in sellados:
    for vla, vlo, vr in idx:
        if abs(vla - sla) > 0.01:
            continue
        # desplazamiento en metros, por ejes: es un cuadrado, no un circulo
        dy = (sla - vla) * 111320.0
        dx = (slo - vlo) * 111320.0 * math.cos(math.radians((sla + vla) / 2))
        if abs(dx) <= MEDIO and abs(dy) <= MEDIO:
            dentro.append((sr.get("name", "?"), vr.get("name", ""), math.hypot(dx, dy)))
            break
        if math.hypot(dx, dy) <= 500:
            cerca.append((sr.get("name", "?"), math.hypot(dx, dy)))

print(f"\n  sellados DENTRO de una viñeta de entrenamiento: {len(dentro)}")
for n, v, d in sorted(dentro, key=lambda x: x[2])[:8]:
    print(f"    {n[:40]:<42}{d:>7.0f} m del centro")
print(f"  sellados a menos de 500 m (sin caer dentro): {len(cerca)}")
if cerca:
    for n, d in sorted(cerca, key=lambda x: x[1])[:5]:
        print(f"    {n[:40]:<42}{d:>7.0f} m")

print()
if dentro:
    print("  *** PRECINTO ROTO: la red ha visto esas imagenes ***")
    raise SystemExit(1)
print("  PRECINTO INTACTO por contencion geometrica, no solo por distancia")
