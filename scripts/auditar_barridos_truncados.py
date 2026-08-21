#!/usr/bin/env python3
"""¿Hay algún veredicto de este proyecto apoyado en un barrido a medias?

El 2026-08-10 el barrido de v9 en Pontevedra murió por memoria con `409` de
`6.877` filas, y `detection_eval.py` lo evaluó igual: dio `F1 0,000`. Esa cifra
es correcta sobre lo que había y **completamente engañosa** sobre el modelo. El
aviso de cobertura estaba impreso —`2 de 40 yacimientos con celda a <256 m`— y
si nadie lo lee, un modelo sano queda anotado como refutado.

No es hipotético: el propio `sweep_grid_lidar.py` lleva escrito un caso del
`2026-08-09` en que un barrido murió por memoria y al relanzarse dejó un
fichero sin cabecera que el evaluador leyó como `0` predicciones.

Este script recorre **todos** los barridos guardados y busca los que están
cortos respecto a la referencia de su bloque. La comparación correcta no es
contra un número absoluto sino **contra otro barrido del mismo bloque**: la
rejilla es la misma para todos los modelos, así que dos barridos del mismo
bloque deben tener aproximadamente las mismas filas. El que se queda corto es
el sospechoso.

Lo que este script NO hace: decidir si un veredicto era falso. Dice qué
ficheros están cortos y cuánto. Releer el veredicto que se apoya en ellos es
trabajo de quien lo escribió.

Uso:
    python3 scripts/auditar_barridos_truncados.py
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

# Por debajo de esta fracción de la referencia, el barrido está cortado.
# `0,90` y no `0,99` porque hay diferencias legítimas: un modelo puede rechazar
# celdas con pocos puntos de suelo y la densidad objetivo cambia entre corridas.
UMBRAL_SOSPECHA = 0.90


def main() -> int:
    d = Path("data")
    barridos = sorted(d.glob("sweep_val_*.tsv"))
    if not barridos:
        print("no hay barridos en data/", file=sys.stderr)
        return 1

    por_bloque: dict[str, list[tuple[str, int, bool]]] = defaultdict(list)
    for f in barridos:
        m = re.match(r"sweep_val_([a-z]+)_(.+)\.tsv$", f.name)
        if not m:
            continue
        bloque, modelo = m.group(1), m.group(2)
        with f.open(encoding="utf-8", errors="replace") as fh:
            primera = fh.readline()
            n = sum(1 for _ in fh)
        cabecera = primera.startswith("id\t")
        por_bloque[bloque].append((modelo, n if cabecera else n + 1, cabecera))

    sospechosos = []
    print("%-12s %-14s %8s %8s  %s" % ("bloque", "modelo", "filas", "vs ref",
                                       "estado"))
    print("-" * 62)
    for bloque in sorted(por_bloque):
        entradas = por_bloque[bloque]
        ref = max(n for _, n, _ in entradas)
        for modelo, n, cabecera in sorted(entradas, key=lambda t: -t[1]):
            frac = n / ref if ref else 0.0
            estado = []
            if not cabecera:
                estado.append("SIN CABECERA")
            if frac < UMBRAL_SOSPECHA:
                estado.append("CORTADO")
                sospechosos.append((bloque, modelo, n, ref, frac))
            print("%-12s %-14s %8d %7.1f%%  %s"
                  % (bloque, modelo, n, frac * 100,
                     " + ".join(estado) if estado else "ok"))
        print()

    if not sospechosos:
        print("PROBLEMAS: ninguno. Todos los barridos llegan al %d%% de la "
              "referencia de su bloque." % (UMBRAL_SOSPECHA * 100))
        return 0

    print("=" * 62)
    print("SOSPECHOSOS: %d barridos por debajo del %d%%\n"
          % (len(sospechosos), UMBRAL_SOSPECHA * 100))
    for bloque, modelo, n, ref, frac in sospechosos:
        print("  %s / %s: %d filas de ~%d (%.0f%%)"
              % (bloque, modelo, n, ref, frac * 100))
    print("\nCada uno de estos puede tener un F1 anotado que mide el barrido y")
    print("no el modelo. Releer el veredicto que se apoya en ellos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
