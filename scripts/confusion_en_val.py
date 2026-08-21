#!/usr/bin/env python3
"""El atajo, ¿esta tambien dentro del examen?

Si dentro de `val` hay castros en bloques de los que **no hay ningun fondo en
val**, entonces acertarlos no exige reconocer un castro: basta reconocer que ese
paisaje, en el examen, solo sale en positivos. La nota sube sin que el modelo
mejore, y en despliegue no queda nada de esa ventaja.

Explicaria la contradiccion que dejo v11p: **mejor validacion que v7 (`0,63`
contra `0,55`) y peor despliegue en los cuatro bloques**.
"""
from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

for nombre in ("v7", "v11p", "v13"):
    idx = Path(f"data/galicia-vignettes-{nombre}/index.tsv")
    if not idx.exists():
        continue
    print(f"\n  {nombre}")
    filas = list(csv.DictReader(idx.open(encoding="utf-8"), delimiter="\t"))
    for split in ("train", "val"):
        pos, neg = Counter(), Counter()
        for r in filas:
            if (r.get("split") or "").strip() != split:
                continue
            b = (r.get("block") or "").strip()
            g = (r.get("group") or "").strip()
            (pos if g.startswith("castro") else neg)[b] += 1
        solo = sum(pos[b] for b in set(pos) - set(neg))
        tot = sum(pos.values())
        print(f"    {split:<6} castros {tot:>5}   en bloques sin fondo del mismo split: "
              f"{solo:>5} ({100*solo/max(tot,1):>3.0f}%)")
