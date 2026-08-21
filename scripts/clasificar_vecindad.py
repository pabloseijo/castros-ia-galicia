#!/usr/bin/env python3
"""Qué tiene cerca cada candidato, y qué significa cada cosa.

`verificar_todos.py` dijo que `375` de `419` tienen «algo conocido muy cerca», y
esa cifra **engaña**: cruzaba contra todos los ficheros de `data/` a la vez, y
ahí conviven tres cosas que quieren decir lo contrario entre sí.

  · **Un yacimiento catalogado cerca** → el candidato probablemente ES ese
    yacimiento. Es un colado y hay que sacarlo.
  · **Un negativo duro minado cerca** —cantera, polígono, terraza— → evidencia
    **en contra**: es el mismo artefacto que ya se etiquetó como no-castro.
  · **Un falso positivo de un barrido anterior cerca** → **no dice nada**. Es la
    misma detección hecha por otro modelo, o por el mismo antes. Contarlo como
    «algo conocido» es circular.

Esto los separa y da la cifra que sí se puede usar.
"""
from __future__ import annotations

import csv
import glob
import math
from collections import Counter
from pathlib import Path

import numpy as np

TOL_CAT, TOL_NEG = 400.0, 250.0


def leer(p):
    with Path(p).open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def clasificar(fichero: str, fila: dict) -> str:
    """A qué familia pertenece un punto del repositorio."""
    b = Path(fichero).name
    if b.startswith("fp_") or "hard_negative" in str(fila.get("group", "")):
        return "deteccion_previa"
    grupo = (fila.get("group") or "").strip()
    if "negativos-osm" in b or grupo in ("modern", "agricultural", "hilltop", "random"):
        return "negativo"
    if grupo.startswith("castro") or grupo.startswith("mamoa") or "truth" in b \
            or "castro" in b.lower() or "mamoa" in b.lower():
        return "yacimiento"
    return "otro"


familias = {"yacimiento": [], "negativo": [], "deteccion_previa": [], "otro": []}
for f in sorted(set(glob.glob("data/**/*.tsv", recursive=True))):
    b = Path(f).name
    if any(x in b for x in ("sweep", "candidatos")) or "tmp-union" in f or "orto" in f:
        continue
    try:
        rs = leer(f)
    except Exception:
        continue
    if not rs or not ({"lon", "lat"} <= set(rs[0])):
        continue
    for r in rs:
        try:
            familias[clasificar(f, r)].append(
                (float(r["lon"]), float(r["lat"]),
                 (r.get("name") or r.get("nombre") or "?")[:38], b))
        except (TypeError, ValueError):
            pass

for k, v in familias.items():
    print(f"  {k:<18} {len(v):>7} puntos")

arr = {k: np.array([[p[0], p[1]] for p in v]) if v else np.empty((0, 2))
       for k, v in familias.items()}

cand = leer("data/candidatos-ineditos.tsv")
etiquetas, filas = Counter(), []
for c in cand:
    lon, lat = float(c["lon"]), float(c["lat"])
    k = 111_320.0 * math.cos(math.radians(lat))

    def dmin(fam):
        A = arr[fam]
        if not len(A):
            return 9e9, -1
        d = np.hypot((A[:, 0] - lon) * k, (A[:, 1] - lat) * 110_540.0)
        i = int(np.argmin(d))
        return float(d[i]), i

    d_yac, i_yac = dmin("yacimiento")
    d_neg, _ = dmin("negativo")

    if d_yac < TOL_CAT:
        et = "ya catalogado"
    elif d_neg < TOL_NEG:
        et = "sobre un negativo conocido"
    else:
        et = "sin explicacion conocida"
    etiquetas[et] += 1
    filas.append({**c, "veredicto": et,
                  "d_yacimiento": f"{d_yac:.0f}" if d_yac < 9e8 else "",
                  "yacimiento": familias["yacimiento"][i_yac][2] if i_yac >= 0 else "",
                  "d_negativo": f"{d_neg:.0f}" if d_neg < 9e8 else ""})

print(f"\n  === los {len(cand)} candidatos ===")
for et in ("ya catalogado", "sobre un negativo conocido", "sin explicacion conocida"):
    n = etiquetas[et]
    print(f"  {et:<28} {n:>4}   {100*n/len(cand):>4.0f}%")

limpios = [r for r in filas if r["veredicto"] == "sin explicacion conocida"]
limpios.sort(key=lambda r: -float(r["score"]))
dest = Path("data/candidatos-limpios.tsv")
with dest.open("w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=list(filas[0].keys()), delimiter="\t")
    w.writeheader()
    w.writerows(limpios)
print(f"\n  -> {dest} ({len(limpios)} candidatos sin nada conocido que los explique)")
for r in limpios[:8]:
    print(f"    {r['score']}  {r['bloque']:<11} {r['lat']},{r['lon']}  "
          f"yacimiento a {r['d_yacimiento']} m")
