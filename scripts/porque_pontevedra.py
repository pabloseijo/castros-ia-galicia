#!/usr/bin/env python3
"""¿Por que Pontevedra tiene precision 0,250 y Lugo 0,594?

La aritmetica del 0,66 senala que ese bloque arrastra al agregado, y que
arreglarlo solo rinde mas que cualquier cambio global. Esto compara los cuatro
en lo que se puede medir sin mirar predicciones nuevas.
"""
import csv
from pathlib import Path

TRUTH = {"coruna": "data/coruna_truth_limpia.tsv",
         "lugo": "data/lugo_castros_truth_limpia.tsv",
         "ourense": "data/ourense_truth_limpia.tsv",
         "pontevedra": "data/pontevedra_truth_limpia.tsv"}
SWEEP = {"coruna": "data/sweep_val_coruna_v7.tsv",
         "lugo": "data/sweep_val_lugo_v7.tsv",
         "ourense": "data/sweep_val_ourense_v7.tsv",
         "pontevedra": "data/sweep_val_pontevedra_v7.tsv"}
# TP/FP/FN medidos en el umbral de mejor F1
MED = {"coruna": (24, 35, 46, 0.60), "lugo": (38, 26, 22, 0.70),
       "ourense": (18, 25, 16, 0.70), "pontevedra": (14, 42, 15, 0.70)}

print(f"{'bloque':12} {'castros':>7} {'celdas':>7} {'dens/1000':>10} "
      f"{'media':>8} {'p95':>7} {'p99':>7} {'>umbral':>8} {'P':>6}")
for b in TRUTH:
    n = sum(1 for _ in open(TRUTH[b], encoding="utf-8")) - 1
    sc = []
    with open(SWEEP[b], encoding="utf-8") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            try:
                sc.append(float(r["p_castro"]))
            except Exception:
                pass
    sc.sort()
    tp, fp, fn, umb = MED[b]
    media = sum(sc) / len(sc)
    p95 = sc[int(0.95 * len(sc))]
    p99 = sc[int(0.99 * len(sc))]
    sobre = sum(1 for s in sc if s >= umb)
    prec = tp / (tp + fp)
    print(f"{b:12} {n:7} {len(sc):7} {1000*n/len(sc):10.2f} "
          f"{media:8.4f} {p95:7.4f} {p99:7.4f} {sobre:8} {prec:6.3f}")

print()
print("Lectura: 'dens/1000' es cuantos castros CATALOGADOS hay por cada 1000")
print("celdas barridas. Si un bloque tiene pocos catalogados pero el modelo")
print("dispara igual, sus 'falsos positivos' pueden ser catalogo incompleto.")
