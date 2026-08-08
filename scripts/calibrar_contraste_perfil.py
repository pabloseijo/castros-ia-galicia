#!/usr/bin/env python3
"""Calibra el contraste del perfil radial con castros de verdad, no con cuatro.

**El problema, medido a ojo el 2026-08-08.** Al revisar las fichas, el contraste
del perfil no separa: Becerreá saca `2,21` y está en parcelario agrícola, Beade
saca `1,86` y es un desmonte forestal, Cerceda saca `2,13` y es el único con
apoyo externo. Los tres en el mismo tramo, significando cosas distintas.

La ficha ya avisaba de que no estaba calibrado —«sobre `4` castros conocidos el
contraste va de `2,2` a `2,8` y sobre `3` falsos positivos de `0,8` a `2,0`, y se
solapan»— pero `4` contra `3` no es una calibración, es una anécdota.

**Y la solución estaba delante:** hay `4.080` castros catalogados y `10.742`
viñetas de terreno aleatorio. Los bloques de validación traen LiDAR de sobra para
medir unos cientos de cada. Con eso el solape deja de ser una frase y pasa a ser
una distribución, con su AUC y su umbral si es que lo hay.

**Puede salir que no separa, y eso también vale.** Si las dos distribuciones se
montan, el contraste se retira de la ficha en vez de seguir insinuando algo que
no sostiene. Un descriptor que no discrimina y se enseña igual es peor que no
enseñar nada, porque quien mire le dará peso.

Busqué literatura antes de escribir esto (`2026-08-08`): Vinci y Vanzani
(`10.1007/s12520-024-02127-w`) hacen morfometría de terraplenes con LiDAR, pero
calibran contra levantamientos topográficos de campo que ya tenían. No hay atajo
publicado; la calibración hay que hacerla con el dato propio.

Uso:
    python3 scripts/calibrar_contraste_perfil.py \\
        --truth data/lugo_fus_truth_limpia.tsv \\
        --negativos data/negativos_puntuados_v3.tsv \\
        --laz-dir data/external/lidar-val-lugo --n 60 --workers 1
"""
from __future__ import annotations

