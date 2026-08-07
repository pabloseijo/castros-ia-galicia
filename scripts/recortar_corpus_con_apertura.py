#!/usr/bin/env python3
"""Re-corta un corpus existente añadiéndole el canal de apertura, sin tocar nada más.

**Por qué existe.** El `2026-08-07` se intentó construir v8 —«v7 más el cuarto
canal»— relanzando `build_trasancos_vignettes.py` con `--con-apertura`. Salieron
`3.458` viñetas contra las `15.311` de v7, y con la composición cambiada: `1.178`
castros contra `960`, `900` mámoas contra `426`, y **cero `random_terrain`**
contra `10.742`.

La causa es que **v7 nunca se construyó de cero**. Es `v6` más los negativos
duros que le añadió `minar_negativos_duros.py`, y `v6` viene de `v5`, y así hacia
atrás: el corpus base con el terreno aleatorio se cortó varias versiones antes,
con `--extra-negatives`. Reconstruir desde `load_samples()` **no reproduce v7**,
produce otro corpus distinto.

Y si el corpus cambia a la vez que el canal, la comparación v7 contra v8 deja de
medir el canal. Que era el único objeto del experimento.

**Lo que hace este script.** Lee el `index.tsv` del corpus de partida y vuelve a
cortar **esas mismas viñetas** —mismo `sid`, mismo grupo, mismo `split`, mismas
coordenadas— con el canal de apertura añadido. El conjunto de muestras es
idéntico por construcción, no por suerte, así que la única variable que cambia
entre los dos corpus es el número de canales.

**Por qué no se calcula la apertura sobre el array ya guardado**, que costaría
minutos en vez de horas: el `.npz` guarda el MDT **normalizado a `[0,1]` por
viñeta** y no guarda la escala. La apertura es una medida angular —depende de
`Δz` en metros contra distancia horizontal—, así que sobre el array normalizado
una viñeta con `200 m` de desnivel y otra con `5 m` darían lo mismo. El canal
dejaría de significar lo que dice Doneus (`10.3390/rs5126427`), que es
precisamente el argumento físico que justifica el experimento.

Es reanudable: `process_group` salta toda viñeta cuyo `.npz` ya exista, y ni
abre los LAZ del grupo si está entero.

Uso:
    python3 scripts/recortar_corpus_con_apertura.py \\
        --origen data/galicia-vignettes-v7 --destino data/galicia-vignettes-v8 \\
        --laz-dir data/external/lidar-positives-v1 data/external/lidar-val-lugo ... \\
        --workers 3
"""
from __future__ import annotations

import argparse
import csv
import shutil
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "scripts"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--origen", type=Path, required=True)
    ap.add_argument("--destino", type=Path, required=True)
    ap.add_argument("--laz-dir", type=Path, nargs="+", required=True)
    ap.add_argument("--extent-m", type=float, default=512.0)
    ap.add_argument("--res-m", type=float, default=1.0)
    ap.add_argument("--workers", type=int, default=3)
    args = ap.parse_args()

    from build_trasancos_vignettes import (group_samples_by_tiles,
                                           lonlat_to_utm29, process_group)

    idx = args.origen / "index.tsv"
    filas = list(csv.DictReader(open(idx, encoding="utf-8"), delimiter="\t"))
    print(f"corpus de partida: {len(filas)} viñetas en {idx}", flush=True)

    arr = args.destino / "arrays"
    arr.mkdir(parents=True, exist_ok=True)

    muestras = []
    for r in filas:
        try:
            x, y = lonlat_to_utm29(float(r["lon"]), float(r["lat"]))
        except (KeyError, TypeError, ValueError):
            continue
        muestras.append({"sid": r["sid"], "x": x, "y": y,
                         "label": int(r["label"])})
    print(f"muestras con coordenada válida: {len(muestras)}", flush=True)

    ya = sum(1 for m in muestras if (arr / f"{m['sid']}.npz").exists())
    print(f"ya cortadas de antes: {ya} | pendientes: {len(muestras)-ya}",
          flush=True)

    teselas = sorted(str(p) for d in args.laz_dir for p in Path(d).glob("*.laz"))
    print(f"teselas LAZ: {len(teselas)}", flush=True)
    # `group_samples_by_tiles` devuelve el numero de huerfanas, no la lista.
    grupos, n_huerfanas = group_samples_by_tiles(muestras, teselas,
                                                 args.extent_m)
    print(f"grupos de teselas: {len(grupos)} | sin cobertura LiDAR: "
          f"{n_huerfanas}", flush=True)

    tareas = [(tp, ss, args.extent_m, args.res_m, str(arr), True)
              for tp, ss in grupos.items()]
    # Los grupos grandes primero: asi los ultimos en terminar son los baratos y
    # no queda un obrero solo masticando el grupo gordo al final.
    tareas.sort(key=lambda t: -len(t[1]))

    escritas, vistas, t0 = 0, 0, time.time()
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        for i, (w, n) in enumerate(ex.map(process_group, tareas), 1):
            escritas += w
            vistas += n
            if i % 20 == 0 or i == len(tareas):
                dt = time.time() - t0
                print(f"  grupo {i}/{len(tareas)} | viñetas {escritas} | "
                      f"{dt/60:.0f} min", flush=True)

    # El indice se copia TAL CUAL, filtrando solo lo que no llego a cortarse.
    # Copiarlo es lo que garantiza que `split`, grupo y nombre son los mismos:
    # regenerarlos volveria a abrir la puerta a que el reparto cambiara.
    salida = args.destino / "index.tsv"
    with open(salida, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0].keys()), delimiter="\t")
        w.writeheader()
        n = 0
        for r in filas:
            if (arr / f"{r['sid']}.npz").exists():
                w.writerow(r); n += 1
    print(f"\nescrito {salida}: {n} de {len(filas)} viñetas del original")
    if n < len(filas):
        print(f"  ({len(filas)-n} sin cortar: sin cobertura LiDAR o con menos "
              f"de 2.000 puntos de suelo)")
    for extra in ("splits.json", "README.md"):
        f = args.origen / extra
        if f.exists():
            shutil.copy2(f, args.destino / extra)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
