#!/usr/bin/env python3
"""¿Es `512 m` la distancia de enlace correcta, o solo la heredada?

El enlace agrupa celdas contiguas en **una ficha**. Está en `512 m` por una
razón que no es una medida: es la tolerancia con que `detection_eval.py` decide
si una detección toca un castro. Se copió de ahí, y nunca se barrió.

Decide dinero. Con enlace corto, un mismo yacimiento se parte en varias fichas
y se paga tres veces por un castro. Con enlace largo, dos candidatos distintos
caen en la misma ficha y uno de los dos no se mira.

**La comparación honesta es a fichas iguales, no a `K` iguales.** Cambiar el
enlace cambia cuántas fichas salen de las mismas celdas, así que comparar a `K`
fijo mide dos cosas a la vez. Aquí se interpola: para cada enlace se busca el
`K` que produce ~`N` fichas y se cuenta qué castros salen con ese presupuesto.

Uso:
    python3 scripts/barrer_enlace.py --modelos v7 v11p v12 v14
"""
from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

import numpy as np

BLOQUES = ["coruna", "lugo", "ourense", "pontevedra"]
TOL = 500.0
ENLACES = [256.0, 384.0, 512.0, 768.0, 1024.0]
# presupuestos de FICHAS totales, que es lo que cuesta revisar
FICHAS = [150, 300, 500, 800]


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


