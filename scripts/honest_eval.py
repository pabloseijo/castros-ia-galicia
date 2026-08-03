#!/usr/bin/env python3
"""Evaluation that refuses to flatter the model.

Three measured facts about this project make naive metrics misleading, and this
module exists so every future number carries its caveat in the same breath:

1. There are 68 usable positives in Trasancos and 7 in the O Val holdout. A
   recall of 0.70 measured on 7 sites has a 95% interval of [0.36, 0.92]. Any
   metric reported without an interval is noise dressed as a result.

2. Training runs at 25 negatives per positive; a real 128 m sweep of Trasancos
   is 474 per positive, an 18.8x gap. Precision measured on the validation mix
   is therefore optimistic by roughly that factor and must be restated at the
   deployment base rate before it means anything.

3. The deliverable is a review queue with a human at the end, so the quantity
   that matters is how much of the top-K is worth opening in QGIS, and how many
   hours that K costs at Landauer et al. (2025) rates: 4 s to screen a site,
   3 min to verify one properly.

Nothing here trains or predicts. It takes scores and labels and reports what
can honestly be claimed from them.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import numpy as np

# Measured on this project's own sweep: 91 plausible castros in 43215 cells.
SWEEP_CELLS = 43215
SWEEP_POSITIVES = 91
DEPLOY_RATIO = (SWEEP_CELLS - SWEEP_POSITIVES) / SWEEP_POSITIVES

SCREEN_SECONDS = 4.0     # Landauer: first-pass triage per site
VERIFY_SECONDS = 180.0   # Landauer: detailed verification per candidate


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson interval: behaves at small n, where the normal approximation lies."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def bootstrap_ci(scores, labels, fn, n_boot=2000, seed=20260803):
    """Percentile interval for any metric that has no closed form (AP, AUC)."""
    rng = np.random.default_rng(seed)
    s, l = np.asarray(scores), np.asarray(labels)
    n = len(s)
    vals = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        if len(np.unique(l[idx])) < 2:
            continue
        vals.append(fn(s[idx], l[idx]))
    if not vals:
        return (float("nan"), float("nan"))
    return (float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5)))


def average_precision(scores, labels) -> float:
    order = np.argsort(-np.asarray(scores))
    l = np.asarray(labels)[order]
    npos = l.sum()
    if npos == 0:
        return float("nan")
    cum = np.cumsum(l)
    prec = cum / np.arange(1, len(l) + 1)
    return float((prec * l).sum() / npos)


def roc_auc(scores, labels) -> float:
    s, l = np.asarray(scores), np.asarray(labels)
    pos, neg = s[l == 1], s[l == 0]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    order = np.argsort(s)
    ranks = np.empty(len(s), float)
    ranks[order] = np.arange(1, len(s) + 1)
    return float((ranks[l == 1].sum() - len(pos) * (len(pos) + 1) / 2)
                 / (len(pos) * len(neg)))


def precision_at_deploy(precision_obs: float, ratio_obs: float,
                        ratio_deploy: float = DEPLOY_RATIO) -> float:
    """Restate an observed precision at the deployment base rate.

    Precision depends on prevalence; recall and false-alarm rate do not. So we
    back out the false-alarm rate implied by the observed precision, then
    recompute precision with the real ratio of negatives to positives. This is
    the number a reviewer would actually experience opening the queue.
    """
    if not (0 < precision_obs < 1):
        return precision_obs
    # precision = R / (R + F*ratio)  =>  F/R = (1-p)/(p*ratio)
    f_over_r = (1 - precision_obs) / (precision_obs * ratio_obs)
    return 1.0 / (1.0 + f_over_r * ratio_deploy)


def review_hours(k: int, precision: float) -> dict:
    screen = k * SCREEN_SECONDS / 3600.0
    verify = k * precision * VERIFY_SECONDS / 3600.0
    return {"screen_h": screen, "verify_h": verify, "total_h": screen + verify}


# --- Marco de precisión diagnóstica -------------------------------------
# La medicina separa dos pares que visión por computador mezcla: sensibilidad
# y especificidad no dependen de la prevalencia y se trasladan del conjunto
# etiquetado al barrido; VPP y VPN sí dependen y hay que recalcularlos. Esa
# distinción es la que hace que un número de validación signifique algo.

DEPLOY_PREVALENCE = SWEEP_POSITIVES / SWEEP_CELLS


def ppv_from(sens: float, spec: float, prevalence: float = DEPLOY_PREVALENCE) -> float:
    """Valor predictivo positivo a una prevalencia dada (Bayes)."""
    tp = sens * prevalence
    fp = (1 - spec) * (1 - prevalence)
    return tp / (tp + fp) if (tp + fp) > 0 else float("nan")


def specificity_needed(target_ppv: float, sens: float,
                       prevalence: float = DEPLOY_PREVALENCE) -> float:
    """Especificidad exigida para alcanzar un VPP objetivo.

    Se despeja de la fórmula de Bayes. Es una meta mucho mejor formulada que
    "precisión 0.75", porque la especificidad se mide en el conjunto
    etiquetado y se traslada, mientras que el VPP no significa nada sin decir
    a qué prevalencia se calcula.
    """
    if not (0 < target_ppv < 1):
        return float("nan")
    fpr = sens * prevalence * (1 - target_ppv) / (target_ppv * (1 - prevalence))
    return 1 - fpr


def number_needed_to_screen(ppv: float) -> float:
    """Celdas que hay que abrir en QGIS por cada castro hallado.

    El NNS viene de Rembold (BMJ 1998) y comunica la carga de revisión mucho
    mejor que una tasa de falsa alarma con cuatro ceros.
    """
    return 1.0 / ppv if ppv and ppv > 0 else float("inf")


def diagnostic_block(scores, labels, thresholds=(0.5,)) -> dict:
    s, l = np.asarray(scores, float), np.asarray(labels, int)
    npos, nneg = int(l.sum()), int((1 - l).sum())
    out = {"prevalence_deploy": DEPLOY_PREVALENCE, "by_threshold": {}}
    for t in thresholds:
        pred = (s >= t).astype(int)
        tp = int(((pred == 1) & (l == 1)).sum())
        tn = int(((pred == 0) & (l == 0)).sum())
        sens = tp / npos if npos else float("nan")
        spec = tn / nneg if nneg else float("nan")
        ppv_d = ppv_from(sens, spec)
        out["by_threshold"][t] = {
            "sensitivity": sens,
            "sensitivity_ci95": list(wilson(tp, npos)) if npos else [0, 1],
            "specificity": spec,
            "specificity_ci95": list(wilson(tn, nneg)) if nneg else [0, 1],
            "ppv_at_deploy_prevalence": ppv_d,
            "number_needed_to_screen": number_needed_to_screen(ppv_d),
        }
    out["specificity_targets"] = {
        f"ppv_{p:.2f}": {
            "specificity_needed": specificity_needed(p, 0.70),
            "false_positives_in_sweep":
                (1 - specificity_needed(p, 0.70)) * (SWEEP_CELLS - SWEEP_POSITIVES),
        } for p in (0.25, 0.50, 0.75)
    }
    return out


def evaluate(scores, labels, ratio_obs=None, ks=(10, 25, 50, 100)) -> dict:
    s = np.asarray(scores, float)
    l = np.asarray(labels, int)
    n, npos = len(l), int(l.sum())
    nneg = n - npos
    if ratio_obs is None:
        ratio_obs = nneg / npos if npos else float("nan")

    order = np.argsort(-s)
    ls = l[order]

    out = {
        "n": n, "n_positives": npos, "n_negatives": nneg,
        "ratio_observed": ratio_obs, "ratio_deploy": DEPLOY_RATIO,
        "ratio_gap": DEPLOY_RATIO / ratio_obs if ratio_obs else float("nan"),
        "roc_auc": roc_auc(s, l),
        "average_precision": average_precision(s, l),
    }
    out["roc_auc_ci95"] = bootstrap_ci(s, l, roc_auc)
    out["average_precision_ci95"] = bootstrap_ci(s, l, average_precision)

    out["at_k"] = {}
    for k in ks:
        if k > n:
            continue
        hits = int(ls[:k].sum())
        p = hits / k
        lo, hi = wilson(hits, k)
        out["at_k"][k] = {
            "precision": p, "precision_ci95": [lo, hi],
            "precision_at_deploy_base_rate": precision_at_deploy(p, ratio_obs),
            "recall": hits / npos if npos else float("nan"),
            "recall_ci95": list(wilson(hits, npos)) if npos else [0, 1],
            "review": review_hours(k, p),
        }

    # Recall at the depth where the queue holds as many items as there are
    # positives: the fairest single summary for a triage list.
    k = max(npos, 1)
    hits = int(ls[:k].sum())
    out["at_npos"] = {"k": k, "hits": hits,
                      "precision": hits / k,
                      "recall_ci95": list(wilson(hits, npos)) if npos else [0, 1]}

    # Marco diagnóstico: la parte trasladable del resultado.
    qs = np.quantile(s, [0.5, 0.75, 0.9]) if len(s) else [0.5]
    out["diagnostic"] = diagnostic_block(s, l, thresholds=tuple(float(q) for q in qs))

    # What this test set can and cannot resolve.
    lo, hi = wilson(round(0.70 * npos), npos) if npos else (0, 1)
    out["resolving_power"] = {
        "ci_width_at_recall_070": hi - lo,
        "can_distinguish_070_from_060": (hi - lo) < 0.10,
        "positives_needed_for_pm005": 300,
    }
    return out


def render(res: dict) -> str:
    L = ["# Evaluación honesta", ""]
    L += [f"`{res['n']}` muestras: `{res['n_positives']}` positivos, "
          f"`{res['n_negatives']}` negativos.", ""]
    gap = res["ratio_gap"]
    L += ["| magnitud | valor |", "|---|---:|",
          f"| ratio neg:pos observado | `1:{res['ratio_observed']:.0f}` |",
          f"| ratio neg:pos en barrido real | `1:{res['ratio_deploy']:.0f}` |",
          f"| **desajuste** | **`{gap:.1f}x`** |",
          f"| ROC-AUC | `{res['roc_auc']:.4f}` "
          f"IC95% `[{res['roc_auc_ci95'][0]:.3f}, {res['roc_auc_ci95'][1]:.3f}]` |",
          f"| average precision | `{res['average_precision']:.4f}` "
          f"IC95% `[{res['average_precision_ci95'][0]:.3f}, "
          f"{res['average_precision_ci95'][1]:.3f}]` |", ""]
    L += ["## Por profundidad de cola", "",
          "| K | precisión | IC95% | **a tasa base real** | recall | horas de revisión |",
          "|---:|---:|---|---:|---:|---:|"]
    for k, d in res["at_k"].items():
        L.append(f"| {k} | `{d['precision']:.2f}` | "
                 f"`[{d['precision_ci95'][0]:.2f}, {d['precision_ci95'][1]:.2f}]` | "
                 f"**`{d['precision_at_deploy_base_rate']:.2f}`** | "
                 f"`{d['recall']:.2f}` | `{d['review']['total_h']:.1f} h` |")
    rp = res["resolving_power"]
    d = res.get("diagnostic", {})
    if d:
        L += ["", "## Marco diagnóstico (lo que sí se traslada al barrido)", "",
              "Sensibilidad y especificidad no dependen de la prevalencia: se miden aquí",
              "y valen igual en el barrido. El VPP sí depende, y se recalcula a la",
              f"prevalencia real (`1:{1/d['prevalence_deploy']:.0f}`).", "",
              "| umbral | sensibilidad | especificidad | VPP a tasa real | celdas por castro |",
              "|---:|---|---|---:|---:|"]
        for t, b in d["by_threshold"].items():
            L.append(f"| `{t:.3f}` | `{b['sensitivity']:.2f}` "
                     f"`[{b['sensitivity_ci95'][0]:.2f}, {b['sensitivity_ci95'][1]:.2f}]` | "
                     f"`{b['specificity']:.4f}` "
                     f"`[{b['specificity_ci95'][0]:.3f}, {b['specificity_ci95'][1]:.3f}]` | "
                     f"**`{b['ppv_at_deploy_prevalence']:.3f}`** | "
                     f"`{b['number_needed_to_screen']:.1f}` |")
        L += ["", "### La meta, formulada como especificidad", "",
              "«Precisión `0.75`» no significa nada sin prevalencia. Esto sí:", "",
              "| VPP objetivo | especificidad necesaria | falsos positivos en el barrido |",
              "|---:|---:|---:|"]
        for k, v in res["diagnostic"]["specificity_targets"].items():
            L.append(f"| `{k.split('_')[1]}` | `{v['specificity_needed']:.5f}` | "
                     f"`{v['false_positives_in_sweep']:.0f}` |")

    L += ["", "## Qué puede resolver este conjunto", "",
          f"Anchura del IC95% al estimar un recall de `0.70`: "
          f"**`{rp['ci_width_at_recall_070']:.2f}`**.", ""]
    if not rp["can_distinguish_070_from_060"]:
        L += ["> **No distingue un recall de `0.70` de uno de `0.60`.** Cualquier",
              "> mejora menor que esa anchura es indistinguible del ruido de muestreo.",
              f"> Harían falta del orden de `{rp['positives_needed_for_pm005']}` positivos.", ""]
    L += ["La columna «a tasa base real» reexpresa la precisión al ratio del barrido",
          "(`1:474`), que es lo que vería quien abra la cola en QGIS. La precisión",
          "medida sobre la mezcla de validación es optimista por construcción.", ""]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scores", type=Path, required=True,
                    help="TSV con columnas score y label")
    ap.add_argument("--score-col", default="score")
    ap.add_argument("--label-col", default="label")
    ap.add_argument("--out-json", type=Path)
    ap.add_argument("--out-md", type=Path)
    args = ap.parse_args()

    s, l = [], []
    with open(args.scores, encoding="utf-8") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            try:
                s.append(float(r[args.score_col]))
                l.append(int(float(r[args.label_col])))
            except (KeyError, TypeError, ValueError):
                continue
    if not s:
        print("sin filas utilizables")
        return 1

    res = evaluate(s, l)
    md = render(res)
    print(md)
    if args.out_json:
        args.out_json.write_text(json.dumps(res, indent=2, default=float), encoding="utf-8")
    if args.out_md:
        args.out_md.write_text(md, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
