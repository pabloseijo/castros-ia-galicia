#!/usr/bin/env python3
"""Línea base entrenada sin GPU, para que la CNN tenga algo que batir.

No pretende competir con un ConvNeXt. Pretende cerrar el circuito de punta a
punta —viñetas, entrenamiento, evaluación honesta— y dejar una cifra medida
antes de que llegue la GPU. Sin esa referencia no habrá forma de saber si la
red aporta algo o solo consume electricidad, que es exactamente el control que
este proyecto exige a cualquier método nuevo.

Extrae de cada viñeta de 1 m descriptores concéntricos —los mismos que ya
demostraron señal en el baseline a mano de O Val, donde el contraste anular
ordenó a los castros por delante de las nueve clases negativas— y entrena un
gradient boosting sobre ellos.

La evaluación va por `honest_eval`, así que cada número sale con su intervalo
y con el VPP reexpresado a la tasa base real del barrido (`1:475`). Un AUC sin
intervalo sobre `68` positivos no significa nada, y aquí no se va a reportar.

El split es por bloque espacial y O Val queda fuera de entrenamiento siempre.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

# Paralelismo de proceso, no de hilo: los arrays son pequeños.
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from honest_eval import evaluate, render, wilson as wilson_ci  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def features(arr: np.ndarray) -> np.ndarray:
    """Descriptores concéntricos sobre los tres canales de relieve.

    Concéntricos porque un castro es un recinto: plataforma con un borde
    alrededor. La escala se barre en vez de fijarse, ya que los radios reales
    van de `38` a `83 m` (p10 a p90 del polígono OSM) y un radio único fue
    justamente el sesgo estructural que costó caro en la versión de 512 m.
    """
    c, h, w = arr.shape
    yy, xx = np.mgrid[0:h, 0:w]
    r = np.hypot(yy - h / 2.0, xx - w / 2.0)
    out = []
    for ch in range(c):
        a = arr[ch].astype(np.float32)
        bg = r > 170
        bg_mean = float(a[bg].mean()) if bg.any() else 0.0
        bg_std = float(a[bg].std()) if bg.any() else 1e-6
        out += [float(a.mean()), float(a.std()),
                float(np.percentile(a, 90) - np.percentile(a, 10))]
        for r0, r1 in ((0, 25), (25, 45), (45, 70), (70, 100), (100, 140)):
            m = (r >= r0) & (r < r1)
            if not m.any():
                out += [0.0, 0.0, 0.0]
                continue
            v = a[m]
            out += [float(v.mean() - bg_mean),
                    float(v.std() / (bg_std + 1e-6)),
                    float(np.percentile(v, 90) - np.percentile(v, 10))]
        # Simetría radial: un recinto es aproximadamente circular, un talud
        # natural o una terraza no lo son.
        for r0, r1 in ((25, 45), (45, 70), (70, 100)):
            m = (r >= r0) & (r < r1)
            if not m.any():
                out.append(0.0)
                continue
            ang = np.arctan2(yy - h / 2.0, xx - w / 2.0)[m]
            sec = ((ang + np.pi) / (2 * np.pi) * 8).astype(int) % 8
            means = [a[m][sec == s].mean() for s in range(8) if (sec == s).any()]
            out.append(float(np.std(means)) if len(means) > 1 else 0.0)
    return np.asarray(out, dtype=np.float32)


def load_split(vig_dir: Path, multiclass: bool = False):
    idx = vig_dir / "index.tsv"
    if not idx.exists():
        raise SystemExit(f"falta {idx}: ejecuta antes build_trasancos_vignettes.py")
    rows = list(csv.DictReader(open(idx, encoding="utf-8"), delimiter="\t"))
    arr_dir = vig_dir / "arrays"
    X, y, meta = [], [], []
    # En multiclase la etiqueta sale del grupo: castro=1, mámoa=2, resto=0.
    # Gomes et al. (2024) montaron justo estas tres clases y su modelo detectó
    # CERO túmulos mientras reportaba 94% de precisión. Por eso aquí las
    # métricas van por clase: una clase que colapsa tiene que verse.
    t0 = time.time()
    for i, r in enumerate(rows, 1):
        f = arr_dir / f"{r['sid']}.npz"
        if not f.exists():
            continue
        try:
            a = np.load(f)["x"].astype(np.float32)
        except Exception:
            continue
        X.append(features(a))
        if multiclass:
            g = (r.get("group") or "").strip()
            y.append(1 if g == "castro" else (2 if g == "mamoa" else 0))
        else:
            y.append(int(r["label"]))
        meta.append(r)
        if i % 500 == 0:
            print(f"  features {i}/{len(rows)} ({time.time()-t0:.0f}s)", flush=True)
    return np.vstack(X), np.asarray(y), meta


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--vig-dir", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--seed", type=int, default=20260803)
    ap.add_argument("--multiclass", action="store_true",
                    help="castro / mámoa / fondo en vez de binario")
    args = ap.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    try:
        from sklearn.ensemble import HistGradientBoostingClassifier
        from sklearn.calibration import CalibratedClassifierCV
    except ImportError:
        raise SystemExit("hace falta scikit-learn")

    X, y, meta = load_split(args.vig_dir, args.multiclass)
    print(f"muestras: {len(y)} | positivos {int(y.sum())} | "
          f"features {X.shape[1]}", flush=True)
    if int(y.sum()) < 10:
        raise SystemExit("demasiados pocos positivos para entrenar")

    splits = np.array([m["split"] for m in meta])
    tr = np.isin(splits, ["train"])
    va = np.isin(splits, ["val"])
    te = np.isin(splits, ["test_o_val"])
    print(f"train {tr.sum()} ({y[tr].sum()} pos) | val {va.sum()} "
          f"({y[va].sum()} pos) | test_o_val {te.sum()} ({y[te].sum()} pos)",
          flush=True)
    if tr.sum() == 0 or y[tr].sum() < 5:
        raise SystemExit("split de entrenamiento vacío o sin positivos")

    # No se reequilibra por remuestreo: está medido que degrada la calibración
    # (RUS multiplica el error de calibración por 6.6 a razón 1:20). Se pesa la
    # clase y se calibra después, que es lo que da menor error de calibración.
    if args.multiclass:
        from collections import Counter as _C
        print("clases:", dict(_C(y.tolist())), flush=True)
        clf = HistGradientBoostingClassifier(
            max_iter=300, learning_rate=0.06, early_stopping=True,
            validation_fraction=0.15, random_state=args.seed,
            class_weight="balanced")
        clf.fit(X[tr], y[tr])
        names = {0: "fondo", 1: "castro", 2: "mamoa"}
        out = {"mode": "multiclass", "n_features": int(X.shape[1]), "per_class": {}}
        for sname, mask in (("val", va), ("test_o_val", te)):
            if mask.sum() == 0:
                continue
            pred, yt = clf.predict(X[mask]), y[mask]
            out["per_class"][sname] = {}
            print(f"\n  {sname}:", flush=True)
            for c, nm in names.items():
                n = int((yt == c).sum())
                if n == 0:
                    continue
                tp = int(((pred == c) & (yt == c)).sum())
                fp = int(((pred == c) & (yt != c)).sum())
                rec = tp / n
                prec = tp / (tp + fp) if tp + fp else 0.0
                lo, hi = wilson_ci(tp, n)
                flag = "  <-- COLAPSADA" if rec == 0 else ""
                print(f"    {nm:8s} n={n:5d}  recall {rec:.3f} "
                      f"[{lo:.2f},{hi:.2f}]  precision {prec:.3f}{flag}", flush=True)
                out["per_class"][sname][nm] = {"n": n, "recall": rec,
                    "recall_ci95": [lo, hi], "precision": prec,
                    "collapsed": rec == 0}
        (args.out_dir / "metrics.json").write_text(
            json.dumps(out, indent=2, default=float), encoding="utf-8")
        return 0

    npos, nneg = int(y[tr].sum()), int((~y[tr].astype(bool)).sum())
    w = np.where(y[tr] == 1, nneg / max(npos, 1), 1.0)

    clf = HistGradientBoostingClassifier(
        max_iter=300, learning_rate=0.06, max_depth=None,
        early_stopping=True, validation_fraction=0.15,
        random_state=args.seed)
    clf.fit(X[tr], y[tr], sample_weight=w)

    # Calibración post-hoc isotónica sobre validación: la vía que la literatura
    # de desequilibrio de clases mide como de menor error de calibración.
    out = {"n_features": int(X.shape[1]), "splits": {}}
    if va.sum() > 20 and y[va].sum() >= 3:
        cal = CalibratedClassifierCV(clf, method="isotonic", cv="prefit")
        cal.fit(X[va], y[va])
        scorer = lambda Z: cal.predict_proba(Z)[:, 1]
        out["calibration"] = "isotonic on val"
    else:
        scorer = lambda Z: clf.predict_proba(Z)[:, 1]
        out["calibration"] = "none (val demasiado pequeño)"

    md_parts = []
    for name, mask in (("val", va), ("test_o_val", te)):
        if mask.sum() == 0 or y[mask].sum() == 0:
            continue
        s = scorer(X[mask])
        res = evaluate(s, y[mask])
        out["splits"][name] = res
        md_parts.append(f"# {name}\n\n" + render(res))
        with open(args.out_dir / f"scores_{name}.tsv", "w", newline="",
                  encoding="utf-8") as fh:
            wr = csv.writer(fh, delimiter="\t")
            wr.writerow(["sid", "name", "group", "label", "score"])
            for m, sc in zip([m for m, k in zip(meta, mask) if k], s):
                wr.writerow([m["sid"], m.get("name", ""), m.get("group", ""),
                             m["label"], f"{sc:.6f}"])

    (args.out_dir / "metrics.json").write_text(
        json.dumps(out, indent=2, default=float), encoding="utf-8")
    report = PROJECT_ROOT / "reports" / f"{args.out_dir.name}.md"
    report.parent.mkdir(exist_ok=True)
    report.write_text("\n\n---\n\n".join(md_parts) or "sin splits evaluables",
                      encoding="utf-8")

    for name, res in out["splits"].items():
        d = res.get("diagnostic", {}).get("by_threshold", {})
        best = max(d.values(), key=lambda b: b["specificity"]) if d else {}
        print(f"  {name}: AP {res['average_precision']:.3f} "
              f"IC95% [{res['average_precision_ci95'][0]:.3f}, "
              f"{res['average_precision_ci95'][1]:.3f}] | "
              f"mejor especificidad {best.get('specificity', float('nan')):.4f} "
              f"-> VPP a tasa real {best.get('ppv_at_deploy_prevalence', float('nan')):.3f}",
              flush=True)
    print(f"informe: {report}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
