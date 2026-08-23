#!/usr/bin/env python3
"""La comparacion HOMOGENEA: la misma fusion, el mismo criterio, los dos sitios.

El precinto se midio con cortes de rango sobre la puntuacion RRF de la fusion
de cuatro modelos. El 0,512 con el que se compara se midio con umbrales de
PROBABILIDAD sobre v7 SOLO. Son dos metricas y dos sistemas distintos: la
comparacion no dice lo que parece decir.

Esto mide la fusion RRF en los cuatro bloques gallegos con el MISMO criterio que
el precinto —cortes de presupuesto de revision— para que las dos cifras sean
comparables.
"""
import csv
import subprocess
from pathlib import Path

BLOQUES = {
    "coruna": "data/coruna_fus_truth_limpia.tsv",
    "lugo": "data/lugo_fus_truth_limpia.tsv",
    "ourense": "data/ourense_fus_truth_limpia.tsv",
    "pontevedra": "data/pontevedra_fus_truth_limpia.tsv",
}
# los mismos presupuestos que uso el precinto
PRESUPUESTOS = [100, 200, 400, 800, 1600, 3200]


def umbral_para(pred, k):
    """El corte de puntuacion que deja k celdas."""
    sc = []
    with open(pred, encoding="utf-8") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            try:
                sc.append(float(r["score"]))
            except (KeyError, ValueError):
                pass
    sc.sort(reverse=True)
    return sc[min(k, len(sc)) - 1] if sc else 0.0


def evalua(pred, truth, umbral):
    out = subprocess.run(
        [".venv-gpu/bin/python", "scripts/detection_eval.py", "--pred", pred,
         "--truth", truth, "--enlace-m", "512", "--umbrales", str(umbral)],
        capture_output=True, text=True).stdout
    for ln in out.splitlines():
        p = ln.split()
        if len(p) >= 8:
            try:
                float(p[0])
                return dict(det=int(p[1]), tp=int(p[2]), fp=int(p[3]), fn=int(p[4]),
                            prec=float(p[5]), rec=float(p[6]), f1=float(p[7]))
            except ValueError:
                continue
    return None


print("FUSION RRF en Galicia, con cortes de presupuesto (mismo criterio que el precinto)\n")
print(f"{'presupuesto':>12} {'fichas':>7} {'TP':>5} {'castros':>8} {'recall':>7} {'F1':>7} {'VPP':>6}")
for k in PRESUPUESTOS:
    TP = FP = FN = DET = 0
    for b, truth in BLOQUES.items():
        pred = f"data/sweep_val_{b}_fusionrrf_full.tsv"
        if not Path(pred).exists():
            continue
        u = umbral_para(pred, k // 4)   # el presupuesto se reparte entre bloques
        r = evalua(pred, truth, u)
        if not r:
            continue
        TP += r["tp"]; FP += r["fp"]; FN += r["fn"]; DET += r["det"]
    if TP + FP == 0:
        continue
    P = TP / (TP + FP)
    R = TP / (TP + FN) if TP + FN else 0
    F = 2 * P * R / (P + R) if P + R else 0
    print(f"{k:>12} {DET:>7} {TP:>5} {TP+FN:>8} {R:>7.3f} {F:>7.3f} {P:>6.2f}")

print()
print("Para comparar, el precinto (129 castros, norte de Portugal):")
print(f"{'top 100':>12} {89:>7} {31:>5} {129:>8} {0.240:>7.3f} {0.284:>7.3f} {0.31:>6.2f}")
print(f"{'top 800':>12} {543:>7} {70:>5} {129:>8} {0.543:>7.3f} {0.209:>7.3f} {0.11:>6.2f}")
print(f"{'top 3200':>12} {1411:>7} {84:>5} {129:>8} {0.651:>7.3f} {0.109:>7.3f} {0.05:>6.2f}")
