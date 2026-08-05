#!/usr/bin/env python3
"""Descomprime cada tesela LiDAR **una sola vez** y guarda su DEM de 1 m.

## Por qué existe, con la medición delante

Perfilado el `2026-08-06` sobre el barrido de Trasancos:

| etapa | % del tiempo |
|---|---:|
| **descomprimir el `.laz`** | **`87,6%`** |
| rellenar huecos (`distance_transform_edt`) | `7,0%` |
| índices y recortes | `4,3%` |
| **rasterizar (`np.minimum.at`)** | **`1,1%`** |

Y encima se descomprime **`8,4` veces cada tesela**: `5.145` lecturas para `611`
teselas únicas, porque el barrido agrupa celdas por conjunto de teselas y cada
grupo vuelve a abrir las suyas.

Es decir: el barrido pasa el `88%` del tiempo haciendo un trabajo que además
repite ocho veces. No lo arregla OpenMP —descomprimir LAZ es serie por fichero—
ni la GPU —no descomprime LAZ—. Lo arregla **no volver a hacerlo**.

## Lo que cambia

- **`8,4×` de entrada**, sin tocar el modelo ni la GPU.
- Los barridos siguientes salen **casi gratis**: probar otro umbral, otro
  checkpoint o v5 entero ya no cuesta descomprimir Galicia otra vez.
- **El DEM ocupa una fracción del `.laz`.** Trasancos: `39 GB` de LiDAR contra
  ~`2,4 GB` de DEM. Extrapolado a Galicia, `2,1 TB` pasan a ~`120 GB`, que **sí
  caben en el disco**. El ciclo deja de ser «descargar 2 TB» y pasa a ser
  descargar por tandas → convertir → **borrar el `.laz`** → conservar el DEM.

El DEM se guarda con las mismas reglas que usaba el barrido —cota mínima de
retorno de suelo por celda, huecos rellenados por vecino más próximo— para que el
resultado sea idéntico al de leer el `.laz`, no parecido.

Uso:
    python3 scripts/laz_a_dem.py --laz-dir data/external/lidar-trasancos-v1 \\
        --out data/dem-cache-1m --workers 10
"""
from __future__ import annotations

import argparse
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import numpy as np

GROUND = 2


def convertir(t):
    """Una tesela -> un `.npz` con el DEM y su georreferencia."""
    ruta, destino, res, margen = t
    ruta = Path(ruta)
    dst = Path(destino) / (ruta.stem + ".npz")
    if dst.exists() and dst.stat().st_size > 1024:
        return {"tesela": ruta.name, "estado": "cache", "s": 0.0}
    t0 = time.perf_counter()
    try:
        import laspy
        las = laspy.read(str(ruta))
        keep = np.asarray(las.classification) == GROUND
        if keep.sum() < 1000:
            del las
            return {"tesela": ruta.name, "estado": "sin-suelo", "s": 0.0}
        x = np.asarray(las.x)[keep]
        y = np.asarray(las.y)[keep]
        z = np.asarray(las.z)[keep]
        del las

        # El margen extiende el DEM más allá de la tesela para que una ventana a
        # caballo entre dos no encuentre un borde vacío. Se rellena luego con la
        # tesela vecina al montar el mosaico.
        minx = np.floor(x.min()) - margen
        maxx = np.ceil(x.max()) + margen
        miny = np.floor(y.min()) - margen
        maxy = np.ceil(y.max()) + margen
        w = int(round((maxx - minx) / res))
        h = int(round((maxy - miny) / res))
        if w < 8 or h < 8 or w * h > 200_000_000:
            return {"tesela": ruta.name, "estado": "tamaño-raro", "s": 0.0}

        ix = np.clip(((x - minx) / res).astype(np.int64), 0, w - 1)
        iy = np.clip(((maxy - y) / res).astype(np.int64), 0, h - 1)
        dem = np.full(w * h, np.inf, dtype=np.float64)
        np.minimum.at(dem, iy * w + ix, z)
        dem = dem.reshape(h, w)
        valid = np.isfinite(dem)
        # Se guarda la máscara: al montar el mosaico, un hueco de esta tesela
        # puede que lo cubra la vecina, y rellenarlo aquí lo daría por bueno.
        if not valid.all():
            from scipy import ndimage
            try:
                idx = ndimage.distance_transform_edt(
                    ~valid, return_distances=False, return_indices=True)
                dem = dem[tuple(idx)]
            except Exception:
                dem[~valid] = np.median(dem[valid])
        np.savez_compressed(dst, dem=dem.astype(np.float32),
                            valida=valid, bounds=np.array([minx, miny, maxx, maxy]),
                            res=np.float64(res))
        return {"tesela": ruta.name, "estado": "ok", "s": time.perf_counter() - t0,
                "px": int(w * h), "cobertura": float(valid.mean())}
    except Exception as e:
        return {"tesela": ruta.name, "estado": "error:" + str(e)[:60], "s": 0.0}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--laz-dir", type=Path, nargs="+", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--res-m", type=float, default=1.0)
    ap.add_argument("--margen-m", type=float, default=256.0,
                    help="borde extra por tesela; media ventana por defecto")
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 4)
    ap.add_argument("--borrar-laz", action="store_true",
                    help="borra el .laz tras convertirlo. IRREVERSIBLE: solo con "
                         "la descarga por tandas, y nunca sobre la copia única")
    ap.add_argument("--limite", type=int, default=0)
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    teselas = sorted({str(p) for d in args.laz_dir for p in Path(d).glob("*.laz")})
    if args.limite:
        teselas = teselas[:args.limite]
    print("teselas: %d | workers: %d | destino: %s"
          % (len(teselas), args.workers, args.out), flush=True)

    tareas = [(t, str(args.out), args.res_m, args.margen_m) for t in teselas]
    hechas, bytes_laz, bytes_dem, t0 = [], 0, 0, time.time()
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(convertir, t): t[0] for t in tareas}
        for i, f in enumerate(as_completed(futs), 1):
            r = f.result()
            hechas.append(r)
            if r["estado"] in ("ok", "cache"):
                src = Path(futs[f])
                dst = args.out / (src.stem + ".npz")
                if dst.exists():
                    bytes_laz += src.stat().st_size
                    bytes_dem += dst.stat().st_size
                if args.borrar_laz and r["estado"] == "ok" and dst.exists():
                    src.unlink()
            elif r["estado"].startswith("error"):
                print("  %s: %s" % (r["tesela"][:34], r["estado"]), flush=True)
            if i % 25 == 0 or i == len(tareas):
                dt = time.time() - t0
                print("  %d/%d teselas (%.0f s, %.2f s/tesela)"
                      % (i, len(tareas), dt, dt / i), flush=True)

    ok = sum(1 for r in hechas if r["estado"] == "ok")
    cache = sum(1 for r in hechas if r["estado"] == "cache")
    print("\nconvertidas %d | ya en caché %d | otras %d"
          % (ok, cache, len(hechas) - ok - cache))
    if bytes_laz:
        print("tamaño: %.1f GB de .laz -> %.1f GB de DEM (%.1fx menos)"
              % (bytes_laz/1e9, bytes_dem/1e9, bytes_laz/max(bytes_dem, 1)))
    (args.out / "_manifest.json").write_text(json.dumps(
        {"res_m": args.res_m, "margen_m": args.margen_m,
         "teselas": len(teselas), "generado": time.strftime("%Y-%m-%dT%H:%M:%S")},
        indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
