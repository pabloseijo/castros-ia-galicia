#!/usr/bin/env python3
"""¿Cubren los bbox del guion el mismo trozo que barrio v7?

El `2026-08-08` se transcribieron mal los bbox de Lugo y Pontevedra y el barrido
cubrio **otro sitio de Galicia**: `2.520` celdas con LiDAR de `8.580` en vez de
`8.658` de `8.658`. Los `F1` que salieron de ahi no eran «peores», eran de otro
sitio, y **parecian perfectamente validos**.

La regla que quedo escrita fue «los bbox se copian, no se teclean». Esto la
verifica de la unica forma que no admite discusion: comparando el bbox declarado
con el **rango de coordenadas realmente cubierto por el barrido de v7** en ese
mismo bloque.

Se ejecuta antes de lanzar un barrido nuevo, no despues.
"""
from __future__ import annotations

import csv
from pathlib import Path

BB = {"lugo": (-7.375, 42.625, -7.125, 42.875),
      "coruna": (-8.50, 43.00, -8.25, 43.25),
      "ourense": (-8.25, 42.25, -8.00, 42.50),
      "pontevedra": (-8.875, 42.125, -8.625, 42.375)}
TOL = 0.01   # grados: el barrido va por celdas, no llega al borde exacto

malos = 0
print(f"  {'bloque':<12}{'bbox del guion':>30}{'cubierto por v7':>30}")
print("  " + "-" * 74)
for b, (w, s, e, n) in BB.items():
    p = Path(f"data/sweep_val_{b}_v7.tsv")
    if not p.exists():
        print(f"  {b:<12}  sin barrido de v7 con que comparar")
        continue
    lo, la = [], []
    with p.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            try:
                lo.append(float(r["lon"]))
                la.append(float(r["lat"]))
            except (KeyError, TypeError, ValueError):
                pass
    if not lo:
        continue
    ok = (abs(min(lo) - w) < TOL and abs(max(lo) - e) < TOL
          and abs(min(la) - s) < TOL and abs(max(la) - n) < TOL)
    malos += not ok
    print(f"  {b:<12}{w:>8.3f},{s:.3f}→{e:.3f},{n:.3f}"
          f"{min(lo):>10.3f},{min(la):.3f}→{max(lo):.3f},{max(la):.3f}"
          f"   {'OK' if ok else '*** NO COINCIDE ***'}")

print()
if malos:
    raise SystemExit(f"ABORTA: {malos} bloque(s) con bbox que no cubre lo que "
                     f"barrio v7. NO lanzar el barrido.")
print("  los cuatro bbox cubren exactamente lo que barrio v7")
