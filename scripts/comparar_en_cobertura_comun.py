#!/usr/bin/env python3
"""Compara dos modelos sobre los yacimientos que AMBOS barridos alcanzan.

Nace de un error del `2026-08-10`: el `F1 0,222` con que se refutó v9 se midió
sobre un barrido que cubría el `44%` del bloque, contra el `0,697` de v7 medido
sobre el `100%`. El evaluador lo había avisado por escrito —*«cobertura 44%,
las cifras de abajo miden el barrido, no el modelo»*— y el aviso no se leyó.

Un barrido truncado deprime el recall **mecánicamente**: un castro sin ninguna
celda puntuada cerca es un fallo del barrido, no del modelo, y entra en el `FN`
igual que un fallo de verdad. Comparar así es comparar cobertura, no calidad.

Este script hace la única comparación honesta posible mientras el barrido
completo no exista: **restringe la verdad de campo a los yacimientos que los
dos barridos alcanzan** y evalúa ambos sobre ese mismo subconjunto. No sustituye
al barrido completo —el subconjunto cubierto no es una muestra aleatoria del
bloque, y eso hay que decirlo— pero separa «el modelo falla» de «el barrido no
llegó».

Uso:
    python3 scripts/comparar_en_cobertura_comun.py \\
        --bloque lugo --modelos v9 v7 --umbral 0.70
"""
from __future__ import annotations

import argparse
import csv
import math
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

# Un yacimiento está "alcanzado" si el barrido puntuó alguna celda a menos de
# esto. Es el mismo criterio que usa el aviso de cobertura de `detection_eval`.
RADIO_COBERTURA = 256.0


def cargar(f: Path) -> tuple[np.ndarray, np.ndarray]:
    filas = list(csv.DictReader(f.open(encoding="utf-8"), delimiter="\t"))
    return (np.array([float(r["lon"]) for r in filas]),
            np.array([float(r["lat"]) for r in filas]))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bloque", required=True)
    ap.add_argument("--modelos", nargs=2, required=True)
    ap.add_argument("--umbral", default="0.70")
    args = ap.parse_args()

    vt = Path(f"data/{args.bloque}_fus_truth_limpia.tsv")
    if not vt.exists():
        vt = Path(f"data/{args.bloque}_truth_limpia.tsv")
    verdad = list(csv.DictReader(vt.open(encoding="utf-8"), delimiter="\t"))
    tlon = np.array([float(r["lon"]) for r in verdad])
    tlat = np.array([float(r["lat"]) for r in verdad])

    # Un solo factor de longitud para todo el bloque.
    k = 111_320.0 * math.cos(math.radians(float(tlat.mean())))
    tx, ty = tlon * k, tlat * 110_540.0

    alcanzado = np.ones(len(verdad), bool)
    for m in args.modelos:
        f = Path(f"data/sweep_val_{args.bloque}_{m}.tsv")
        if not f.exists():
            print("falta %s" % f, file=sys.stderr)
            return 1
        plon, plat = cargar(f)
        px, py = plon * k, plat * 110_540.0
        cerca = np.array([
            float(np.hypot(px - a, py - b).min()) <= RADIO_COBERTURA
            if len(px) else False
            for a, b in zip(tx, ty)])
        print("  %-5s alcanza %d de %d yacimientos (%.0f%%)"
              % (m, cerca.sum(), len(verdad), 100 * cerca.mean()))
        alcanzado &= cerca

    n = int(alcanzado.sum())
    print("\ncobertura COMUN: %d de %d yacimientos (%.0f%%)"
          % (n, len(verdad), 100 * n / max(len(verdad), 1)))
    if n < 10:
        print("\nMenos de 10 yacimientos en comun: no se compara. Con esta n,")
        print("cualquier diferencia cabe dentro del intervalo de confianza.")
        return 0

    tmp = Path(tempfile.mkdtemp()) / f"{args.bloque}_comun.tsv"
    with tmp.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, delimiter="\t", fieldnames=verdad[0].keys())
        w.writeheader()
        w.writerows([r for r, ok in zip(verdad, alcanzado) if ok])

    masc = Path(f"data/{args.bloque}_fus_mascara_train.tsv")
    print("\n=== evaluados sobre los MISMOS %d yacimientos ===" % n)
    for m in args.modelos:
        cmd = [sys.executable, "scripts/detection_eval.py",
               "--pred", f"data/sweep_val_{args.bloque}_{m}.tsv",
               "--truth", str(tmp), "--umbral", args.umbral]
        if masc.exists():
            cmd += ["--mascara", str(masc)]
        out = subprocess.run(cmd, capture_output=True, text=True).stdout
        linea = [l for l in out.splitlines() if l.startswith("mejor F1")]
        cov = [l for l in out.splitlines() if "cobertura" in l.lower()]
        print("  %-5s %s" % (m, linea[0] if linea else "(sin resultado)"))
        for c in cov:
            print("        %s" % c.strip())

    print("\nLo que esto NO dice: que el subconjunto cubierto represente al")
    print("bloque. No es una muestra aleatoria — el barrido murio por donde iba,")
    print("no por sorteo. Separa 'el modelo falla' de 'el barrido no llego', y")
    print("nada mas. La cifra que vale sigue siendo la del barrido completo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
