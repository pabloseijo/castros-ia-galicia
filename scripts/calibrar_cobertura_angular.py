#!/usr/bin/env python3
"""¿Sirve la cobertura angular del anillo para separar castro de falso positivo?

`morfologia_candidatos.py` emite `cobertura_angular` desde el `2026-08-08` con
una nota en su propia cabecera: **«sin calibrar todavía — se emite como columna
para mirarla contra los veredictos visuales, no como criterio»**. Nunca se
miró contra verdad de campo. Esto lo mira.

## Por qué esta columna y no otra

La literatura de detección de castros nombra la **pista forestal** como falso
positivo dominante, y la separa del recinto por una sola propiedad geométrica:
**la pista sigue la curva de nivel pero no cierra**. El contraste del perfil
radial ya se calibró y salió `AUC 0,663` —ordena, no decide—, y la revisión
visual explicó por qué: un lazo de autovía da un pico tan alto como un
parapeto. Lo que el ojo usa para distinguirlos no es la altura del pico sino
**si el anillo da la vuelta entera**.

`cobertura_angular` = fracción de los `72` sectores de `5°` del anillo cuyo
valor medio supera la mediana de la viñeta.

## Lo que se mide

`AUC` de cada descriptor separando los `113` aciertos de los `230` falsos del
punto de operación de v7, con intervalo de confianza por bootstrap. Y, lo que
de verdad decide: **cuántos falsos se quitarían perdiendo cuántos castros**.

Un descriptor solo vale como criba si existe un corte que tire muchos falsos y
casi ningún acierto. Un `AUC` de `0,70` puede no tener ese corte.

Uso:
    python3 scripts/calibrar_cobertura_angular.py \\
        --morfo data/morfo_calib.tsv --etiquetas data/calib_morfo.tsv
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np

COLUMNAS = ["cobertura_angular", "contraste", "radio_m", "n_maximos"]


def auc(pos: np.ndarray, neg: np.ndarray) -> float:
    """AUC = P(un positivo puntúa más que un negativo), con empates a 0,5."""
    if not len(pos) or not len(neg):
        return float("nan")
    todos = np.concatenate([pos, neg])
    r = np.empty(len(todos), float)
    orden = np.argsort(todos)
    t = todos[orden]
    i = 0
    while i < len(t):
        j = i
        while j + 1 < len(t) and t[j + 1] == t[i]:
            j += 1
        r[orden[i:j + 1]] = (i + j) / 2.0 + 1
        i = j + 1
    return (r[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2.0) / \
        (len(pos) * len(neg))


def ic_bootstrap(pos, neg, n=2000, semilla=7):
    rng = np.random.default_rng(semilla)
    vals = [auc(rng.choice(pos, len(pos), replace=True),
                rng.choice(neg, len(neg), replace=True)) for _ in range(n)]
    return np.percentile(vals, [2.5, 97.5])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--morfo", type=Path, default=Path("data/morfo_calib.tsv"))
    ap.add_argument("--etiquetas", type=Path,
                    default=Path("data/calib_morfo.tsv"))
    args = ap.parse_args()

    etq = {(r["bloque"], r["n"]): r["etiqueta"]
           for r in csv.DictReader(args.etiquetas.open(encoding="utf-8"),
                                   delimiter="\t")}
    filas = list(csv.DictReader(args.morfo.open(encoding="utf-8"),
                                delimiter="\t"))
    print("fichas medidas: %d   etiquetas: %d" % (len(filas), len(etq)))

    datos = {c: {"castro": [], "falso": []} for c in COLUMNAS}
    sin_etiqueta = 0
    for r in filas:
        e = etq.get((r["bloque"], r["n"]))
        if e is None:
            sin_etiqueta += 1
            continue
        for c in COLUMNAS:
            v = r.get(c, "")
            if v not in ("", None):
                try:
                    datos[c][e].append(float(v))
                except ValueError:
                    pass
    if sin_etiqueta:
        print("sin etiqueta: %d (omitidas)" % sin_etiqueta)

    print("\n%-20s %6s %6s  %8s %8s  %s"
          % ("descriptor", "n+", "n−", "media+", "media−", "AUC (IC95%)"))
    print("-" * 76)
    resultados = {}
    for c in COLUMNAS:
        p = np.array(datos[c]["castro"])
        n = np.array(datos[c]["falso"])
        if len(p) < 10 or len(n) < 10:
            print("%-20s  faltan datos (%d/%d)" % (c, len(p), len(n)))
            continue
        a = auc(p, n)
        lo, hi = ic_bootstrap(p, n)
        resultados[c] = (a, lo, hi, p, n)
        print("%-20s %6d %6d  %8.3f %8.3f  %.3f [%.3f–%.3f]"
              % (c, len(p), len(n), p.mean(), n.mean(), a, lo, hi))

    print("\n%s" % ("=" * 76))
    print("LO QUE DECIDE: ¿hay un corte que tire falsos sin perder castros?\n")
    for c, (a, lo, hi, p, n) in resultados.items():
        # se prueba en los dos sentidos: el descriptor puede ser alto o bajo
        mejor = None
        for signo in (1, -1):
            cortes = np.unique(np.concatenate([p, n]))
            for t in cortes:
                keep_p = (signo * p >= signo * t).mean()
                keep_n = (signo * n >= signo * t).mean()
                if keep_p >= 0.95:                     # perder <=5% de castros
                    tirados = 1 - keep_n
                    if mejor is None or tirados > mejor[0]:
                        mejor = (tirados, t, signo, keep_p)
        if mejor is None or mejor[0] < 0.05:
            print("  %-20s ningún corte útil: perdiendo ≤5%% de castros no "
                  "quita ni el 5%% de falsos" % c)
        else:
            tirados, t, signo, keep_p = mejor
            print("  %-20s corte %s %.3f -> quita el %.0f%% de los falsos "
                  "conservando el %.0f%% de los castros"
                  % (c, ">=" if signo > 0 else "<=", t,
                     100 * tirados, 100 * keep_p))

    if resultados:
        c = "cobertura_angular"
        if c in resultados:
            a, lo, hi, _, _ = resultados[c]
            print("\nVEREDICTO sobre la cobertura angular:")
            if hi < 0.60:
                print("  AUC %.3f con IC hasta %.3f: NO separa. La hipótesis de"
                      " que\n  «la pista no cierra y el castro sí» no se"
                      " sostiene en estos datos." % (a, hi))
            elif lo > 0.70:
                print("  AUC %.3f con IC desde %.3f: separa de verdad."
                      % (a, lo))
            else:
                print("  AUC %.3f [%.3f–%.3f]: ordena, no decide — como el"
                      " contraste\n  del perfil. Sirve para priorizar la cola"
                      " de revisión, no para cribar." % (a, lo, hi))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
