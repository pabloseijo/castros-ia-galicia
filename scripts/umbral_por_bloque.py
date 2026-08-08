#!/usr/bin/env python3
"""¿El rendimiento flojo es del modelo o del punto de operación? Solo CPU.

Toda la sesión ha medido a umbral `0.70`, que es una elección heredada y
arbitraria. Pero la precisión de v7 va de `0.864` a `0.129` según el umbral **en
el mismo bloque**, así que la cifra que duele —precisión media `0.632`, `0.391`
en Pontevedra— puede ser en buena parte una decisión de despliegue mal tomada,
no una carencia del modelo.

Esto lo mide sin tocar la GPU: los barridos ya están hechos y el umbral es un
parámetro de lectura.

## Cómo se elige el umbral sin hacer trampa

Elegir el umbral mirando el mismo bloque donde luego se mide es optimismo puro.
Aquí se usa **dejar un bloque fuera**: el umbral de cada bloque se elige
maximizando el `F1` en **los otros tres**, y se evalúa en el que quedó fuera. Es
la estimación honesta de lo que daría un umbral elegido en validación y aplicado
a territorio nuevo — que es exactamente lo que pasará al barrer Galicia.

Se reportan tres cifras por modelo:

- `F1@0.70`: el punto preregistrado, para comparar con lo ya publicado.
- `F1 oráculo`: eligiendo el mejor umbral de cada bloque **mirando ese bloque**.
  Es una cota superior inalcanzable, y sirve para saber cuánto hay en juego.
- `F1 honesto`: umbral elegido dejando el bloque fuera. **Es la cifra que vale.**

Uso:
    python3 scripts/umbral_por_bloque.py --modelos v7 v8 --bloques lugo coruna ourense pontevedra
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from detection_eval import a_metros, agrupar, leer_tsv  # noqa: E402


def prf(pred, truth, masc, umbral, enlace=512.0, tol=500.0):
    """Precisión, recall y F1 a un umbral, con el mismo agrupado que la evaluación."""
    sel = [p for p in pred if p["score"] >= umbral]
    if not sel:
        return 0.0, 0.0, 0.0
    lat0 = float(np.mean([t["lat"] for t in truth]))
    px, py = a_metros([p["lon"] for p in sel], [p["lat"] for p in sel], lat0)
    tx, ty = a_metros([t["lon"] for t in truth], [t["lat"] for t in truth], lat0)
    mx = my = None
    if masc:
        mx, my = a_metros([m["lon"] for m in masc], [m["lat"] for m in masc], lat0)
    tp = fp = 0
    tocados = set()
    for g in agrupar(px, py, enlace):
        cx, cy = float(np.mean(px[g])), float(np.mean(py[g]))
        d = np.hypot(tx - cx, ty - cy)
        if d.min() <= tol:
            tp += 1
            tocados.add(int(d.argmin()))
        elif mx is not None and np.hypot(mx-cx, my-cy).min() <= tol:
            pass                                   # contaminado: ni TP ni FP
        else:
            fp += 1
    rec = len(tocados) / max(len(truth), 1)
    pre = tp / max(tp + fp, 1)
    f1 = 2 * pre * rec / max(pre + rec, 1e-9)
    return pre, rec, f1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--modelos", nargs="+", default=["v7"])
    ap.add_argument("--bloques", nargs="+",
                    default=["lugo", "coruna", "ourense", "pontevedra"])
    ap.add_argument("--grid", type=float, nargs=3, default=[0.30, 0.96, 0.02])
    args = ap.parse_args()

    us = np.arange(args.grid[0], args.grid[1], args.grid[2])
    for mod in args.modelos:
        curvas = {}
        for B in args.bloques:
            f = Path(f"data/sweep_val_{B}_{mod}.tsv")
            if not f.exists():
                print(f"{mod}/{B}: sin barrido"); continue
            pred = [p for p in leer_tsv(f, ("lon", "lat", "score"))
                    if "score" in p]
            for p in pred:
                p["score"] = float(p["score"])
            truth = leer_tsv(Path(f"data/{B}_fus_truth_limpia.tsv"))
            mk = Path(f"data/{B}_fus_mascara_train.tsv")
            masc = leer_tsv(mk) if mk.exists() else []
            curvas[B] = np.array([prf(pred, truth, masc, u)[2] for u in us])
            print(f"  {mod}/{B} curva calculada", flush=True)
        if len(curvas) < 2:
            continue

        print(f"\n{'='*66}\nMODELO {mod}\n{'='*66}")
        print(f"{'bloque':<12}{'F1@0.70':>9}{'u* propio':>11}{'F1 oraculo':>12}"
              f"{'u* fuera':>10}{'F1 honesto':>12}")
        i70 = int(np.argmin(np.abs(us - 0.70)))
        a70, aor, aho = [], [], []
        for B, c in curvas.items():
            j_or = int(np.nanargmax(c))
            otros = np.mean([curvas[o] for o in curvas if o != B], axis=0)
            j_ho = int(np.nanargmax(otros))
            a70.append(c[i70]); aor.append(c[j_or]); aho.append(c[j_ho])
            print(f"{B:<12}{c[i70]:>9.3f}{us[j_or]:>11.2f}{c[j_or]:>12.3f}"
                  f"{us[j_ho]:>10.2f}{c[j_ho]:>12.3f}")
        print(f"{'MEDIA':<12}{np.mean(a70):>9.3f}{'':>11}{np.mean(aor):>12.3f}"
              f"{'':>10}{np.mean(aho):>12.3f}")
        print(f"\n  ganancia honesta sobre el umbral fijo 0.70: "
              f"{np.mean(aho)-np.mean(a70):+.3f}")
        print("  (el oraculo es cota superior inalcanzable: elige mirando el "
              "propio bloque)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
