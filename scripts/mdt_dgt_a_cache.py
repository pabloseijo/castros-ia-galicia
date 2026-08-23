#!/usr/bin/env python3
"""Convierte el MDT-50cm de la DGT portuguesa a la cache .npz de 1 m que
`sweep_grid_lidar.py --dem-dir` sabe leer.

**Por que existe.** `DESCARGA-PORTUGAL.md` §2 pone por delante de las 74
descargas restantes una decision que nadie tomo: si el raster de la DGT
(`273 GB` en total) da lo mismo que su nube de puntos (`2,38 TB`), se bajan
las 74 como raster. La orden 1 se bajo en LOS DOS formatos justo para medirlo.

Genera DOS variantes, porque el estadistico de agregacion no es inocente:

  min   - imita a `grid_from_points`, que se queda con el retorno de suelo mas
          bajo de cada celda ("Lowest ground return per cell")
  media - lo natural al remuestrear un MDT ya filtrado a suelo

Si las dos se separan del LAZ, el problema es el raster. Si solo se separa una,
el problema era el estadistico y tiene arreglo.

El CRS no se toca: la DGT sirve en EPSG:3763 y el barrido de Portugal ya
trabaja en EPSG:3763.
"""
from __future__ import annotations

import argparse
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import rasterio


def convierte(args_tupla) -> tuple[str, str, int, float]:
    tif, destino_dir, modo, res_obj = args_tupla
    tif = Path(tif)
    dst = Path(destino_dir) / (tif.stem + ".npz")
    if dst.exists():
        return (tif.name, "ya-estaba", 0, 0.0)

    with rasterio.open(tif) as src:
        a = src.read(1).astype(np.float64)
        nod = src.nodata
        b = src.bounds
        res_src = src.res[0]

    if nod is not None:
        a[a == nod] = np.nan
    a[a < -400] = np.nan  # -999 y centinelas parecidos

    factor = int(round(res_obj / res_src))
    if factor < 1:
        return (tif.name, "resolucion-mayor-que-objetivo", 0, 0.0)

    h, w = a.shape
    h2, w2 = (h // factor) * factor, (w // factor) * factor
    a = a[:h2, :w2]
    bloques = a.reshape(h2 // factor, factor, w2 // factor, factor)

    with np.errstate(all="ignore"):
        if modo == "min":
            dem = np.nanmin(bloques, axis=(1, 3))
        else:
            dem = np.nanmean(bloques, axis=(1, 3))

    valida = np.isfinite(dem)
    frac = float(valida.mean())
    if frac < 0.30:
        return (tif.name, f"descartada-huecos-{frac:.2f}", 0, frac)

    # rellenar huecos por vecino mas proximo, igual que la via del LAZ
    if not valida.all():
        from scipy import ndimage
        idx = ndimage.distance_transform_edt(~valida, return_distances=False,
                                             return_indices=True)
        dem = dem[tuple(idx)]

    minx = b.left
    maxy = b.top
    maxx = minx + dem.shape[1] * res_obj
    miny = maxy - dem.shape[0] * res_obj

    dst.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(dst, dem=dem.astype(np.float32), valida=valida,
                        bounds=np.array([minx, miny, maxx, maxy]),
                        res=np.float64(res_obj))
    return (tif.name, "ok", dem.size, frac)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tif-dir", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--modo", choices=("min", "media"), default="min")
    ap.add_argument("--res", type=float, default=1.0)
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()

    tifs = sorted(a.tif_dir.rglob("*.tif"))
    print(f"{len(tifs)} teselas MDT -> {a.out_dir} (modo {a.modo}, {a.res} m)")
    if not tifs:
        return 1
    a.out_dir.mkdir(parents=True, exist_ok=True)

    tareas = [(str(t), str(a.out_dir), a.modo, a.res) for t in tifs]
    ok = ya = mal = 0
    fracs = []
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        futs = [ex.submit(convierte, t) for t in tareas]
        for n, f in enumerate(as_completed(futs), 1):
            nombre, estado, celdas, frac = f.result()
            if estado == "ok":
                ok += 1
                fracs.append(frac)
            elif estado == "ya-estaba":
                ya += 1
            else:
                mal += 1
                print(f"   {estado}: {nombre}")
            if n % 25 == 0:
                print(f"  {n}/{len(tareas)}", flush=True)

    print(f"\nconvertidas {ok} | ya estaban {ya} | descartadas {mal}")
    if fracs:
        print(f"cobertura valida antes de rellenar: mediana {np.median(fracs):.3f} "
              f"| minima {min(fracs):.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
