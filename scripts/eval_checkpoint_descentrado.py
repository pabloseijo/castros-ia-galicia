#!/usr/bin/env python3
"""Compara checkpoints en la condición que importa: la viñeta descentrada.

Existe por un fallo concreto. `best.pt` se elige durante el entrenamiento por F1
macro sobre **validación centrada**, y está medido que centrado y descentrado no
son la misma tarea: un castro de validación pasa de mediana `0.988` a `0.386` al
verse desde la celda del barrido, mientras que los negativos no se mueven.

Eso convierte la comparación «con traslación contra sin traslación» en una
trampa: la augmentación por traslación **tiene que perder** en validación
centrada —es lo que hace, descentrar— y por tanto el checkpoint que se guarda
como mejor es el que menos ha aprendido lo que se quería probar. Un barrido
lanzado con ese `best.pt` decide el experimento con el modelo equivocado.

Este script puntúa cada checkpoint sobre la misma validación con desplazamiento
**determinista** —sembrado por índice de muestra, para que la comparación entre
checkpoints sea la misma imagen— y reporta F1 macro en las dos condiciones.

Uso:
    python3 scripts/eval_checkpoint_descentrado.py --vig-dir data/galicia-vignettes-v3 \\
        --ckpt data/cls-v4/best.pt data/cls-v4/last.pt data/cls-v3/best.pt --translate 128
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np
import torch


def desplazar(a, dy, dx, t):
    _, h, w = a.shape
    pad = np.pad(a, ((0, 0), (t, t), (t, t)), mode="reflect")
    return pad[:, t-dy:t-dy+h, t-dx:t-dx+w]


def cargar(ckpt, dev):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from train_unet_multiclass import UNetMulticlass

    est = torch.load(ckpt, map_location="cpu", weights_only=False)
    cfg = est.get("args", {}) or {}
    m = UNetMulticlass(3, cfg.get("encoder", "resnet34"), cfg.get("head", "cls"),
                       False, cfg.get("lse_r", 8.0))
    m.load_state_dict(est["model"])
    return m.to(dev).eval(), est.get("epoch"), cfg.get("translate", 0)


def f1_macro(pred, true):
    f1s = []
    for c in (1, 2):                      # castro, mamoa; el fondo no interesa
        tp = int(((pred == c) & (true == c)).sum())
        fp = int(((pred == c) & (true != c)).sum())
        fn = int(((pred != c) & (true == c)).sum())
        r = tp / (tp + fn) if tp + fn else 0.0
        p = tp / (tp + fp) if tp + fp else 0.0
        f1s.append(2*r*p/(r+p) if r+p else 0.0)
    return float(np.mean(f1s)), f1s


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vig-dir", type=Path, required=True)
    ap.add_argument("--ckpt", type=Path, nargs="+", required=True)
    ap.add_argument("--translate", type=int, default=128)
    ap.add_argument("--split", default="val")
    ap.add_argument("--lote", type=int, default=32)
    args = ap.parse_args()

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    filas = [r for r in csv.DictReader(
        open(args.vig_dir / "index.tsv", encoding="utf-8"), delimiter="\t")
        if r["split"] == args.split]
    grupo = {"castro": 1, "mamoa": 2}
    y = np.array([grupo.get(r["group"], 0) if r["label"] == "1" else 0
                  for r in filas])
    print("validación: %d viñetas | castro %d | mámoa %d"
          % (len(filas), (y == 1).sum(), (y == 2).sum()), flush=True)

    print("\n%-26s %5s %5s %10s %10s %8s %9s %9s"
          % ("checkpoint", "ép", "tr", "F1 centr.", "F1 desc.", "caída",
             "P@2% ctr", "P@2% desc"))
    print("-" * 92)
    for ck in args.ckpt:
        modelo, ep, tr = cargar(ck, dev)
        res, prec = {}, {}
        for cond in ("centrado", "descentrado"):
            preds, probs = [], []
            with torch.no_grad():
                for i in range(0, len(filas), args.lote):
                    trozo = filas[i:i+args.lote]
                    arrs = []
                    for k, r in enumerate(trozo):
                        a = np.load(args.vig_dir / "arrays" /
                                    ("%s.npz" % r["sid"]))["x"].astype(np.float32)
                        if cond == "descentrado":
                            rng = np.random.default_rng(20260805 + i + k)
                            t = args.translate
                            a = desplazar(a, int(rng.integers(-t, t+1)),
                                          int(rng.integers(-t, t+1)), t)
                        arrs.append(np.ascontiguousarray(a))
                    x = torch.from_numpy((np.stack(arrs)-0.5)/0.5).float().to(dev)
                    lg, _ = modelo(x)
                    preds.append(lg.argmax(1).cpu().numpy())
                    probs.append(torch.softmax(lg.float(), 1)[:, 1].cpu().numpy())
            res[cond] = f1_macro(np.concatenate(preds), y)[0]
            # **Precisión en el extremo alto, que es donde se usa esto.**
            # El F1 por `argmax` mide UN punto de operación implícito, y este
            # proyecto no despliega ahí: barre con umbral alto y sacrifica
            # recall a propósito, para que un humano no tenga que abrir
            # cientos de candidatos. Los dos números pueden ordenar al revés, y
            # el 2026-08-07 lo hicieron: la criba puso a `v6-focal` el último
            # por F1 descentrado (`0.2316`) mientras el barrido real le daba la
            # mejor precisión de todo el proyecto —`0.957` en Lugo, `34`
            # candidatos y **un** falso positivo—. Elegir por F1 habría tirado
            # el mejor resultado que hay.
            S = np.concatenate(probs)
            k = max(1, int(0.02 * len(S)))   # top 2%: el orden del barrido real
            res_top = (y[np.argsort(-S)[:k]] == 1)
            prec[cond] = float(res_top.mean())
        print("%-26s %5s %5s %10.4f %10.4f %+8.4f %9.3f %9.3f"
              % (str(ck)[-24:], ep, tr, res["centrado"], res["descentrado"],
                 res["descentrado"] - res["centrado"],
                 prec["centrado"], prec["descentrado"]))
        del modelo
        if dev == "cuda":
            torch.cuda.empty_cache()
    print("\n`P@2% desc` es la fracción de aciertos entre el 2% mejor puntuado,")
    print("descentrado. Se añadió porque el F1 mide UN punto de operación y este")
    print("proyecto despliega en el extremo alto del umbral — y ordenan al revés.")
    print("\nPERO NINGUNA DE LAS DOS PREDICE EL BARRIDO, y hay que saber por qué:")
    print("aquí la tasa base es ~6% de castros (180 de 2.991) y en el barrido")
    print("ciego es 1:475, o sea 0,2%. Treinta veces menos. Una precisión alta")
    print("sobre viñetas curadas no se traslada a una rejilla donde casi todo es")
    print("terreno vacío. Esta criba sirve para DESCARTAR un checkpoint roto en")
    print("minutos; para elegir el mejor prospector no hay atajo — hay que barrer.")
    print("\nEl barrido debe lanzarse con el mejor en la columna DESCENTRADA:")
    print("es la única que se parece a lo que ve el modelo en despliegue.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
