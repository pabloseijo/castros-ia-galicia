#!/usr/bin/env python3
"""Recalcula el F1 de despliegue de TODAS las versiones desde los barridos crudos.

No lee ningun log ni ninguna pagina de la wiki: vuelve a puntuar cada fichero
`sweep_val_<bloque>_<version>.tsv` contra la verdad del bloque, con el mismo
umbral y la misma mascara de entrenamiento que uso la version publicada.

Existe porque en este proyecto ya han circulado tres cifras que no eran lo que
parecian: dos barridos con el `bbox` mal tecleado (otro trozo de Galicia), un
bloque dado por completo al `79%`, y un barrido reanudado sin cabecera que se
leyo como `0` predicciones. **Una cifra que no se puede recalcular no es un
resultado, es un recuerdo.**

Marca ademas los barridos incompletos comparandolos con el de v7 del mismo
bloque, que es la referencia de tamano.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

BLOQUES = ["lugo", "coruna", "ourense", "pontevedra"]
UMBRAL = "0.70"

versiones = defaultdict(dict)
for p in sorted(Path("data").glob("sweep_val_*.tsv")):
    m = re.match(r"sweep_val_([a-z]+)_(.+)\.tsv$", p.name)
    if not m or m.group(1) not in BLOQUES:
        continue
    versiones[m.group(2)][m.group(1)] = p

ref = {b: Path(f"data/sweep_val_{b}_v7.tsv") for b in BLOQUES}
tam_ref = {b: (p.stat().st_size if p.exists() else 0) for b, p in ref.items()}

filas = []
for v in sorted(versiones):
    fila = {"version": v}
    for b in BLOQUES:
        p = versiones[v].get(b)
        if p is None:
            fila[b] = None
            continue
        frac = p.stat().st_size / max(tam_ref[b], 1)
        if frac < 0.90:
            fila[b] = ("INCOMPLETO", frac)
            continue
        cmd = [".venv-gpu/bin/python", "scripts/detection_eval.py",
               "--pred", str(p), "--truth", f"data/{b}_fus_truth_limpia.tsv",
               "--mascara", f"data/{b}_fus_mascara_train.tsv", "--umbral", UMBRAL]
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=600).stdout
        except subprocess.TimeoutExpired:
            fila[b] = ("TIMEOUT", 0)
            continue
        f1 = re.findall(r"f1[\"']?\s*[:=]\s*([0-9.]+)", out, re.I)
        if not f1:
            f1 = re.findall(r"\bF1\b\D{0,12}([0-9]\.[0-9]+)", out)
        fila[b] = float(f1[-1]) if f1 else ("SIN CIFRA", 0)
    filas.append(fila)

anchura = 13
print("\n" + "version".ljust(anchura) + "".join(b[:10].rjust(12) for b in BLOQUES)
      + "media".rjust(12))
print("-" * (anchura + 12 * 5))
for f in filas:
    vals = [f.get(b) for b in BLOQUES]
    nums = [v for v in vals if isinstance(v, float)]
    med = sum(nums) / len(nums) if len(nums) == 4 else None
    def fmt(v):
        if v is None:
            return "-".rjust(12)
        if isinstance(v, tuple):
            return (v[0][:9] if v[0] != "INCOMPLETO" else f"{100*v[1]:.0f}%inc").rjust(12)
        return f"{v:.3f}".rjust(12)
    linea = f["version"].ljust(anchura) + "".join(fmt(v) for v in vals)
    linea += (f"{med:.3f}".rjust(12) if med is not None
              else f"({len(nums)}/4)".rjust(12))
    print(linea)
print("\n  umbral 0.70 | media solo cuando estan los cuatro bloques")
