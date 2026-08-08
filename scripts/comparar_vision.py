#!/usr/bin/env python3
"""Compara dos revisiones de fichas (p. ej. 3B contra 7B) sobre lo que importa.

**Lo que importa no es el acuerdo entre ellos**, sino si los campos *varian*. El
`2026-08-08` se midio que `qwen2.5vl:3b` contesta «no» a `aterrazamiento` en `39`
de `39` fichas y lo mismo a `parcelario_agricola`, que son los dos confusores
dominantes de Ourense y Lugo. Un campo constante no filtra nada por muy bien
escrito que este el prompt, y ese era el proposito entero de delegar.

Asi que esto reporta, por modelo y campo: el reparto de valores, la **entropia
normalizada** (`0` = constante e inutil, `1` = reparto uniforme) y, cuando hay
lecturas humanas, el acuerdo con su intervalo y su `p` contra el azar.

Uso:
    python3 scripts/comparar_vision.py data/revision_local.tsv data/revision_local_7b.tsv
"""
from __future__ import annotations

import csv
import math
import sys
from collections import Counter
from pathlib import Path

COLS = ["ficha", "bloque", "recinto_cerrado", "aterrazamiento",
        "parcelario_agricola", "obra_moderna", "entorno", "cima_natural",
        "confianza_castro", "nota"]
CAMPOS = COLS[2:8]

# Lecturas humanas del 2026-08-08 (wiki: revision-visual-candidatos-2026-08-08).
HUMANO = {
    "pontevedra/cand-001": "dudoso",  "coruna/cand-001": "prometedor",
    "lugo/cand-001": "dudoso",        "ourense/cand-001": "dudoso",
    "ourense/cand-002": "no",         "pontevedra/cand-002": "prometedor",
    "ourense/cand-003": "dudoso",     "lugo/cand-002": "no",
}


def leer(p: Path):
    filas = {}
    if not p.exists():
        return filas
    for c in csv.reader(p.open(encoding="utf-8"), delimiter="\t"):
        if len(c) >= 9 and c[0] != "ficha":
            filas[c[0]] = dict(zip(COLS, c))
    return filas


def entropia_norm(vals):
    """0 = campo constante (no informa), 1 = reparto uniforme."""
    c = Counter(vals)
    n = sum(c.values())
    if n == 0 or len(c) < 2:
        return 0.0
    h = -sum((v/n) * math.log2(v/n) for v in c.values())
    return h / math.log2(len(c))


def binom_cola(k, n, p):
    return sum(math.comb(n, i) * p**i * (1-p)**(n-i) for i in range(k, n+1))


def veredicto(r):
    conf = float(r["confianza_castro"] or 0)
    cer = r["recinto_cerrado"]
    if cer == "si" and conf >= 0.75:
        return "prometedor"
    return "no" if cer == "no" else "dudoso"


def main() -> int:
    rutas = [Path(a) for a in sys.argv[1:]] or [Path("data/revision_local.tsv")]
    datos = {r.stem: leer(r) for r in rutas}

    for nombre, filas in datos.items():
        print(f"\n{'='*66}\n{nombre}: {len(filas)} fichas\n{'='*66}")
        if not filas:
            print("  vacio"); continue
        print(f"{'campo':<22}{'entropia':>10}  reparto")
        for campo in CAMPOS:
            vals = [v[campo] for v in filas.values()]
            e = entropia_norm(vals)
            marca = "  <-- CONSTANTE, no filtra" if e < 0.15 else ""
            print(f"  {campo:<20}{e:>10.2f}  {dict(Counter(vals))}{marca}")

        pares = [(HUMANO[k], veredicto(v)) for k, v in filas.items() if k in HUMANO]
        if pares:
            ac = sum(a == b for a, b in pares)
            n = len(pares)
            p = binom_cola(ac, n, 1/3)
            print(f"\n  acuerdo con lectura humana: {ac}/{n} = {ac/n:.0%} "
                  f"(azar 33%) | P(>= {ac} por azar) = {p:.3f}")
            print(f"  -> {'NO se distingue del azar' if p > 0.05 else 'se distingue del azar'}")

    if len(datos) == 2:
        a, b = datos.values()
        comunes = set(a) & set(b)
        print(f"\n{'='*66}\ncoinciden entre modelos, sobre {len(comunes)} fichas comunes\n{'='*66}")
        for campo in CAMPOS:
            ig = sum(a[k][campo] == b[k][campo] for k in comunes)
            print(f"  {campo:<22}{ig}/{len(comunes)} = {ig/max(len(comunes),1):.0%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
