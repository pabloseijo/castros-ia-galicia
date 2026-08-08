#!/usr/bin/env python3
"""Saca los falsos positivos de un barrido: el material de entrenamiento que falta.

**El diagnóstico, con los números del 2026-08-08.** El corpus de v7 tiene `534`
negativos duros contra `10.742` de terreno aleatorio — el `3,8%` de la clase
fondo — y todos entran con el mismo peso `0,366`. El modelo ve **veinte veces más
negativos fáciles que difíciles y los trata igual**. Por eso la sesión del `06`
midió que añadir negativos duros «mueve poco»: no era que no sirvieran, era que
el entrenamiento los diluía.

Los cuatro barridos de v7 ofrecen `1.306` celdas por encima de `0.5` que no caen
sobre castro catalogado ni sobre la máscara de contaminación. **Esas son las
equivocaciones reales del modelo en despliegue**, no negativos inventados: cada
una es un sitio donde disparó y no había nada.

Es la palanca de Canedo y colegas, que pasaron de `5.678` detecciones a `40` con
una ronda de minería. Está documentada en la wiki desde el principio y sigue sin
ejecutarse a fondo.

## La cautela que hace esto legítimo

Un falso positivo del barrido **puede ser un castro inédito**: es literalmente lo
que el proyecto busca. Meterlo como negativo enseñaría al modelo a no encontrar
lo que se le pide.

Por eso se excluyen los que la revisión marcó como prometedores, y se deja
`--excluir` para pasar la lista. Con el resto se asume el riesgo consciente: a
`0.5` la precisión medida es `0,082-0,230` según bloque, así que la enorme
mayoría son error. El riesgo residual queda anotado, no escondido.

Uso:
    python3 scripts/extraer_fp_barrido.py --pred data/sweep_val_lugo_v7.tsv \\
        --truth data/lugo_fus_truth_limpia.tsv \\
        --mascara data/lugo_mascara.tsv --umbral 0.5 \\
        --excluir data/prometedores.tsv --out data/fp_lugo.tsv
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from detection_eval import a_metros, agrupar, leer_tsv  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pred", type=Path, required=True)
    ap.add_argument("--truth", type=Path, required=True)
    ap.add_argument("--mascara", type=Path, default=None)
    ap.add_argument("--catalogo-completo", type=Path,
                    default=Path("data/weak_label_master_fusionado.tsv"))
    ap.add_argument("--excluir", type=Path, default=None,
                    help="TSV lon/lat de candidatos que NO deben entrar como "
                         "negativo: los que la revision marco prometedores")
    ap.add_argument("--umbral", type=float, default=0.5)
    ap.add_argument("--enlace-m", type=float, default=256.0)
    ap.add_argument("--tolerancia-m", type=float, default=500.0)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    pred = [p for p in leer_tsv(args.pred, ("lon", "lat", "score"))
            if "score" in p]
    for p in pred:
        p["score"] = float(p["score"])
    sel = [p for p in pred if p["score"] >= args.umbral]
    if not sel:
        raise SystemExit("ninguna celda supera el umbral")
    truth = leer_tsv(args.truth)
    masc = leer_tsv(args.mascara) if args.mascara else []

    todos = []
    if args.catalogo_completo.exists():
        with open(args.catalogo_completo, encoding="utf-8") as fh:
            for r in csv.DictReader(fh, delimiter="\t"):
                try:
                    todos.append({"lon": float(r["longitude"]),
                                  "lat": float(r["latitude"])})
                except (KeyError, TypeError, ValueError):
                    continue
    excl = leer_tsv(args.excluir) if (args.excluir and args.excluir.exists()) \
        else []

    lat0 = float(np.mean([t["lat"] for t in truth]))
    px, py = a_metros([p["lon"] for p in sel], [p["lat"] for p in sel], lat0)
    tx, ty = a_metros([t["lon"] for t in truth], [t["lat"] for t in truth], lat0)
    mx = my = gx = gy = ex = ey = None
    if masc:
        mx, my = a_metros([m["lon"] for m in masc], [m["lat"] for m in masc], lat0)
    if todos:
        gx, gy = a_metros([t["lon"] for t in todos], [t["lat"] for t in todos], lat0)
    if excl:
        ex, ey = a_metros([e["lon"] for e in excl], [e["lat"] for e in excl], lat0)

    filas = 0
    n_cast = n_masc = n_excl = 0
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter="\t")
        w.writerow(["lon", "lat", "score"])
        for g in agrupar(px, py, args.enlace_m):
            cx, cy = float(np.mean(px[g])), float(np.mean(py[g]))
            sc = max(sel[i]["score"] for i in g)
            if np.hypot(tx - cx, ty - cy).min() <= args.tolerancia_m:
                n_cast += 1; continue
            if mx is not None and np.hypot(mx-cx, my-cy).min() <= args.tolerancia_m:
                n_masc += 1; continue
            if gx is not None and np.hypot(gx-cx, gy-cy).min() <= args.tolerancia_m:
                n_cast += 1; continue
            if ex is not None and np.hypot(ex-cx, ey-cy).min() <= args.tolerancia_m:
                n_excl += 1; continue
            lon = cx / (6371000.0 * math.cos(math.radians(lat0))) * 180 / math.pi
            lat = cy / 6371000.0 * 180 / math.pi
            w.writerow([f"{lon:.6f}", f"{lat:.6f}", f"{sc:.4f}"])
            filas += 1

    print(f"umbral {args.umbral} | agrupadas: {filas+n_cast+n_masc+n_excl}")
    print(f"  sobre castro conocido:        {n_cast}")
    print(f"  sobre la máscara:             {n_masc}")
    print(f"  excluidas por prometedoras:   {n_excl}")
    print(f"  **FALSOS POSITIVOS a minar:   {filas}**")
    print(f"\nescrito: {args.out}")
    print("\nCAUTELA: algunos de estos pueden ser castros inéditos — es lo que")
    print("el proyecto busca. A este umbral la precisión medida es 0,08-0,23,")
    print("así que la mayoría son error, pero el riesgo residual existe y no")
    print("se esconde: queda en esta salida y en el registro.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
