#!/usr/bin/env python3
"""Stage 2: Landauer-style castro classifier over 1 m relief vignettes.

Follows the recipe that swept 180.000 km2 in Landauer et al. (2025): a modern
CNN pretrained on ImageNet, a training set deliberately skewed towards
negatives, flips and crops for augmentation, and evaluation that reports
precision honestly rather than accuracy on an unbalanced set.

Two departures, both deliberate:

  - Their negatives were random landscape. Ours are *named*: quarries, forest
    tracks, medieval ruins, hilltop hamlets, natural landforms. Landauer lists
    exactly these as the false positives that survive at continental scale, so
    training against them by name is the cheapest available shortcut to the
    precision they did not reach (0.26).

  - We report precision@K as the headline. The deliverable is a review queue
    with a human at the end, so what matters is how much of the top of the
    list is worth opening in QGIS, not global accuracy.

Needs torch and timm, so this runs on the GPU box, not the Raspberry. The
vignette cache from stage 1 is portable: copy data/trasancos-vignettes-v1.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
VIG_DIR = PROJECT_ROOT / "data/trasancos-vignettes-v1"
OUT_DIR = PROJECT_ROOT / "data/trasancos-classifier-v1"
REPORT = PROJECT_ROOT / "reports/trasancos_classifier_v1.md"


def load_index(vig_dir: Path):
    rows = list(csv.DictReader(open(vig_dir / "index.tsv", encoding="utf-8"),
                               delimiter="\t"))
    for r in rows:
        r["label"] = int(r["label"])
    return rows


class VignetteDataset:
    def __init__(self, rows, arr_dir: Path, train: bool, size: int = 224):
        self.rows, self.arr_dir, self.train, self.size = rows, arr_dir, train, size

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, i):
        import torch
        import torch.nn.functional as F

        r = self.rows[i]
        x = np.load(self.arr_dir / f"{r['sid']}.npz")["x"].astype(np.float32)
        t = torch.from_numpy(x)
        if self.train:
            if random.random() < 0.5:
                t = torch.flip(t, dims=[2])
            if random.random() < 0.5:
                t = torch.flip(t, dims=[1])
            k = random.randint(0, 3)
            if k:
                t = torch.rot90(t, k, dims=[1, 2])
            # Small random crop: the object is not always dead centre in a
            # blind sweep, and this is the cheap way to say so.
            c, h, w = t.shape
            m = int(h * 0.1)
            if m > 1:
                oy, ox = random.randint(0, m), random.randint(0, m)
                t = t[:, oy:h - (m - oy), ox:w - (m - ox)]
        t = F.interpolate(t.unsqueeze(0), size=(self.size, self.size),
                          mode="bilinear", align_corners=False).squeeze(0)
        return t, float(r["label"])


def collate(batch):
    import torch
    xs, ys = zip(*batch)
    return torch.stack(xs), torch.tensor(ys, dtype=torch.float32)


def metrics_at(scores, labels, ks=(10, 25, 50, 100)):
    order = np.argsort(-scores)
    lab = np.asarray(labels)[order]
    out = {}
    npos = int(lab.sum())
    for k in ks:
        if k <= len(lab):
            out[f"precision@{k}"] = float(lab[:k].mean())
    if npos:
        # Precision at the operating point where recall reaches 70%, the
        # regime Landauer reported (recall 0.71, precision 0.26).
        cum = np.cumsum(lab)
        idx = np.argmax(cum >= 0.7 * npos)
        if cum[idx] >= 0.7 * npos:
            out["precision@recall70"] = float(cum[idx] / (idx + 1))
            out["k_for_recall70"] = int(idx + 1)
    return out


def evaluate(model, loader, device):
    import torch
    model.eval()
    S, L = [], []
    with torch.no_grad():
        for x, y in loader:
            p = torch.sigmoid(model(x.to(device)).squeeze(1)).cpu().numpy()
            S.append(p)
            L.append(y.numpy())
    return np.concatenate(S), np.concatenate(L)


def summarise(scores, labels, thr=0.5):
    pred = (scores >= thr).astype(int)
    lab = np.asarray(labels).astype(int)
    tp = int(((pred == 1) & (lab == 1)).sum())
    fp = int(((pred == 1) & (lab == 0)).sum())
    fn = int(((pred == 0) & (lab == 1)).sum())
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    try:
        from sklearn.metrics import roc_auc_score, average_precision_score
        auc = float(roc_auc_score(lab, scores))
        ap = float(average_precision_score(lab, scores))
    except Exception:
        auc = ap = float("nan")
    d = {"tp": tp, "fp": fp, "fn": fn, "precision": prec, "recall": rec,
         "f1": f1, "roc_auc": auc, "average_precision": ap}
    d.update(metrics_at(scores, lab))
    return d


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--vig-dir", type=Path, default=VIG_DIR)
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    ap.add_argument("--model", default="convnext_tiny",
                    help="timm name; Landauer used ConvNeXt pretrained on ImageNet")
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--size", type=int, default=224)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--seed", type=int, default=20260803)
    args = ap.parse_args()

    try:
        import timm
        import torch
        import torch.nn as nn
        from torch.utils.data import DataLoader
    except ImportError as exc:
        print(f"needs torch and timm on this machine: {exc}")
        print("stage 1 (build_trasancos_vignettes.py) runs without them.")
        return 1

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    rows = load_index(args.vig_dir)
    arr_dir = args.vig_dir / "arrays"
    by = defaultdict(list)
    for r in rows:
        by[r["split"]].append(r)
    for sp in ("train", "val", "test_o_val"):
        c = Counter(r["label"] for r in by[sp])
        print(f"{sp}: {c[1]} positives, {c[0]} negatives", flush=True)
    if not by["train"]:
        print("empty training split; run stage 1 first")
        return 1

    device = ("cuda" if torch.cuda.is_available()
              else "mps" if torch.backends.mps.is_available() else "cpu")
    print(f"device: {device} | model: {args.model}", flush=True)

    model = timm.create_model(args.model, pretrained=True, in_chans=3,
                              num_classes=1).to(device)

    npos = sum(1 for r in by["train"] if r["label"] == 1)
    nneg = len(by["train"]) - npos
    # The negative skew is the point, not an accident, so do not balance it
    # away: just stop it from drowning the gradient entirely.
    pos_weight = torch.tensor([min(nneg / max(npos, 1), 25.0)], device=device)
    print(f"pos_weight: {pos_weight.item():.1f} (neg:pos = {nneg}:{npos})", flush=True)
    crit = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.05)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=args.epochs)

    mk = lambda rws, tr: DataLoader(
        VignetteDataset(rws, arr_dir, tr, args.size), batch_size=args.batch_size,
        shuffle=tr, num_workers=args.workers, collate_fn=collate, drop_last=False)
    tl, vl = mk(by["train"], True), mk(by["val"], False)
    testl = mk(by["test_o_val"], False) if by["test_o_val"] else None

    best, best_state, history = -1.0, None, []
    for ep in range(1, args.epochs + 1):
        model.train()
        tot, n = 0.0, 0
        t0 = time.time()
        for x, y in tl:
            x, y = x.to(device), y.to(device)
            opt.zero_grad()
            loss = crit(model(x).squeeze(1), y)
            loss.backward()
            opt.step()
            tot += loss.item() * len(y)
            n += len(y)
        sched.step()
        s, l = evaluate(model, vl, device)
        m = summarise(s, l)
        history.append({"epoch": ep, "train_loss": tot / max(n, 1), **m})
        print(f"ep {ep:02d} loss {tot/max(n,1):.4f} | val AP {m['average_precision']:.4f} "
              f"AUC {m['roc_auc']:.4f} P@25 {m.get('precision@25', float('nan')):.2f} "
              f"| {time.time()-t0:.0f}s", flush=True)
        if m["average_precision"] > best:
            best = m["average_precision"]
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}

    if best_state:
        model.load_state_dict(best_state)
        torch.save(best_state, args.out_dir / "best.pt")

    vs, vlab = evaluate(model, vl, device)
    final = {"val": summarise(vs, vlab)}
    if testl is not None:
        ts, tlab = evaluate(model, testl, device)
        final["test_o_val"] = summarise(ts, tlab)
        with open(args.out_dir / "test_o_val_scores.tsv", "w", newline="",
                  encoding="utf-8") as fh:
            w = csv.writer(fh, delimiter="\t")
            w.writerow(["sid", "name", "group", "label", "score"])
            for r, sc in zip(by["test_o_val"], ts):
                w.writerow([r["sid"], r["name"], r["group"], r["label"], f"{sc:.6f}"])

    (args.out_dir / "metrics.json").write_text(
        json.dumps({"final": final, "history": history,
                    "model": args.model, "epochs": args.epochs}, indent=2),
        encoding="utf-8")

    lines = ["# Trasancos vignette classifier v1", "",
             f"Backbone `{args.model}` pretrained on ImageNet, `{args.epochs}` epochs, "
             f"`{args.size}px`, three relief channels at `1 m`.", "",
             "Negatives are named modern and natural features from OSM, matching the "
             "false-positive taxonomy of Landauer et al. (2025), plus catalogued mounds.",
             "", "| split | metric | value |", "|---|---|---:|"]
    for sp, m in final.items():
        for k, v in m.items():
            lines.append(f"| `{sp}` | `{k}` | `{v:.4f}` |" if isinstance(v, float)
                         else f"| `{sp}` | `{k}` | `{v}` |")
    lines += ["", "## Reference points", "",
              "| source | precision | recall | F1 |", "|---|---:|---:|---:|",
              "| Landauer et al. 2025, England | `0.26` | `0.71` | `0.38` |",
              "| Canedo et al. 2024, NW Iberia (after mining) | | | `0.66` |", "",
              "Beating `0.26` precision at comparable recall is the bar this run has "
              "to clear to justify the named-negative approach.", ""]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("\nfinal:", json.dumps(final, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
