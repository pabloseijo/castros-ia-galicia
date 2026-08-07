#!/usr/bin/env python3
"""¿Por qué hay castros conocidos con prominencia negativa?

El `2026-08-07` el triaje imprimió sus calibraciones y salió esto:

    Lugo      mediana 27,3 m, rango -36,1 a 69,9 m
    A Coruña  mediana  8,4 m, rango  -1,4 a 43,1 m

**Una prominencia negativa no es un castro bajito.** `medir` calcula
`percentil90(sitio) - mediana(entorno)`, así que sale negativa cuando el punto
catalogado está en un **valle** respecto a lo que lo rodea. Un recinto
fortificado no está en un valle: se pone donde se ve venir a la gente.

Colándose en la calibración arrastraban el percentil hacia abajo y dejaban el
criterio sin discriminar — el umbral de A Coruña salía en `4,0 m`, que **todo**
candidato supera.

## La hipótesis que comprueba

Que las lecturas negativas sean **las entradas del catálogo que no son
recintos**. La auditoría del mismo día encontró que el `15,4%` de lo etiquetado
como castro en Galicia son casas, iglesias, cruceiros, fuentes y puentes: y una
fuente, un molino o un puente están **por definición** en el fondo del valle.

Si la hipótesis se sostiene, la contaminación del catálogo sí tiene un efecto
medible — no escondiendo candidatos, como se comprobó que no hacía, sino
**estropeando la calibración del triaje**, que es un camino que nadie había
mirado.

Uso:
    python3 scripts/diagnosticar_calibracion.py \\
        --truth data/lugo_fus_truth_limpia.tsv \\
        --laz-dir data/external/lidar-val-lugo --etiqueta lugo
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "scripts"))

# Mismo criterio que `auditar_catalogo.py`: el nombre menciona otro monumento.
OTRO = (r"\bmili[aá]rio?\b|\bestela\b|petr[oó]glif|inscultur|\broch[ae]\b|"
        r"\bm[aá]moas?\b|\bmedoñ|\bt[uú]mulo|\bdolmen\b|"
        r"\bigrexa\b|\bcapela\b|\bermida\b|\bmosteiro\b|\bconvento\b|"
        r"\bfonte\b|\blavadoiro\b|\bpozo\b|\bponte\b|\bcalzada\b|"
        r"\bpazo\b|\btorre\b|\bcasa\b|\bh[oó]rreo\b|\bcruceiro\b|\bcruz\b|"
        r"\bmui[nñ]o\b|\bmina\b|\bcanteira\b|\bcampo d[ae]\b|\bromar[ií]a\b")
# Los que ADEMAS dicen castro casi siempre son castros de verdad bautizados por
# lo que tienen al lado: `Castro da Capela`, `Castro do Pazo`.
RECINTO = r"\bcastros?\b|\bcroa\b|\bcividade\b|\bcitania\b|castrom"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--truth", type=Path, required=True)
    ap.add_argument("--laz-dir", type=Path, nargs="+", required=True)
    ap.add_argument("--etiqueta", default="bloque")
    ap.add_argument("--limite", type=int, default=40)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    from contexto_topografico import medir
    from build_trasancos_vignettes import (grid_from_points,
                                           group_samples_by_tiles,
                                           lonlat_to_utm29)
    import laspy

    # Los mismos parametros que usa el triaje al calibrar, para que el
    # diagnostico explique la calibracion de verdad y no una parecida.
    ext, res = 540.0, 2.0

    filas = list(csv.DictReader(open(args.truth, encoding="utf-8"),
                                delimiter="\t"))[:args.limite]
    nom = next((c for c in ("name", "nombre", "nome") if c in filas[0]), None)
    if nom is None:
        print(f"la verdad no trae columna de nombre: {list(filas[0])}")
        return 1
    tiles = sorted(str(p) for d in args.laz_dir for p in Path(d).glob("*.laz"))

    cel = []
    for j, r in enumerate(filas):
        x, y = lonlat_to_utm29(float(r["lon"]), float(r["lat"]))
        cel.append({"id": j, "x": x, "y": y,
                    "lon": float(r["lon"]), "lat": float(r["lat"])})
    grupos, _ = group_samples_by_tiles(cel, tiles, ext)

    med = {}
    for tp, cs in grupos.items():
        xs, ys, zs = [], [], []
        for t in tp:
            try:
                with laspy.open(t) as fh:
                    for p in fh.chunk_iterator(4_000_000):
                        kk = np.asarray(p.classification) == 2
                        if not kk.any():
                            continue
                        xs.append(np.asarray(p.x)[kk].astype(np.float32))
                        ys.append(np.asarray(p.y)[kk].astype(np.float32))
                        zs.append(np.asarray(p.z)[kk].astype(np.float32))
            except Exception:
                continue
        if not xs:
            continue
        X = np.concatenate(xs); Y = np.concatenate(ys); Z = np.concatenate(zs)
        for c in cs:
            h = ext / 2.0
            b = (c["x"]-h, c["y"]-h, c["x"]+h, c["y"]+h)
            m = (X >= b[0]) & (X <= b[2]) & (Y >= b[1]) & (Y <= b[3])
            if m.sum() < 2000:
                continue
            dem = grid_from_points(X[m], Y[m], Z[m], b, res)
            if dem is None or np.ndim(dem) != 2:
                continue
            rr = medir(dem, res, 60.0, 250.0)
            if rr:
                med[c["id"]] = rr["prominencia_m"]
        del X, Y, Z

    reg = []
    for j, r in enumerate(filas):
        if j not in med:
            continue
        n = (r.get(nom) or "").lower() if nom else ""
        dudosa = bool(re.search(OTRO, n)) and not re.search(RECINTO, n)
        reg.append({"nombre": (r.get(nom) or "")[:46], "prom": med[j],
                    "dudosa": dudosa})

    if not reg:
        print("ninguna lectura válida"); return 1
    p = np.array([r["prom"] for r in reg])
    d = np.array([r["dudosa"] for r in reg])
    neg = p <= 0

    print(f"\n=== {args.etiqueta} — {len(reg)} castros con lectura ===")
    print(f"prominencia: mediana {np.median(p):.1f} m | "
          f"rango {p.min():.1f} a {p.max():.1f} m")
    print(f"con prominencia NO FÍSICA (<= 0): {neg.sum()} "
          f"({100*neg.mean():.0f}%)")
    print(f"con nombre de otro monumento:     {d.sum()}")

    if neg.any():
        print(f"\nde las {neg.sum()} no físicas, {int((neg & d).sum())} tienen "
              f"nombre de otro monumento")
    if d.any():
        print(f"mediana de prominencia | nombre dudoso: "
              f"{np.median(p[d]):6.1f} m  (n={d.sum()})")
    if (~d).any():
        print(f"                       | nombre limpio: "
              f"{np.median(p[~d]):6.1f} m  (n={(~d).sum()})")

    print("\nlas diez lecturas más bajas:")
    for r in sorted(reg, key=lambda r: r["prom"])[:10]:
        marca = " ← nombre de otro monumento" if r["dudosa"] else ""
        print(f"  {r['prom']:7.1f} m  {r['nombre']}{marca}")

    print("\nefecto sobre la calibración:")
    from verificar_candidatos import calibrar
    for etq, sel in (("con todo", p), ("solo físicas", p[~neg])):
        if len(sel) >= 5:
            u, s = calibrar(list(sel))
            print(f"  {etq:13s} n={len(sel):3d}  umbral {u:5.1f} m  sigma {s:4.1f} m")

    if args.out:
        with open(args.out, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["nombre", "prom", "dudosa"])
            w.writeheader(); w.writerows(reg)
        print(f"\nescrito: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
