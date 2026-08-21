#!/usr/bin/env python3
"""El F1 sobre todo lo catalogado y sobre lo que conserva relieve.

Medido el `2026-08-09`: en A Coruna, `55` de sus `75` castros catalogados **no
tienen recinto que ver** —revision a ciegas, `0` de `18`—, y la causa esta
identificada con `p = 0,002` dentro del bloque: el arado. Un castro arrasado
cuenta hoy como **falso negativo** y hunde el `F1` sin que el modelo se equivoque.

Esto informa **las dos cifras**, que es lo que hace un trabajo serio cuando la
verdad de campo es heterogenea:

  · `F1` sobre **todo** lo catalogado — la cifra oficial, la comparable con la
    literatura, y **no se sustituye**;
  · `F1` sobre los castros que **conservan relieve**, que dice lo que el metodo
    puede hacer donde hay algo que encontrar.

El criterio de «conserva relieve» **no puede ser la puntuacion del modelo** —eso
seria evaluar al modelo contra su propia opinion—. Se usa el **uso del suelo**,
medido con ortofoto e independiente del LiDAR: se descartan los que estan en
terreno claro y liso por encima del umbral que separo hallados de perdidos.
"""
from __future__ import annotations

import csv
import json
import re
import subprocess
from pathlib import Path

import numpy as np

BLOQUES = ["lugo", "coruna", "ourense", "pontevedra"]
TMP = Path("data/tmp-alcanzable")
TMP.mkdir(exist_ok=True)

suelo = json.load(open("data/uso_suelo_214.json"))
# El corte se toma de la mediana de los HALLADOS, no de los perdidos: usar los
# perdidos para definir el criterio y luego medir sobre ellos seria circular.
hall = [r for r in suelo if r["hallado"]]
LUM_CORTE = float(np.percentile([r["lum"] for r in hall], 90))
print(f"  corte de luminancia: {LUM_CORTE:.1f} "
      f"(percentil 90 de los {len(hall)} castros hallados)")

por_nombre = {}
for r in suelo:
    por_nombre.setdefault((r["bloque"], r["nombre"]), r)


def evaluar(pred, truth, bloque, umbral=0.70, mascara=None):
    m = mascara or f"data/{bloque}_fus_mascara_train.tsv"
    r = subprocess.run(
        [".venv-gpu/bin/python", "scripts/detection_eval.py", "--pred", str(pred),
         "--truth", str(truth), "--mascara", str(m),
         "--umbral", str(umbral)], capture_output=True, text=True, timeout=600).stdout
    m = re.findall(r"mejor F1: ([0-9.]+)", r)
    return float(m[-1]) if m else float("nan")


print(f"\n  {'bloque':<12}{'todos':>9}{'n':>5}{'alcanzables':>13}{'n':>5}{'diferencia':>12}")
print("  " + "-" * 58)
tot_a, tot_b = [], []
for b in BLOQUES:
    orig = Path(f"data/{b}_fus_truth_limpia.tsv")
    filas = list(csv.DictReader(orig.open(encoding="utf-8"), delimiter="\t"))
    campos = list(filas[0].keys())
    alcanzables = []
    for t in filas:
        r = por_nombre.get((b, (t.get("name") or "")))
        # sin medida de suelo se conserva: no se descarta por falta de dato
        if r is None or r["lum"] <= LUM_CORTE:
            alcanzables.append(t)
    sub = TMP / f"{b}_alcanzables.tsv"
    with sub.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=campos, delimiter="\t")
        w.writeheader()
        w.writerows(alcanzables)

    # **Los no alcanzables se ENMASCARAN, no se borran.** Borrarlos de la verdad
    # deja sus detecciones en el barrido contandose como falsos positivos, que es
    # exactamente lo contrario de lo que se quiere: en el primer intento eso
    # hundio Pontevedra `0,078` y el efecto era del metodo, no del dato. La
    # mascara los saca de los DOS recuentos, que es como se trata un objeto que
    # no se puede ni acertar ni fallar.
    no_alc = [t for t in filas if t not in alcanzables]
    masc_orig = list(csv.DictReader(
        open(f"data/{b}_fus_mascara_train.tsv", encoding="utf-8"), delimiter="\t"))
    masc = TMP / f"{b}_mascara_ampliada.tsv"
    campos_m = list(masc_orig[0].keys()) if masc_orig else campos
    with masc.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=campos_m, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        w.writerows(masc_orig)
        w.writerows(no_alc)

    pred = f"data/sweep_val_{b}_v7.tsv"
    f_todos = evaluar(pred, orig, b)
    f_alc = evaluar(pred, sub, b, mascara=masc)
    tot_a.append(f_todos); tot_b.append(f_alc)
    print(f"  {b:<12}{f_todos:>9.3f}{len(filas):>5}{f_alc:>13.3f}"
          f"{len(alcanzables):>5}{f_alc - f_todos:>+12.3f}")

print(f"  {'MEDIA':<12}{np.mean(tot_a):>9.3f}{'':>5}{np.mean(tot_b):>13.3f}"
      f"{'':>5}{np.mean(tot_b) - np.mean(tot_a):>+12.3f}")
