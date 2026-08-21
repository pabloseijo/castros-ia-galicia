#!/usr/bin/env python3
"""¿El arado explica qué castros se pierden? Contraste sobre los 214.

Lee `data/uso_suelo_214.json` —luminancia y textura de la ortofoto en el centro
de `256 m` de cada castro catalogado, mas la mejor puntuacion de v7 a `250 m`— y
contesta tres preguntas en este orden, que es de menor a mayor exigencia:

1. **¿Se separan hallados y perdidos** por uso del suelo, en el conjunto?
2. **¿Pasa en los cuatro bloques** o solo en A Coruna? Si es general, es un
   mecanismo; si es de uno, es una peculiaridad de ese sitio.
3. **¿Sobrevive el efecto dentro de cada bloque?** Es el control que importa: si
   A Coruna tiene a la vez mas campo abierto y peor recall, el efecto global
   podria ser solo esa correlacion entre bloques y no valer dentro de ninguno.
"""
from __future__ import annotations

import json
import numpy as np
from scipy.stats import mannwhitneyu

d = json.load(open("data/uso_suelo_214.json"))
print(f"  {len(d)} castros con ortofoto\n")


def contraste(sub, campo, alt):
    h = np.array([r[campo] for r in sub if r["hallado"]])
    p = np.array([r[campo] for r in sub if not r["hallado"]])
    if len(h) < 3 or len(p) < 3:
        return None
    u, pv = mannwhitneyu(p, h, alternative=alt)
    return len(h), len(p), h.mean(), p.mean(), u / (len(h) * len(p)), pv


print("  [1] los 214 juntos")
print(f"      {'indice':<12}{'hallados':>10}{'perdidos':>10}{'efecto':>9}{'p':>10}")
for campo, alt in (("lum", "greater"), ("tex", "less")):
    r = contraste(d, campo, alt)
    if r:
        nh, np_, mh, mp, ef, pv = r
        print(f"      {campo:<12}{mh:>10.1f}{mp:>10.1f}{ef:>9.3f}{pv:>10.4f}"
              f"   (n {nh} vs {np_})")

print("\n  [2] y [3] dentro de cada bloque")
print(f"      {'bloque':<12}{'indice':<6}{'hallados':>10}{'perdidos':>10}"
      f"{'efecto':>9}{'p':>10}")
for b in ("lugo", "coruna", "ourense", "pontevedra"):
    sub = [r for r in d if r["bloque"] == b]
    for campo, alt in (("lum", "greater"), ("tex", "less")):
        r = contraste(sub, campo, alt)
        if r:
            nh, np_, mh, mp, ef, pv = r
            marca = "*" if pv < 0.05 else " "
            print(f"      {b:<12}{campo:<6}{mh:>10.1f}{mp:>10.1f}{ef:>9.3f}"
                  f"{pv:>10.4f}{marca}  (n {nh} vs {np_})")
