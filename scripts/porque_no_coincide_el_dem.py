#!/usr/bin/env python3
"""¿Por qué la vía del DEM sigue sin coincidir tras alinear la rejilla?

`verificar_dem.py` dio el `2026-08-11`, ya con la rejilla alineada a metro
entero de UTM: peor caso `0,912`, mediana `0,971`, y `21` de `25` celdas por
debajo de `0,99`. El arreglo funcionó —antes el peor caso era `0,53`— pero no
basta para una medida de conjunto de prueba.

**Hipótesis, escrita antes de medir**: lo que queda es **el relleno de huecos**.

- `grid_from_points` rellena por vecino más próximo **dentro de la ventana** de
  `512 m` que se está recortando.
- La caché de `laz_a_dem.py` rellena **dentro de la tesela** entera.

Vecindarios distintos dan rellenos distintos, y eso **no lo arregla ninguna
alineación**. Si la hipótesis es cierta, la correlación por celda tiene que caer
justo donde hay más huecos.

**Y si es falsa** —correlación mala también sin huecos— la causa es otra y hay
que buscarla, porque desbloquear `--dem-dir` vale el `87,6%` del coste de todo
barrido y `72×` de almacenamiento.

Uso:
    python3 scripts/porque_no_coincide_el_dem.py \\
        --laz-dir data/external/lidar-val-lugo --dem-dir data/dem-cache-lugo --n 30
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "scripts"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--laz-dir", type=Path, required=True)
    ap.add_argument("--dem-dir", type=Path, required=True)
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--extent", type=float, default=512.0)
    ap.add_argument("--res", type=float, default=1.0)
    args = ap.parse_args()

    import sweep_grid_lidar as S
    import laspy

    dems = sorted(args.dem_dir.glob("*.npz"))
    filas = []
    for d in dems:
        laz = args.laz_dir / f"{d.stem}.laz"
        if not laz.exists():
            continue
        z = np.load(d)
        b = z["bounds"]
        cx = (float(b[0]) + float(b[2])) / 2.0
        cy = (float(b[1]) + float(b[3])) / 2.0
        c = {"x": cx, "y": cy, "id": d.stem, "lon": 0.0, "lat": 0.0}

        a = S.cortar_desde_dem(([str(d)], [c], args.extent, args.res))
        bb = S.cortar_grupo(([str(laz)], [c], args.extent, args.res))
        if not a or not bb:
            continue
        ca = np.asarray(a[0][-1], dtype=np.float32)
        cb = np.asarray(bb[0][-1], dtype=np.float32)
        if ca.shape != cb.shape:
            continue
        m = np.isfinite(ca) & np.isfinite(cb)
        if m.sum() < 1000:
            continue
        cor = float(np.corrcoef(ca[m].ravel(), cb[m].ravel())[0, 1])

        # **La fracción de huecos, calculada como la calcula el propio
        # `grid_from_points`**: celdas del recorte sin ningún retorno de suelo.
        half = args.extent / 2.0
        las = laspy.read(str(laz))
        k = np.asarray(las.classification) == 2
        X = np.asarray(las.x)[k]; Y = np.asarray(las.y)[k]
        caja = (cx - half, cy - half, cx + half, cy + half)
        dentro = (X >= caja[0]) & (X <= caja[2]) & (Y >= caja[1]) & (Y <= caja[3])
        w = int(round(args.extent / args.res))
        ix = np.clip(((X[dentro] - caja[0]) / args.res).astype(np.int64), 0, w - 1)
        iy = np.clip(((caja[3] - Y[dentro]) / args.res).astype(np.int64), 0, w - 1)
        ocupadas = np.zeros(w * w, bool)
        ocupadas[iy * w + ix] = True
        huecos = float(1.0 - ocupadas.mean())

        filas.append((d.stem, cor, huecos))
        print("  %-38s corr %.4f  huecos %5.1f%%" % (d.stem[-34:], cor,
                                                     100 * huecos), flush=True)
        if len(filas) >= args.n:
            break

    if len(filas) < 8:
        print("muy pocas celdas comparables: %d" % len(filas))
        return 1

    cor = np.array([f[1] for f in filas])
    hue = np.array([f[2] for f in filas])
    r = float(np.corrcoef(cor, hue)[0, 1])

    print("\n%s" % ("=" * 62))
    print("celdas comparadas: %d" % len(filas))
    print("correlacion de canales: mediana %.4f, peor %.4f"
          % (np.median(cor), cor.min()))
    print("huecos: mediana %.1f%%, maximo %.1f%%"
          % (100 * np.median(hue), 100 * hue.max()))
    print()
    print("CORRELACION ENTRE 'cuantos huecos' y 'cuanto se parecen': %+.3f" % r)
    print()
    if r < -0.4:
        print("HIPOTESIS SOSTENIDA: cuantos mas huecos, peor coinciden.")
        print("La causa es el relleno, y se arregla rellenando IGUAL en las dos")
        print("vias — no alineando mas.")
    elif abs(r) < 0.25:
        print("HIPOTESIS REFUTADA: los huecos no explican la diferencia.")
        print("Hay que buscar otra causa antes de reactivar --dem-dir.")
        sin = cor[hue < np.median(hue)]
        print("  y en las celdas con MENOS huecos la correlacion sigue en %.4f"
              % np.median(sin))
    else:
        print("Relacion debil (%+.3f): los huecos explican parte, no todo." % r)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
