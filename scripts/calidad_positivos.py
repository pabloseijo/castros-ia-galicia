#!/usr/bin/env python3
"""¿Son peores los positivos que trajo la descarga que los originales de v7?

**La hipotesis que quedo en pie** al refutarse v13 (`2026-08-09`): v11p y v13
comparten una sola cosa que v7 no tiene —sus positivos salen del corpus ampliado—
y los dos salen permisivos. Si entre esos positivos nuevos hay sitios mal
situados, dudosos o destruidos, **cada uno le ensena al modelo que un trozo de
monte cualquiera es un castro**.

**Como se comprueba sin verdad de campo.** Se puntuan las viñetas con el modelo de
v7, que **no vio ninguna de las nuevas al entrenar**, y se compara la distribucion:

- Si los nuevos puntuan como los viejos -> son igual de castro. La hipotesis cae.
- Si los nuevos puntuan **mas bajo** -> a ojos de un modelo entrenado con los
  buenos, se parecen menos a un castro. Es consistente con que sean peores.

No demuestra que esten mal —podrian ser castros raros y legitimos— pero mide si
son **distintos**, que es lo que la hipotesis afirma.

Va en CPU y por muestra: no hace falta puntuar `3.795` viñetas para comparar dos
distribuciones.
"""
from __future__ import annotations

import csv
import random
import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, "scripts")
from train_unet_multiclass import UNetMulticlass  # noqa: E402

N = int(sys.argv[1]) if len(sys.argv) > 1 else 250
dev = "cpu"

st = torch.load("data/cls-v7/best.pt", map_location=dev, weights_only=False)
a = st.get("args", {})
modelo = UNetMulticlass(n_classes=3, encoder=a.get("encoder", "resnet34"),
                        head=a.get("head", "cls"), pretrained=False, in_ch=3).to(dev)
modelo.load_state_dict(st["model"]); modelo.eval()

def sids(idx):
    out = set()
    with open(idx, encoding="utf-8") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            if (r.get("group") or "").strip().startswith("castro"):
                out.add(r["sid"])
    return out

viejos = sids("data/galicia-vignettes-v7/index.tsv")
todos = sids("data/galicia-vignettes-v11p/index.tsv")
nuevos = todos - viejos
print(f"castros en v7: {len(viejos)} | en v11p: {len(todos)} | nuevos: {len(nuevos)}")

arr = Path("data/galicia-vignettes-v11p/arrays")
rnd = random.Random(20260809)

def puntuar(conj, etiqueta):
    sel = rnd.sample(sorted(conj), min(N, len(conj)))
    sc = []
    lote = []
    for s in sel:
        f = arr / f"{s}.npz"
        if not f.exists():
            continue
        lote.append(np.load(f)["x"].astype(np.float32))
        if len(lote) >= 8:
            with torch.no_grad():
                o = modelo(torch.from_numpy(np.stack(lote)))
                lg = o[0] if isinstance(o, (tuple, list)) else o
                p = torch.softmax(lg, 1)[:, 1]      # probabilidad de castro
                sc.extend(p.numpy().tolist())
            lote = []
    if lote:
        with torch.no_grad():
            o = modelo(torch.from_numpy(np.stack(lote)))
            lg = o[0] if isinstance(o, (tuple, list)) else o
            sc.extend(torch.softmax(lg, 1)[:, 1].numpy().tolist())
    v = np.array(sc)
    print(f"  {etiqueta:<22}{len(v):>5}   mediana {np.median(v):.3f} | "
          f"media {v.mean():.3f} | >0,5: {100*(v>0.5).mean():.0f}%")
    return v

print(f"\n  puntuacion de castro que les da v7 (que NO vio los nuevos):")
a_ = puntuar(viejos, "positivos de v7")
b_ = puntuar(nuevos, "positivos nuevos")

if len(a_) and len(b_):
    U = sum(1 for x in a_ for y in b_ if x > y) / (len(a_)*len(b_))
    print(f"\n  P(un positivo viejo puntue mas alto que uno nuevo) = {U:.3f}")
    print("  (0,5 = son iguales | >0,6 = los nuevos son menos castro)")
