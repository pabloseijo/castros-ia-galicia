#!/usr/bin/env python3
"""¿Este proyecto sobreajusta o subajusta? La pregunta que nunca se hizo.

Goodfellow, Bengio & Courville, *Deep Learning*, §5.2, lo pone como **la**
primera pregunta de cualquier diagnóstico:

> «Los factores que determinan lo bien que funciona un algoritmo de aprendizaje
> son su capacidad para **1. hacer pequeño el error de entrenamiento** y
> **2. hacer pequeña la brecha entre el error de entrenamiento y el de test**.
> Estos dos factores corresponden a los dos retos centrales: **subajuste** y
> **sobreajuste**. El subajuste ocurre cuando el modelo no consigue un error
> suficientemente bajo en el conjunto de entrenamiento. El sobreajuste, cuando
> la brecha entre el error de entrenamiento y el de test es demasiado grande.»

`metrics.json` de los quince checkpoints de este proyecto guarda `val` y
`test_o_val`. **No guarda `train`.** Se registra la *pérdida* por época —v7 baja
de `0,386` a `0,133`— pero la pérdida focal ponderada no es comparable con el
recall de validación, así que la brecha nunca se ha podido leer.

Sin ese número no se puede elegir entre las dos únicas direcciones que existen:

- **Subajuste** → el modelo no puede ni con sus propios datos. Se arregla con
  capacidad o con una representación mejor. Más datos **no** ayudan.
- **Sobreajuste** → memoriza. Se arregla con más datos o más regularización.

Este proyecto ha gastado v11p, v13, v12 y v14 en **más y mejores datos**, y las
cuatro fueron refutadas. Si resulta que subajusta, esas cuatro refutaciones
tenían una explicación previsible desde el principio.

Se mide **sin aumento** —el aumento cambia los ejemplos y lo que se quiere saber
es si el modelo se ajusta a los datos que vio— y con la misma función
`per_class_block` que produce las cifras de validación, para que sean
comparables número a número.

Uso:
    python3 scripts/error_de_entrenamiento.py --modelo v7 --vig data/galicia-vignettes-v7
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader

# **`file_system` y no `file_descriptor`.** Con la estrategia por defecto, cada
# tensor que un obrero del `DataLoader` pasa al padre consume un descriptor de
# fichero, y sobre `12.136` viñetas se agota el límite: `RuntimeError: Too many
# open files. Communication with the workers is no longer possible`. Reventó
# midiendo v15a y v15b el 2026-08-11, y encima en silencio, porque el `grep`
# del orquestador solo miraba las líneas de resultado.
torch.multiprocessing.set_sharing_strategy("file_system")

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "scripts"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--modelo", required=True, help="v7, v14, ...")
    ap.add_argument("--vig", type=Path, required=True)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--dispositivo", default=None)
    args = ap.parse_args()

    from train_unet_multiclass import (CLASS_NAMES, UNetMulticlass, Vignettes,
                                       cupo_vram, infer, label_of,
                                       per_class_block)

    dev = args.dispositivo or ("cuda" if torch.cuda.is_available() else "cpu")
    # **Cupo de VRAM.** Esta medida convive con un barrido en la misma GPU, y sin
    # cupo el que llega segundo muere con `CUDA error: out of memory`. En CPU
    # tarda más de una hora sobre 12.136 viñetas y además le roba núcleos al
    # barrido, que es E/S de LAZ y va justo. Con `CASTROS_VRAM_FRAC=0.25` cabe.
    cupo_vram(dev)
    ck = Path(f"data/cls-{args.modelo}/best.pt")
    st = torch.load(ck, map_location=dev, weights_only=False)
    in_ch = int(st["model"]["stem.0.weight"].shape[1])

    idx = args.vig / "index.tsv"
    arr = args.vig / "arrays"
    filas = [r for r in csv.DictReader(idx.open(encoding="utf-8"),
                                       delimiter="\t")
             if (arr / f"{r['sid']}.npz").exists()]
    por_split = {}
    for r in filas:
        por_split.setdefault(r["split"], []).append(r)

    # **La cabeza se lee del checkpoint, no se supone.** Con `head="cls"` fijo
    # esto reventaba al medir v15a, que es `mil`: «Missing key(s): fc.weight /
    # Unexpected key(s): d4.conv..., seg.weight». El entrenador guarda sus
    # propios argumentos en el `.pt`, así que la fuente de verdad está dentro.
    _args = st.get("args") or {}
    cabeza = _args.get("head", "cls")
    codificador = _args.get("encoder", "resnet34")
    modelo = UNetMulticlass(head=cabeza, encoder=codificador, pretrained=False,
                            in_ch=in_ch).to(dev)
    modelo.load_state_dict(st["model"])
    modelo.eval()
    print("modelo %s | cabeza %s | canales %d | dispositivo %s"
          % (args.modelo, cabeza, in_ch, dev))

    resultados = {}
    for split in ("train", "val", "test_o_val"):
        rr = por_split.get(split)
        if not rr:
            continue
        # **augment=False también en train.** Con aumento se mediría el ajuste
        # a ejemplos que el modelo no vio exactamente así, que es otra pregunta.
        dl = DataLoader(Vignettes(rr, arr, augment=False, translate=0,
                                  val_translate=0),
                        batch_size=args.batch, shuffle=False, num_workers=2)
        # `infer` devuelve TRES cosas: predicción, verdad y probabilidades.
        pred, true, _prob = infer(modelo, dl, dev, amp=(dev == "cuda"))
        resultados[split] = per_class_block(np.asarray(pred), np.asarray(true))
        n = len(rr)
        print("  %-11s %5d viñetas" % (split, n), flush=True)

    print("\n%-12s %-9s %8s %10s" % ("clase", "split", "recall", "precisión"))
    print("-" * 44)
    for clase in CLASS_NAMES.values():
        for split in ("train", "val"):
            b = resultados.get(split, {}).get(clase)
            if b:
                print("%-12s %-9s %8.3f %10.3f"
                      % (clase, split, b["recall"], b["precision"]))
        print()

    tr = resultados.get("train", {})
    va = resultados.get("val", {})
    if "castro" in tr and "castro" in va:
        rt, rv = tr["castro"]["recall"], va["castro"]["recall"]
        brecha = rt - rv
        print("=" * 60)
        print("DIAGNÓSTICO (clase castro)")
        print("  recall en entrenamiento: %.3f" % rt)
        print("  recall en validación:    %.3f" % rv)
        print("  brecha:                  %.3f" % brecha)
        print()
        if rt < 0.90:
            print("  SUBAJUSTE. El modelo no consigue un error bajo ni sobre los")
            print("  datos que vio. Con recall de entrenamiento %.3f, el techo no" % rt)
            print("  está en los datos: está en la capacidad o en la")
            print("  representación. Más datos NO pueden ayudar, y eso explica")
            print("  v11p, v13, v12 y v14.")
        elif brecha > 0.20:
            print("  SOBREAJUSTE. Memoriza el entrenamiento (%.3f) y no")
            print("  generaliza (%.3f). Se ataca con más datos o más" % (rt, rv))
            print("  regularización.")
        else:
            print("  Ni una cosa ni la otra de forma clara: %.3f contra %.3f."
                  % (rt, rv))
            print("  Con la brecha pequeña y el entrenamiento alto, el modelo")
            print("  está cerca de su capacidad útil con esta representación.")

    salida = Path(f"data/cls-{args.modelo}/error_entrenamiento.json")
    salida.write_text(json.dumps(resultados, indent=1))
    print("\nescrito: %s" % salida)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
