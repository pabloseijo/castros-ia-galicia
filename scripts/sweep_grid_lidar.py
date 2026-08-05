#!/usr/bin/env python3
"""Barrido ciego sobre una rejilla, cortando del LiDAR y puntuando con la red.

Es la pieza que faltaba entre el modelo entrenado y `detection_eval.py`. Todo lo
medido hasta ahora en este proyecto se mide sobre **viñetas centradas en el
yacimiento**, lo que responde «¿sabe ordenar candidatos ya localizados?» y no
«¿sabe encontrarlos?». La distinción no es teórica: el ranker anterior tenía
`0.944` de AUC sobre holdouts y recuperó **el `18%`** en barrido ciego, porque
sus features eran concéntricas respecto al centro del recorte.

Dos decisiones vienen de la literatura, no de la intuición:

- **Paso de media ventana** (`50%` de solape). Landauer lo fijó empíricamente y
  Canedo lo justifica: garantiza que un sitio hipotético se vea **entero al menos
  una vez**. Es `4x` celdas, no el `16x` que costaría un solape del `75%`.
- **No se guardan las viñetas.** Un barrido de Trasancos a paso `256 m` son
  ~`11.000` recortes de `512x512x3`; escribirlos serían decenas de GB que solo
  se leen una vez. Se cortan, se puntúan y se tiran, y lo que se guarda es el
  TSV de coordenadas y puntuación, que pesa nada.

La salida alimenta directamente a `detection_eval.py`, que agrupa, filtra y
reporta F1 con tolerancia de distancia y VPP a la tasa base real.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
           "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_trasancos_vignettes import (channels_from_dem,  # noqa: E402
                                       grid_from_points, group_samples_by_tiles,
                                       laz_bounds, lonlat_to_utm29)

GROUND_CLASS = 2


def cortar_grupo(args_tuple):
    """Corta todas las celdas de un grupo que comparte teselas. Devuelve arrays."""
    tile_paths, celdas, extent, res = args_tuple
    import laspy
    half = extent / 2.0

    # Recuadro que de verdad hace falta: la union de las celdas del grupo.
    # Sin esto se cargaban los puntos de hasta cuatro teselas enteras en float64,
    # y con varios obreros a la vez el OOM killer se llevo el barrido dos veces
    # el 2026-08-05, la segunda ya con solo tres obreros. Filtrar al leer y
    # guardar en float32 es la diferencia entre caber y no caber en 8 GB.
    ux0 = min(c["x"] for c in celdas) - half
    ux1 = max(c["x"] for c in celdas) + half
    uy0 = min(c["y"] for c in celdas) - half
    uy1 = max(c["y"] for c in celdas) + half

    xs_l, ys_l, zs_l = [], [], []
    for tp in tile_paths:
        las = laspy.read(tp)
        keep = np.asarray(las.classification) == GROUND_CLASS
        if not keep.any():
            del las
            continue
        x = np.asarray(las.x)[keep]
        y = np.asarray(las.y)[keep]
        z = np.asarray(las.z)[keep]
        del las
        dentro = (x >= ux0) & (x <= ux1) & (y >= uy0) & (y <= uy1)
        if not dentro.any():
            continue
        xs_l.append(x[dentro].astype(np.float32))
        ys_l.append(y[dentro].astype(np.float32))
        zs_l.append(z[dentro].astype(np.float32))
        del x, y, z
    if not xs_l:
        return []
    xs = np.concatenate(xs_l); del xs_l
    ys = np.concatenate(ys_l); del ys_l
    zs = np.concatenate(zs_l); del zs_l

    salida = []
    for c in celdas:
        b = (c["x"] - half, c["y"] - half, c["x"] + half, c["y"] + half)
        m = (xs >= b[0]) & (xs <= b[2]) & (ys >= b[1]) & (ys <= b[3])
        if m.sum() < 2000:
            continue
        dem = grid_from_points(xs[m], ys[m], zs[m], b, res)
        if dem is None:
            continue
        arr = channels_from_dem(dem, res).astype(np.float16)
        salida.append((c["id"], c["lon"], c["lat"], arr))
    return salida


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--laz-dir", type=Path, nargs="+", required=True)
    ap.add_argument("--checkpoint", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--bbox", type=float, nargs=4, required=True,
                    metavar=("W", "S", "E", "N"))
    ap.add_argument("--extent-m", type=float, default=512.0)
    ap.add_argument("--step-m", type=float, default=None,
                    help="por defecto media ventana, como Landauer y Canedo")
    ap.add_argument("--res-m", type=float, default=1.0)
    ap.add_argument("--workers", type=int, default=4,
                    help="lo limita la RAM por obrero, no el numero de hilos")
    ap.add_argument("--batch", type=int, default=16)
    args = ap.parse_args()
    step = args.step_m or args.extent_m / 2.0

    import torch
    from train_unet_multiclass import UNetMulticlass

    # --- rejilla ---
    w, s, e, n = args.bbox
    x0, y0 = lonlat_to_utm29(w, s)
    x1, y1 = lonlat_to_utm29(e, n)
    from pyproj import Transformer
    inv = Transformer.from_crs("EPSG:25829", "EPSG:4326", always_xy=True)
    celdas = []
    yy = y0
    while yy <= y1:
        xx = x0
        while xx <= x1:
            lon, lat = inv.transform(xx, yy)
            celdas.append({"id": len(celdas), "x": xx, "y": yy,
                           "lon": lon, "lat": lat})
            xx += step
        yy += step
    print(f"rejilla: {len(celdas)} celdas de {args.extent_m:.0f} m "
          f"con paso {step:.0f} m ({100*(1-step/args.extent_m):.0f}% de solape)",
          flush=True)

    tiles = sorted({str(p) for d in args.laz_dir for p in Path(d).glob("*.laz")})
    grupos, huerfanas = group_samples_by_tiles(celdas, tiles, args.extent_m)
    cubiertas = sum(len(v) for v in grupos.values())
    print(f"teselas: {len(tiles)} | celdas con LiDAR: {cubiertas} | "
          f"fuera de cobertura: {huerfanas}", flush=True)

    # --- modelo ---
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    st = torch.load(args.checkpoint, map_location=dev, weights_only=False)
    cfg = st.get("args", {})
    modelo = UNetMulticlass(3, cfg.get("encoder", "resnet34"),
                            cfg.get("head", "cls"), pretrained=False).to(dev)
    modelo.load_state_dict(st["model"])
    modelo.eval()
    print(f"modelo: cabeza {cfg.get('head')} | epoca {st.get('epoch', -1)+1} "
          f"| dispositivo {dev}", flush=True)

    # --- reanudacion: no recortar lo ya puntuado ---
    hechas = set()
    if args.out.exists():
        with open(args.out, encoding="utf-8") as fh:
            for r in csv.DictReader(fh, delimiter="\t"):
                hechas.add(int(r["id"]))
        print(f"reanudando: {len(hechas)} celdas ya puntuadas", flush=True)

    tareas = []
    for k, v in grupos.items():
        pend = [c for c in v if c["id"] not in hechas]
        if pend:
            tareas.append((list(k), pend, args.extent_m, args.res_m))

    nuevo = not args.out.exists()
    fh = open(args.out, "a", newline="", encoding="utf-8")
    wr = csv.writer(fh, delimiter="\t")
    if nuevo:
        wr.writerow(["id", "lon", "lat", "score", "p_fondo", "p_castro", "p_mamoa"])

    t0, hechos = time.time(), 0
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(cortar_grupo, t) for t in tareas]
        lote_meta, lote_arr = [], []

        def vaciar():
            nonlocal lote_meta, lote_arr, hechos
            if not lote_arr:
                return
            x = torch.from_numpy(
                (np.stack(lote_arr).astype(np.float32) - 0.5) / 0.5).to(dev)
            with torch.no_grad(), torch.autocast("cuda", enabled=(dev == "cuda")):
                logits, _ = modelo(x)
            p = torch.softmax(logits.float(), 1).cpu().numpy()
            for (cid, lon, lat), pr in zip(lote_meta, p):
                wr.writerow([cid, f"{lon:.6f}", f"{lat:.6f}", f"{pr[1]:.6f}",
                             f"{pr[0]:.6f}", f"{pr[1]:.6f}", f"{pr[2]:.6f}"])
            hechos += len(lote_meta)
            fh.flush()
            lote_meta, lote_arr = [], []

        for i, f in enumerate(as_completed(futs), 1):
            for cid, lon, lat, arr in f.result():
                lote_meta.append((cid, lon, lat))
                lote_arr.append(arr)
                if len(lote_arr) >= args.batch:
                    vaciar()
            if i % 25 == 0 or i == len(tareas):
                print(f"  {i}/{len(tareas)} grupos, {hechos} celdas puntuadas "
                      f"({time.time()-t0:.0f}s)", flush=True)
        vaciar()
    fh.close()
    print(f"\nlisto: {hechos} celdas nuevas en {args.out}", flush=True)
    print("siguiente: scripts/detection_eval.py --pred "
          f"{args.out} --truth <castros.tsv>", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
