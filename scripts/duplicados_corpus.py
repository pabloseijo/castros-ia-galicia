#!/usr/bin/env python3
"""Fuga L1.4: ¿hay el mismo sitio dos veces con `sid` distinto, y a los dos lados?

Kapoor y Narayanan (`10.1016/j.patter.2023.100804`) listan los duplicados como uno
de los ocho tipos de fuga: si un registro aparece en entrenamiento y en test con
identificadores distintos, el modelo se examina de algo que ya vio.

**Aquí nunca se ha medido**, y el corpus fusiona tres fuentes —catalogo oficial,
OSM y el maestro debil—, que es justo el escenario donde aparecen duplicados: el
mismo castro con nombre distinto y coordenadas a pocos metros.

Se mide en metros, no por identificador: dos entradas del mismo sitio no comparten
`sid` ni nombre, pero sí posicion. El umbral por defecto son `100 m`, muy por
debajo del radio de `500 m` con que la evaluacion considera acertado un castro.
"""
from __future__ import annotations

import argparse
import csv
import math
from collections import Counter, defaultdict
from pathlib import Path


def metros(a, b):
    dlat = (a[0] - b[0]) * 111320.0
    dlon = (a[1] - b[1]) * 111320.0 * math.cos(math.radians((a[0] + b[0]) / 2))
    return math.hypot(dlat, dlon)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--index", type=Path, required=True)
    ap.add_argument("--radio-m", type=float, default=100.0)
    args = ap.parse_args()

    filas = []
    with args.index.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            try:
                filas.append((float(r["lat"]), float(r["lon"]),
                              (r.get("split") or "").strip(),
                              (r.get("group") or "").strip(),
                              (r.get("name") or "").strip(), r["sid"]))
            except (KeyError, TypeError, ValueError):
                continue
    print(f"corpus: {len(filas)} viñetas | radio de duplicado {args.radio_m:.0f} m")

    # rejilla gruesa para no comparar todo con todo
    celda = args.radio_m / 111320.0 * 2
    cubos = defaultdict(list)
    for i, f in enumerate(filas):
        cubos[(int(f[0] / celda), int(f[1] / celda))].append(i)

    pares, cruzados = 0, []
    for (cx, cy), idx in cubos.items():
        vec = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                vec.extend(cubos.get((cx + dx, cy + dy), ()))
        for i in idx:
            for j in vec:
                if j <= i:
                    continue
                a, b = filas[i], filas[j]
                if metros((a[0], a[1]), (b[0], b[1])) > args.radio_m:
                    continue
                pares += 1
                if a[2] != b[2] and {a[2], b[2]} & {"train"}:
                    cruzados.append((a, b))

    print(f"\n  pares a menos de {args.radio_m:.0f} m: {pares}")
    print(f"  de ellos, con splits DISTINTOS e implicando a train: {len(cruzados)}")
    if cruzados:
        print(f"\n  {'split A':<12}{'split B':<14}{'grupo A':<16}nombre A")
        for a, b in cruzados[:12]:
            print(f"    {a[2]:<12}{b[2]:<14}{a[3][:14]:<16}{(a[4] or '(sin nombre)')[:34]}")
        cc = Counter(tuple(sorted((a[2], b[2]))) for a, b in cruzados)
        print(f"\n  combinaciones: {dict(cc)}")
        pos = sum(1 for a, b in cruzados
                  if a[3].startswith(("castro", "mamoa")) or b[3].startswith(("castro", "mamoa")))
        print(f"  de los cruzados, con un positivo implicado: {pos}")
        print("\n  *** FUGA L1.4: el mismo sitio esta a los dos lados de la particion ***")
        return 1
    print("\n  OK: ningun sitio duplicado cruza la particion")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
