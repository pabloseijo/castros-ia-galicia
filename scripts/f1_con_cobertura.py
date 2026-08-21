#!/usr/bin/env python3
"""Recalcula el F1 de cada modelo en cada bloque, **con su cobertura al lado**.

El `2026-08-10` se descubrió que el veredicto de v9 se apoyaba en un barrido
que cubría el `44%` del bloque. La pregunta inmediata es si hay más veredictos
así, y esta es la tabla que la contesta: **ninguna cifra de este proyecto
debería volver a citarse sin la cobertura del barrido que la produjo**.

Cómo leerla:

- `cobertura` = fracción de castros catalogados con alguna celda puntuada a
  menos de `256 m`. Es el techo mecánico del recall: un castro que el barrido
  no alcanzó cuenta como fallo del modelo sin serlo.
- **`F1` con cobertura por debajo de `0,95` no es comparable** con uno al
  `100%`, y la columna `¿fiable?` lo dice sin que haya que interpretarlo.

Uso:
    python3 scripts/f1_con_cobertura.py [--umbral 0.70]
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

BLOQUES = ["coruna", "lugo", "ourense", "pontevedra"]
COBERTURA_MINIMA = 0.95


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--umbral", default="0.70")
    args = ap.parse_args()

    d = Path("data")
    pares = []
    for f in sorted(d.glob("sweep_val_*.tsv")):
        m = re.match(r"sweep_val_([a-z]+)_(.+)\.tsv$", f.name)
        if m and m.group(1) in BLOQUES:
            pares.append((m.group(1), m.group(2), f))

    print("%-11s %-14s %9s %8s %8s  %s"
          % ("bloque", "modelo", "cobertura", "F1", "recall", "¿fiable?"))
    print("-" * 68)

    dudosos = []
    for bloque, modelo, f in pares:
        verdad = d / f"{bloque}_fus_truth_limpia.tsv"
        if not verdad.exists():
            verdad = d / f"{bloque}_truth_limpia.tsv"
        if not verdad.exists():
            continue
        cmd = [sys.executable, "scripts/detection_eval.py",
               "--pred", str(f), "--truth", str(verdad),
               "--umbral", args.umbral]
        masc = d / f"{bloque}_fus_mascara_train.tsv"
        if masc.exists():
            cmd += ["--mascara", str(masc)]
        try:
            out = subprocess.run(cmd, capture_output=True, text=True,
                                 timeout=600).stdout
        except subprocess.TimeoutExpired:
            print("%-11s %-14s %9s" % (bloque, modelo, "(timeout)"))
            continue

        cob = float("nan")
        mc = re.search(r"cobertura: (\d+) de (\d+)", out)
        if mc:
            cob = int(mc.group(1)) / max(int(mc.group(2)), 1)
        f1 = rec = float("nan")
        mf = re.search(r"mejor F1: ([\d.]+).*?recall ([\d.]+)", out)
        if mf:
            f1, rec = float(mf.group(1)), float(mf.group(2))

        fiable = cob >= COBERTURA_MINIMA
        if not fiable:
            dudosos.append((bloque, modelo, cob, f1))
        print("%-11s %-14s %8.0f%% %8.3f %8.3f  %s"
              % (bloque, modelo, 100 * cob, f1, rec,
                 "sí" if fiable else "NO — mide el barrido"))

    if not dudosos:
        print("\nNinguna cifra por debajo del %.0f%% de cobertura."
              % (100 * COBERTURA_MINIMA))
        return 0

    print("\n" + "=" * 68)
    print("CIFRAS QUE NO MIDEN AL MODELO: %d\n" % len(dudosos))
    for bloque, modelo, cob, f1 in sorted(dudosos, key=lambda t: t[2]):
        print("  %-11s %-10s cobertura %3.0f%%  ->  el F1 %.3f no es del modelo"
              % (bloque, modelo, 100 * cob, f1))
    print("\nCualquier veredicto escrito sobre estas hay que releerlo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
