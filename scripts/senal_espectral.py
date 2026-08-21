#!/usr/bin/env python3
"""¿Lleva la ortofoto alguna señal sobre si hay castro? La otra causa de v9.

v9 —RGB como canal de entrada— se hundió a `F1 0,222`. Su página dejó dos causas
candidatas. El desalineamiento se ha medido en `3,3 m` medianos, que es poco para
explicar un derrumbe de tres veces. Queda la segunda, y es la fuerte:

> «Su objetivo son terrazas, que son cambios de textura vegetal. Un castro bajo
> bosque cerrado no tiene firma espectral: la copa lo tapa. Ahí el canal de color
> no aporta señal, solo varianza.»

**Eso se comprueba sin entrenar nada**: si la ortofoto no distingue un castro de
un trozo de monte cualquiera, meterla como canal solo puede añadir ruido.

Se comparan las ortofotos del corpus entre positivos (`castro`) y fondo
(`random_terrain`), con descriptores simples: luminancia, verdor, textura y
contraste entre el núcleo y el anillo — este último es el que importa, porque un
castro es un objeto **local** y lo que se pregunta es si destaca de su entorno.
"""
from __future__ import annotations

import csv
import random
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.stats import mannwhitneyu

ORTO = Path("data/ortofotos-corpus")
N = 260
B = 8


def rasgos(p: Path):
    im = np.asarray(Image.open(p).convert("RGB"), dtype=np.float32)
    n = im.shape[0]
    c = n // 2
    r = n // 6                      # núcleo de ~170 m
    nuc = im[c - r:c + r, c - r:c + r]
    bor = np.concatenate([im[:r, :].reshape(-1, 3), im[-r:, :].reshape(-1, 3)])

    def tex(a):
        g = a.mean(axis=2)
        h, w = (g.shape[0] // B) * B, (g.shape[1] // B) * B
        return float(g[:h, :w].reshape(h // B, B, w // B, B).std(axis=(1, 3)).mean())

    verdor = lambda a: float((a[..., 1] - (a[..., 0] + a[..., 2]) / 2).mean())
    return {
        "lum_nuc": float(nuc.mean()),
        "tex_nuc": tex(nuc),
        "verdor_nuc": verdor(nuc),
        # el contraste con el borde: ¿destaca el objeto de su entorno?
        "lum_contraste": float(nuc.mean() - bor.mean()),
        "tex_contraste": tex(nuc) - tex(bor.reshape(-1, 1, 3).repeat(1, 1)) if False else tex(nuc),
        "verdor_contraste": verdor(nuc) - verdor(bor),
    }


idx = list(csv.DictReader(open("data/galicia-vignettes-v7/index.tsv",
                               encoding="utf-8"), delimiter="\t"))
hay = {p.stem for p in ORTO.glob("*.jpg")}
pos = [r for r in idx if (r.get("group") or "").startswith("castro") and r["sid"] in hay]
neg = [r for r in idx if (r.get("group") or "").startswith("random") and r["sid"] in hay]
rnd = random.Random(20260810)
pos = rnd.sample(pos, min(N, len(pos)))
neg = rnd.sample(neg, min(N, len(neg)))
print(f"  {len(pos)} castros contra {len(neg)} de terreno aleatorio, con ortofoto\n")

A = [rasgos(ORTO / f"{r['sid']}.jpg") for r in pos]
Bg = [rasgos(ORTO / f"{r['sid']}.jpg") for r in neg]

print(f"  {'rasgo':<20}{'castros':>10}{'fondo':>10}{'efecto':>9}{'p':>10}")
print("  " + "-" * 59)
for k in ("lum_nuc", "tex_nuc", "verdor_nuc", "lum_contraste", "verdor_contraste"):
    a = np.array([x[k] for x in A]); b = np.array([x[k] for x in Bg])
    u, p = mannwhitneyu(a, b, alternative="two-sided")
    ef = u / (len(a) * len(b))
    marca = " *" if p < 0.01 else ""
    print(f"  {k:<20}{a.mean():>10.2f}{b.mean():>10.2f}{ef:>9.3f}{p:>10.4f}{marca}")

print("\n  efecto 0,5 = la ortofoto NO distingue castro de monte cualquiera")
print("  (y entonces meterla como canal solo puede anadir varianza)")
