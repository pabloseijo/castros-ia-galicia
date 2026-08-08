#!/usr/bin/env python3
"""¿Cuantos castros catalogados tienen ya su tesela LiDAR descargada?

La descarga de `6.274` teselas va por la mitad y la pregunta practica no es
«cuanto falta» sino **«cuantos positivos entrenables hay YA»**. Si la curva se
aplana —porque las teselas que quedan cubren castros que ya estaban cubiertos por
otra—, esperar `25 h` mas no compra casi nada y v11 puede arrancar antes.

Se resuelve por nombre de tesela: los ficheros del PNOA llevan sus coordenadas
UTM en kilometros dentro del nombre (`PNOA-2024-GAL-571-4798-H29`), asi que se
puede saber que tesela le toca a cada castro sin abrir un solo LAZ.
"""
from __future__ import annotations

import csv
import math
import re
import sys
from pathlib import Path

DIR = Path(sys.argv[1] if len(sys.argv) > 1
           else "data/external/lidar-positives-v1")
MAESTRO = Path(sys.argv[2] if len(sys.argv) > 2
               else "data/weak_label_master_fusionado.tsv")

# nombre -> (este_km, norte_km_del_BORDE_SUPERIOR)
#
# **Ojo con la Y.** Una tesela `PNOA-2024-AST-655-4789` cubre de `4788000` a
# `4789000`: el nombre lleva el borde **superior**, no el inferior. Verificado
# leyendo la cabecera de un LAZ, no suponiendo. Sin esta correccion la cobertura
# sale desplazada un kilometro entero y da un `22%` donde hay mas.
PAT = re.compile(r"-(\d{3})-(\d{4})-H29")
tengo = set()
for f in DIR.glob("*.laz"):
    m = PAT.search(f.name)
    if m:
        tengo.add((int(m.group(1)), int(m.group(2))))
print(f"teselas descargadas y legibles por nombre: {len(tengo)}")


def a_utm29(lon, lat):
    """WGS84 -> UTM 29N, suficiente para saber en que tesela de 1 km cae."""
    a, f = 6378137.0, 1 / 298.257223563
    e2 = f * (2 - f)
    k0, lon0 = 0.9996, math.radians(-9.0)
    lat_r, lon_r = math.radians(lat), math.radians(lon)
    N = a / math.sqrt(1 - e2 * math.sin(lat_r) ** 2)
    T = math.tan(lat_r) ** 2
    C = e2 / (1 - e2) * math.cos(lat_r) ** 2
    A = math.cos(lat_r) * (lon_r - lon0)
    e4, e6 = e2 * e2, e2 * e2 * e2
    M = a * ((1 - e2/4 - 3*e4/64 - 5*e6/256) * lat_r
             - (3*e2/8 + 3*e4/32 + 45*e6/1024) * math.sin(2*lat_r)
             + (15*e4/256 + 45*e6/1024) * math.sin(4*lat_r)
             - (35*e6/3072) * math.sin(6*lat_r))
    x = k0*N*(A + (1-T+C)*A**3/6 + (5-18*T+T*T+72*C-58*e2/(1-e2))*A**5/120) + 500000
    y = k0*(M + N*math.tan(lat_r)*(A*A/2 + (5-T+9*C+4*C*C)*A**4/24
            + (61-58*T+T*T+600*C-330*e2/(1-e2))*A**6/720))
    return x, y


with MAESTRO.open(encoding="utf-8") as fh:
    filas = list(csv.DictReader(fh, delimiter="\t"))

col_lon = next((c for c in filas[0] if c.lower() in ("lon", "longitude", "x")), None)
col_lat = next((c for c in filas[0] if c.lower() in ("lat", "latitude", "y")), None)
col_tipo = next((c for c in filas[0] if "class" in c.lower() or "tipo" in c.lower()
                 or "label" in c.lower()), None)
print(f"maestro: {len(filas)} filas | lon={col_lon} lat={col_lat} tipo={col_tipo}")

cubiertos = total = 0
por_tipo = {}
for r in filas:
    try:
        lon, lat = float(r[col_lon]), float(r[col_lat])
    except (TypeError, ValueError, KeyError):
        continue
    total += 1
    x, y = a_utm29(lon, lat)
    ok = (int(x // 1000), int(y // 1000) + 1) in tengo
    cubiertos += ok
    if col_tipo:
        t = (r.get(col_tipo) or "?")[:22]
        d = por_tipo.setdefault(t, [0, 0])
        d[0] += 1; d[1] += ok

print(f"\nyacimientos con tesela descargada: {cubiertos} de {total} "
      f"({cubiertos/max(total,1):.1%})")
if por_tipo:
    print(f"\n{'tipo':<24}{'total':>8}{'cubiertos':>11}{'%':>7}")
    for t, (n, c) in sorted(por_tipo.items(), key=lambda kv: -kv[1][0])[:8]:
        print(f"  {t:<22}{n:>8}{c:>11}{c/max(n,1):>7.0%}")
