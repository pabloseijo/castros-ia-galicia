#!/usr/bin/env python3
"""El coste real de revisar la union de modelos, en fichas y no en celdas.

`union_modelos.py` cuenta **celdas** sobre umbral, que no es lo que revisa una
persona: las celdas se agrupan en sitios y un sitio es una ficha. Esto fusiona
los barridos quedandose con la **puntuacion maxima por celda** —que es
exactamente la union: una celda pasa el umbral si algun modelo la pasa— y luego
usa el evaluador de siempre, con su enlace, su `min-celdas` y su margen.

Asi la comparacion es honesta: mismo agrupamiento para todas las
configuraciones, y el numero que sale es **cuantas fichas hay que mirar para
encontrar los castros que se encuentran**.
"""
from __future__ import annotations

import csv
import re
import subprocess
import sys
from pathlib import Path

BLOQUES = ["lugo", "coruna", "ourense", "pontevedra"]
TMP = Path("data/tmp-union")
TMP.mkdir(exist_ok=True)


def fusionar(modelos, bloque) -> Path | None:
    """Maximo por celda. La celda se identifica por su `id`, que es la rejilla."""
    mejor: dict[str, dict] = {}
    campos = None
    for m in modelos:
        p = Path(f"data/sweep_val_{bloque}_{m}.tsv")
        if not p.exists():
            continue
        with p.open(encoding="utf-8") as fh:
            r = csv.DictReader(fh, delimiter="\t")
            campos = campos or r.fieldnames
            for fila in r:
                try:
                    s = float(fila["score"])
                except (KeyError, TypeError, ValueError):
                    continue
                cid = fila.get("id") or f"{fila['lon']},{fila['lat']}"
                if cid not in mejor or s > float(mejor[cid]["score"]):
                    mejor[cid] = fila
    if not mejor:
        return None
    out = TMP / f"{bloque}_{'-'.join(modelos)}.tsv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=campos, delimiter="\t")
        w.writeheader()
        w.writerows(mejor.values())
    return out


# v12 entra aqui aunque este refutada como modelo (`F1 0,459` contra `0,512`):
# gana `25` castros que v7 no ve y pierde `24`, exactamente el mismo patron de
# v11p. **Un detector se juzga en la union por lo que ve distinto, no por su
# media**, y esa es la leccion del dia.
CONFIGS = [(["v7"], 0.70), (["v7"], 0.60),
           (["v7", "v11p"], 0.60),
           (["v7", "v11p", "v12"], 0.65), (["v7", "v11p", "v12"], 0.60),
           (["v7", "v14"], 0.60),
           (["v7", "v11p", "v14"], 0.65),
           (["v7", "v11p", "v12", "v14"], 0.65),
           (["v7", "v11p", "v12", "v14"], 0.60)]

print(f"  {'configuracion':<22}{'umbral':>7}{'fichas':>9}{'hallados':>10}"
      f"{'recall':>9}{'fichas/castro':>15}")
print("  " + "-" * 72)
for modelos, umbral in CONFIGS:
    tot_det = tot_tp = tot_truth = 0
    for b in BLOQUES:
        f = fusionar(modelos, b)
        if f is None:
            continue
        cmd = [".venv-gpu/bin/python", "scripts/detection_eval.py", "--pred", str(f),
               "--truth", f"data/{b}_fus_truth_limpia.tsv",
               "--mascara", f"data/{b}_fus_mascara_train.tsv", "--umbral", str(umbral)]
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=900).stdout
        m = re.search(rf"^\s*{umbral:.2f}\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)", out, re.M)
        if not m:
            continue
        tot_det += int(m.group(1)); tot_tp += int(m.group(2))
        tot_truth += sum(1 for _ in csv.DictReader(
            open(f"data/{b}_fus_truth_limpia.tsv", encoding="utf-8"), delimiter="\t"))
    if not tot_truth:
        continue
    print(f"  {'+'.join(modelos):<22}{umbral:>7.2f}{tot_det:>9}{tot_tp:>10}"
          f"{tot_tp/tot_truth:>9.3f}{tot_det/max(tot_tp,1):>15.1f}")
