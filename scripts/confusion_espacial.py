#!/usr/bin/env python3
"""¿Vienen los positivos y el fondo de los mismos sitios?

Refutada la calidad de los positivos nuevos (`2026-08-09`: puntuan **mas alto**
que los de v7 con el propio modelo de v7), queda otra explicacion para que v11p y
v13 salgan permisivos, y es geometrica en vez de arqueologica:

> Si los positivos vienen de `904` bloques y el fondo de `18`, hay tipos de
> terreno que el modelo **solo ha visto dentro de una viñeta de castro**. No
> necesita aprender el castro: le basta aprender el paisaje.

Es confusion espacial —un atajo, no una fuga— y explica exactamente el sintoma:
alto recall de castro, fondo hundido, precision mala en despliegue.

Se mide contando de que bloque sale cada viñeta y comparando los dos repartos.
"""
from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path


def bloques(idx: Path):
    """Devuelve, por corpus, el reparto de bloques de positivos y de fondo."""
    pos, neg = Counter(), Counter()
    with idx.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            b = (r.get("bloque") or r.get("block") or r.get("tile")
                 or r.get("laz") or "").strip()
            if not b:
                # sin columna de bloque: se deriva de la rejilla de 2 km
                try:
                    x, y = float(r["x"]), float(r["y"])
                    b = f"{int(x // 2000)}_{int(y // 2000)}"
                except (KeyError, ValueError):
                    continue
            g = (r.get("group") or "").strip()
            (pos if g.startswith("castro") else neg)[b] += 1
    return pos, neg


for nombre in ("v7", "v11p", "v13"):
    idx = Path(f"data/galicia-vignettes-{nombre}/index.tsv")
    if not idx.exists():
        continue
    pos, neg = bloques(idx)
    solo_pos = set(pos) - set(neg)
    n_solo = sum(pos[b] for b in solo_pos)
    tot = sum(pos.values())
    print(f"\n  {nombre}")
    print(f"    bloques con positivos: {len(pos):>5}   con fondo: {len(neg):>5}   "
          f"compartidos: {len(set(pos) & set(neg)):>5}")
    print(f"    positivos en bloques SIN NADA de fondo: {n_solo}/{tot} "
          f"({100*n_solo/max(tot,1):.0f}%)")
