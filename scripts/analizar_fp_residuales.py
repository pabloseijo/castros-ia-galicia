#!/usr/bin/env python3
"""¿De dónde salen los falsos positivos que quedan? La pregunta que decide la vía.

Existe por una medición del `2026-08-06` que cambió el diagnóstico del proyecto.
Con `v6` —el corpus con `534` negativos duros minados de OSM— se extrajeron los
falsos positivos del barrido de Pontevedra y se midió su distancia a los sitios
que el propio entrenamiento había visto etiquetados como negativo:

    **16 de 26 estaban a 1 metro.** El mismo punto, sin margen de error.

Es decir: el modelo vio el confusor, con la etiqueta correcta, y lo puntúa igual
`0.82`-`0.99`. Eso descarta «faltan negativos» y apunta a **cómo se pesan**: con
`CrossEntropyLoss(weight=balanced)` el peso va por frecuencia de clase, así que
los `534` negativos duros son el `4,9%` de la clase «fondo» y se llevan `~1,6%`
del gradiente. La dilución es invisible en el recall agregado de «fondo», porque
fallarlos todos costaría `~5` puntos.

Este script existe para poder repetir esa medición contra cualquier barrido y
cualquier checkpoint, que es lo único que distingue las dos hipótesis vivas:

- si tras cambiar la pérdida esos sitios **se apagan**, era el peso;
- si **siguen disparando**, el relieve no basta y toca la ortofoto.

Un falso positivo se cuenta como tal igual que en `detection_eval.py`: agrupado,
lejos de la verdad de campo y lejos de la máscara de contaminación. Y se
clasifica por su origen, que es lo que aquí importa.

**Cautela que no se puede omitir al leer la salida:** «falso positivo» significa
aquí *no catalogado*, no *no arqueológico*. Canedo revisó sus `40` residuales y
`9` eran castros inéditos. Los hallazgos viven dentro del error, así que un
recuento de FP no es una lista de fallos hasta que un arqueólogo la mira.

Uso:
    python3 scripts/analizar_fp_residuales.py \\
        --pred data/sweep_val_pontevedra_v6focal.tsv \\
        --truth data/pontevedra_truth_limpia.tsv \\
        --mascara data/pontevedra_mascara_train.tsv \\
        --negativos data/negativos-osm-pontevedra.tsv data/fp_pontevedra.tsv
"""
from __future__ import annotations

import argparse
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
    ap.add_argument("--negativos", type=Path, nargs="+", default=[],
                    help="TSV de sitios vistos como negativo en entrenamiento")
    ap.add_argument("--umbrales", type=float, nargs="+", default=[0.7, 0.8])
    ap.add_argument("--enlace-m", type=float, default=512.0)
    ap.add_argument("--tolerancia-m", type=float, default=500.0)
    ap.add_argument("--memoria-m", type=float, default=300.0,
                    help="a esta distancia se considera 'el mismo sitio' que un "
                         "negativo de entrenamiento")
    args = ap.parse_args()

    pred = [p for p in leer_tsv(args.pred, ("lon", "lat", "score")) if "score" in p]
    for p in pred:
        p["score"] = float(p["score"])
    truth = leer_tsv(args.truth)
    mascara = leer_tsv(args.mascara) if args.mascara else []
    if not pred or not truth:
        raise SystemExit("faltan predicciones o verdad de campo")

    lat0 = float(np.mean([t["lat"] for t in truth]))
    tx, ty = a_metros([t["lon"] for t in truth], [t["lat"] for t in truth], lat0)
    if mascara:
        mx, my = a_metros([m["lon"] for m in mascara],
                          [m["lat"] for m in mascara], lat0)

    negs = {}
    for f in args.negativos:
        filas = leer_tsv(f)
        if filas:
            negs[f.stem] = a_metros([r["lon"] for r in filas],
                                    [r["lat"] for r in filas], lat0)
        print(f"negativos de entrenamiento '{f.stem}': {len(filas)}", flush=True)

    # La cobertura primero, como en detection_eval: un barrido a medias da
    # cifras plausibles y falsas, y aqui pasaria igual.
    _px, _py = a_metros([p["lon"] for p in pred], [p["lat"] for p in pred], lat0)
    _d = np.array([float(np.hypot(_px - tx[i], _py - ty[i]).min())
                   for i in range(len(tx))])
    print("cobertura: %d de %d yacimientos con celda a <256 m (%.0f%%)"
          % ((_d <= 256).sum(), len(_d), 100 * (_d <= 256).mean()), flush=True)
    if (_d <= 256).mean() < 0.95:
        print("*** AVISO: cobertura baja. Lo de abajo mide el barrido, no el "
              "modelo. ***", flush=True)

    for umbral in args.umbrales:
        sel = [p for p in pred if p["score"] >= umbral]
        if not sel:
            print(f"\n=== umbral {umbral}: sin detecciones ===")
            continue
        px, py = a_metros([p["lon"] for p in sel], [p["lat"] for p in sel], lat0)
        grupos = agrupar(px, py, args.enlace_m)
        centros = [(float(np.mean(px[g])), float(np.mean(py[g])), len(g),
                    max(sel[i]["score"] for i in g)) for g in grupos]

        fps = []
        for cx, cy, n, sc in centros:
            if np.hypot(tx - cx, ty - cy).min() <= args.tolerancia_m:
                continue                      # acierto
            if mascara and np.hypot(mx - cx, my - cy).min() <= args.tolerancia_m:
                continue                      # contaminacion enmascarada
            orig, dmin = "NUEVO", float("inf")
            for nombre, (nx, ny) in negs.items():
                d = float(np.hypot(nx - cx, ny - cy).min())
                if d < dmin:
                    dmin, orig = d, (nombre if d <= args.memoria_m else "NUEVO")
            lon = cx / (6371000.0 * math.cos(math.radians(lat0))) * 180 / math.pi
            lat = cy / 6371000.0 * 180 / math.pi
            fps.append({"lon": lon, "lat": lat, "n": n, "score": sc,
                        "origen": orig, "d_neg": dmin})

        memorizados = [f for f in fps if f["origen"] != "NUEVO"]
        print(f"\n=== umbral {umbral} ===")
        print(f"detecciones: {len(centros)} | falsos positivos: {len(fps)}")
        if fps:
            print(f"  YA VISTOS como negativo en entrenamiento (<{args.memoria_m:.0f} m): "
                  f"{len(memorizados)}  ({100*len(memorizados)/len(fps):.0f}%)")
            print(f"  nuevos: {len(fps) - len(memorizados)}")
            print("\n  los que el entrenamiento no logró apagar, por puntuación:")
            print("    score  ncel   d_neg  origen")
            for f in sorted(memorizados, key=lambda r: -r["score"])[:20]:
                print(f"    {f['score']:.2f}  {f['n']:4d}  {f['d_neg']:6.0f}m  "
                      f"{f['origen']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
