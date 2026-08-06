#!/usr/bin/env python3
"""Convierte falsos positivos del barrido en viñetas negativas del corpus.

Es el paso que separa este proyecto del mejor resultado publicado. Canedo et al.
pasaron de `5.678` a `40` falsos positivos en **una** iteración haciendo esto, y
`9` de esos `40` residuales resultaron ser castros sin catalogar: **los hallazgos
viven dentro del error, después de la minería.**

Y ataca el defecto de construcción del corpus: el `98,2%` de sus negativos vive a
menos de `5 km` de un castro catalogado, porque el LiDAR se descargó centrado en
positivos. Estos negativos son de terreno **no visto**, y de los dos regímenes
—Lugo rural y la ría de Vigo urbanizada— que es donde está el cuello: la
precisión cae de `0.808` a `0.179` entre uno y otro.

Uso:
    python3 scripts/minar_negativos_duros.py \\
        --fp data/fp_lugo.tsv:data/external/lidar-val-lugo \\
             data/fp_pontevedra.tsv:data/external/lidar-val-pontevedra \\
        --corpus data/galicia-vignettes-v3 --salida data/galicia-vignettes-v4
"""
from __future__ import annotations

import argparse
import csv
import shutil
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_trasancos_vignettes import group_samples_by_tiles, lonlat_to_utm29
from sweep_grid_lidar import cortar_grupo

EXTENT, RES = 512.0, 1.0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fp", nargs="+", required=True,
                    metavar="TSV:LAZDIR")
    ap.add_argument("--corpus", type=Path, required=True)
    ap.add_argument("--salida", type=Path, required=True)
    ap.add_argument("--grupo", default="hard_negative_barrido")
    ap.add_argument("--workers", type=int, default=2)
    args = ap.parse_args()

    args.salida.mkdir(parents=True, exist_ok=True)
    arr_dst = args.salida / "arrays"
    arr_dst.mkdir(exist_ok=True)

    # El corpus original no se toca: se enlaza. Copiar 14.614 viñetas para
    # anadir 123 seria absurdo, y un enlace deja claro que la base es la misma.
    arr_src = args.corpus / "arrays"
    enlazadas = 0
    for p in arr_src.glob("*.npz"):
        d = arr_dst / p.name
        if not d.exists():
            try:
                d.symlink_to(p.resolve())
                enlazadas += 1
            except OSError:
                shutil.copy2(p, d)
                enlazadas += 1
    print("viñetas del corpus base enlazadas: %d" % enlazadas, flush=True)

    filas = list(csv.DictReader(open(args.corpus / "index.tsv", encoding="utf-8"),
                                delimiter="\t"))
    campos = list(filas[0].keys())
    nuevas, n_id = [], 0

    for spec in args.fp:
        tsv, lazdir = spec.rsplit(":", 1)
        pts = [r for r in csv.DictReader(open(tsv, encoding="utf-8"), delimiter="\t")
               if r.get("clase", "FP") == "FP"]
        origen = Path(tsv).stem
        print("\n%s: %d falsos positivos" % (origen, len(pts)), flush=True)
        celdas = []
        for r in pts:
            x, y = lonlat_to_utm29(float(r["lon"]), float(r["lat"]))
            celdas.append({"id": n_id, "x": x, "y": y,
                           "lon": float(r["lon"]), "lat": float(r["lat"])})
            n_id += 1
        tiles = sorted(str(p) for p in Path(lazdir).glob("*.laz"))
        grupos, huerf = group_samples_by_tiles(celdas, tiles, EXTENT)
        print("  con LiDAR: %d | fuera: %d"
              % (sum(len(v) for v in grupos.values()), huerf), flush=True)

        from concurrent.futures import ProcessPoolExecutor, as_completed
        tareas = [(list(k), v, EXTENT, RES, None) for k, v in grupos.items()]
        hechas = 0
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            futs = [ex.submit(cortar_grupo, t) for t in tareas]
            for f in as_completed(futs):
                for cid, lon, lat, arr in f.result():
                    sid = "hn-%s-%04d" % (origen[:12], cid)
                    np.savez_compressed(arr_dst / ("%s.npz" % sid),
                                        x=arr.astype(np.float16))
                    fila = {c: "" for c in campos}
                    fila.update({"sid": sid, "label": "0", "group": args.grupo,
                                 "name": "FP %s" % origen, "lon": lon, "lat": lat,
                                 "block": "minado", "split": "train"})
                    nuevas.append(fila)
                    hechas += 1
        print("  viñetas creadas: %d" % hechas, flush=True)

    with open(args.salida / "index.tsv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=campos, delimiter="\t")
        w.writeheader()
        w.writerows(filas)
        w.writerows(nuevas)
    print("\ncorpus v4: %d viñetas (%d base + %d negativos duros)"
          % (len(filas) + len(nuevas), len(filas), len(nuevas)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
