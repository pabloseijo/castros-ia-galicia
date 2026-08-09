#!/usr/bin/env python3
"""L3.3, primera causa: ¿el rendimiento sigue a la densidad del LiDAR?

Fontana et al. (`10.1002/arp.1951`) avisan de que en un barrido LiDAR la
visibilidad de cada tipologia depende de la resolucion del sensor, asi que un mapa
de hallazgos es en parte un mapa de cobertura. El PNOA va de `1` a `2,7 pt/m²`
segun la zona.

Esto lo convierte de advertencia en numero: densidad media de puntos de suelo por
bloque contra el `F1` medido alli. Si correlacionan, hay que publicar los dos
mapas juntos; si no, la advertencia sigue en pie pero no domina.

Se muestrean pocas teselas por bloque a proposito: leer `638` LAZ por bloque
costaria horas y el estimador de la mediana no lo necesita.
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

import numpy as np

F1_V7 = {"lugo": 0.697, "coruna": 0.396, "ourense": 0.535, "pontevedra": 0.419}
N_TESELAS = int(sys.argv[1]) if len(sys.argv) > 1 else 6

try:
    import laspy
except ImportError:
    print("sin laspy"); raise SystemExit(1)

print(f"{'bloque':<12}{'teselas':>8}{'pt/m2 suelo':>13}{'F1 de v7':>10}")
dens, f1s = [], []
rnd = random.Random(20260809)
for b, f1 in F1_V7.items():
    d = Path(f"data/external/lidar-val-{b}")
    lazs = sorted(d.glob("*.laz"))
    if not lazs:
        print(f"{b:<12}{'sin LAZ':>8}")
        continue
    muestra = rnd.sample(lazs, min(N_TESELAS, len(lazs)))
    vals = []
    for f in muestra:
        try:
            with laspy.open(f) as fh:
                pts = fh.read()
                suelo = np.asarray(pts.classification) == 2
                area = ((pts.header.maxs[0] - pts.header.mins[0]) *
                        (pts.header.maxs[1] - pts.header.mins[1]))
                if area > 0:
                    vals.append(float(suelo.sum()) / area)
        except Exception:
            continue
    if not vals:
        continue
    m = float(np.median(vals))
    dens.append(m); f1s.append(f1)
    print(f"{b:<12}{len(vals):>8}{m:>13.2f}{f1:>10.3f}")

if len(dens) >= 3:
    r = float(np.corrcoef(dens, f1s)[0, 1])
    print(f"\n  correlacion densidad-F1: {r:+.3f}  (n={len(dens)})")
    print(f"  rango de densidad: {min(dens):.2f} a {max(dens):.2f} pt/m2 "
          f"({max(dens)/max(min(dens),1e-9):.1f}x)")
    if abs(r) > 0.7:
        print("  -> el rendimiento SIGUE a la densidad: hay que publicar los dos mapas")
    else:
        print("  -> con n=4 no se sostiene una correlacion; la advertencia de")
        print("     Fontana sigue en pie pero NO esta demostrada aqui")
