#!/usr/bin/env python3
"""U-Net multiclase sobre las viñetas de relieve a `1 m`: castro / mámoa / fondo.

La línea base de CPU (`train_cpu_baseline.py --multiclass`) dejó medido el suelo
que esta red tiene que batir: castro recall `0.722`, mámoa `0.361`, fondo `0.901`
en validación. Si la GPU no supera eso con holgura, no justifica la electricidad.

## Por qué multiclase, y por qué se reporta por clase

Gomes et al. (2024), la referencia geográficamente más cercana —Alto Miño, mismo
tipo de castro y de túmulo—, montó estas tres clases y reportó `94%` de precisión
en hillforts mientras **no detectaba ni un solo túmulo**. Una clase pequeña puede
colapsar a cero sin que la métrica global lo delate. Por eso aquí no existe una
cifra agregada: cada clase sale con su recall, su intervalo de Wilson y una marca
`COLAPSADA` explícita, y la selección de modelo va por la **media de recall de
castro y mámoa**, no por exactitud global, que premiaría predecir fondo siempre.

## La decisión que el corpus obliga a tomar

Las viñetas traen etiqueta de imagen, no máscaras: `data/annotations` tiene `8`
polígonos en Trasancos, insuficiente para segmentar. Una U-Net supervisa por
píxel, así que hay dos formas honestas de entrenarla sin inventarse geometría, y
el script implementa ambas para que la comparación se mida en vez de discutirse:

- `--head mil`: U-Net entera. El decodificador emite logits por píxel y se
  agregan a etiqueta de imagen con *log-sum-exp* (Pinheiro y Collobert, 2015).
  No asume ningún radio, entrena el decodificador y deja mapas de calor
  revisables en QGIS como subproducto.
- `--head cls`: solo el codificador `resnet34` con *global average pooling* y
  capa lineal. Es el clasificador de viñetas de Landauer et al. (2025), que es
  literalmente lo que este corpus es. El decodificador queda sin usar.

Lo que **no** se hace es fabricar máscaras de disco con un radio fijo. Los radios
reales van de `38` a `83 m` (p10–p90 del polígono OSM) y un radio único ya fue el
sesgo estructural que costó caro en la versión de `512 m`.

## Cautelas que el script impone

- El split viene del corpus, por bloque espacial. O Val nunca entra en
  entrenamiento: es el holdout histórico y contiene Pena Lopesa.
- Los pesos de clase son `balanced`, no se remuestrea: está medido que el
  submuestreo aleatorio multiplica por `6.6` el error de calibración a `1:20`.
- La evaluación pasa por `honest_eval`, así que el VPP sale reexpresado a la
  tasa base real del barrido (`1:475`) y no a la mezcla de validación.
- Todo es reanudable (`--resume`): esta infraestructura se cuelga, y un
  entrenamiento de 40 épocas que solo escribe al final es un entrenamiento que
  no existe.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from honest_eval import (average_precision, evaluate, render,  # noqa: E402
                         roc_auc, wilson)

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CLASS_NAMES = {0: "fondo", 1: "castro", 2: "mamoa"}


# --- Datos ---------------------------------------------------------------

def label_of(row: dict) -> int:
    """castro=1, mámoa=2, todo lo demás=0. Misma convención que la línea base."""
    g = (row.get("group") or "").strip()
    return 1 if g == "castro" else (2 if g == "mamoa" else 0)


def _desplazar(a, dy, dx, t):
    """Desplaza rellenando por reflejo. Ver la nota en `Vignettes.__getitem__`."""
    _, h, w = a.shape
    pad = np.pad(a, ((0, 0), (t, t), (t, t)), mode="reflect")
    return pad[:, t-dy:t-dy+h, t-dx:t-dx+w]


class Vignettes(Dataset):
    def __init__(self, rows, arr_dir: Path, augment: bool = False,
                 translate: int = 0, val_translate: int = 0):
        self.rows = rows
        self.arr_dir = arr_dir
        self.augment = augment
        self.translate = translate
        # Descentrado **determinista** de la validación: el despliegue nunca
        # centra, así que una métrica de selección medida sobre viñetas centradas
        # elige el checkpoint por lo que no se va a usar. Determinista y no
        # aleatorio porque la métrica tiene que ser comparable entre épocas: si
        # cada época ve un desplazamiento distinto, la mejora y el ruido del
        # sorteo se mezclan y «mejor modelo» deja de significar nada.
        self.val_translate = val_translate

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, i: int):
        r = self.rows[i]
        a = np.load(self.arr_dir / f"{r['sid']}.npz")["x"].astype(np.float32)
        if self.augment:
            # El relieve no tiene orientación privilegiada y un recinto es
            # aproximadamente circular: los ocho elementos del grupo diedro son
            # augmentación gratis y sin supuestos.
            if random.random() < 0.5:
                a = a[:, ::-1, :]
            if random.random() < 0.5:
                a = a[:, :, ::-1]
            k = random.randint(0, 3)
            if k:
                a = np.rot90(a, k, axes=(1, 2))
            if self.translate:
                # Descentrado deliberado, porque el despliegue nunca centra. Medido
                # sobre v3: un castro centrado saca mediana `0.988` y el mismo
                # castro visto desde la celda del barrido saca `0.386` —cruza el
                # umbral—, mientras que los negativos no se mueven (`0.030` a
                # `0.024`). Descentrar solo destruye la señal positiva.
                #
                # Relleno por reflejo y no `np.roll`: envolver la imagen pega el
                # borde norte contra el sur y crea una costura recta que no existe
                # en el terreno; con `t=128` sobre `512 px` eso sería un cuarto de
                # la viñeta enseñando un artefacto aprendible.
                t = self.translate
                a = _desplazar(a, random.randint(-t, t), random.randint(-t, t), t)
            a = np.ascontiguousarray(a)
        elif self.val_translate:
            t = self.val_translate
            rng = np.random.default_rng(20260805 + i)
            a = np.ascontiguousarray(
                _desplazar(a, int(rng.integers(-t, t+1)),
                           int(rng.integers(-t, t+1)), t))
        # El corpus ya viene normalizado a [0,1]; se centra en cero para que la
        # primera convolución preentrenada reciba un rango parecido al suyo.
        return torch.from_numpy((a - 0.5) / 0.5), label_of(r), i


# --- Modelo --------------------------------------------------------------

class DecoderBlock(nn.Module):
    def __init__(self, in_ch: int, skip_ch: int, out_ch: int):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv2d(in_ch + skip_ch, out_ch, 3, padding=1, bias=False),
            nn.BatchNorm2d(out_ch), nn.ReLU(inplace=True),
            nn.Conv2d(out_ch, out_ch, 3, padding=1, bias=False),
            nn.BatchNorm2d(out_ch), nn.ReLU(inplace=True))

    def forward(self, x, skip=None):
        x = F.interpolate(x, scale_factor=2, mode="nearest")
        if skip is not None:
            x = torch.cat([x, skip], dim=1)
        return self.conv(x)


class UNetMulticlass(nn.Module):
    """U-Net con codificador `resnet34` preentrenado en ImageNet.

    ImageNet y no un modelo fundacional de teledetección a propósito: Prithvi,
    Clay y TerraMind están preentrenados a `10-30 m/píxel` y aquí el objeto pide
    `1 m`. Manda la escala del objeto, no el tamaño del modelo. ConvNeXt/ResNet
    de ImageNet es además lo que Landauer demostró sobre castros europeos.
    """

    def __init__(self, n_classes: int = 3, encoder: str = "resnet34",
                 head: str = "mil", pretrained: bool = True, lse_r: float = 8.0):
        super().__init__()
        import torchvision.models as tvm

        if encoder not in ("resnet18", "resnet34", "resnet50"):
            raise SystemExit(f"codificador no soportado: {encoder}")
        weights = "IMAGENET1K_V1" if pretrained else None
        net = getattr(tvm, encoder)(weights=weights)
        self.head_kind = head
        self.lse_r = lse_r

        self.stem = nn.Sequential(net.conv1, net.bn1, net.relu)  # /2
        self.pool = net.maxpool
        self.layer1, self.layer2 = net.layer1, net.layer2
        self.layer3, self.layer4 = net.layer3, net.layer4

        chs = [64, 64, 128, 256, 512] if encoder != "resnet50" else \
              [64, 256, 512, 1024, 2048]
        if head == "cls":
            self.fc = nn.Linear(chs[4], n_classes)
        else:
            self.d4 = DecoderBlock(chs[4], chs[3], 256)
            self.d3 = DecoderBlock(256, chs[2], 128)
            self.d2 = DecoderBlock(128, chs[1], 64)
            self.d1 = DecoderBlock(64, chs[0], 32)
            self.seg = nn.Conv2d(32, n_classes, 1)

    def forward(self, x):
        x0 = self.stem(x)               # /2
        x1 = self.layer1(self.pool(x0))  # /4
        x2 = self.layer2(x1)             # /8
        x3 = self.layer3(x2)             # /16
        x4 = self.layer4(x3)             # /32

        if self.head_kind == "cls":
            return self.fc(F.adaptive_avg_pool2d(x4, 1).flatten(1)), None

        m = self.d4(x4, x3)
        m = self.d3(m, x2)
        m = self.d2(m, x1)
        m = self.d1(m, x0)               # /2, basta para un mapa de calor
        seg = self.seg(m)                # B, C, H/2, W/2

        # Log-sum-exp: media suave que tiende al máximo al subir `r`. Media pura
        # diluiría un recinto de 50 m en una viñeta de 512 m; el máximo puro se
        # engancha a un píxel de ruido.
        r = self.lse_r
        b, c, h, w = seg.shape
        flat = seg.reshape(b, c, h * w)
        logits = (torch.logsumexp(r * flat, dim=2) - np.log(h * w)) / r
        return logits, seg


# --- Métrica -------------------------------------------------------------

def per_class_block(pred: np.ndarray, true: np.ndarray) -> dict:
    """Recall, precisión, Wilson y marca de colapso, clase por clase."""
    out = {}
    for c, nm in CLASS_NAMES.items():
        n = int((true == c).sum())
        if n == 0:
            continue
        tp = int(((pred == c) & (true == c)).sum())
        fp = int(((pred == c) & (true != c)).sum())
        rec = tp / n
        lo, hi = wilson(tp, n)
        out[nm] = {"n": n, "recall": rec, "recall_ci95": [lo, hi],
                   "precision": tp / (tp + fp) if tp + fp else 0.0,
                   "collapsed": rec == 0}
    return out


class FocalLoss(nn.Module):
    """Focal loss (Lin et al. 2017, `10.1109/iccv.2017.324`).

    `CrossEntropyLoss(weight=w)` pesa por **frecuencia de clase**: dentro de
    "fondo" un negativo duro (una viñeta de campo de fútbol que el modelo
    puntúa 0.9 como castro) pesa exactamente igual que un negativo trivial que
    ya acierta con confianza. Medido el 2026-08-06: con `balanced` los 534
    negativos duros minados de OSM son el 4,9% de las viñetas de "fondo" y se
    llevan ~1,6% del gradiente total — 16 de 26 falsos positivos de Pontevedra
    resultaron estar a 1 m de un sitio visto así en entrenamiento y aun así el
    modelo lo puntuaba 0.82-0.99. La dilución es invisible en el recall
    agregado de "fondo" porque perder el 100% de esos 534 solo le costaría ~5
    puntos.

    `FL(p_t) = -alpha_t * (1-p_t)^gamma * log(p_t)` reescala cada ejemplo por
    lo mal que el modelo lo tiene clasificado en ese momento, no por la
    frecuencia de su clase. Un negativo duro que el modelo sigue puntuando
    alto sigue pesando fuerte en cada época; uno que ya aprendió a suprimir
    pesa casi cero. `alpha` sigue siendo el balanceo por clase existente —
    focal loss lo complementa, no lo sustituye.
    """

    def __init__(self, alpha: torch.Tensor, gamma: float = 2.0):
        super().__init__()
        self.alpha = alpha
        self.gamma = gamma

    def forward(self, logits: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        logp = F.log_softmax(logits, dim=1)
        logp_t = logp.gather(1, target.unsqueeze(1)).squeeze(1)
        p_t = logp_t.exp()
        alpha_t = self.alpha[target]
        loss = -alpha_t * (1 - p_t).pow(self.gamma) * logp_t
        return loss.mean()


def selection_score(block: dict) -> float:
    """F1 macro de castro y mámoa: las dos clases que importan.

    Exactitud global no sirve —predecir fondo siempre daría `0.85`— y una media
    de las tres esconde justo el fallo que Gomes et al. documentaron.

    **Era la media de recall, y estaba mal.** El control sin decodificador lo
    demostró el `2026-08-05`: la media de recall ignora la precisión, así que un
    modelo que grita «mámoa» a casi todo saca `0.847` de recall con `0.153` de
    precisión y **gana la selección siendo peor en ROC-AUC, en AP y en las otras
    dos clases**. F1 penaliza exactamente esa estrategia.
    """
    f1s = []
    for k in ("castro", "mamoa"):
        if k not in block:
            continue
        r, p = block[k]["recall"], block[k]["precision"]
        f1s.append(2 * r * p / (r + p) if (r + p) > 0 else 0.0)
    return float(np.mean(f1s)) if f1s else 0.0


# --- Bucle ---------------------------------------------------------------

@torch.no_grad()
def infer(model, loader, device, amp: bool):
    model.eval()
    P, Y, S = [], [], []
    for x, y, _ in loader:
        x = x.to(device, non_blocking=True)
        with torch.autocast("cuda", enabled=amp):
            logits, _ = model(x)
        prob = torch.softmax(logits.float(), dim=1)
        P.append(prob.argmax(1).cpu().numpy())
        S.append(prob.cpu().numpy())
        Y.append(y.numpy())
    return np.concatenate(P), np.concatenate(Y), np.concatenate(S)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vig-dir", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--encoder", default="resnet34")
    ap.add_argument("--head", default="mil", choices=("mil", "cls"),
                    help="mil = U-Net entera con pooling log-sum-exp; "
                         "cls = solo codificador + GAP (Landauer)")
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--weight-decay", type=float, default=1e-4)
    ap.add_argument("--lse-r", type=float, default=8.0)
    ap.add_argument("--loss", default="focal", choices=("ce", "focal"),
                    help="focal (Lin et al. 2017, 10.1109/iccv.2017.324) pesa "
                         "cada ejemplo por su dificultad, no solo por la "
                         "frecuencia de su clase — necesario para que los "
                         "negativos duros minados no se diluyan dentro de "
                         "'fondo'. ce es el CrossEntropyLoss balanceado por "
                         "clase que usaban v3-v6")
    ap.add_argument("--focal-gamma", type=float, default=2.0,
                    help="foco sobre lo difícil; 2.0 es el valor de Lin et al.")
    ap.add_argument("--val-translate", type=int, default=0,
                    help="descentrado determinista de la validación; con esto la "
                         "métrica de selección mide despliegue y no centrado")
    ap.add_argument("--translate", type=int, default=0,
                    help="desplazamiento aleatorio en píxeles (=metros a 1 m)")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--seed", type=int, default=20260804)
    ap.add_argument("--limit", type=int, default=0, help="prueba de humo")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--no-amp", action="store_true")
    ap.add_argument("--no-pretrained", action="store_true")
    args = ap.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    torch.backends.cudnn.benchmark = True

    device = "cuda" if torch.cuda.is_available() else "cpu"
    amp = (device == "cuda") and not args.no_amp
    if device == "cpu":
        print("[!] sin GPU: esto va a ser lento", flush=True)

    idx = args.vig_dir / "index.tsv"
    if not idx.exists():
        raise SystemExit(f"falta {idx}")
    rows = list(csv.DictReader(open(idx, encoding="utf-8"), delimiter="\t"))
    arr_dir = args.vig_dir / "arrays"
    rows = [r for r in rows if (arr_dir / f"{r['sid']}.npz").exists()]
    if args.limit:
        rows = rows[:args.limit]

    by_split = {"train": [], "val": [], "test_o_val": []}
    for r in rows:
        if r["split"] in by_split:
            by_split[r["split"]].append(r)
    if not by_split["train"]:
        raise SystemExit("split de entrenamiento vacío")

    counts = {k: {CLASS_NAMES[c]: sum(1 for r in v if label_of(r) == c)
                  for c in CLASS_NAMES} for k, v in by_split.items()}
    print(f"dispositivo: {device} | cabeza: {args.head} | AMP: {amp}", flush=True)
    for k, v in counts.items():
        print(f"  {k:11s} {sum(v.values()):5d}  {v}", flush=True)

    ytr = np.array([label_of(r) for r in by_split["train"]])
    # `balanced` de sklearn: n / (k * n_c). Sin remuestrear.
    w = torch.tensor([len(ytr) / (3 * max((ytr == c).sum(), 1))
                      for c in range(3)], dtype=torch.float32, device=device)
    print(f"  pesos de clase: {[round(float(x), 3) for x in w]}", flush=True)

    mk = lambda rr, aug, shuf: DataLoader(
        Vignettes(rr, arr_dir, augment=aug, translate=args.translate,
                  val_translate=0 if aug else args.val_translate),
        batch_size=args.batch, shuffle=shuf, num_workers=args.workers,
        pin_memory=(device == "cuda"), drop_last=False,
        persistent_workers=args.workers > 0)
    loaders = {"train": mk(by_split["train"], True, True)}
    for k in ("val", "test_o_val"):
        if by_split[k]:
            loaders[k] = mk(by_split[k], False, False)

    model = UNetMulticlass(3, args.encoder, args.head,
                           not args.no_pretrained, args.lse_r).to(device)
    n_par = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"  parámetros entrenables: {n_par/1e6:.1f} M", flush=True)

    opt = torch.optim.AdamW(model.parameters(), lr=args.lr,
                            weight_decay=args.weight_decay)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=args.epochs)
    scaler = torch.amp.GradScaler("cuda", enabled=amp)
    crit = FocalLoss(w, args.focal_gamma) if args.loss == "focal" \
        else nn.CrossEntropyLoss(weight=w)
    print(f"  pérdida: {args.loss}"
          + (f" (gamma {args.focal_gamma})" if args.loss == "focal" else ""),
          flush=True)

    ck_last, ck_best = args.out_dir / "last.pt", args.out_dir / "best.pt"
    start, best, history = 0, -1.0, []
    if args.resume and ck_last.exists():
        st = torch.load(ck_last, map_location=device, weights_only=False)
        model.load_state_dict(st["model"]); opt.load_state_dict(st["opt"])
        sched.load_state_dict(st["sched"]); scaler.load_state_dict(st["scaler"])
        start, best = st["epoch"] + 1, st["best"]
        history = st.get("history", [])
        print(f"  reanudado en época {start} (mejor {best:.4f})", flush=True)

    for ep in range(start, args.epochs):
        model.train()
        t0, tot, seen = time.time(), 0.0, 0
        for bi, (x, y, _) in enumerate(loaders["train"], 1):
            x = x.to(device, non_blocking=True)
            y = y.to(device, non_blocking=True)
            opt.zero_grad(set_to_none=True)
            with torch.autocast("cuda", enabled=amp):
                logits, _ = model(x)
                loss = crit(logits, y)
            scaler.scale(loss).backward()
            scaler.step(opt); scaler.update()
            tot += float(loss.detach()) * len(y); seen += len(y)
            if bi % 100 == 0:
                print(f"    ép {ep+1} lote {bi}/{len(loaders['train'])} "
                      f"pérdida {tot/seen:.4f} ({time.time()-t0:.0f}s)", flush=True)
        sched.step()

        pred, true, prob = infer(model, loaders["val"], device, amp)
        blk = per_class_block(pred, true)
        sc = selection_score(blk)
        # ROC-AUC y AP de castro-contra-resto en CADA época, no solo al final.
        # El 2026-08-05 hubo que descartar una comparación entre arquitecturas
        # porque solo existían estas cifras para el checkpoint que había elegido
        # una métrica de selección equivocada, y los pesos del resto de épocas ya
        # no estaban. Cuestan milisegundos y evitan reentrenar para revisar.
        lab = (true == 1).astype(int)
        rank = {}
        if lab.sum() and (1 - lab).sum():
            rank = {"roc_auc": roc_auc(prob[:, 1], lab),
                    "average_precision": average_precision(prob[:, 1], lab)}
        line = " | ".join(
            f"{nm} {b['recall']:.3f}" + ("*COLAPSADA*" if b["collapsed"] else "")
            for nm, b in blk.items())
        print(f"  época {ep+1}/{args.epochs} pérdida {tot/seen:.4f} "
              f"[{time.time()-t0:.0f}s] val: {line} | selección {sc:.4f}",
              flush=True)
        history.append({"epoch": ep + 1, "loss": tot / seen,
                        "selection": sc, "per_class": blk, "ranking": rank})

        st = {"model": model.state_dict(), "opt": opt.state_dict(),
              "sched": sched.state_dict(), "scaler": scaler.state_dict(),
              "epoch": ep, "best": max(best, sc), "history": history,
              "args": vars(args)}
        torch.save(st, ck_last)
        if sc > best:
            best = sc
            torch.save(st, ck_best)
            print(f"    -> mejor modelo guardado ({sc:.4f})", flush=True)

    if ck_best.exists():
        model.load_state_dict(torch.load(ck_best, map_location=device,
                                         weights_only=False)["model"])

    out = {"mode": "multiclass", "head": args.head, "encoder": args.encoder,
           "params_m": n_par / 1e6, "epochs": args.epochs,
           "selection_best": best, "counts": counts,
           "baseline_cpu": {"castro": 0.7222, "mamoa": 0.3611, "fondo": 0.9007},
           "per_class": {}, "history": history}
    md_parts = []
    for name in ("val", "test_o_val"):
        if name not in loaders:
            continue
        pred, true, prob = infer(model, loaders[name], device, amp)
        blk = per_class_block(pred, true)
        out["per_class"][name] = blk
        print(f"\n  {name}:", flush=True)
        for nm, b in blk.items():
            flag = "  <-- COLAPSADA" if b["collapsed"] else ""
            print(f"    {nm:8s} n={b['n']:5d}  recall {b['recall']:.3f} "
                  f"[{b['recall_ci95'][0]:.2f},{b['recall_ci95'][1]:.2f}]  "
                  f"precision {b['precision']:.3f}{flag}", flush=True)

        # Bloque diagnóstico castro-contra-resto: es donde vive el VPP a tasa
        # base real, que es lo único trasladable al barrido.
        s = prob[:, 1]
        lab = (true == 1).astype(int)
        if lab.sum() and (1 - lab).sum():
            res = evaluate(s, lab)
            out.setdefault("castro_vs_rest", {})[name] = res
            md_parts.append(f"# {name} — castro contra resto\n\n" + render(res))
        rr = by_split[name]
        with open(args.out_dir / f"scores_{name}.tsv", "w", newline="",
                  encoding="utf-8") as fh:
            wr = csv.writer(fh, delimiter="\t")
            wr.writerow(["sid", "name", "group", "label", "true", "pred",
                         "p_fondo", "p_castro", "p_mamoa", "score"])
            for m, p, t, pr in zip(rr, pred, true, prob):
                wr.writerow([m["sid"], m.get("name", ""), m.get("group", ""),
                             m["label"], int(t), int(p),
                             f"{pr[0]:.6f}", f"{pr[1]:.6f}", f"{pr[2]:.6f}",
                             f"{pr[1]:.6f}"])

    (args.out_dir / "metrics.json").write_text(
        json.dumps(out, indent=2, default=float), encoding="utf-8")
    if md_parts:
        rep = PROJECT_ROOT / "reports" / f"{args.out_dir.name}.md"
        rep.parent.mkdir(exist_ok=True)
        rep.write_text("\n\n---\n\n".join(md_parts), encoding="utf-8")
        print(f"\ninforme: {rep}", flush=True)

    v = out["per_class"].get("val", {})
    print("\n=== contra la línea base de CPU (val) ===", flush=True)
    for nm, base in (("castro", 0.7222), ("mamoa", 0.3611), ("fondo", 0.9007)):
        if nm in v:
            d = v[nm]["recall"] - base
            print(f"  {nm:8s} {v[nm]['recall']:.3f} vs {base:.3f} "
                  f"({d:+.3f}){'  <-- COLAPSADA' if v[nm]['collapsed'] else ''}",
                  flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
