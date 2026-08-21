#!/usr/bin/env python3
"""¿Y si se baja el umbral y se limpia con OSM lo que entra de mas?

**El diagnostico que lo motiva.** Medido el 2026-08-09 sobre v7:

| bloque | u=0.50 | u=0.70 |
| --- | --- | --- |
| Pontevedra | recall `0,775`, precision `0,175` | recall `0,450`, precision `0,391` |
| A Coruna | recall `0,453`, precision `0,340` | recall `0,267`, precision `0,769` |

**El recall existe a umbral bajo**: en Pontevedra el modelo encuentra el `77,5%` de
los castros. Lo que sobra son falsos positivos, y en la ria de Vigo son obra
moderna —canteras, poligonos, urbanizaciones—, que es exactamente lo que OSM sabe
y no exige juicio arqueologico.

La hipotesis: **bajar el umbral y cribar despues** bate a subir el umbral. Se mide
de verdad, no se estima: se cuentan los TP que la criba tambien se lleva, porque
ese es su coste y es el que decide si sirve.

Uso:
    python3 scripts/criba_como_filtro.py pontevedra v7 0.50
"""
from __future__ import annotations

import csv
import math
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "scripts")
from detection_eval import a_metros, agrupar, leer_tsv  # noqa: E402

B = sys.argv[1] if len(sys.argv) > 1 else "pontevedra"
M = sys.argv[2] if len(sys.argv) > 2 else "v7"
U = float(sys.argv[3]) if len(sys.argv) > 3 else 0.50
TOL, ENLACE = 500.0, 512.0

pred = [p for p in leer_tsv(Path(f"data/sweep_val_{B}_{M}.tsv"), ("lon", "lat", "score"))
        if "score" in p and float(p["score"]) >= U]
for p in pred:
    p["score"] = float(p["score"])
truth = leer_tsv(Path(f"data/{B}_fus_truth_limpia.tsv"))
lat0 = float(np.mean([t["lat"] for t in truth]))
px, py = a_metros([p["lon"] for p in pred], [p["lat"] for p in pred], lat0)
tx, ty = a_metros([t["lon"] for t in truth], [t["lat"] for t in truth], lat0)

# un punto por deteccion agrupada, con su clase
sitios = []
for g in agrupar(px, py, ENLACE):
    cx, cy = float(np.mean(px[g])), float(np.mean(py[g]))
    d = np.hypot(tx - cx, ty - cy)
    lon = float(np.mean([pred[i]["lon"] for i in g]))
    lat = float(np.mean([pred[i]["lat"] for i in g]))
    sitios.append({"lon": lon, "lat": lat,
                   "clase": "TP" if d.min() <= TOL else "FP",
                   "idx": int(d.argmin()) if d.min() <= TOL else -1})
tp0 = len({s["idx"] for s in sitios if s["clase"] == "TP"})
fp0 = sum(1 for s in sitios if s["clase"] == "FP")
print(f"{B} / {M} a umbral {U}: {len(sitios)} detecciones | TP {tp0} | FP {fp0}")

tmp = Path(f"/tmp/det_{B}_{M}.tsv")
with tmp.open("w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh, delimiter="\t")
    w.writerow(["lon", "lat", "clase"])
    for s in sitios:
        w.writerow([f"{s['lon']:.6f}", f"{s['lat']:.6f}", s["clase"]])

out = Path(f"/tmp/det_{B}_{M}_cribado.tsv")
r = subprocess.run([".venv-gpu/bin/python", "scripts/criba_osm.py",
                    "--detecciones", str(tmp), "--radio-m", "200",
                    "--out", str(out)], capture_output=True, text=True)
if r.returncode == 3 or not out.exists():
    print("  la criba no pudo consultar Overpass; sin resultado (no se inventa)")
    raise SystemExit(3)

filas = list(csv.DictReader(out.open(encoding="utf-8"), delimiter="\t"))
vivos = [f for f in filas if f.get("descartado") != "1"]
tp1 = sum(1 for f in vivos if f.get("clase") == "TP")
fp1 = sum(1 for f in vivos if f.get("clase") == "FP")
n_t = len(truth)


def f1(tp, fp, n):
    rec = tp / max(n, 1)
    pre = tp / max(tp + fp, 1)
    return 2*pre*rec/max(pre+rec, 1e-9), pre, rec


a, pa, ra = f1(tp0, fp0, n_t)
b, pb, rb = f1(tp1, fp1, n_t)
print(f"\n  {'':<14}{'TP':>5}{'FP':>6}{'precision':>11}{'recall':>9}{'F1':>8}")
print(f"  {'sin criba':<14}{tp0:>5}{fp0:>6}{pa:>11.3f}{ra:>9.3f}{a:>8.3f}")
print(f"  {'con criba':<14}{tp1:>5}{fp1:>6}{pb:>11.3f}{rb:>9.3f}{b:>8.3f}")
print(f"\n  la criba quito {fp0-fp1} falsos ({100*(fp0-fp1)/max(fp0,1):.0f}%) "
      f"y {tp0-tp1} verdaderos ({100*(tp0-tp1)/max(tp0,1):.0f}%)")
print(f"  cambio de F1: {b-a:+.3f}")
