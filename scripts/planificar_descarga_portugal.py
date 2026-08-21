#!/usr/bin/env python3
"""El plan de descarga del conjunto de prueba portugués, en peticiones de 200 km².

La fase 3 del roadmap —romper el precinto— está bloqueada porque **no existe
proveedor de elevación portugués**. El repositorio ya lo tenía escrito hace
meses: *«Portugal queda `rgb_only_until_portugal_dem_provider` hasta tener
proveedor DGT/CDD portugués con CRS, resolución, licencia y cobertura por tile
registrados»*, y aun así el precinto se fijó sobre Portugal.

## Lo que se comprobó en la fuente el 2026-08-11

| | |
| --- | --- |
| datos | **abiertos**, sin restricciones de uso |
| nube de puntos | `10 pt/m²`, LAZ |
| **ráster** | **MDT y MDS en GeoTIFF a `50 cm` y `2 m`** |
| portal | `https://cdd.dgterritorio.gov.pt` |
| API pública | **no existe** — la DGT dice que llegará «posteriormente» |
| WCS / WMS del MDT | **no encontrado** |
| descarga | **carrito con ruta protegida**: exige cuenta |
| tope por sesión | **`~200 km²`** |

Es decir: **la descarga no se puede automatizar sin credenciales**, y activar un
canal con login es decisión de Pablo, no de la máquina.

## Lo que sí se puede dejar resuelto, que es esto

Convertir «hay que bajar el norte de Portugal» —que suena a infinito— en **una
lista concreta y ordenada de rectángulos de `≤200 km²`**, cada uno con sus
coordenadas listas para dibujar en el visor, y con cuántos castros del precinto
cubre.

Así la única parte manual es pedir los ficheros, y todo lo de después ya está
construido.

## El orden importa: por castros cubiertos, no por geografía

El precinto se rompe **una vez**, así que no hace falta bajar los `23.254 km²`
de la caja envolvente: hace falta cubrir los `282` castros **y su fondo**. Los
rectángulos salen ordenados por cuántos castros aportan, de modo que las
primeras peticiones son las que más miden.

Uso:
    python3 scripts/planificar_descarga_portugal.py --km2 200
"""
from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

import numpy as np

# Metadatos del proveedor, que es lo que el proyecto exigía tener registrado.
PROVEEDOR = {
    "nombre": "DGT — Direção-Geral do Território (Portugal)",
    "portal": "https://cdd.dgterritorio.gov.pt",
    "producto": "Levantamento LiDAR de Portugal Continental",
    "nube_puntos": "LAZ, densidad media 10 pt/m²",
    "raster": "MDT y MDS en GeoTIFF a 50 cm y 2 m",
    "crs_nativo": "ETRS89 / PT-TM06 — EPSG:3763",
    "licencia": "datos abiertos, sin restricciones de uso",
    "acceso": "carrito con sesión (ruta protegida); sin API pública a 2026-08-11",
    "tope_por_sesion_km2": 200,
    "cobertura": "~90% del territorio; el noroeste seguía en produccion segun "
                 "la propia DGT — HAY QUE VERIFICARLO PARA EL AREA DEL PRECINTO",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--precinto", type=Path,
                    default=Path("data/precinto-portugal.tsv"))
    ap.add_argument("--km2", type=float, default=200.0,
                    help="tope por peticion del portal")
    ap.add_argument("--margen-m", type=float, default=1500.0,
                    help="fondo alrededor de cada castro. El barrido necesita "
                         "contexto y negativos: sin fondo, la precision medida "
                         "no significa nada")
    ap.add_argument("--out", type=Path,
                    default=Path("data/plan-descarga-portugal.tsv"))
    args = ap.parse_args()

    filas = list(csv.DictReader(args.precinto.open(encoding="utf-8"),
                                delimiter="\t"))
    lon = np.array([float(r["lon"]) for r in filas])
    lat = np.array([float(r["lat"]) for r in filas])
    print("castros precintados: %d" % len(filas))

    # Un solo factor de longitud para toda la caja: la lección de los 3 km.
    k = 111_320.0 * math.cos(math.radians(float(lat.mean())))
    x = lon * k
    y = lat * 110_540.0

    lado = math.sqrt(args.km2) * 1000.0
    print("peticion maxima: %.0f km2 = %.1f x %.1f km" % (args.km2,
                                                          lado / 1000, lado / 1000))
    print("margen por castro: %.0f m\n" % args.margen_m)

    # Rejilla de peticiones anclada al minimo, y se cuenta cuantos castros cae
    # en cada celda. Solo se piden las celdas con castros: el resto del norte de
    # Portugal no hace falta para medir.
    x0, y0 = x.min() - args.margen_m, y.min() - args.margen_m
    ix = ((x - x0) / lado).astype(int)
    iy = ((y - y0) / lado).astype(int)
    celdas: dict[tuple[int, int], list[int]] = {}
    for n, (a, b) in enumerate(zip(ix, iy)):
        celdas.setdefault((int(a), int(b)), []).append(n)

    orden = sorted(celdas.items(), key=lambda kv: -len(kv[1]))
    print("peticiones necesarias: %d" % len(orden))
    print("superficie total: %.0f km2 (contra %.0f de la caja envolvente)"
          % (len(orden) * args.km2,
             (x.max() - x.min()) * (y.max() - y.min()) / 1e6))
    print()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter="\t")
        w.writerow(["orden", "castros", "acumulado", "lon_min", "lat_min",
                    "lon_max", "lat_max"])
        acum = 0
        print("%5s %8s %10s   %s" % ("orden", "castros", "acumulado",
                                     "rectangulo (lon/lat WGS84)"))
        print("-" * 78)
        for i, ((a, b), idxs) in enumerate(orden, 1):
            xa, xb = x0 + a * lado, x0 + (a + 1) * lado
            ya, yb = y0 + b * lado, y0 + (b + 1) * lado
            lo0, lo1 = xa / k, xb / k
            la0, la1 = ya / 110_540.0, yb / 110_540.0
            acum += len(idxs)
            w.writerow([i, len(idxs), acum, "%.6f" % lo0, "%.6f" % la0,
                        "%.6f" % lo1, "%.6f" % la1])
            if i <= 12 or len(idxs) >= 5:
                print("%5d %8d %9d%%   %.4f,%.4f  ->  %.4f,%.4f"
                      % (i, len(idxs), 100 * acum // len(filas),
                         lo0, la0, lo1, la1))

    print("\nescrito: %s" % args.out)
    print()
    print("=" * 78)
    print("PROVEEDOR REGISTRADO")
    for k_, v in PROVEEDOR.items():
        print("  %-22s %s" % (k_, v))
    print()
    print("Lo que falta y NO puede hacer la maquina sola:")
    print("  1. Cuenta en el portal de la DGT (la descarga es ruta protegida).")
    print("  2. Verificar que el noroeste ya esta publicado para esta area.")
    print("Todo lo de despues —barrer, evaluar, borrar— ya esta construido.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
