#!/usr/bin/env python3
"""Imprime el `--bbox` que reproduce la rejilla de un barrido ya hecho.

Existe para que **ningún script vuelva a escribir un bbox a mano**. El
2026-08-10 se escribieron tres de memoria y los tres estaban mal; Ourense por
`0,4` grados de longitud, que es otra comarca. La constante que no existe no
puede estar mal.

La rejilla se define por su esquina mínima y el paso, así que tomar el mínimo
de los centros de celda del barrido de referencia reproduce el mismo origen y,
por tanto, las mismas celdas. Al máximo se le suma un paso corto para que la
última fila y columna entren.

Uso:
    python3 scripts/bbox_de_barrido.py data/sweep_val_lugo_v7.tsv
    -> -7.3750 42.6210 -7.1230 42.8810
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

# Un paso de rejilla de 256 m en grados, redondeado hacia arriba. Sobrar una
# celda no cuesta nada; faltar una deja un borde sin barrer.
MARGEN_LON = 0.004
MARGEN_LAT = 0.003


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__.strip().splitlines()[-2].strip(), file=sys.stderr)
        return 2
    f = Path(sys.argv[1])
    if not f.exists():
        print("no existe: %s" % f, file=sys.stderr)
        return 1

    lon, lat = [], []
    with f.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            if r.get("lon") and r.get("lat"):
                lon.append(float(r["lon"]))
                lat.append(float(r["lat"]))
    if len(lon) < 100:
        # Un barrido de referencia con cuatro filas no define ninguna rejilla, y
        # devolver un bbox diminuto es peor que no devolver nada.
        print("referencia con solo %d celdas: no define rejilla" % len(lon),
              file=sys.stderr)
        return 1

    # **Ocho decimales, no cuatro.** `sweep_grid_lidar` transforma la esquina a
    # UTM y la redondea al metro (`floor(x/res)*res`), así que un bbox redondeado
    # a `1e-4` grados —unos `8 m` en longitud— cae en OTRO metro entero y toda la
    # rejilla se desplaza. Medido el 2026-08-10 sobre el barrido de v9 en Lugo:
    # **desplazamiento mediano de `101,9 m`**, casi media celda, y solo el `24%`
    # de las celdas caían a menos de `20 m` de su homóloga de v7. Con el modelo
    # medido como muy sensible al descentrado, eso no es un detalle: confunde la
    # comparación entre versiones.
    print("%.8f %.8f %.8f %.8f"
          % (min(lon), min(lat), max(lon) + MARGEN_LON, max(lat) + MARGEN_LAT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
