#!/usr/bin/env python3
"""Fusión por rango contra fusión por puntuación: ¿cuál gasta menos fichas?

Lo único que ha funcionado en este proyecto sin entrenar nada es **combinar los
modelos que ya existen**: la unión pasa de `95` castros a `180`. Pero las
mezclas probadas hasta hoy son todas **por puntuación** —media, máximo, media
geométrica— y esa familia tiene un defecto conocido: si dos modelos no están
calibrados igual, el más permisivo domina la mezcla. Y aquí no lo están: v11p
quedó descrito como «permisivo» en su propio veredicto y v7 es conservador.

**La fusión por rango elimina esa asimetría por construcción.** Cada modelo
ordena sus celdas y solo se usa la posición, no el valor: da igual que uno
puntúe todo a `0,9` y otro a `0,3`. La receta estándar es *Reciprocal Rank
Fusion* —`s = suma de 1/(k + rango)`, con `k = 60`—, que en recuperación de
información bate a mezclas de puntuación mucho más elaboradas.

## La moneda de la comparación

**No es el `F1`.** Este proyecto ya midió que el punto de operación vale más que
el modelo, y que lo que decide es *cuántos castros aparecen por cuántas fichas
hay que revisar*. Así que se compara así: para cada método, se ordenan los
grupos y se cuenta cuántos castros catalogados caen en los `N` primeros.

Un método es mejor si encuentra más castros con el mismo presupuesto de
revisión. Si gana en `N = 1000` y pierde en `N = 200`, se dice — porque el
presupuesto real está más cerca de `200`.

Uso:
    python3 scripts/fusion_por_rango.py --modelos v7 v11p v12 v14
"""
from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

import numpy as np

BLOQUES = ["coruna", "lugo", "ourense", "pontevedra"]
ENLACE = 512.0
TOL = 500.0
K_RRF = 60.0
# K = cuantas celdas se queda cada metodo. Mismo K para todos:
# es lo que hace justa la comparacion. Se traduce a fichas al
# agrupar, y son las fichas -no K- lo que cuesta dinero.
PRESUPUESTOS = [50, 100, 200, 400, 800, 1600]


def leer(p: Path) -> dict[str, tuple[float, float, float]]:
    out = {}
    with p.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            if r.get("lon") and r.get("p_castro"):
                out[r["id"]] = (float(r["lon"]), float(r["lat"]),
                                float(r["p_castro"]))
    return out


def agrupar(px, py, enlace):
    n = len(px)
    visto = np.zeros(n, bool)
    grupos = []
    for i in range(n):
        if visto[i]:
            continue
        pila, g = [i], []
        visto[i] = True
        while pila:
            j = pila.pop()
            g.append(j)
            nuevos = np.where((np.hypot(px - px[j], py - py[j]) <= enlace)
                              & (~visto))[0]
            visto[nuevos] = True
            pila.extend(nuevos.tolist())
        grupos.append(g)
    return grupos


