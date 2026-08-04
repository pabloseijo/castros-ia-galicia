#!/usr/bin/env python3
"""Mide cada etapa de la cascada por separado, y el sistema entero.

Sigue el método de la escalera de ablación del TFG de reTAG: cada cambio se
reporta con su delta en puntos porcentuales, y los que empeoran se reportan
igual —allí el *score fusion* restó `8,54` pp y el TTA en solitario `0,79`—
porque una escalera que solo enseña las subidas no dice qué aporta cada pieza.

Aquí las etapas son:

  1. **Criba** (barata, sobre MDT5 a `512 m`): descarta terreno. Su métrica
     propia es qué fracción del espacio elimina y a costa de cuántos castros.
  2. **Modelo** (caro, sobre relieve a `1 m`): ordena lo que sobrevive.
  3. **Sistema**: la composición de ambas.

Lo que hay que entender, y es la razón de medirlas aparte: la sensibilidad de
la cascada es el **producto** de las sensibilidades, así que una criba al `98%`
pone un techo del `98%` a todo lo que venga después. En cambio la especificidad
compone a favor. Por eso la criba se juzga por recall y el modelo por
especificidad, y mezclarlas en una sola cifra esconde justo el intercambio que
hay que decidir.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from honest_eval import (  # noqa: E402
    DEPLOY_PREVALENCE, SWEEP_CELLS, SWEEP_POSITIVES,
    number_needed_to_screen, ppv_from, wilson,
)

SCREEN_S, VERIFY_S = 4.0, 180.0


def stage_metrics(y, keep, name):
    """Sensibilidad y especificidad de una etapa binaria de paso/no paso."""
    y = np.asarray(y, int)
    keep = np.asarray(keep, bool)
    npos, nneg = int(y.sum()), int((1 - y).sum())
    tp = int((keep & (y == 1)).sum())
    tn = int((~keep & (y == 0)).sum())
    sens = tp / npos if npos else float("nan")
    spec = tn / nneg if nneg else float("nan")
    return {
        "stage": name,
        "sensitivity": sens, "sensitivity_ci95": list(wilson(tp, npos)),
        "specificity": spec, "specificity_ci95": list(wilson(tn, nneg)),
        "kept_fraction": float(keep.mean()),
        "discarded_fraction": float(1 - keep.mean()),
    }


def system_metrics(sens, spec, prevalence=DEPLOY_PREVALENCE, sweep=SWEEP_CELLS,
                   positives=SWEEP_POSITIVES):
    """Traduce sensibilidad y especificidad a lo que vería un revisor."""
    ppv = ppv_from(sens, spec, prevalence)
    fp = (1 - spec) * (sweep - positives)
    tp = sens * positives
    k = tp + fp
    return {
        "sensitivity": sens, "specificity": spec, "ppv_at_deploy": ppv,
        "expected_true_positives": tp, "expected_false_positives": fp,
        "candidates_to_review": k,
        "number_needed_to_screen": number_needed_to_screen(ppv),
        "review_hours": k * SCREEN_S / 3600.0 + k * ppv * VERIFY_S / 3600.0,
    }


def ladder(rows):
    """Escalera con delta en puntos porcentuales sobre el escalón anterior."""
    out, prev = [], None
    for name, m in rows:
        d = dict(m)
        d["name"] = name
        if prev is not None:
            d["delta_ppv_pp"] = (m["ppv_at_deploy"] - prev["ppv_at_deploy"]) * 100
            d["delta_sens_pp"] = (m["sensitivity"] - prev["sensitivity"]) * 100
        out.append(d)
        prev = m
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scores", type=Path, required=True,
                    help="TSV con score y label del modelo fino")
    ap.add_argument("--screen-scores", type=Path,
                    help="TSV con score y label de la criba; si falta, se "
                         "simula con las tasas medidas")
    ap.add_argument("--screen-recall", type=float, default=0.98,
                    help="recall al que se corta la criba")
    ap.add_argument("--out-json", type=Path)
    ap.add_argument("--out-md", type=Path)
    args = ap.parse_args()

    def read(p):
        s, y = [], []
        for r in csv.DictReader(open(p, encoding="utf-8"), delimiter="\t"):
            try:
                s.append(float(r["score"]))
                y.append(int(float(r["label"])))
            except (KeyError, TypeError, ValueError):
                continue
        return np.asarray(s), np.asarray(y, int)

    sm, ym = read(args.scores)
    if len(sm) == 0:
        raise SystemExit("sin filas utilizables en --scores")

    # --- Etapa 1: la criba ------------------------------------------------
    if args.screen_scores and args.screen_scores.exists():
        ss, ys = read(args.screen_scores)
        thr = float(np.percentile(ss[ys == 1], (1 - args.screen_recall) * 100))
        st1 = stage_metrics(ys, ss >= thr, "criba")
    else:
        # Medido el 2026-08-04 sobre 3071 castros y 5988 muestras de terreno
        # aleatorio: al 98% de recall la criba descarta el 67.4% del terreno.
        st1 = {"stage": "criba (tasas medidas)",
               "sensitivity": args.screen_recall,
               "sensitivity_ci95": [np.nan, np.nan],
               "specificity": 0.674, "specificity_ci95": [np.nan, np.nan],
               "kept_fraction": 0.326, "discarded_fraction": 0.674}

    # --- Etapa 2: el modelo fino -----------------------------------------
    # Se evalúa a varios cortes, porque el punto de operación es una decisión,
    # no una propiedad del modelo.
    npos = int(ym.sum())
    rows_md = []
    results = {"stage1": st1, "operating_points": []}

    base_prev = DEPLOY_PREVALENCE
    scr_prev = min(base_prev * st1["sensitivity"] / max(1 - st1["specificity"], 1e-9), 1.0)

    for target_sens in (0.90, 0.80, 0.70, 0.60):
        thr = float(np.percentile(sm[ym == 1], (1 - target_sens) * 100))
        tn = int(((sm < thr) & (ym == 0)).sum())
        nneg = int((1 - ym).sum())
        spec = tn / nneg if nneg else float("nan")

        solo = system_metrics(target_sens, spec, base_prev)
        casc_sens = target_sens * st1["sensitivity"]      # se multiplican
        casc_spec = 1 - (1 - spec) * (1 - st1["specificity"])  # componen a favor
        casc = system_metrics(casc_sens, casc_spec, base_prev)

        lad = ladder([("solo modelo", solo), ("criba + modelo", casc)])
        results["operating_points"].append(
            {"target_sensitivity": target_sens, "model_specificity": spec,
             "ladder": lad})
        rows_md.append((target_sens, spec, solo, casc, lad[-1]))

    L = ["# Cascada: precisión por etapa", "",
         "Cada etapa se mide aparte porque componen de forma distinta: **las",
         "sensibilidades se multiplican** —una criba al `98%` pone un techo del",
         "`98%` a todo lo que venga detrás— mientras que **las especificidades",
         "componen a favor**. Mezclarlas en una sola cifra esconde el",
         "intercambio que hay que decidir.", "",
         "## Etapa 1 — la criba", "", "| magnitud | valor |", "|---|---:|",
         f"| sensibilidad | `{st1['sensitivity']:.3f}` |",
         f"| especificidad | `{st1['specificity']:.3f}` |",
         f"| terreno descartado | `{st1['discarded_fraction']:.1%}` |",
         f"| tasa base | `1:{1/base_prev:.0f}` → `1:{1/scr_prev:.0f}` |", "",
         "## Etapa 2 y sistema", "",
         "| sens. objetivo | espec. modelo | VPP solo modelo | VPP con criba | Δ pp | candidatos | horas |",
         "|---:|---:|---:|---:|---:|---:|---:|"]
    for ts, spec, solo, casc, last in rows_md:
        L.append(f"| `{ts:.2f}` | `{spec:.4f}` | `{solo['ppv_at_deploy']:.3f}` | "
                 f"**`{casc['ppv_at_deploy']:.3f}`** | "
                 f"`{last.get('delta_ppv_pp', 0):+.1f}` | "
                 f"`{casc['candidates_to_review']:.0f}` | "
                 f"`{casc['review_hours']:.1f} h` |")
    L += ["", "El Δ es en puntos porcentuales de VPP sobre usar el modelo solo,",
          "siguiendo la escalera de ablación del TFG de reTAG. Un Δ negativo se",
          "reporta igual: una etapa que no aporta tiene que verse.", ""]

    md = "\n".join(L)
    print(md)
    if args.out_md:
        args.out_md.write_text(md, encoding="utf-8")
    if args.out_json:
        args.out_json.write_text(json.dumps(results, indent=2, default=float),
                                 encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
