#!/usr/bin/env python3
"""La tabla que faltaba: F1 medio sobre los cuatro bloques, para cada modelo.

Toda la serie se ha comparado con `v7 = 0,542` como referencia, pero esa cifra se
fijo hace dias y nunca se reviso si algun modelo anterior la superaba. Hay
barridos completos guardados de varios modelos y evaluarlos no cuesta GPU: solo
leer TSV. Si alguno bate a v7, la referencia de toda la serie de preregistros
esta mal elegida, y eso cambia los veredictos de v8, v9 y v10.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BLOQUES = ["lugo", "coruna", "ourense", "pontevedra"]
UMBRAL = "0.70"


def f1_de(modelo, bloque):
    pred = Path(f"data/sweep_val_{bloque}_{modelo}.tsv")
    truth = Path(f"data/{bloque}_fus_truth_limpia.tsv")
    if not pred.exists() or not truth.exists():
        return None
    if sum(1 for _ in pred.open(encoding="utf-8")) < 10:
        return None                      # barrido vacio o solo cabecera
    cmd = [".venv-gpu/bin/python", "scripts/detection_eval.py",
           "--pred", str(pred), "--truth", str(truth), "--umbral", UMBRAL]
    masc = Path(f"data/{bloque}_fus_mascara_train.tsv")
    if masc.exists():
        cmd += ["--mascara", str(masc)]
    p = subprocess.run(cmd, capture_output=True, text=True)
    for ln in p.stdout.splitlines():
        c = ln.split()
        if c and c[0] == UMBRAL and len(c) >= 8:
            try:
                return float(c[7])
            except ValueError:
                pass
    return None


modelos = sys.argv[1:] or ["v6", "v6focal", "v7", "v8", "v9", "v7t"]
print(f"{'modelo':<10}" + "".join(f"{b[:5]:>9}" for b in BLOQUES) + f"{'media':>9}{'n':>4}")
print("-" * (10 + 9*len(BLOQUES) + 13))
filas = []
for m in modelos:
    vs = [f1_de(m, b) for b in BLOQUES]
    ok = [v for v in vs if v is not None]
    media = sum(ok)/len(ok) if ok else None
    filas.append((m, media, len(ok)))
    print(f"{m:<10}" + "".join(f"{v:>9.3f}" if v is not None else f"{'—':>9}" for v in vs)
          + (f"{media:>9.3f}" if media is not None else f"{'—':>9}") + f"{len(ok):>4}")

print("\ncomparacion con la referencia declarada (v7 = 0,542 sobre 4 bloques):")
for m, media, n in filas:
    if media is None or m == "v7":
        continue
    d = media - 0.542
    marca = "  <-- SUPERA la referencia" if d > 0 and n == 4 else ""
    print(f"  {m:<10}{media:>7.3f}  ({d:+.3f}, {n} bloques){marca}")
