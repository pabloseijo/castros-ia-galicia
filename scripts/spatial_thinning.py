#!/usr/bin/env python3
"""Diluido espacial de positivos: una rejilla, un castro por celda.

Es la corrección de sesgo de muestreo mejor valorada de las cinco que compara
Fourcade et al. (2014, PLoS ONE `9(5)`: `e97122`), con rango medio `2.11` sobre
`5`, por delante de split (`2.53`), cluster (`2.61`), fichero de sesgo (`3.31`) y
fondo restringido (`4.44`). Y lo hacen aplicando cada método **sin saber cuál es
el sesgo**, que es nuestra situación exacta.

## Por qué hace falta aquí

Los castros catalogados no están donde hay castros: están donde alguien miró.
Valdoviño aporta `20` a la verdad de campo de Trasancos y Neda `3`, y esa
diferencia dice más sobre la historia de la prospección que sobre la densidad
castrexa real. Sin diluir, el modelo aprende el sesgo del catálogo como si fuera
señal, y una comarca bien prospectada domina el entrenamiento.

## Qué hace exactamente

Rejilla de celda fija en metros, y **un solo positivo por celda**, elegido al
azar con semilla fija para que sea reproducible. Reduce la agregación espacial de
los registros sin tocar los negativos.

**Lo que NO corrige**, y el paper lo dice: la falta de datos en zonas poco
prospectadas. Diluir no inventa castros donde nadie buscó. Y puede infravalorar
zonas donde la densidad alta de registros sí refleja densidad real — un riesgo
que en Galicia hay que tener presente, porque la costa de Ferrolterra pudo ser
genuinamente más poblada.

Uso:
    python3 scripts/spatial_thinning.py --index data/galicia-vignettes-v3/index.tsv \\
        --out data/galicia-vignettes-v3/index_thinned.tsv --cell-m 2000
"""
from __future__ import annotations

import argparse
import csv
import math
import random
from collections import Counter, defaultdict
from pathlib import Path


def a_metros(lon, lat, lat0):
    x = math.radians(lon) * 6371000.0 * math.cos(math.radians(lat0))
    y = math.radians(lat) * 6371000.0
    return x, y


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--index", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--cell-m", type=float, default=2000.0,
                    help="lado de la celda de diluido en metros")
    ap.add_argument("--group", default="castro",
                    help="grupo a diluir; los demas pasan intactos")
    ap.add_argument("--seed", type=int, default=20260805)
    args = ap.parse_args()

    filas = list(csv.DictReader(open(args.index, encoding="utf-8"), delimiter="\t"))
    if not filas:
        raise SystemExit("indice vacio")
    objetivo = [r for r in filas if r.get("group") == args.group]
    resto = [r for r in filas if r.get("group") != args.group]
    if not objetivo:
        raise SystemExit(f"no hay filas del grupo {args.group!r}")

    lat0 = sum(float(r["lat"]) for r in objetivo) / len(objetivo)
    celdas = defaultdict(list)
    for r in objetivo:
        x, y = a_metros(float(r["lon"]), float(r["lat"]), lat0)
        celdas[(int(x // args.cell_m), int(y // args.cell_m))].append(r)

    rng = random.Random(args.seed)
    conservados = [rng.choice(v) for v in celdas.values()]

    print(f"diluido de {args.group!r} con celda de {args.cell_m:.0f} m")
    print(f"  antes: {len(objetivo)}  ->  despues: {len(conservados)} "
          f"({100*len(conservados)/len(objetivo):.1f}%)")
    print(f"  celdas ocupadas: {len(celdas)}")
    lleno = Counter(len(v) for v in celdas.values())
    print("  registros por celda antes del diluido:")
    for k in sorted(lleno)[:6]:
        print(f"    {k} en la celda: {lleno[k]} celdas")
    if max(lleno) > 1:
        peor = max(celdas.values(), key=len)
        print(f"  celda mas agregada: {len(peor)} registros "
              f"(p.ej. {peor[0].get('name','')[:40]!r})")

    # Reparto por split, que es lo que el entrenador va a ver
    antes = Counter(r["split"] for r in objetivo)
    despues = Counter(r["split"] for r in conservados)
    print("  por split:")
    for s in sorted(antes):
        print(f"    {s:12s} {antes[s]:5d} -> {despues.get(s,0):5d}")

    salida = resto + conservados
    salida.sort(key=lambda r: r["sid"])
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0].keys()), delimiter="\t")
        w.writeheader()
        w.writerows(salida)
    print(f"\nescrito: {args.out}  ({len(salida)} filas, "
          f"{len(filas)-len(salida)} descartadas)")
    print("Nota: diluir NO corrige la falta de datos donde nadie prospectó.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
