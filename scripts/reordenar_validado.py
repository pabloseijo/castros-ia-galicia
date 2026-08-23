#!/usr/bin/env python3
"""¿La reordenacion aguanta fuera del bloque donde se ajusto el peso?

La primera pasada encontro que `score - 0,25 x n_maximos` mejora la cabecera de
la cola. Pero el peso se eligio MIRANDO ese mismo resultado, que es sobreajuste
puro: el proyecto ya tiene medido que elegir el umbral con oraculo da +0,010 y
dejando el bloque fuera da -0,001.

Asi que aqui el peso se elige en tres bloques y se mide en el cuarto. Cuatro
veces, una por bloque.
"""
import csv
from pathlib import Path


def carga(p):
    return list(csv.DictReader(open(p, encoding="utf-8"), delimiter="\t"))


def num(v, d=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


etiq = {}
for f in ("data/calib_morfo.tsv", "data/control_morfo.tsv"):
    for r in carga(f):
        etiq[(r["bloque"], r["n"])] = {"etiqueta": r.get("etiqueta", ""),
                                       "score": num(r.get("score")),
                                       "bloque": r["bloque"]}
morfo = {}
for f in ("data/morfo_calib.tsv", "data/morfo_control.tsv"):
    for r in carga(f):
        morfo[(r["bloque"], r["n"])] = r

filas = []
for k, e in etiq.items():
    m = morfo.get(k)
    if not m or e["score"] is None:
        continue
    nm = num(m.get("n_maximos"))
    if nm is None:
        continue
    filas.append({"bloque": e["bloque"], "score": e["score"], "n_maximos": nm,
                  "es_castro": e["etiqueta"] in ("castro", "1", "positivo")})

MX = max(abs(f["n_maximos"]) for f in filas) or 1.0
PESOS = [0.0, 0.1, 0.25, 0.5, 0.75, 1.0]
BLOQUES = sorted({f["bloque"] for f in filas})
K = 50


def castros_en_cabeza(sub, w, k=K):
    orden = sorted(sub, key=lambda f: f["score"] - w * f["n_maximos"] / MX, reverse=True)
    return sum(1 for f in orden[:k] if f["es_castro"])


print(f"{len(filas)} puntos | bloques: {', '.join(BLOQUES)} | k={K}\n")
print(f"{'bloque fuera':13} {'peso elegido':>13} {'castros con w=0':>16} {'castros con w':>14} {'dif':>6}")
tot0 = totw = 0
for b in BLOQUES:
    dentro = [f for f in filas if f["bloque"] != b]
    fuera = [f for f in filas if f["bloque"] == b]
    if len(fuera) < K:
        kk = max(10, len(fuera) // 2)
    else:
        kk = K
    mejor_w, mejor = 0.0, -1
    for w in PESOS:
        c = castros_en_cabeza(dentro, w)
        if c > mejor:
            mejor, mejor_w = c, w
    c0 = castros_en_cabeza(fuera, 0.0, kk)
    cw = castros_en_cabeza(fuera, mejor_w, kk)
    tot0 += c0
    totw += cw
    print(f"{b:13} {mejor_w:>13.2f} {c0:>16} {cw:>14} {cw-c0:>+6}")

print()
print(f"{'TOTAL':13} {'':>13} {tot0:>16} {totw:>14} {totw-tot0:>+6}")
print()
if totw > tot0:
    print("La reordenacion aguanta fuera del bloque donde se ajusto el peso.")
elif totw == tot0:
    print("Empate: el peso ajustado NO aporta nada fuera de su bloque.")
else:
    print("PEOR fuera: era sobreajuste. La reordenacion no sirve.")
