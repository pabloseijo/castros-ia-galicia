#!/usr/bin/env python3
"""¿Se parecen los candidatos a los castros conservados o al campo labrado?

Contrasta los `120` candidatos mejor puntuados contra los tres grupos de
referencia medidos el mismo dia sobre los `214` castros catalogados:

- **hallados**: castros que el modelo detecta. Si los candidatos son castros aun
  sin catalogar, deberian parecerse a estos.
- **perdidos**: castros catalogados que el modelo no detecta, y que estan en
  campo abierto — es el grupo que la prediccion dice que NO deben parecerse.

La prediccion escrita antes de mirar: los candidatos estaran **bajo monte**, o
sea oscuros y rugosos, como los hallados.
"""
from __future__ import annotations

import json
import numpy as np
from scipy.stats import mannwhitneyu

cat = json.load(open("data/uso_suelo_214.json"))
cand = json.load(open("data/uso_suelo_candidatos.json"))

hall = [r for r in cat if r["hallado"]]
perd = [r for r in cat if not r["hallado"]]

print(f"  {'grupo':<26}{'n':>5}{'luminancia':>12}{'textura':>10}")
print("  " + "-" * 54)
for nombre, g in (("catalogados HALLADOS", hall), ("catalogados PERDIDOS", perd),
                  ("CANDIDATOS ineditos", cand)):
    L = np.array([r["lum"] for r in g]); T = np.array([r["tex"] for r in g])
    print(f"  {nombre:<26}{len(g):>5}{L.mean():>12.1f}{T.mean():>10.2f}")

print("\n  contrastes (Mann-Whitney, dos colas):")
for etiqueta, g in (("contra los HALLADOS", hall), ("contra los PERDIDOS", perd)):
    for campo, nombre in (("lum", "luminancia"), ("tex", "textura")):
        a = np.array([r[campo] for r in cand]); b = np.array([r[campo] for r in g])
        u, p = mannwhitneyu(a, b, alternative="two-sided")
        ef = u / (len(a) * len(b))
        marca = "  <-- se parecen" if p > 0.05 else "  <-- DIFIEREN"
        print(f"    candidatos {etiqueta:<22}{nombre:<12} efecto {ef:.3f}"
              f"  p={p:.4f}{marca}")