import argparse
import csv
import random
import sys
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "scripts"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--truth", type=Path, required=True)
    ap.add_argument("--negativos", type=Path, default=None,
                    help="TSV con lon/lat de terreno sin castro")
    ap.add_argument("--laz-dir", type=Path, nargs="+", required=True)
    ap.add_argument("--n", type=int, default=60, help="por clase")
    ap.add_argument("--lado-m", type=float, default=600.0)
    ap.add_argument("--res-m", type=float, default=1.0)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--semilla", type=int, default=20260808)
    args = ap.parse_args()

    from build_trasancos_vignettes import (grid_from_points,
                                           group_samples_by_tiles,
                                           lonlat_to_utm29)
    from ficha_candidato import perfil_radial, pico_del_perfil
    import laspy

    random.seed(args.semilla)

    def leer(p, lon_c, lat_c, etiqueta):
        filas = list(csv.DictReader(open(p, encoding="utf-8"), delimiter="\t"))
        random.shuffle(filas)
        out = []
        for r in filas:
            try:
                out.append((float(r[lon_c]), float(r[lat_c]), etiqueta))
            except (KeyError, TypeError, ValueError):
                continue
            if len(out) >= args.n:
                break
        return out

    puntos = leer(args.truth, "lon", "lat", 1)
    if args.negativos and args.negativos.exists():
        cab = open(args.negativos, encoding="utf-8").readline()
        lc = "lon" if "\tlon\t" in cab or cab.startswith("lon") else "longitude"
        la = "lat" if "\tlat\t" in cab or "\tlat" in cab else "latitude"
        puntos += leer(args.negativos, lc, la, 0)
    print(f"puntos: {sum(1 for p in puntos if p[2]==1)} castros, "
          f"{sum(1 for p in puntos if p[2]==0)} negativos", flush=True)

    celdas = []
    for i, (lon, lat, y) in enumerate(puntos):
        x, yy = lonlat_to_utm29(lon, lat)
        celdas.append({"id": i, "x": x, "y": yy, "lab": y})
    teselas = sorted(str(p) for d in args.laz_dir for p in Path(d).glob("*.laz"))
    grupos, fuera = group_samples_by_tiles(celdas, teselas, args.lado_m + 40)
    print(f"grupos: {len(grupos)} | sin cobertura: {fuera}", flush=True)

    res, half = args.res_m, args.lado_m / 2
    filas_out = []
    for gi, (tp, cs) in enumerate(grupos.items(), 1):
        xs, ys, zs = [], [], []
        for t in tp:
            try:
                las = laspy.read(t)
                k = np.asarray(las.classification) == 2
                if not k.any():
                    continue
                xs.append(np.asarray(las.x)[k]); ys.append(np.asarray(las.y)[k])
                zs.append(np.asarray(las.z)[k])
            except Exception:
                continue
        if not xs:
            continue
        X, Y, Z = np.concatenate(xs), np.concatenate(ys), np.concatenate(zs)
        for c in cs:
            b = (c["x"]-half, c["y"]-half, c["x"]+half, c["y"]+half)
            m = (X >= b[0]) & (X <= b[2]) & (Y >= b[1]) & (Y <= b[3])
            if m.sum() < 2000:
                continue
            dem = grid_from_points(X[m], Y[m], Z[m], b, res)
            if dem is None or np.ndim(dem) != 2:
                continue
            rs, perf, _ = perfil_radial(dem, res)
            j, con = pico_del_perfil(rs, perf)
            filas_out.append({"lab": c["lab"],
                              "radio": "" if j is None else f"{rs[j]:.0f}",
                              "contraste": "" if j is None else f"{con:.3f}"})
        del X, Y, Z
        if gi % 10 == 0:
            print(f"  grupo {gi}/{len(grupos)} | medidos {len(filas_out)}",
                  flush=True)

    pos = [float(r["contraste"]) for r in filas_out
           if r["lab"] == 1 and r["contraste"]]
    neg = [float(r["contraste"]) for r in filas_out
           if r["lab"] == 0 and r["contraste"]]
    sin_anillo = {e: sum(1 for r in filas_out
                         if r["lab"] == e and not r["contraste"])
                  for e in (1, 0)}
    print(f"\ncastros medidos: {len(pos)}  (sin anillo: {sin_anillo[1]})")
    print(f"negativos:       {len(neg)}  (sin anillo: {sin_anillo[0]})")
    if len(pos) < 10 or len(neg) < 10:
        print("\nmuestra insuficiente para calibrar"); return 1

    p, n = np.array(pos), np.array(neg)
    print(f"\n{'':12}{'n':>5}{'mediana':>9}{'p25':>8}{'p75':>8}{'min':>8}{'max':>8}")
    for etq, v in (("castros", p), ("negativos", n)):
        print(f"{etq:12}{len(v):>5}{np.median(v):>9.2f}{np.percentile(v,25):>8.2f}"
              f"{np.percentile(v,75):>8.2f}{v.min():>8.2f}{v.max():>8.2f}")

    # AUC por Mann-Whitney, sin dependencias
    todos = np.concatenate([p, n])
    orden = todos.argsort()
    rangos = np.empty(len(todos), float)
    rangos[orden] = np.arange(1, len(todos) + 1)
    auc = ((rangos[:len(p)].sum() - len(p) * (len(p) + 1) / 2)
           / (len(p) * len(n)))
    print(f"\nAUC = {auc:.3f}")
    if auc < 0.60:
        print("  -> NO SEPARA. El contraste debe salir de la ficha: un")
        print("     descriptor que no discrimina y se enseña igual es peor que")
        print("     no enseñar nada, porque quien mire le dara peso.")
    elif auc < 0.70:
        print("  -> separa poco. Vale para ordenar, no para decidir.")
    else:
        print("  -> separa. Se puede proponer un umbral con su tasa de error.")

    if args.out:
        with open(args.out, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["lab", "radio", "contraste"],
                               delimiter="\t")
            w.writeheader(); w.writerows(filas_out)
        print(f"\nescrito: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