def curva(orden, px, py, tx, ty, enlace, ks, sc):
    """Para cada K: (castros hallados, fichas). Se agrupa lo SELECCIONADO.

    **Un castro cuenta como hallado solo si cae dentro de la ficha que se va a
    mirar**, y la ficha es una sola por grupo, centrada en su celda de máxima
    puntuación. Contarlo contra *cualquier* celda del grupo —como hacían las
    tres versiones anteriores de este script— regala castros que nadie llegaría
    a ver: con enlace de `1.024 m` medio bloque se funde en unos pocos grupos
    enormes que «contienen» los `214` castros, y salía que con `150` fichas se
    encontraban todos.

    Es exactamente el fallo que ya se cometió con el «Castro do Monte da Guía»,
    que apareció como hallazgo inédito por comparar el centroide del grupo en
    vez de sus celdas. La lección repetida: **el grupo no es la ficha**.
    """
    out = []
    for K in ks:
        sel = orden[:K]
        sx, sy, ss = px[sel], py[sel], sc[sel]
        grupos = agrupar(sx, sy, enlace)
        enc = set()
        for g in grupos:
            i = max(g, key=lambda j: ss[j])          # la celda de la ficha
            if len(tx):
                d = np.hypot(tx - sx[i], ty - sy[i])
                j = int(np.argmin(d))
                if d[j] <= TOL:
                    enc.add(j)
        out.append((len(enc), len(grupos)))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--modelos", nargs="+",
                    default=["v7", "v11p", "v12", "v14"])
    args = ap.parse_args()

    # Hasta 6.000 celdas: con enlace de 1.024 m casi todo se funde y
    # hacen falta muchas para gastar 800 fichas. Con pocas K, el
    # enlace grande sale artificialmente bien porque nunca llega.
    ks = [25, 50, 75, 100, 150, 200, 300, 400, 600, 800, 1200,
          1600, 2400, 3200, 4500, 6000]
    # acumulado por enlace: lista paralela a `ks` de (castros, fichas)
    acum = {e: [(0, 0)] * len(ks) for e in ENLACES}
    total = 0

    for bloque in BLOQUES:
        preds = {}
        for m in args.modelos:
            f = Path(f"data/sweep_val_{bloque}_{m}.tsv")
            if not f.exists():
                continue
            with f.open(encoding="utf-8") as fh:
                preds[m] = {r["id"]: (float(r["lon"]), float(r["lat"]),
                                      float(r["p_castro"]))
                            for r in csv.DictReader(fh, delimiter="\t")
                            if r.get("p_castro")}
        if len(preds) < 2:
            continue
        ids = sorted(set.intersection(*(set(p) for p in preds.values())))
        vt = Path(f"data/{bloque}_fus_truth_limpia.tsv")
        if not vt.exists():
            vt = Path(f"data/{bloque}_truth_limpia.tsv")
        verdad = list(csv.DictReader(vt.open(encoding="utf-8"), delimiter="\t"))
        total += len(verdad)

        lon = np.array([preds[args.modelos[0]][i][0] for i in ids])
        lat = np.array([preds[args.modelos[0]][i][1] for i in ids])
        k = 111_320.0 * math.cos(math.radians(float(lat.mean())))
        px, py = lon * k, lat * 110_540.0
        tx = np.array([float(r["lon"]) for r in verdad]) * k
        ty = np.array([float(r["lat"]) for r in verdad]) * 110_540.0

        # el mejor combinador medido: promedio de puntuaciones
        sc = np.mean([[preds[m][i][2] for i in ids] for m in preds], axis=0)
        orden = np.argsort(-sc)

        for e in ENLACES:
            res = curva(orden, px, py, tx, ty, e, ks, sc)
            acum[e] = [(a[0] + b[0], a[1] + b[1])
                       for a, b in zip(acum[e], res)]
        print("  %s hecho" % bloque, flush=True)

    print("\nCASTROS de %d hallados con un presupuesto de N FICHAS" % total)
    print("%-9s %s" % ("enlace", "".join("%9d" % n for n in FICHAS)))
    print("-" * 52)
    filas = []
    for e in ENLACES:
        c = [x[0] for x in acum[e]]
        g = [x[1] for x in acum[e]]
        # **Sin interpolar y sin suponer monotonía.** Las fichas NO crecen con
        # `K`: a `512 m` y `K=6.000` salen `48` fichas, menos que con `K=800`,
        # porque al añadir celdas los grupos se sueldan entre sí. La curva sube
        # y luego baja. Dos versiones anteriores de este informe dieron
        # resultados absurdos por dar por hecho lo contrario —una decía que con
        # `150` fichas se hallaban los `208` castros—.
        #
        # La pregunta que no necesita suponer nada: **con un presupuesto de
        # como mucho `N` fichas, ¿cuál es el máximo de castros alcanzable?**
        # Se toma el mejor `K` entre los que caben en el presupuesto.
        # **Y se informa con cuántas fichas se logró, no con el presupuesto
        # nominal.** Un corte duro en `<= N` descarta opciones que se pasan por
        # nueve fichas y las hace retroceder al `K` anterior, que puede estar
        # muy por debajo. Pasó: con corte en `150`, el enlace de `512 m` caía a
        # `47` castros porque su mejor punto gastaba `159`, y `1024 m` parecía
        # ganar por `+27` cuando a fichas comparables pierde por `3`.
        vals = []
        for n in FICHAS:
            caben = [(ci, gi) for ci, gi in zip(c, g) if gi <= n * 1.10]
            vals.append(max(caben) if caben else (float("nan"), 0))
        filas.append((e, [v[0] for v in vals]))
        print("%6.0f m %s   (tope %d castros)"
              % (e, "".join("      —    " if v != v else "%4.0f/%4df " % (v, gi)
                            for v, gi in vals), max(c)))

    print("\nEl enlace actual es 512 m. '—' = ese presupuesto no se alcanza.")
    for i, n in enumerate(FICHAS):
        cand = [f for f in filas if f[1][i] == f[1][i]]
        if not cand:
            print("  a %4d fichas: ningún enlace llega" % n)
            continue
        mejor = max(cand, key=lambda f: f[1][i])
        act = next((f for f in cand if f[0] == 512.0), None)
        if act is None:
            print("  a %4d fichas: mejor %4.0f m (%.1f); 512 m no llega"
                  % (n, mejor[0], mejor[1][i]))
            continue
        d = mejor[1][i] - act[1][i]
        print("  a %4d fichas: mejor %4.0f m (%.1f castros), "
              "512 m da %.1f  -> %+.1f"
              % (n, mejor[0], mejor[1][i], act[1][i], d))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
