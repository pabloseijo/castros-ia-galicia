#!/usr/bin/env python3
"""Diseña el cribado de terreno que ataca el cuello dominante: la tasa base.

Con 1 castro por cada 475 celdas, alcanzar un VPP de 0.75 con sensibilidad 0.70
exige una especificidad de 0.99951, o sea 21 falsos positivos en todo el
barrido. Ninguna arquitectura da eso. Lo que sí lo da es **reducir el espacio de
búsqueda antes del modelo fino**, porque el VPP depende de la prevalencia:

    espacio          celdas   tasa base   VPP con el mismo modelo
    todo Trasancos    43215      1:474              0.23
    al 20%             8643       1:95              0.60

Es la primera etapa de una cascada, en el sentido de Canedo y de la literatura
de detección gruesa-a-fina: una criba barata y muy sensible que descarta terreno
imposible, seguida del modelo caro sobre lo que queda.

El requisito que manda es **preservar el recall**. Una criba que descarte un
castro lo pierde para siempre, y ningún modelo posterior lo recupera. Así que
los umbrales no se eligen a ojo: se derivan de la distribución de los castros
conocidos, tomando el percentil que conserva la fracción exigida, y se reporta
qué área se descarta a cambio.

No entrena nada. Mide qué cribado es posible y a qué precio.
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

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SWEEP_CELLS, SWEEP_POSITIVES = 43215, 91
DEPLOY_PREVALENCE = SWEEP_POSITIVES / SWEEP_CELLS


def terrain_stats(arr: np.ndarray) -> dict:
    """Descriptores baratos de terreno, calculables sin modelo.

    Deliberadamente crudos: esta etapa tiene que poder correr sobre millones de
    celdas, así que nada que necesite ajuste ni inferencia.
    """
    ndtm, lrm, slope = (arr[i].astype(np.float32) for i in range(3))
    h, w = ndtm.shape
    yy, xx = np.mgrid[0:h, 0:w]
    r = np.hypot(yy - h / 2.0, xx - w / 2.0)
    core = r < 60          # el recinto plausible
    bg = r > 170           # contexto

    return {
        # Relieve total: el mar y las marismas son planos, un castro no.
        "relief_range": float(np.percentile(ndtm, 98) - np.percentile(ndtm, 2)),
        # Prominencia: el núcleo por encima de su contexto.
        "prominence": float(ndtm[core].mean() - ndtm[bg].mean()),
        # Pendiente mediana: un castro necesita plataforma habitable; un
        # acantilado o una ladera pura no lo son.
        "slope_median": float(np.median(slope)),
        "slope_core_median": float(np.median(slope[core])),
        # Energía del relieve local: terreno sin microtopografía no esconde nada.
        "lrm_std": float(lrm.std()),
        "lrm_core_std": float(lrm[core].std()),
    }


def rows_from_filenames(arr_dir: Path):
    """Reconstruye etiqueta y clase desde el nombre del `.npz`.

    El cortador escribe `index.tsv` solo al terminar, así que durante una
    ejecución larga —o tras una caída del disco, que aquí ha pasado tres veces
    en un día— no existe. Los `sid` tienen forma `{label}_{group}_{i}`, así que
    lo que hace falta está en el propio nombre y no hay que esperar.
    """
    rows = []
    for p in sorted(arr_dir.glob("*.npz")):
        parts = p.stem.split("_")
        if len(parts) < 3 or parts[0] not in ("0", "1"):
            continue
        rows.append({"sid": p.stem, "label": parts[0],
                     "group": "_".join(parts[1:-1]), "split": "pool"})
    return rows


def load(vig_dir: Path):
    arr_dir = vig_dir / "arrays"
    index = vig_dir / "index.tsv"
    if index.exists():
        rows = list(csv.DictReader(open(index, encoding="utf-8"), delimiter="\t"))
    else:
        rows = rows_from_filenames(arr_dir)
        print(f"  sin index.tsv; reconstruidas {len(rows)} filas desde los nombres",
              flush=True)
    feats, labels, groups = [], [], []
    for i, r in enumerate(rows, 1):
        f = arr_dir / f"{r['sid']}.npz"
        if not f.exists():
            continue
        try:
            a = np.load(f)["x"].astype(np.float32)
        except Exception:
            continue
        feats.append(terrain_stats(a))
        labels.append(int(r["label"]))
        groups.append(r.get("group", ""))
        if i % 400 == 0:
            print(f"  {i}/{len(rows)}", flush=True)
    return feats, np.asarray(labels), groups


def ppv_at(prevalence, sens=0.70, fpr=0.005):
    tp = sens * prevalence
    fp = fpr * (1 - prevalence)
    return tp / (tp + fp) if (tp + fp) else float("nan")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--vig-dir", type=Path,
                    default=PROJECT_ROOT / "data/trasancos-vignettes-v1")
    ap.add_argument("--out-dir", type=Path,
                    default=PROJECT_ROOT / "data/terrain-cascade-v1")
    ap.add_argument("--keep-recall", type=float, default=0.98,
                    help="fracción de castros que la criba debe conservar")
    args = ap.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    feats, y, groups = load(args.vig_dir)
    if len(y) == 0:
        raise SystemExit("sin viñetas: ejecuta antes build_trasancos_vignettes.py")
    npos = int(y.sum())
    print(f"viñetas: {len(y)} | castros: {npos} | negativos: {len(y)-npos}",
          flush=True)
    if npos < 10:
        raise SystemExit("demasiados pocos castros para calibrar umbrales")

    names = list(feats[0].keys())
    M = np.array([[f[n] for n in names] for f in feats], dtype=np.float32)
    pos_mask = y == 1

    # Un umbral por descriptor, colocado en el percentil que conserva la
    # fracción exigida de castros. Se prueban las dos direcciones porque para
    # unos descriptores lo descartable es el valor bajo y para otros el alto.
    lo_q = (1 - args.keep_recall) * 100
    rules = []
    for j, n in enumerate(names):
        v_pos, v_all = M[pos_mask, j], M[:, j]
        for direction in ("min", "max"):
            if direction == "min":
                thr = float(np.percentile(v_pos, lo_q))
                keep = v_all >= thr
            else:
                thr = float(np.percentile(v_pos, 100 - lo_q))
                keep = v_all <= thr
            kept_pos = float(keep[pos_mask].mean())
            kept_all = float(keep.mean())
            if kept_pos >= args.keep_recall and kept_all < 0.999:
                rules.append({"feature": n, "direction": direction,
                              "threshold": thr, "kept_positives": kept_pos,
                              "kept_all": kept_all,
                              "discarded_area": 1 - kept_all})

    rules.sort(key=lambda r: -r["discarded_area"])
    print("\n=== reglas individuales que conservan "
          f"≥{args.keep_recall:.0%} de castros ===", flush=True)
    print(f"  {'descriptor':22s} {'dir':>4} {'umbral':>10} "
          f"{'castros':>8} {'área descartada':>16}")
    for r in rules[:12]:
        print(f"  {r['feature']:22s} {r['direction']:>4} {r['threshold']:10.4f} "
              f"{r['kept_positives']:8.3f} {r['discarded_area']:15.1%}")

    # Combinación codiciosa: añadir reglas mientras el recall aguante.
    keep = np.ones(len(y), bool)
    chosen = []
    for r in rules:
        j = names.index(r["feature"])
        cand = keep & (M[:, j] >= r["threshold"] if r["direction"] == "min"
                       else M[:, j] <= r["threshold"])
        if cand[pos_mask].mean() >= args.keep_recall:
            keep = cand
            chosen.append(r)

    kept_pos = float(keep[pos_mask].mean())
    kept_all = float(keep.mean())
    kept_neg = float(keep[~pos_mask].mean())
    new_prev = DEPLOY_PREVALENCE / max(kept_neg, 1e-9)
    new_prev = min(new_prev, 1.0)

    print(f"\n=== cascada combinada ({len(chosen)} reglas) ===", flush=True)
    print(f"  castros conservados      {kept_pos:.3f}")
    print(f"  negativos conservados    {kept_neg:.3f}")
    print(f"  área conservada          {kept_all:.3f}  "
          f"(descarta el {1-kept_all:.1%})")
    print(f"  tasa base   1:{1/DEPLOY_PREVALENCE:.0f}  ->  1:{1/new_prev:.0f}")
    print(f"  VPP con sens 0.70 y FPR 0.005: "
          f"{ppv_at(DEPLOY_PREVALENCE):.3f} -> {ppv_at(new_prev):.3f}")

    by_group = {}
    for g in sorted(set(groups)):
        m = np.array([x == g for x in groups])
        if m.sum():
            by_group[g] = {"n": int(m.sum()), "kept": float(keep[m].mean())}
    print("\n  descarte por clase de negativo:", flush=True)
    for g, d in sorted(by_group.items(), key=lambda kv: kv[1]["kept"]):
        print(f"    {g:24s} n={d['n']:5d}  conserva {d['kept']:.2f}")

    out = {"keep_recall_target": args.keep_recall,
           "n_samples": int(len(y)), "n_positives": npos,
           "rules": chosen,
           "combined": {"kept_positives": kept_pos, "kept_negatives": kept_neg,
                        "kept_all": kept_all,
                        "base_rate_before": DEPLOY_PREVALENCE,
                        "base_rate_after": new_prev,
                        "ppv_before": ppv_at(DEPLOY_PREVALENCE),
                        "ppv_after": ppv_at(new_prev)},
           "by_group": by_group}
    (args.out_dir / "cascade.json").write_text(
        json.dumps(out, indent=2, default=float), encoding="utf-8")

    L = ["# Cribado de terreno: primera etapa de la cascada", "",
         f"Calibrado sobre `{len(y)}` viñetas (`{npos}` castros) para conservar "
         f"al menos el `{args.keep_recall:.0%}` de los castros conocidos.", "",
         "Una criba que descarte un castro lo pierde para siempre: ningún modelo",
         "posterior lo recupera. Por eso los umbrales salen del percentil de la",
         "distribución de castros, no de la intuición.", "",
         "| descriptor | dirección | umbral | castros | área descartada |",
         "|---|---|---:|---:|---:|"]
    for r in chosen:
        L.append(f"| `{r['feature']}` | `{r['direction']}` | `{r['threshold']:.4f}` "
                 f"| `{r['kept_positives']:.3f}` | `{r['discarded_area']:.1%}` |")
    L += ["", "## Efecto combinado", "", "| magnitud | antes | después |", "|---|---:|---:|",
          f"| castros conservados | `1.000` | `{kept_pos:.3f}` |",
          f"| área conservada | `1.000` | `{kept_all:.3f}` |",
          f"| tasa base | `1:{1/DEPLOY_PREVALENCE:.0f}` | `1:{1/new_prev:.0f}` |",
          f"| VPP (sens `0.70`, FPR `0.005`) | `{ppv_at(DEPLOY_PREVALENCE):.3f}` | "
          f"**`{ppv_at(new_prev):.3f}`** |", "",
          "## Cautelas", "",
          f"- Calibrado sobre `{npos}` castros: los umbrales heredan ese intervalo.",
          "- Las viñetas provienen de sitios catalogados, que son los que alguien",
          "  encontró. Un castro bajo dosel cerrado y muy erosionado podría caer",
          "  fuera de estos percentiles sin que el corpus lo revele: es sesgo de",
          "  espectro, y no se puede corregir con estos datos.",
          "- El área descartada se mide sobre la mezcla de viñetas, no sobre",
          "  terreno real. En barrido ciego habrá más terreno trivial, así que el",
          "  descarte real debería ser **mayor**, no menor.", ""]
    rep = PROJECT_ROOT / "reports/terrain_cascade_v1.md"
    rep.parent.mkdir(exist_ok=True)
    rep.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"\ninforme: {rep}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
