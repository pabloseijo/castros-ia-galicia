#!/usr/bin/env python3
"""El Esceptico senala una discrepancia que decide si la brecha al 0,66 es de
0,15 o de 0,25: la cifra de cabecera 0,512 es media POR BLOQUES, y agrupando
los aciertos de los cuatro sale otra cosa. Media por bloques pondera igual a
Ourense (34 castros) que a A Coruna (70). Esto lo resuelve con los ficheros.
"""
import csv
import subprocess
from pathlib import Path

BLOQ = {
    "coruna": ("data/sweep_val_coruna_v7.tsv", "data/coruna_truth_limpia.tsv"),
    "lugo": ("data/sweep_val_lugo_v7.tsv", "data/lugo_castros_truth_limpia.tsv"),
    "ourense": ("data/sweep_val_ourense_v7.tsv", "data/ourense_truth_limpia.tsv"),
    "pontevedra": ("data/sweep_val_pontevedra_v7.tsv", "data/pontevedra_truth_limpia.tsv"),
}
UMBRALES = [0.30, 0.50, 0.60, 0.70, 0.80]


def evalua(pred, truth, umbral):
    """Llama al evaluador real del proyecto y saca TP/FP/FN de su tabla."""
    out = subprocess.run(
        [".venv-gpu/bin/python", "scripts/detection_eval.py", "--pred", pred,
         "--truth", truth, "--enlace-m", "512"],
        capture_output=True, text=True).stdout
    for ln in out.splitlines():
        p = ln.split()
        if len(p) >= 8:
            try:
                if abs(float(p[0]) - umbral) < 1e-6:
                    return int(p[2]), int(p[3]), int(p[4])
            except ValueError:
                continue
    return None


def f1(p, r):
    return 2 * p * r / (p + r) if p + r else 0.0


print("Para cada umbral: media POR BLOQUES contra AGREGADO (micro)\n")
print(f"{'umbral':>7} {'F1 medio bloques':>17} {'F1 agregado':>12} {'TP':>5} {'FP':>5} {'FN':>5}")
mejor = None
for u in UMBRALES:
    f1s, TP, FP, FN = [], 0, 0, 0
    ok = True
    for b, (pr, tr) in BLOQ.items():
        r = evalua(pr, tr, u)
        if not r:
            ok = False
            break
        tp, fp, fn = r
        TP += tp; FP += fp; FN += fn
        p = tp / (tp + fp) if tp + fp else 0
        rc = tp / (tp + fn) if tp + fn else 0
        f1s.append(f1(p, rc))
    if not ok:
        continue
    macro = sum(f1s) / len(f1s)
    P, R = TP / (TP + FP), TP / (TP + FN)
    micro = f1(P, R)
    print(f"{u:>7.2f} {macro:>17.4f} {micro:>12.4f} {TP:>5} {FP:>5} {FN:>5}")
    if mejor is None or macro > mejor[1]:
        mejor = (u, macro, micro, TP, FP, FN)

print()
u, macro, micro, TP, FP, FN = mejor
print(f"Mejor umbral comun por macro-F1: {u}")
print(f"  macro (media de bloques) = {macro:.4f}")
print(f"  micro (agregado)         = {micro:.4f}")
print(f"  diferencia               = {macro - micro:+.4f}")
print()
print("La macro pondera igual bloques con distinto numero de castros; la micro")
print("cuenta castros. Para 'cuantos castros encuentro' la honesta es la MICRO.")
