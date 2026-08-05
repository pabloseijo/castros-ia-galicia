"""¿Da la cache de DEM el MISMO resultado que leer el .laz? Si no, no sirve.

Una optimizacion que cambia el numero en silencio es peor que no optimizar. Esto
corta las mismas celdas por las dos vias y compara los canales que entran a la
red, que es lo unico que decide la puntuacion.
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "scripts")
from sweep_grid_lidar import cortar_desde_dem, cortar_grupo
from build_trasancos_vignettes import lonlat_to_utm29

EXT, RES = 512.0, 1.0
dems = sorted(Path("data/dem-cache-1m").glob("*.npz"))
print("teselas en cache: %d" % len(dems))

# celdas en el centro de las teselas convertidas, para que caigan dentro
celdas = []
for i, d in enumerate(dems[:6]):
    b = np.load(d)["bounds"]
    cx = (float(b[0]) + float(b[2])) / 2.0
    cy = (float(b[1]) + float(b[3])) / 2.0
    celdas.append({"id": i, "x": cx, "y": cy, "lon": 0.0, "lat": 0.0})
print("celdas de prueba: %d" % len(celdas))

# --- via caché ---
por_dem = cortar_desde_dem((tuple(str(d) for d in dems), celdas, EXT, RES))
print("por caché de DEM: %d celdas cortadas" % len(por_dem))

# --- via laz, con las teselas que corresponden ---
laz = sorted(Path("data/external/lidar-trasancos-v1").glob("*.laz"))
nombres = {d.stem for d in dems}
laz_usadas = tuple(str(p) for p in laz if p.stem in nombres)
por_laz = cortar_grupo((laz_usadas, celdas, EXT, RES))
print("por .laz directo : %d celdas cortadas" % len(por_laz))

d1 = {c[0]: c[3] for c in por_dem}
d2 = {c[0]: c[3] for c in por_laz}
comunes = sorted(set(d1) & set(d2))
print("\ncomparables: %d celdas" % len(comunes))
if not comunes:
    raise SystemExit("ninguna celda comun: la prueba no dice nada")

peor_rel, peor_abs = 0.0, 0.0
for k in comunes:
    a = d1[k].astype(np.float32)
    b = d2[k].astype(np.float32)
    if a.shape != b.shape:
        print("  celda %d: FORMAS DISTINTAS %s vs %s" % (k, a.shape, b.shape))
        continue
    dif = np.abs(a - b)
    rango = float(b.max() - b.min()) or 1.0
    peor_abs = max(peor_abs, float(dif.max()))
    peor_rel = max(peor_rel, float(dif.max()) / rango)
    print("  celda %d: dif media %.5f | dif max %.5f | corr %.6f"
          % (k, float(dif.mean()), float(dif.max()),
             float(np.corrcoef(a.ravel(), b.ravel())[0, 1])))

print("\npeor diferencia absoluta: %.5f (%.3f%% del rango)"
      % (peor_abs, 100 * peor_rel))
print("VEREDICTO: %s" % ("equivalente, la caché sirve" if peor_rel < 0.01
                         else "DISTINTO: la caché cambia el resultado, NO usar"))
