#!/usr/bin/env python3
"""Verdad de campo y máscara de contaminación para un bloque de validación.

Un bloque de validación solo vale si se sabe **qué parte de él vio el modelo**.
El corpus de entrenamiento es de toda Galicia, así que un bloque cualquiera
contiene castros que estuvieron en `train` o en `val`: detectarlos es memoria, no
prospección. En el bloque de Lugo eran `33` de `93`, y sin enmascararlos el F1
salía `0.644` en vez de `0.590`.

Escribe dos ficheros: la verdad limpia —lo nunca visto, contra lo que se mide— y
la máscara —lo visto, cuyas detecciones no suman ni restan—.

Uso:
    python3 scripts/preparar_bloque_validacion.py --nombre pontevedra \\
        --bbox -8.875 42.125 -8.625 42.375
"""
from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--nombre", required=True)
    ap.add_argument("--bbox", type=float, nargs=4, required=True,
                    metavar=("W", "S", "E", "N"))
    ap.add_argument("--maestro", type=Path,
                    default=RAIZ / "data/weak-label-splits-v1/weak_label_master.tsv")
    ap.add_argument("--indice", type=Path,
                    default=RAIZ / "data/galicia-vignettes-v3/index.tsv")
    ap.add_argument("--out-dir", type=Path, default=RAIZ / "data")
    ap.add_argument("--tolerancia-m", type=float, default=300.0)
    ap.add_argument("--barrido", type=Path, default=None,
                    help="TSV del barrido. Con esto la verdad se toma del "
                         "TERRENO REALMENTE BARRIDO y no del bbox, que es lo "
                         "correcto: las teselas de 1 km se desbordan del bbox y "
                         "los castros de ese borde se contaban como falsos "
                         "positivos. Pasó en Trasancos (6 castros) y otra vez en "
                         "Lugo (4 de los 20 mejores candidatos).")
    args = ap.parse_args()

    W, S, E, N = args.bbox
    limpios = [r for r in csv.DictReader(open(args.maestro, encoding="utf-8"),
                                          delimiter="\t")
               if r["label_class"] == "1"
               and r["weak_label_status"] == "weak_positive_candidate"
               and r["longitude"] and r["latitude"]]
    if args.barrido:
        sw = list(csv.DictReader(open(args.barrido, encoding="utf-8"),
                                 delimiter="\t"))
        la0 = float(np.mean([float(r["lat"]) for r in sw]))
        kk = 111320.0
        kkx = kk * np.cos(np.radians(la0))
        bx = np.array([float(r["lon"]) for r in sw]) * kkx
        by = np.array([float(r["lat"]) for r in sw]) * kk
        M = [r for r in limpios
             if np.hypot(bx - float(r["longitude"]) * kkx,
                         by - float(r["latitude"]) * kk).min() <= 400.0]
        print("verdad tomada del terreno barrido (%d celdas): %d castros"
              % (len(sw), len(M)))
    else:
        M = [r for r in limpios
             if W <= float(r["longitude"]) <= E and S <= float(r["latitude"]) <= N]
    if not M:
        raise SystemExit("el bloque no contiene castros catalogados")

    lat0 = float(np.mean([float(r["latitude"]) for r in M]))
    k = 111320.0
    kx = k * np.cos(np.radians(lat0))

    IX = [r for r in csv.DictReader(open(args.indice, encoding="utf-8"),
                                    delimiter="\t")
          if r["split"] in ("train", "val")]
    vx = np.array([float(r["lon"]) for r in IX]) * kx
    vy = np.array([float(r["lat"]) for r in IX]) * k

    limpio, visto = [], []
    for r in M:
        d = np.hypot(vx - float(r["longitude"]) * kx,
                     vy - float(r["latitude"]) * k).min()
        (visto if d <= args.tolerancia_m else limpio).append(r)

    for sufijo, rs in (("truth_limpia", limpio), ("mascara_train", visto)):
        dst = args.out_dir / ("%s_%s.tsv" % (args.nombre, sufijo))
        with open(dst, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh, delimiter="\t")
            w.writerow(["lon", "lat", "name", "concello"])
            for r in rs:
                w.writerow([r["longitude"], r["latitude"], r.get("name", ""),
                            r.get("municipality", "")])
        print("  %s: %d" % (dst.name, len(rs)))

    print("\nbloque %s: %d castros catalogados" % (args.nombre, len(M)))
    print("  NO vistos (se mide contra estos): %d" % len(limpio))
    print("  vistos en train/val (enmascarados): %d" % len(visto))
    print("  concellos: %s" % Counter(
        r.get("municipality", "?") for r in limpio).most_common(6))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
