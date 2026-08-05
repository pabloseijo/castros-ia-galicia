#!/usr/bin/env python3
"""¿El modelo falla en sus propios negativos, o solo cuando los ve descentrados?

`15` de los `25` candidatos del barrido caen a menos de `300 m` de una viñeta que
el modelo tuvo en entrenamiento **etiquetada como negativo**, y con el tipo de
negativo que corresponde a lo que se ve en la ortofoto: cantera donde la etiqueta
dice `mining_quarry`, embalse donde dice `modern_infrastructure`. Hay dos causas
posibles y piden arreglos opuestos:

**A. Infraajuste de los negativos.** El modelo nunca aprendió a rechazarlos y les
   da puntuación alta también centrados. Entonces minar *más* negativos —lo que
   hizo Canedo— es echar agua en un cubo agujereado: lo que falta es peso sobre
   los negativos que ya hay (minería *dentro* del conjunto, pérdida focal).

**B. Sensibilidad a la traslación.** Centrados los rechaza bien, pero el barrido
   los ve desplazados hasta media ventana y ahí se rompe. Entonces el arreglo es
   augmentación por traslación, no tocar los negativos.

Se distinguen puntuando cada negativo de entrenamiento **centrado** y comparándolo
con lo que sacó **en el barrido**. Uso:

    python3 scripts/score_training_negatives.py --vig-dir data/galicia-vignettes-v3 \\
        --ckpt data/cls-v3/best.pt --sweep data/sweep_trasancos_v3.tsv \\
        --out data/negativos_puntuados_v3.tsv
"""
from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

import numpy as np
import torch


def cargar_modelo(ckpt, dispositivo):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from train_unet_multiclass import UNetMulticlass  # noqa

    est = torch.load(ckpt, map_location="cpu", weights_only=False)
    cfg = est.get("args", est.get("config", {})) or {}
    modelo = UNetMulticlass(n_classes=3, encoder=cfg.get("encoder", "resnet34"),
                            head=cfg.get("head", "cls"), pretrained=False)
    modelo.load_state_dict(est.get("model", est.get("state_dict", est)))
    return modelo.to(dispositivo).eval(), cfg


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vig-dir", type=Path, required=True)
    ap.add_argument("--ckpt", type=Path, required=True)
    ap.add_argument("--sweep", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--lote", type=int, default=32)
    ap.add_argument("--label", default="0",
                    help="0 = negativos, 1 = positivos; con positivos la "
                         "comparación mide la dependencia del centrado")
    ap.add_argument("--split", default="train")
    args = ap.parse_args()

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    modelo, cfg = cargar_modelo(args.ckpt, dev)
    print("modelo cargado en %s | cabeza %s" % (dev, cfg.get("head")), flush=True)

    idx = list(csv.DictReader(open(args.vig_dir / "index.tsv", encoding="utf-8"),
                              delimiter="\t"))
    neg = [r for r in idx
           if r["split"] == args.split and r["label"] == args.label]
    print("viñetas label=%s split=%s: %d" % (args.label, args.split, len(neg)),
          flush=True)

    sw = list(csv.DictReader(open(args.sweep, encoding="utf-8"), delimiter="\t"))
    sx = np.array([float(r["lon"]) for r in sw])
    sy = np.array([float(r["lat"]) for r in sw])
    ss = np.array([float(r["score"]) for r in sw])

    filas = []
    with torch.no_grad():
        for i in range(0, len(neg), args.lote):
            trozo = neg[i:i+args.lote]
            arrs = [np.load(args.vig_dir / "arrays" / ("%s.npz" % r["sid"]))["x"]
                    .astype(np.float32) for r in trozo]
            # misma normalizacion que en entrenamiento, o las cifras no comparan
            x = torch.from_numpy((np.stack(arrs) - 0.5) / 0.5).float().to(dev)
            logits, _ = modelo(x)
            p = torch.softmax(logits, dim=1)[:, 1].cpu().numpy()   # clase castro
            for r, pc in zip(trozo, p):
                lo, la = float(r["lon"]), float(r["lat"])
                d = np.hypot((sx-lo)*111320*math.cos(math.radians(la)),
                             (sy-la)*111320)
                j = int(np.argmin(d))
                filas.append({"sid": r["sid"], "group": r["group"],
                              "lon": lo, "lat": la,
                              "p_centrado": round(float(pc), 4),
                              "p_barrido": round(float(ss[j]), 4),
                              "dist_celda_m": round(float(d[j]), 1)})
            if (i // args.lote) % 20 == 0:
                print("  %d/%d" % (i, len(neg)), flush=True)

    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0].keys()), delimiter="\t")
        w.writeheader()
        w.writerows(filas)

    pc = np.array([f["p_centrado"] for f in filas])
    pb = np.array([f["p_barrido"] for f in filas
                   if f["dist_celda_m"] <= 300])
    print("\n=== puntuados CENTRADOS ===")
    for u in (0.3, 0.5, 0.7, 0.9):
        print("  p_castro >= %.1f : %5d de %d (%.1f%%)"
              % (u, (pc >= u).sum(), len(pc), 100*(pc >= u).mean()))
    print("  mediana %.4f | p90 %.4f | p99 %.4f"
          % (np.median(pc), np.percentile(pc, 90), np.percentile(pc, 99)))
    print("\n=== los mismos sitios, DESCENTRADOS en el barrido ===")
    for u in (0.3, 0.5, 0.7, 0.9):
        print("  p_castro >= %.1f : %5d de %d (%.1f%%)"
              % (u, (pb >= u).sum(), len(pb), 100*(pb >= u).mean()))
    print("  mediana %.4f | p90 %.4f | p99 %.4f"
          % (np.median(pb), np.percentile(pb, 90), np.percentile(pb, 99)))
    print("\nescrito: %s" % args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
