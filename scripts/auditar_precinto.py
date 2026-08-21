#!/usr/bin/env python3
"""¿Es el conjunto precintado realmente el norte de Portugal?

Al construir v14 (`2026-08-09`) el control del precinto marco **`6` castros
sellados a `0 m` del entrenamiento**, con nombres gallegos: «O Montiño»,
«A Cidá», «Chavella». No eran una fuga: eran **castros gallegos dentro del
fichero de verdad precintada**.

Importa en las dos direcciones, y las dos son malas:

- Un castro gallego sellado que **si esta en entrenamiento** convierte el examen
  final en una nota inflada.
- Un castro gallego sellado que **no esta** es, aun asi, un fallo automatico: el
  LiDAR de la DGT portuguesa no cubre Galicia, asi que el barrido nunca podra
  encontrarlo y contara como falso negativo.

Se clasifica por el campo `concello`, cruzado con los concellos que aparecen en
el maestro de castros de Galicia.
"""
from __future__ import annotations

import csv
import glob
from collections import Counter
from pathlib import Path

t = list(csv.DictReader(open("data/portugal-test_truth_limpia.tsv", encoding="utf-8"),
                        delimiter="\t"))

gal: set[str] = set()
ficheros = [f for pat in ("data/**/*castro*.tsv", "data/**/*maestro*.tsv",
                          "data/**/*galicia*.tsv")
            for f in glob.glob(pat, recursive=True)]
for f in ficheros:
    if "portugal" in f.lower() or "precinto" in f.lower():
        continue
    try:
        for r in csv.DictReader(open(f, encoding="utf-8"), delimiter="\t"):
            c = (r.get("concello") or r.get("municipio") or "").strip()
            if c:
                gal.add(c)
    except Exception:
        pass

print(f"concellos gallegos conocidos: {len(gal)} (de {len(ficheros)} ficheros)")

dentro = [r for r in t if (r.get("concello") or "").strip() in gal]
fuera = [r for r in t if (r.get("concello") or "").strip() not in gal]
print(f"\n  de los {len(t)} del precinto:")
print(f"    en concello GALLEGO:      {len(dentro)}")
print(f"    en municipio portugues:   {len(fuera)}")
if dentro:
    print("\n  concellos gallegos implicados:")
    for c, n in Counter((r.get("concello") or "").strip() for r in dentro).most_common():
        print(f"    {c:<26} {n}")

sal = Path("data/portugal-test_truth_SOLO-PORTUGAL.tsv")
if fuera:
    with sal.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(t[0].keys()), delimiter="\t")
        w.writeheader()
        w.writerows(fuera)
    print(f"\n  escrito {sal} con {len(fuera)} castros")
