#!/usr/bin/env python3
"""¿Es el arado o es el alto? Decide entre las dos explicaciones.

Cruza `data/uso_suelo_214.json` (luminancia y textura de la ortofoto) con
`data/topografia_214.json` (prominencia y pendiente del LiDAR) y hace tres cosas,
en orden:

1. **¿Separa la topografia** a hallados de perdidos? Si no separa, no hay
   confusor que valga y el uso del suelo se queda solo con la explicacion.
2. **¿Estan correlacionados** uso del suelo y topografia? Si no lo estan, tampoco
   hay confusion posible.
3. **Estratificado por topografia**: dentro de los sitios de prominencia
   parecida, ¿sigue separando el uso del suelo? Es la pregunta que decide, y se
   hace solo en A Coruna, que es donde el efecto existe.
"""
from __future__ import annotations

import json
import numpy as np
from scipy.stats import mannwhitneyu, spearmanr

suelo = json.load(open("data/uso_suelo_214.json"))
topo = json.load(open("data/topografia_214.json"))

# se cruzan por (bloque, nombre, score); el nombre puede repetirse, el score no
idx = {(r["bloque"], r["nombre"], r["score"]): r for r in topo}
d = []
for r in suelo:
    t = idx.get((r["bloque"], r["nombre"], r["score"]))
    if t:
        d.append({**r, "prominencia": t["prominencia"], "pendiente": t["pendiente"]})
print(f"  {len(d)} castros con las dos medidas (de {len(suelo)} y {len(topo)})\n")

cor = [r for r in d if r["bloque"] == "coruna"]
print(f"  A Coruna: {len(cor)}  ({sum(r['hallado'] for r in cor)} hallados)\n")


def prueba(sub, campo, alt, etiqueta):
    h = np.array([r[campo] for r in sub if r["hallado"]])
    p = np.array([r[campo] for r in sub if not r["hallado"]])
    if len(h) < 3 or len(p) < 3:
        return
    u, pv = mannwhitneyu(p, h, alternative=alt)
    print(f"    {etiqueta:<26}{campo:<12} hallados {h.mean():>7.3f} | "
          f"perdidos {p.mean():>7.3f} | efecto {u/(len(h)*len(p)):.3f} | p={pv:.4f}")


print("  [1] ¿separa la TOPOGRAFIA a hallados de perdidos?")
for campo, alt in (("prominencia", "less"), ("pendiente", "less")):
    prueba(cor, campo, alt, "A Coruna")
    prueba(d, campo, alt, "los cuatro bloques")

print("\n  [2] ¿estan correlacionados uso del suelo y topografia? (A Coruna)")
for a in ("lum", "tex"):
    for b in ("prominencia", "pendiente"):
        r, p = spearmanr([x[a] for x in cor], [x[b] for x in cor])
        print(f"    {a:<5} vs {b:<12} rho={r:>6.3f}  p={p:.4f}")

print("\n  [3] estratificado por prominencia (A Coruna, mitades)")
med = float(np.median([r["prominencia"] for r in cor]))
for etiqueta, sub in (("prominencia BAJA", [r for r in cor if r["prominencia"] <= med]),
                      ("prominencia ALTA", [r for r in cor if r["prominencia"] > med])):
    n_h = sum(r["hallado"] for r in sub)
    print(f"    --- {etiqueta} (n={len(sub)}, {n_h} hallados) ---")
    for campo, alt in (("lum", "greater"), ("tex", "less")):
        prueba(sub, campo, alt, "")
