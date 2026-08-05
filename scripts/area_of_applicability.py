#!/usr/bin/env python3
"""Índice de disimilitud y área de aplicabilidad sobre la incrustación de la red.

Implementa Meyer y Pebesma (2021), *Predicting into unknown space? Estimating the
area of applicability of spatial prediction models*, Methods in Ecology and
Evolution, DOI `10.1111/2041-210x.13650`, adaptado a una CNN.

## Qué contesta

Dónde **aplica** el error medido en validación, y dónde no. Su resultado central:
dentro del área, el error de validación cruzada se cumple; **fuera, no aplica**.
Está validado precisamente para datos de entrenamiento agrupados espacialmente
con validación cruzada espacial, que es nuestro caso.

## La adaptación, y dónde se aparta del original

Ellos trabajan con predictores explícitos —variables climáticas— y los ponderan
por su importancia en el modelo. Una CNN no expone importancias equivalentes, así
que aquí el espacio de predictores es **la incrustación del penúltimo nivel**,
que es lo que la red realmente usa para decidir. La ponderación queda implícita
en lo aprendido, que es más fiel que inventar pesos.

El DI de cada punto de entrenamiento se calcula **excluyendo su propio bloque
espacial**, que es el equivalente a «respecto a la estrategia de validación
cruzada empleada» del original. Sin eso, el vecino más cercano sería siempre la
viñeta de al lado y el umbral saldría absurdamente bajo.

Umbral: percentil `95` del DI de entrenamiento, como en el paper. **No está
validado para detección de objetos raros**, así que conviene reportarlo como
indicativo y no como garantía.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader

sys.path.insert(0, str(Path(__file__).resolve().parent))
from train_unet_multiclass import UNetMulticlass, Vignettes, label_of  # noqa: E402

CLASES = {0: "fondo", 1: "castro", 2: "mamoa"}


@torch.no_grad()
def incrustar(model, rows, arr_dir, device, batch, workers):
    """Incrustación del penúltimo nivel: salida del codificador tras pooling."""
    dl = DataLoader(Vignettes(rows, arr_dir, augment=False), batch_size=batch,
                    shuffle=False, num_workers=workers, pin_memory=(device == "cuda"))
    salida = []
    for x, _, _ in dl:
        x = x.to(device, non_blocking=True)
        with torch.autocast("cuda", enabled=(device == "cuda")):
            f = model.stem(x)
            f = model.layer1(model.pool(f))
            f = model.layer2(f)
            f = model.layer3(f)
            f = model.layer4(f)
            e = torch.nn.functional.adaptive_avg_pool2d(f, 1).flatten(1)
        salida.append(e.float().cpu().numpy())
    return np.concatenate(salida)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vig-dir", type=Path, required=True)
    ap.add_argument("--checkpoint", type=Path, required=True)
    ap.add_argument("--train-sample", type=int, default=2000,
                    help="muestra de entrenamiento; el DI solo necesita el vecino mas cercano")
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--seed", type=int, default=20260805)
    ap.add_argument("--out-json", type=Path)
    args = ap.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    st = torch.load(args.checkpoint, map_location=device, weights_only=False)
    cfg = st.get("args", {})
    model = UNetMulticlass(3, cfg.get("encoder", "resnet34"), cfg.get("head", "cls"),
                           pretrained=False).to(device)
    model.load_state_dict(st["model"])
    model.eval()

    filas = list(csv.DictReader(open(args.vig_dir / "index.tsv", encoding="utf-8"),
                                delimiter="\t"))
    arr = args.vig_dir / "arrays"
    filas = [r for r in filas if (arr / f"{r['sid']}.npz").exists()]
    tr = [r for r in filas if r["split"] == "train"]
    ev = [r for r in filas if r["split"] == "test_o_val"]
    if not ev:
        raise SystemExit("no hay test_o_val")

    rng = np.random.default_rng(args.seed)
    if len(tr) > args.train_sample:
        tr = [tr[i] for i in rng.choice(len(tr), args.train_sample, replace=False)]
    print(f"entrenamiento: {len(tr)} viñetas | O Val: {len(ev)}", flush=True)

    E_tr = incrustar(model, tr, arr, device, args.batch, args.workers)
    E_ev = incrustar(model, ev, arr, device, args.batch, args.workers)

    # Estandarizar cada dimension, que es lo que hace el original antes de medir
    mu, sd = E_tr.mean(0), E_tr.std(0) + 1e-8
    A = (E_tr - mu) / sd
    B = (E_ev - mu) / sd

    # Distancia media entre puntos de entrenamiento: el normalizador del DI
    idx = rng.choice(len(A), min(500, len(A)), replace=False)
    sub = A[idx]
    d_all = np.sqrt(((sub[:, None, :] - sub[None, :, :]) ** 2).sum(-1))
    norm = d_all[np.triu_indices(len(sub), 1)].mean()

    # DI de entrenamiento excluyendo el propio bloque espacial
    bloques = np.array([r["block"] for r in tr])
    DI_tr = np.empty(len(A))
    for i in range(len(A)):
        m = bloques != bloques[i]
        if not m.any():
            DI_tr[i] = np.nan; continue
        DI_tr[i] = np.sqrt(((A[m] - A[i]) ** 2).sum(1)).min() / norm
    DI_tr = DI_tr[~np.isnan(DI_tr)]
    umbral = float(np.quantile(DI_tr, 0.95))

    DI_ev = np.array([np.sqrt(((A - b) ** 2).sum(1)).min() / norm for b in B])

    print(f"\numbral del area de aplicabilidad (p95 del entrenamiento): {umbral:.4f}")
    print(f"  DI de entrenamiento: mediana {np.median(DI_tr):.4f}, "
          f"p95 {umbral:.4f}, max {DI_tr.max():.4f}")
    dentro = DI_ev <= umbral
    print(f"\nO Val: {dentro.sum()}/{len(DI_ev)} dentro del area "
          f"({100*dentro.mean():.1f}%)")

    print(f"\n{'clase':10s} {'n':>4s} {'dentro':>8s} {'DI mediana':>11s}")
    res = {}
    for c, nm in CLASES.items():
        m = np.array([label_of(r) == c for r in ev])
        if not m.any():
            continue
        print(f"{nm:10s} {m.sum():4d} {100*dentro[m].mean():7.1f}% "
              f"{np.median(DI_ev[m]):11.4f}")
        res[nm] = {"n": int(m.sum()), "dentro_pct": float(100*dentro[m].mean()),
                   "di_mediana": float(np.median(DI_ev[m]))}

    print("\nLectura: si una clase cae mayoritariamente FUERA del area, su fallo se")
    print("explica por falta de soporte en el entrenamiento — es geografia. Si cae")
    print("DENTRO y aun asi falla, el modelo tenia con que aprender y no lo hizo:")
    print("el problema son los datos de esa clase, no el terreno.")

    if args.out_json:
        args.out_json.write_text(json.dumps(
            {"umbral": umbral, "o_val_dentro_pct": float(100*dentro.mean()),
             "por_clase": res}, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
