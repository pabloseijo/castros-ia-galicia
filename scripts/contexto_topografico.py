#!/usr/bin/env python3
"""Mide si un candidato ocupa la posición que ocupa un castro. Del LiDAR propio.

La revisión visual dice si **hay** un recinto; esto dice si está **donde debe**.
Son cosas distintas y las dos hacen falta: un bancal agrícola puede dibujar arcos
concéntricos preciosos a media ladera, y una cantera puede tener bancos que
imitan parapetos, pero **ninguno de los dos se sienta en una cima que domina**.

Un castro se emplaza para ver y para defender. Eso deja tres huellas medibles en
el modelo digital del terreno, sin necesidad de criterio arqueológico:

- **Prominencia local**: cuánto sobresale el punto respecto al terreno de
  alrededor. Un recinto en cima da valores altos; uno a media ladera, no.
- **Percentil de altura en el entorno**: qué fracción del terreno cercano queda
  por debajo. En un castro se acerca al `100%`.
- **Pendiente del emplazamiento contra la del entorno**: la plataforma superior
  es **llana** aunque esté rodeada de laderas fuertes. Un bancal, al contrario,
  está en pendiente y es llano solo en franjas estrechas.

Se calcula todo sobre el mismo LiDAR con el que se detectó, así que no depende
de ninguna fuente externa ni de que el sitio esté cartografiado.

Uso:
    python3 scripts/contexto_topografico.py --puntos data/candidatos_ourense.tsv \\
        --laz-dir data/external/lidar-val-ourense
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_trasancos_vignettes import (grid_from_points,  # noqa: E402
                                       group_samples_by_tiles, lonlat_to_utm29)


def medir(dem, res, radio_sitio_m, radio_ent_m):
    n = dem.shape[0]
    yy, xx = np.ogrid[:n, :n]
    c = (n - 1) / 2.0
    d = np.hypot((yy - c) * res, (xx - c) * res)
    sitio = d <= radio_sitio_m
    ent = (d > radio_sitio_m * 1.5) & (d <= radio_ent_m)
    if sitio.sum() < 9 or ent.sum() < 50:
        return None
    z_s, z_e = dem[sitio], dem[ent]
    z_s = z_s[np.isfinite(z_s)]
    z_e = z_e[np.isfinite(z_e)]
    if len(z_s) < 9 or len(z_e) < 50:
        return None
    cima = float(np.percentile(z_s, 90))
    prom = cima - float(np.median(z_e))
    pct = float((z_e < np.median(z_s)).mean())
    gy, gx = np.gradient(dem.astype(np.float64), res)
    pend = np.degrees(np.arctan(np.hypot(gy, gx)))
    p_s = float(np.nanmedian(pend[sitio]))
    p_e = float(np.nanmedian(pend[ent]))
    return {"prominencia_m": prom, "pct_entorno_debajo": pct,
            "pend_sitio": p_s, "pend_entorno": p_e,
            "llaneza": p_e - p_s}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--puntos", type=Path, required=True)
    ap.add_argument("--laz-dir", type=Path, nargs="+", required=True)
    ap.add_argument("--radio-sitio-m", type=float, default=60.0)
    ap.add_argument("--radio-entorno-m", type=float, default=250.0)
    ap.add_argument("--res-m", type=float, default=2.0)
    args = ap.parse_args()

    filas = list(csv.DictReader(open(args.puntos, encoding="utf-8"),
                                delimiter="\t"))
    ext = args.radio_entorno_m * 2 + 40
    celdas = []
    for i, r in enumerate(filas):
        x, y = lonlat_to_utm29(float(r["lon"]), float(r["lat"]))
        celdas.append({"id": i, "x": x, "y": y,
                       "lon": float(r["lon"]), "lat": float(r["lat"])})
    tiles = sorted(str(p) for d in args.laz_dir for p in Path(d).glob("*.laz"))
    grupos, huerf = group_samples_by_tiles(celdas, tiles, ext)
    print(f"puntos: {len(celdas)} | sin LiDAR: {huerf}", flush=True)

    import laspy
    res = args.res_m
    out = {}
    for tp, cs in grupos.items():
        xs_l, ys_l, zs_l = [], [], []
        for t in tp:
            try:
                with laspy.open(t) as fh:
                    for p in fh.chunk_iterator(4_000_000):
                        k = np.asarray(p.classification) == 2
                        if not k.any():
                            continue
                        xs_l.append(np.asarray(p.x)[k].astype(np.float32))
                        ys_l.append(np.asarray(p.y)[k].astype(np.float32))
                        zs_l.append(np.asarray(p.z)[k].astype(np.float32))
            except Exception:
                continue
        if not xs_l:
            continue
        X = np.concatenate(xs_l); Y = np.concatenate(ys_l); Z = np.concatenate(zs_l)
        for c in cs:
            h = ext / 2.0
            b = (c["x"]-h, c["y"]-h, c["x"]+h, c["y"]+h)
            m = (X >= b[0]) & (X <= b[2]) & (Y >= b[1]) & (Y <= b[3])
            if m.sum() < 2000:
                continue
            dem = grid_from_points(X[m], Y[m], Z[m], b, res)
            if dem is None:
                continue
            r = medir(dem, res, args.radio_sitio_m, args.radio_entorno_m)
            if r:
                out[c["id"]] = r
        del X, Y, Z

    print(f"\n{'#':>3} {'score':>6} {'promin.':>8} {'%debajo':>8} "
          f"{'pend.sitio':>11} {'pend.ent':>9} {'llaneza':>8}  veredicto")
    print("-" * 78)
    for i, fila in enumerate(filas):
        # La verdad de campo no trae `score`; los candidatos si. Se acepta las
        # dos, porque este script se usa TAMBIEN sobre castros conocidos para
        # calibrar: sin ese control no se sabe que valores son los normales.
        sc = float(fila.get("score") or 0.0)
        r = out.get(i)
        if not r:
            print(f"{i+1:>3} {sc:>6.3f}   (sin lectura)")
            continue
        # Un castro: sobresale, casi todo el entorno queda debajo, y su
        # plataforma es mas llana que la ladera que la rodea.
        v = []
        if r["prominencia_m"] >= 15: v.append("cima")
        if r["pct_entorno_debajo"] >= 0.85: v.append("domina")
        if r["llaneza"] >= 3: v.append("plataforma")
        print(f"{i+1:>3} {sc:>6.3f} {r['prominencia_m']:>7.1f}m "
              f"{100*r['pct_entorno_debajo']:>7.0f}% {r['pend_sitio']:>10.1f}° "
              f"{r['pend_entorno']:>8.1f}° {r['llaneza']:>7.1f}°  "
              f"{' + '.join(v) if v else '-'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
