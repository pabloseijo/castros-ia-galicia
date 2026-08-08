#!/usr/bin/env python3
"""Morfometría por candidato que la revisión visual hacía a ojo: en lote y en CPU.

La medida nueva es la **cobertura angular del anillo**. El contraste del perfil
radial se calibró el `2026-08-08` y salió `AUC 0,663` — ordena, no decide — y la
revisión visual explicó por qué: un lazo de autovía o un bancal dan un pico tan
alto como un parapeto. Lo que el ojo usaba para distinguirlos no era la altura
del pico sino **si el anillo da la vuelta entera**:

- un recinto cerrado tiene apertura positiva en casi todos los rumbos del anillo;
- una rampa de enlace, un bancal en curva de nivel o una linde la tienen en un
  arco y en el resto no.

`cobertura_angular` = fracción de los `72` sectores de `5°` del anillo del pico
cuyo valor medio supera la mediana global de la viñeta. Cerrado ≈ `>0,7`; arco
suelto ≈ `<0,5`. **Sin calibrar todavía** — se emite como columna para mirarla
contra los veredictos visuales, no como criterio.

También emite `n_maximos` (cuántos máximos locales tiene el perfil entre `25` y
`140 m`): un castro multivallado puede tener `2-3`; un campo de bancales, `5+`.

Corre en `oval-server` con `nice 19`: lee LAZ, que ya están allí.

Uso:
    python3 scripts/morfologia_candidatos.py --candidatos todos.tsv \\
        --laz-base data/external --out data/morfo_candidatos.tsv
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "scripts"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidatos", type=Path, required=True)
    ap.add_argument("--laz-base", type=Path, default=Path("data/external"))
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--lado-m", type=float, default=600.0)
    args = ap.parse_args()

    from build_trasancos_vignettes import (grid_from_points,
                                           group_samples_by_tiles,
                                           lonlat_to_utm29)
    from ficha_candidato import perfil_radial, pico_del_perfil
    from openness import apertura
    import laspy

    filas = list(csv.DictReader(open(args.candidatos, encoding="utf-8"),
                                delimiter="\t"))
    print("candidatos: %d" % len(filas), flush=True)

    hechos = set()
    if args.out.exists():
        for r in csv.DictReader(open(args.out, encoding="utf-8"),
                                delimiter="\t"):
            hechos.add((r["bloque"], r["n"]))
        print("reanudando: %d" % len(hechos), flush=True)

    nuevo = not args.out.exists()
    fh = open(args.out, "a", newline="", encoding="utf-8")
    w = csv.writer(fh, delimiter="\t")
    if nuevo:
        w.writerow(["bloque", "n", "radio_m", "contraste", "cobertura_angular",
                    "n_maximos"])

    # agrupar por bloque para leer cada conjunto de teselas una vez
    por_bloque = {}
    for r in filas:
        por_bloque.setdefault(r["bloque"], []).append(r)

    half = args.lado_m / 2.0
    for bloque, cs in por_bloque.items():
        pend = [c for c in cs if (bloque, c["n"]) not in hechos]
        if not pend:
            continue
        teselas = sorted(str(p) for p in
                         (args.laz_base / f"lidar-val-{bloque}").glob("*.laz"))
        celdas = []
        for c in pend:
            x, y = lonlat_to_utm29(float(c["lon"]), float(c["lat"]))
            celdas.append({"id": c["n"], "x": x, "y": y, "fila": c})
        grupos, _ = group_samples_by_tiles(celdas, teselas, args.lado_m + 40)
        print("== %s: %d pendientes en %d grupos" % (bloque, len(pend),
                                                     len(grupos)), flush=True)
        for tp, cls_ in grupos.items():
            xs, ys, zs = [], [], []
            for t in tp:
                try:
                    las = laspy.read(t)
                    k = np.asarray(las.classification) == 2
                    if not k.any():
                        continue
                    xs.append(np.asarray(las.x)[k])
                    ys.append(np.asarray(las.y)[k])
                    zs.append(np.asarray(las.z)[k])
                except Exception:
                    continue
            if not xs:
                continue
            X = np.concatenate(xs); Y = np.concatenate(ys)
            Z = np.concatenate(zs)
            for c in cls_:
                b = (c["x"]-half, c["y"]-half, c["x"]+half, c["y"]+half)
                m = (X >= b[0]) & (X <= b[2]) & (Y >= b[1]) & (Y <= b[3])
                if m.sum() < 2000:
                    continue
                dem = grid_from_points(X[m], Y[m], Z[m], b, 1.0)
                if dem is None or np.ndim(dem) != 2:
                    continue
                rs, perf, _ = perfil_radial(dem, 1.0)
                j, con = pico_del_perfil(rs, perf)

                cob = float("nan")
                nmax = 0
                r_ = np.asarray(rs, float)
                y_ = np.asarray(perf, float)
                ok = (r_ >= 25.0)
                idx = np.where(ok)[0]
                nmax = sum(1 for i2 in idx[1:-1]
                           if np.isfinite(y_[i2]) and y_[i2] > y_[i2-1]
                           and y_[i2] > y_[i2+1])
                if j is not None:
                    # apertura sin reducir, mismos parametros que el perfil
                    pos, neg = apertura(dem, 1.0, 30.0, 8)
                    v = pos - neg
                    n = v.shape[0]
                    cc = (n - 1) / 2.0
                    yy, xx = np.ogrid[:n, :n]
                    dist = np.hypot(yy - cc, xx - cc) * 1.0
                    ang = np.arctan2(yy - cc, xx - cc)
                    rp = float(rs[j])
                    anillo = (dist >= rp - 4) & (dist < rp + 4)
                    med = float(np.nanmedian(v))
                    sect = np.floor((ang[anillo] + np.pi) / (2 * np.pi) * 72)
                    vals = v[anillo]
                    cubiertos = 0
                    for s in range(72):
                        vs = vals[sect == s]
                        if len(vs) and np.nanmean(vs) > med:
                            cubiertos += 1
                    cob = cubiertos / 72.0

                w.writerow([bloque, c["id"],
                            "" if j is None else "%.0f" % rs[j],
                            "" if j is None else "%.2f" % con,
                            "" if not np.isfinite(cob) else "%.2f" % cob,
                            nmax])
                fh.flush()
                print("  %s n%s: r=%s cob=%s nmax=%d"
                      % (bloque, c["id"],
                         "-" if j is None else "%.0f" % rs[j],
                         "-" if not np.isfinite(cob) else "%.2f" % cob,
                         nmax), flush=True)
            del X, Y, Z
    fh.close()
    print("\nescrito: %s" % args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
