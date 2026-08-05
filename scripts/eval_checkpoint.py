#!/usr/bin/env python3
"""Evalúa un checkpoint ya entrenado, sin reentrenar nada.

Existe porque el `2026-08-05` hubo que retirar una comparación entre la U-Net
completa y la cabeza sin decodificador: los checkpoints que se compararon los
había elegido una métrica de selección defectuosa, así que enfrentaban épocas
distintas y no medían la arquitectura. Los `last.pt` de ambas corridas **sí** son
de la misma época, de modo que compararlos es la vía honesta que queda sin
gastar otras diez horas de GPU.

Reporta lo mismo que el entrenador —recall, precisión, Wilson y marca de
colapso por clase— más ROC-AUC y AP de castro-contra-resto, que es lo que
faltaba por época.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from honest_eval import average_precision, roc_auc  # noqa: E402
from train_unet_multiclass import (CLASS_NAMES, UNetMulticlass,  # noqa: E402
                                   Vignettes, infer, label_of, per_class_block,
                                   selection_score)
from torch.utils.data import DataLoader


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--vig-dir", type=Path, required=True)
    ap.add_argument("--checkpoint", type=Path, required=True)
    ap.add_argument("--splits", nargs="+", default=["val", "test_o_val"])
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    st = torch.load(args.checkpoint, map_location=device, weights_only=False)
    cfg = st.get("args", {})
    head = cfg.get("head", "mil")
    encoder = cfg.get("encoder", "resnet34")
    epoch = st.get("epoch", -1) + 1
    print(f"checkpoint: {args.checkpoint}")
    print(f"  cabeza {head} | codificador {encoder} | época {epoch}", flush=True)

    model = UNetMulticlass(3, encoder, head, pretrained=False,
                           lse_r=cfg.get("lse_r", 8.0)).to(device)
    model.load_state_dict(st["model"])

    rows = list(csv.DictReader(open(args.vig_dir / "index.tsv", encoding="utf-8"),
                               delimiter="\t"))
    arr_dir = args.vig_dir / "arrays"
    rows = [r for r in rows if (arr_dir / f"{r['sid']}.npz").exists()]

    out = {"checkpoint": str(args.checkpoint), "head": head,
           "encoder": encoder, "epoch": epoch, "per_class": {}, "ranking": {}}
    for split in args.splits:
        rr = [r for r in rows if r["split"] == split]
        if not rr:
            continue
        dl = DataLoader(Vignettes(rr, arr_dir, augment=False),
                        batch_size=args.batch, shuffle=False,
                        num_workers=args.workers, pin_memory=(device == "cuda"))
        pred, true, prob = infer(model, dl, device, device == "cuda")
        blk = per_class_block(pred, true)
        out["per_class"][split] = blk
        print(f"\n  {split}:", flush=True)
        for nm, b in blk.items():
            flag = "  <-- COLAPSADA" if b["collapsed"] else ""
            print(f"    {nm:8s} n={b['n']:5d}  recall {b['recall']:.3f} "
                  f"[{b['recall_ci95'][0]:.2f},{b['recall_ci95'][1]:.2f}]  "
                  f"precision {b['precision']:.3f}{flag}", flush=True)
        lab = (true == 1).astype(int)
        if lab.sum() and (1 - lab).sum():
            r = {"roc_auc": roc_auc(prob[:, 1], lab),
                 "average_precision": average_precision(prob[:, 1], lab)}
            out["ranking"][split] = r
            print(f"    castro-vs-resto: ROC-AUC {r['roc_auc']:.4f} | "
                  f"AP {r['average_precision']:.4f}", flush=True)
        print(f"    F1 macro (castro+mámoa): {selection_score(blk):.4f}", flush=True)
        out.setdefault("selection", {})[split] = selection_score(blk)

    print("\n" + json.dumps(out, indent=2, default=float)[:0] or "", end="")
    dest = args.checkpoint.parent / f"eval_{args.checkpoint.stem}.json"
    dest.write_text(json.dumps(out, indent=2, default=float), encoding="utf-8")
    print(f"\nguardado: {dest}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
