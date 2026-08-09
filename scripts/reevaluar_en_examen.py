#!/usr/bin/env python3
"""Puntua un checkpoint viejo sobre el examen de OTRO corpus, para comparar justo.

**Por que hace falta.** El 2026-08-09, el corpus de v11p heredo el examen de v7
pero solo pudo cortar las viñetas que tambien existian en el: los positivos
entraron completos (`180` castros, `122` mamoas) y faltaron `2.404` de fondo. El
examen paso de `15:1` a `1,6:1` de negativos por positivo, y en un examen
equilibrado la precision es mucho mas facil.

Comparar el `selection_best` de v11p con el `0,4605` de v7 seria entonces
comparar dos examenes distintos: si sale mas alto no se sabria si es la dosis de
datos o la benevolencia del examen. Esto lo resuelve **puntuando v7 sobre el
examen exacto de v11p**.

Uso:
    python3 scripts/reevaluar_en_examen.py --checkpoint data/cls-v7/best.pt \\
        --vig-dir data/galicia-vignettes-v11p --split val
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from train_unet_multiclass import UNetMulticlass, selection_score  # noqa: E402

CLASES = ["fondo", "castro", "mamoa"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--checkpoint", type=Path, required=True)
    ap.add_argument("--vig-dir", type=Path, required=True)
    ap.add_argument("--split", default="val")
    ap.add_argument("--batch", type=int, default=16)
    args = ap.parse_args()

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    st = torch.load(args.checkpoint, map_location=dev, weights_only=False)
    a = st.get("args", {})
    # **Los canales se leen del checkpoint, no se suponen.** v8 entrena con `4`
    # (apertura) y v9 con `7` (apertura mas ortofoto): cargarlos en un modelo de
    # `3` revienta con un `size mismatch` de `stem.0.weight`. Y no es un fallo que
    # arreglar: un modelo de `7` canales **no puede** evaluarse sobre un corpus de
    # `3`, porque le faltan entradas. Se dice y se salta, en vez de volcar un
    # traceback que parece un error del guion.
    w = st["model"].get("stem.0.weight")
    in_ch = int(w.shape[1]) if w is not None else 3
    z0 = np.load(next((args.vig_dir / "arrays").glob("*.npz")))
    ch_corpus = int(z0["x"].shape[0])
    if in_ch != ch_corpus:
        print(f"  SALTADO: {args.checkpoint.parent.name} espera {in_ch} canales y "
              f"el corpus tiene {ch_corpus}. No son comparables en este examen.")
        return 0
    model = UNetMulticlass(n_classes=3, encoder=a.get("encoder", "resnet34"),
                           head=a.get("head", "cls"), pretrained=False,
                           in_ch=in_ch).to(dev)
    model.load_state_dict(st["model"])
    model.eval()

    filas = []
    with (args.vig_dir / "index.tsv").open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            if (r.get("split") or "").strip() == args.split:
                filas.append(r)
    print(f"examen: {len(filas)} viñetas de {args.vig_dir.name}/{args.split}")

    # **La clase sale del `group`, no del `label` del npz.** El `label` es binario
    # (0/1) y no distingue mamoa de castro: leyendolo, las `122` mamoas del examen
    # aparecian como fondo y la seleccion habria salido de otra cosa. El propio
    # entrenamiento hace este mapeo (`train_unet_multiclass.py`, linea 122).
    def clase(g):
        g = (g or "").strip()
        return 1 if g == "castro" else (2 if g == "mamoa" else 0)

    # **Por lotes, sin acumular.** La primera version cargaba las `587` viñetas
    # enteras antes de puntuar: `587 x 3 x 512 x 512` en `float32` son `1,8 GB`, y
    # con el modelo y las copias de torch el pico llego a `2,9 GB` y el cgroup lo
    # mato. No hace falta tenerlas todas: se leen, se puntuan y se sueltan.
    arr = args.vig_dir / "arrays"
    ys, pred = [], []
    lote_x, lote_y = [], []

    def _vaciar():
        if not lote_x:
            return
        with torch.no_grad():
            b = torch.from_numpy(np.stack(lote_x)).to(dev)
            o = model(b)
            lg = o[0] if isinstance(o, (tuple, list)) else o
            pred.extend(lg.argmax(1).cpu().numpy().tolist())
        ys.extend(lote_y)
        lote_x.clear(); lote_y.clear()

    leidas = 0
    for r in filas:
        f = arr / f"{r['sid']}.npz"
        if not f.exists():
            continue
        z = np.load(f)
        lote_x.append(z["x"].astype(np.float32))
        lote_y.append(clase(r.get("group")))
        leidas += 1
        if len(lote_x) >= args.batch:
            _vaciar()
    _vaciar()
    xs = None
    print(f"  leidas {leidas} | reparto real: "
          f"{dict(zip(*np.unique(ys, return_counts=True)))}")

    pred = np.array(pred)
    ys = np.array(ys)

    bloque = {}
    print(f"\n  {'clase':<10}{'n':>6}{'recall':>9}{'precision':>11}{'F1':>8}")
    for i, nom in enumerate(CLASES):
        n = int((ys == i).sum())
        if n == 0:
            continue
        tp = int(((pred == i) & (ys == i)).sum())
        rec = tp / n
        pp = int((pred == i).sum())
        pre = tp / pp if pp else 0.0
        f1 = 2*rec*pre/(rec+pre) if (rec+pre) else 0.0
        bloque[nom] = {"recall": rec, "precision": pre, "collapsed": rec == 0}
        print(f"  {nom:<10}{n:>6}{rec:>9.3f}{pre:>11.3f}{f1:>8.3f}")

    s = selection_score(bloque)
    print(f"\n  SELECCION de {args.checkpoint.parent.name} sobre este examen: {s:.4f}")
    print("  (comparar SOLO contra otro modelo puntuado en el mismo examen)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
