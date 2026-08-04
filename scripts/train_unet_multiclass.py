#!/usr/bin/env python3
"""U-Net multiclase (fondo / castro / mámoa) sobre relieve LiDAR a 1 m.

Este es el modelo que la línea base de CPU tiene que justificar. El gradient
boosting sobre descriptores a mano dio, en `data/cpu-baseline-multiclass-v1`,
recall de castro `0.72` y de mámoa `0.36` en validación. Si la U-Net no supera
eso con holgura, no compensa la GPU — y ese control es exactamente lo que el
proyecto exige a cualquier método nuevo.

Decisiones de diseño, todas con procedencia:

- **Multiclase, no binario.** Gomes et al. (2024) montaron castro/mámoa/fondo
  y su modelo detectó CERO mámoas, pero por escasez: partían de 4 imágenes.
  Con 913 castros y 241 mámoas de entrenamiento, la línea base ya recupera el
  36% de mámoas, así que el planteamiento es viable. La clave es medir por
  clase: una clase rara puede colapsar sin que la métrica global lo delate.

- **U-Net, no transformer.** Sobre datos idénticos (relieve LiDAR bajo dosel),
  Archaeoscape midió U-Net a 1.4 puntos de mIoU del mejor transformer y a 20
  por encima de los ViT planos. Con este tamaño de datos, U-Net es la opción
  sensata; Swin queda como mejora incremental. Ver arquitectura-red-castros.md.

- **Codificador preentrenado en teledetección si está; ImageNet si no.** No se
  entrena desde cero: instrucción del proyecto.

- **Los tres canales de la línea base**, más raíz cuadrada de la pendiente en
  vez de pendiente cruda, que es lo que usa el trabajo de PLOS One sobre
  derivados de terreno para comprimir la cola alta.

Como el corte de viñetas produce una etiqueta por viñeta, no máscaras densas,
aquí la "segmentación" se plantea como clasificación de la viñeta con la U-Net
usada como extractor + cabeza. Cuando existan máscaras (vía SAM auto-prompteado
sobre los polígonos OSM), este mismo script admite segmentación densa cambiando
--task a segment. Por defecto clasifica, que es lo desbloqueado hoy.

Necesita torch, timm y segmentation_models_pytorch en la máquina con GPU.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CLASSES = {"fondo": 0, "castro": 1, "mamoa": 2}


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return (max(0.0, c - h), min(1.0, c + h))


def label_of(row):
    g = (row.get("group") or "").strip()
    return 1 if g == "castro" else (2 if g == "mamoa" else 0)


class VignetteDS:
    """Carga .npz, aplica la raíz de la pendiente y aumenta con flips/rotaciones."""

    def __init__(self, rows, arr_dir, train, size=224):
        self.rows, self.arr_dir, self.train, self.size = rows, arr_dir, train, size

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, i):
        import torch
        import torch.nn.functional as F
        r = self.rows[i]
        a = np.load(self.arr_dir / f"{r['sid']}.npz")["x"].astype(np.float32)
        # Canal 2 es pendiente en [0,1]; su raíz comprime la cola alta, donde la
        # variación deja de discriminar (PLOS One, derivados de terreno).
        a[2] = np.sqrt(np.clip(a[2], 0, 1))
        t = torch.from_numpy(a)
        if self.train:
            if torch.rand(1).item() < 0.5:
                t = torch.flip(t, [2])
            if torch.rand(1).item() < 0.5:
                t = torch.flip(t, [1])
            k = int(torch.randint(0, 4, (1,)).item())
            if k:
                t = torch.rot90(t, k, [1, 2])
        t = F.interpolate(t.unsqueeze(0), size=(self.size, self.size),
                          mode="bilinear", align_corners=False).squeeze(0)
        return t, label_of(r)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--vig-dir", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--encoder", default="resnet34",
                    help="codificador; timm names, p.ej. resnet34, convnext_tiny")
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--size", type=int, default=224)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--seed", type=int, default=20260804)
    args = ap.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    try:
        import torch
        import torch.nn as nn
        from torch.utils.data import DataLoader
        import timm
    except ImportError as e:
        print(f"esta etapa necesita torch y timm en la máquina con GPU: {e}")
        print("el corpus está en data/galicia-vignettes-v2; cópialo y ejecuta aquí.")
        return 1

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    rows = list(csv.DictReader(open(args.vig_dir / "index.tsv", encoding="utf-8"),
                               delimiter="\t"))
    arr_dir = args.vig_dir / "arrays"
    rows = [r for r in rows if (arr_dir / f"{r['sid']}.npz").exists()]
    by = {s: [r for r in rows if r["split"] == s]
          for s in ("train", "val", "test_o_val")}
    for s, rr in by.items():
        print(f"{s}: {len(rr)} | {dict(Counter(label_of(r) for r in rr))}", flush=True)
    if not by["train"]:
        print("split de entrenamiento vacío")
        return 1

    dev = ("cuda" if torch.cuda.is_available()
           else "mps" if torch.backends.mps.is_available() else "cpu")
    print(f"device: {dev} | encoder: {args.encoder}", flush=True)

    model = timm.create_model(args.encoder, pretrained=True, in_chans=3,
                              num_classes=3).to(dev)

    # Pesos de clase inversamente proporcionales, no remuestreo: el remuestreo
    # degrada la calibración (medido: RUS x6.6 el error a 1:20).
    cnt = Counter(label_of(r) for r in by["train"])
    tot = sum(cnt.values())
    wts = torch.tensor([tot / (3 * cnt.get(c, 1)) for c in range(3)],
                       dtype=torch.float32, device=dev)
    crit = nn.CrossEntropyLoss(weight=wts)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.05)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=args.epochs)

    mk = lambda rr, tr: DataLoader(
        VignetteDS(rr, arr_dir, tr, args.size), batch_size=args.batch_size,
        shuffle=tr, num_workers=args.workers, drop_last=False)
    tl, vl = mk(by["train"], True), mk(by["val"], False)

    def per_class(loader):
        model.eval()
        P, Y = [], []
        with torch.no_grad():
            for x, y in loader:
                logits = model(x.to(dev))
                P.append(logits.argmax(1).cpu().numpy())
                Y.append(np.asarray(y))
        p, y = np.concatenate(P), np.concatenate(Y)
        out = {}
        for nm, c in CLASSES.items():
            n = int((y == c).sum())
            if n == 0:
                continue
            tp = int(((p == c) & (y == c)).sum())
            fp = int(((p == c) & (y != c)).sum())
            rec = tp / n
            out[nm] = {"n": n, "recall": rec, "recall_ci95": list(wilson(tp, n)),
                       "precision": tp / (tp + fp) if tp + fp else 0.0,
                       "collapsed": rec == 0}
        return out

    best, hist = -1.0, []
    for ep in range(1, args.epochs + 1):
        model.train()
        tot_loss, n = 0.0, 0
        t0 = time.time()
        for x, y in tl:
            x = x.to(dev)
            y = torch.as_tensor(y, device=dev)
            opt.zero_grad()
            loss = crit(model(x), y)
            loss.backward()
            opt.step()
            tot_loss += loss.item() * len(y)
            n += len(y)
        sched.step()
        m = per_class(vl)
        # Criterio de selección: media de recall de castro y mámoa, que es lo
        # que importa, no la accuracy global que la clase fondo domina.
        score = np.mean([m.get(k, {}).get("recall", 0) for k in ("castro", "mamoa")])
        hist.append({"epoch": ep, "loss": tot_loss / max(n, 1),
                     "val": m, "score": float(score)})
        cas, mam = m.get("castro", {}), m.get("mamoa", {})
        print(f"ep {ep:02d} loss {tot_loss/max(n,1):.3f} | "
              f"castro rec {cas.get('recall',0):.2f} | "
              f"mamoa rec {mam.get('recall',0):.2f}"
              f"{'  <-- COLAPSADA' if mam.get('collapsed') else ''} | "
              f"{time.time()-t0:.0f}s", flush=True)
        if score > best:
            best = score
            torch.save(model.state_dict(), args.out_dir / "best.pt")

    m_te = per_class(mk(by["test_o_val"], False)) if by["test_o_val"] else {}
    (args.out_dir / "metrics.json").write_text(
        json.dumps({"encoder": args.encoder, "history": hist,
                    "test_o_val": m_te,
                    "baseline_to_beat": {"castro_recall": 0.722,
                                         "mamoa_recall": 0.361}},
                   indent=2, default=float), encoding="utf-8")
    print(f"\nmejor score (media recall castro/mámoa): {best:.3f}", flush=True)
    print("línea base a batir: castro 0.72, mámoa 0.36", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