def castros_en_los_primeros(orden, px, py, tx, ty, seleccion):
    """Castros hallados y fichas gastadas al quedarse con las K mejores celdas.

    **La agrupación va sobre lo SELECCIONADO, no sobre todo.** Agrupar las
    `8.572` celdas del bloque con enlace de `512 m` sobre una rejilla de `256 m`
    las suelda todas en una componente: el primer intento de este script dio
    literalmente `1 grupo` y `214` castros para los siete métodos, que es la
    forma que tiene un resultado de decir que la pregunta estaba mal hecha.

    `K` es el mismo para todos los métodos, que es lo que hace justa la
    comparación: cada uno elige *sus* `K` mejores celdas y se cuenta qué saca.
    """
    out = []
    for K in seleccion:
        sel = orden[:K]
        grupos = agrupar(px[sel], py[sel], ENLACE)
        encontrados = set()
        sx, sy = px[sel], py[sel]
        for g in grupos:
            for i in g:
                if len(tx):
                    d = np.hypot(tx - sx[i], ty - sy[i])
                    j = int(np.argmin(d))
                    if d[j] <= TOL:
                        encontrados.add(j)
        out.append((len(encontrados), len(grupos)))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--modelos", nargs="+", default=["v7", "v11p", "v12", "v14"])
    args = ap.parse_args()

    total_verdad = 0
    # (castros hallados, fichas gastadas) por presupuesto. Tuplas desde el
    # principio: inicializarlo con enteros y sumarlo como tuplas fue el fallo
    # del primer intento.
    acum = {m: [(0, 0)] * len(PRESUPUESTOS) for m in
            list(args.modelos) + ["MEDIA", "MAXIMO", "RANGO (RRF)"]}

    for bloque in BLOQUES:
        preds = {}
        for m in args.modelos:
            f = Path(f"data/sweep_val_{bloque}_{m}.tsv")
            if f.exists():
                preds[m] = leer(f)
        if len(preds) < 2:
            print("%s: menos de dos modelos con barrido — omitido" % bloque)
            continue

        # solo las celdas que TODOS puntuaron: comparar sobre lo mismo
        ids = sorted(set.intersection(*(set(p) for p in preds.values())))
        if not ids:
            continue
        vt = Path(f"data/{bloque}_fus_truth_limpia.tsv")
        if not vt.exists():
            vt = Path(f"data/{bloque}_truth_limpia.tsv")
        verdad = list(csv.DictReader(vt.open(encoding="utf-8"), delimiter="\t"))
        total_verdad += len(verdad)

        lon = np.array([preds[args.modelos[0]][i][0] for i in ids])
        lat = np.array([preds[args.modelos[0]][i][1] for i in ids])
        k = 111_320.0 * math.cos(math.radians(float(lat.mean())))
        px, py = lon * k, lat * 110_540.0
        tx = np.array([float(r["lon"]) for r in verdad]) * k
        ty = np.array([float(r["lat"]) for r in verdad]) * 110_540.0

        sc = {m: np.array([preds[m][i][2] for i in ids]) for m in preds}

        # rangos: 0 = la celda mejor puntuada de ese modelo
        rangos = {m: np.empty(len(ids), int) for m in sc}
        for m, v in sc.items():
            rangos[m][np.argsort(-v)] = np.arange(len(ids))

        metodos = {}
        for m in sc:
            metodos[m] = np.argsort(-sc[m])
        metodos["MEDIA"] = np.argsort(-np.mean(list(sc.values()), axis=0))
        metodos["MAXIMO"] = np.argsort(-np.max(list(sc.values()), axis=0))
        rrf = np.sum([1.0 / (K_RRF + rangos[m]) for m in rangos], axis=0)
        metodos["RANGO (RRF)"] = np.argsort(-rrf)

        print("\n=== %s: %d celdas comunes, %d castros ==="
              % (bloque, len(ids), len(verdad)))
        print("  %-13s %s" % ("(K celdas)",
                              " ".join("%9d" % k for k in PRESUPUESTOS)))
        for nombre, orden in metodos.items():
            res = castros_en_los_primeros(orden, px, py, tx, ty, PRESUPUESTOS)
            acum.setdefault(nombre, [(0, 0)] * len(PRESUPUESTOS))
            acum[nombre] = [(a[0] + b[0], a[1] + b[1])
                            for a, b in zip(acum[nombre], res)]
            print("  %-13s %s"
                  % (nombre, " ".join("%4d/%4df" % (h, g) for h, g in res)))

    print("\n" + "=" * 78)
    print("CASTROS HALLADOS de %d  /  FICHAS a revisar, sumando los 4 bloques"
          % total_verdad)
    print("%-13s %s" % ("metodo",
                        " ".join("%9d" % k for k in PRESUPUESTOS)))
    print("-" * 78)
    for nombre, v in sorted(acum.items(), key=lambda kv: -kv[1][2][0]):
        print("%-13s %s" % (nombre,
                            " ".join("%4d/%4df" % (h, g) for h, g in v)))

    print("\nLa columna que decide es la que gasta ~300 fichas en total.")
    rrf = acum["RANGO (RRF)"]
    otros = {n: v for n, v in acum.items() if n != "RANGO (RRF)"}
    # se compara al presupuesto de fichas mas parecido, no al mismo K
    i = min(range(len(PRESUPUESTOS)), key=lambda j: abs(rrf[j][1] - 300))
    mejor_n, mejor_v = max(otros.items(), key=lambda kv: kv[1][i][0])
    print("  con K=%d celdas -> %d fichas:" % (PRESUPUESTOS[i], rrf[i][1]))
    print("    fusión por rango: %d castros" % rrf[i][0])
    print("    mejor de los demás (%s): %d" % (mejor_n, mejor_v[i][0]))
    d = rrf[i][0] - mejor_v[i][0]
    print("    diferencia: %+d castros%s"
          % (d, "" if d else "  — NO APORTA"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
