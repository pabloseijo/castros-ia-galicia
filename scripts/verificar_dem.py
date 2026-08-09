#!/usr/bin/env python3
"""¿Da la via del DEM cacheado los mismos canales que la via del LAZ?

**Por que decide el proyecto entero.** Medido el 2026-08-06, el barrido gasta el
**`87,6%`** del tiempo descomprimiendo LAZ, y lo hace **`8,4` veces por tesela**.
La via del DEM lo hace una sola vez y ademas reduce el almacenamiento `72x`
—`73,1 MB` de LAZ contra `1,02 MB` de DEM—, lo que convierte los `2,96 TB` del
barrido de Galicia y el norte de Portugal en `42 GB`, que si caben en el disco.

Pero `--dem-dir` esta desactivado desde entonces: la correlacion de los canales
bajaba a `0.53` en el peor caso por **desalineamiento sub-pixel**. La rejilla del
barrido ya se alineo a metro entero de UTM (`math.floor(x0/res)*res`), y este
guion es el que debia volver a pasarse y **no existia en el repositorio**.

Compara celda a celda: DEM crudo y, sobre todo, los **canales despues de
`channels_from_dem`**, que es lo que ve la red y donde se detecto el problema.

Uso:
    python3 scripts/verificar_dem.py --laz-dir data/external/lidar-val-lugo \\
        --dem-dir data/dem-cache-1m --n 40
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "scripts")
import sweep_grid_lidar as S  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--laz-dir", type=Path, required=True)
    ap.add_argument("--dem-dir", type=Path, required=True)
    ap.add_argument("--n", type=int, default=30, help="celdas a comparar")
    ap.add_argument("--extent", type=float, default=512.0)
    ap.add_argument("--res", type=float, default=1.0)
    ap.add_argument("--checkpoint", type=Path, default=None,
                    help="si se da, compara ademas las PUNTUACIONES del modelo")
    args = ap.parse_args()

    demf = sorted(args.dem_dir.glob("*.npz"))
    if not demf:
        print("no hay DEM cacheados"); return 1

    # celdas centradas en teselas que existan por las DOS vias
    celdas, dems_usados, lazs_usados = [], [], []
    for d in demf:
        laz = args.laz_dir / (d.stem + ".laz")
        if not laz.exists():
            continue
        z = np.load(d)
        minx, miny, maxx, maxy = [float(v) for v in z["bounds"]]
        # centro de la tesela, alineado a metro entero como hace el barrido
        cx = float(math.floor(((minx + maxx) / 2) / args.res) * args.res)
        cy = float(math.floor(((miny + maxy) / 2) / args.res) * args.res)
        # las celdas del barrido llevan id/lon/lat ademas de x/y; las funciones
        # de corte los reemiten tal cual, asi que hay que darselos
        celdas.append({"x": cx, "y": cy, "id": d.stem, "lon": 0.0, "lat": 0.0})
        dems_usados.append(d)
        lazs_usados.append(laz)
        if len(celdas) >= args.n:
            break
    if not celdas:
        print("ninguna tesela tiene las dos vias"); return 1
    print(f"comparando {len(celdas)} celdas presentes en LAZ y en DEM\n")

    cors_dem, cors_canal, difs = [], [], []
    arrs_dem, arrs_laz = [], []
    for c, d, lz in zip(celdas, dems_usados, lazs_usados):
        a = S.cortar_desde_dem(([d], [c], args.extent, args.res))
        b = S.cortar_grupo(([lz], [c], args.extent, args.res))
        if not a or not b:
            continue
        # cada salida es (id, lon, lat, arr): el array es el ultimo elemento
        ca = np.asarray(a[0][-1], dtype=np.float32)
        cb = np.asarray(b[0][-1], dtype=np.float32)
        if ca.shape != cb.shape:
            print(f"  formas distintas: {ca.shape} vs {cb.shape}")
            continue
        m = np.isfinite(ca) & np.isfinite(cb)
        if m.sum() < 1000:
            continue
        cors_canal.append(float(np.corrcoef(ca[m].ravel(), cb[m].ravel())[0, 1]))
        difs.append(float(np.nanmean(np.abs(ca[m] - cb[m]))))
        arrs_dem.append(np.nan_to_num(ca, nan=0.0))
        arrs_laz.append(np.nan_to_num(cb, nan=0.0))

    if not cors_canal:
        print("no se pudo comparar ninguna celda"); return 1

    # ## Lo que de verdad decide: ¿puntua el MODELO distinto?
    #
    # Que los canales difieran un `2%` no dice nada por si solo. La pregunta de
    # despliegue es si el modelo cambia de opinion, y esa se responde puntuando
    # las mismas celdas por las dos vias y mirando la correlacion de puntuaciones
    # y el solape de las mejores. Si el modelo no se entera, la via del DEM vale
    # y con ella se ahorra el `87,6%` del tiempo y `72x` de disco.
    if args.checkpoint and args.checkpoint.exists():
        import torch
        dev = "cuda" if torch.cuda.is_available() else "cpu"
        st = torch.load(args.checkpoint, map_location=dev, weights_only=False)
        a_ = st.get("args", {})
        from train_unet_multiclass import UNetMulticlass
        modelo = UNetMulticlass(n_classes=3, encoder=a_.get("encoder", "resnet34"),
                                head=a_.get("head", "cls"), pretrained=False,
                                in_ch=3).to(dev)
        modelo.load_state_dict(st["model"]); modelo.eval()

        def puntuar(arrs):
            out = []
            with torch.no_grad():
                for i in range(0, len(arrs), 8):
                    b = torch.from_numpy(np.stack(arrs[i:i+8])).to(dev)
                    o = modelo(b)
                    lg = o[0] if isinstance(o, (tuple, list)) else o
                    pr = torch.softmax(lg, 1)[:, 1:].sum(1)   # castro + mamoa
                    out.extend(pr.cpu().numpy().tolist())
            return np.array(out)

        sa, sb = puntuar(arrs_dem), puntuar(arrs_laz)
        r = float(np.corrcoef(sa, sb)[0, 1])
        dmax = float(np.abs(sa - sb).max())
        k = max(1, len(sa) // 4)
        top_a = set(np.argsort(-sa)[:k]); top_b = set(np.argsort(-sb)[:k])
        solape = len(top_a & top_b) / k
        print(f"\n    PUNTUACIONES del modelo por las dos vias")
        print(f"    correlacion {r:.4f} | diferencia maxima {dmax:.4f} | "
              f"solape del cuartil alto {solape:.0%}")
        if r >= 0.995 and dmax < 0.05:
            print("    -> el modelo NO se entera de la diferencia: la via del DEM sirve")
        else:
            print("    -> el modelo SI cambia de opinion: no activar --dem-dir")
    cc = np.array(cors_canal)
    print(f"{'':4}{'correlacion de los CANALES (lo que ve la red)':<48}")
    print(f"    min {cc.min():.4f} | mediana {np.median(cc):.4f} | media {cc.mean():.4f}")
    print(f"    celdas por debajo de 0.99: {(cc < 0.99).sum()} de {len(cc)}")
    print(f"    diferencia absoluta media: {np.mean(difs):.4f}")
    print()
    if cc.min() >= 0.99:
        print("  VEREDICTO: las dos vias coinciden. --dem-dir se puede activar.")
        return 0
    print(f"  VEREDICTO: NO coinciden (peor caso {cc.min():.4f}).")
    print("  Referencia del 2026-08-06, antes de alinear: peor caso 0.53.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
