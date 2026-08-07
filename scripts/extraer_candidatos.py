#!/usr/bin/env python3
"""Saca los candidatos NO catalogados de un barrido, para llevarlos a revisión.

Es el paso que el proyecto lleva pendiente desde el principio y el único que
puede producir un hallazgo. Todo lo medido hasta ahora —`F1`, precisión,
recall— cuenta como acierto **recuperar un castro que ya estaba en el
catálogo**, y como fallo cualquier detección que no lo esté. Pero el objetivo
declarado es justo lo contrario: **encontrar los que no están**.

Canedo revisó sus `40` residuales y **`9` eran castros inéditos**. Con el
criterio de aquí esos `9` habrían contado como falsos positivos y habrían
empujado a «arreglar» el modelo para dejar de encontrarlos. Mientras nadie mire
los candidatos, **la métrica castiga al sistema justo por hacer su trabajo**.

Este script coge un barrido, agrupa igual que `detection_eval.py` —mismo enlace,
mismo criterio— y escribe los que **no** caen sobre un yacimiento conocido ni
sobre la máscara de contaminación. Su salida alimenta a
`render_candidate_relief.py`, que dibuja sombreado multidireccional y relieve
local, que es lo que de verdad enseña un parapeto.

**Dónde mirar primero, y por qué.** No en Lugo: allí a umbral `0.80` hay `34`
candidatos y `33` son castros ya catalogados —el catálogo está bien hecho y el
modelo lo recupera—. Los inéditos, si los hay, están donde el catálogo es más
pobre: **Ourense tiene `478` castros en toda la provincia**, muy por debajo de la
densidad del norte, y sus falsos positivos no son obra moderna sino laderas
aterrazadas y monte, varios indistinguibles de un castro.

Uso:
    python3 scripts/extraer_candidatos.py --pred data/sweep_val_ourense_v6focal.tsv \\
        --truth data/ourense_truth_limpia.tsv \\
        --mascara data/ourense_mascara_train.tsv --umbral 0.7 \\
        --out data/candidatos_ourense.tsv
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
    # **Sin esto se re-proponen castros conocidos del borde.** La verdad del
    # bloque se construye desde un bbox, pero las teselas de 1 km se desbordan y
    # el barrido puntua terreno de fuera. Un castro que caiga 300 m mas alla del
    # borde no esta en la verdad, asi que su deteccion sale como «sin
    # catalogar». Paso el 2026-08-07 con el Castro da Igrexa/Castro de Lebruxo:
    # a 22 m de un candidato de Lugo, catalogado, y a 0,003 grados por encima
    # del bbox. Es la tercera vez que este desborde muerde —ya paso en Trasancos
    # con 6 castros y en Lugo con 4 de los 20 mejores— y por eso la comprobacion
    # va contra el catalogo ENTERO, no contra el recorte del bloque.
    ap.add_argument("--catalogo-completo", type=Path,
                    default=Path("data/weak_label_master_fusionado.tsv"),
                    help="maestro con TODOS los castros, para no re-proponer "
                         "los que caen justo fuera del recuadro")
    ap.add_argument("--umbral", type=float, default=0.7)
    ap.add_argument("--enlace-m", type=float, default=512.0)
    ap.add_argument("--tolerancia-m", type=float, default=500.0)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    pred = [p for p in leer_tsv(args.pred, ("lon", "lat", "score"))
            if "score" in p]
    for p in pred:
        p["score"] = float(p["score"])
    truth = leer_tsv(args.truth)
    masc = leer_tsv(args.mascara) if args.mascara else []
    todos = []
    if args.catalogo_completo and Path(args.catalogo_completo).exists():
        with open(args.catalogo_completo, encoding="utf-8") as fh:
            for r in csv.DictReader(fh, delimiter="\t"):
                if r.get("label_class") != "1":
                    continue
                lo, la = r.get("longitude"), r.get("latitude")
                try:
                    todos.append({"lon": float(lo), "lat": float(la)})
                except (TypeError, ValueError):
                    continue
    sel = [p for p in pred if p["score"] >= args.umbral]
    if not sel:
        raise SystemExit("ninguna celda supera el umbral")

    lat0 = float(np.mean([t["lat"] for t in truth]))
    px, py = a_metros([p["lon"] for p in sel], [p["lat"] for p in sel], lat0)
    tx, ty = a_metros([t["lon"] for t in truth], [t["lat"] for t in truth], lat0)
    if masc:
        mx, my = a_metros([m["lon"] for m in masc],
                          [m["lat"] for m in masc], lat0)
    if todos:
        gx, gy = a_metros([t_["lon"] for t_ in todos],
                          [t_["lat"] for t_ in todos], lat0)

    filas, n_conocidos, n_masc, n_borde = [], 0, 0, 0
    for g in agrupar(px, py, args.enlace_m):
        cx, cy = float(np.mean(px[g])), float(np.mean(py[g]))
        sc = max(sel[i]["score"] for i in g)
        if np.hypot(tx - cx, ty - cy).min() <= args.tolerancia_m:
            n_conocidos += 1
            continue
        if masc and np.hypot(mx - cx, my - cy).min() <= args.tolerancia_m:
            n_masc += 1
            continue
        if todos and np.hypot(gx - cx, gy - cy).min() <= args.tolerancia_m:
            n_borde += 1
            continue
        lon = cx / (6371000.0 * math.cos(math.radians(lat0))) * 180 / math.pi
        lat = cy / 6371000.0 * 180 / math.pi
        filas.append({"lon": round(lon, 6), "lat": round(lat, 6),
                      "score": round(sc, 4), "celdas": len(g),
                      "estado": "CANDIDATO"})

    filas.sort(key=lambda r: -r["score"])
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["lon", "lat", "score", "celdas",
                                           "estado"], delimiter="\t")
        w.writeheader()
        w.writerows(filas)

    print(f"umbral {args.umbral} | detecciones agrupadas: "
          f"{len(filas)+n_conocidos+n_masc+n_borde}")
    print(f"  sobre castro catalogado: {n_conocidos}")
    print(f"  sobre la máscara (visto en entrenamiento): {n_masc}")
    print(f"  sobre un castro del catálogo fuera del recuadro: {n_borde}")
    print(f"  **SIN CATALOGAR, a revisar: {len(filas)}**")
    print(f"\nescrito: {args.out}")
    if filas:
        print(f"mejor puntuado: {filas[0]['score']:.3f} en "
              f"{filas[0]['lat']:.5f}, {filas[0]['lon']:.5f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
