#!/usr/bin/env python3
"""Barre un territorio grande sin llegar a tenerlo entero en disco.

Existe por una cuenta hecha el `2026-08-07`. Con las constantes medidas del
proyecto —`64 MB` por tesela de `1 km²`, `290` teselas/hora del CNIG, `2,37`
celdas/s de barrido— Galicia entera son **`1.848 GB`**, y `oval-server` tiene
`914 GB` de disco **total**. Con el flujo de siempre —bajarlo todo y después
barrer— el techo está en **una provincia y a duras penas**: A Coruña dejaría
`110 GB` libres y Lugo directamente no cabe.

Así que el disco no puede escalar con el área. Tiene que escalar con el
**conjunto de trabajo**, y eso es lo que hace este script: recorre el
territorio por bloques, y de cada bloque baja sus teselas, lo barre, guarda las
puntuaciones —que pesan nada— y **borra los `.laz`** antes de pasar al
siguiente.

Es el patrón del programa Lidar HD del IGN francés, que procesa `3` petabytes
sobre `550.000 km²` **secuenciando en bloques de `50×50 km`** en vez de tratar
el país como un solo lote. La diferencia de escala no cambia la forma.

## Las dos cosas que hay que hacer bien, o sale mal en silencio

**El halo.** Una celda del barrido mira `512 m` a su alrededor, así que las
celdas del borde de un bloque necesitan teselas del bloque de al lado. Sin
halo, `grid_from_points` recibe una ventana medio vacía, `cortar_grupo` la
descarta por debajo del `30%` de cobertura y **el resultado es una rejilla con
costuras sin barrer que ninguna métrica delata** — el mismo fallo que ya costó
tres barridos dados por buenos al `59%`, `74%` y `76%`.

**No borrar lo que hace falta luego.** Se recorre en orden de filas y se
conserva lo que pide el bloque siguiente, así que una tesela compartida se baja
una vez y no dos. Con bloques de `25 km` el rehecho queda en torno al `15%`.

## Por qué un TSV por bloque y no uno solo

`sweep_grid_lidar.py` numera las celdas por su posición dentro de la rejilla de
**esa** invocación. Dos bloques distintos reutilizarían los mismos `id`, y su
propia reanudación —que salta los `id` ya escritos— se saltaría celdas de otro
bloque sin avisar. Cada bloque escribe el suyo y se juntan al final;
`detection_eval.py` solo lee `lon`, `lat` y `score`, así que el `id` no hace
falta para nada aguas abajo.

Uso:
    python3 scripts/barrer_streaming.py --bbox -8.9 42.8 -8.0 43.4 \\
        --checkpoint data/cls-v6-focal/best.pt --nombre coruna-prov \\
        --bloque-km 25
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))

TESELA_M = 1000.0
HALO_M = 600.0        # ventana de 512 m -> 256 m de radio, con margen


def utm(lon, lat):
    from pyproj import Transformer
    return Transformer.from_crs("EPSG:4326", "EPSG:25829",
                                always_xy=True).transform(lon, lat)


def a_lonlat(x, y):
    from pyproj import Transformer
    return Transformer.from_crs("EPSG:25829", "EPSG:4326",
                                always_xy=True).transform(x, y)


def teselas_de(x0, y0, x1, y1):
    """Identificadores `x-y` en km de las teselas que cubren un recuadro UTM."""
    out = set()
    tx = math.floor(x0 / TESELA_M) * TESELA_M
    while tx < x1:
        ty = math.floor(y0 / TESELA_M) * TESELA_M
        while ty < y1:
            out.add((int(tx / 1000), int(ty / 1000)))
            ty += TESELA_M
        tx += TESELA_M
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bbox", type=float, nargs=4, required=True,
                    metavar=("W", "S", "E", "N"))
    ap.add_argument("--checkpoint", type=Path, required=True)
    ap.add_argument("--nombre", required=True, help="etiqueta de la salida")
    ap.add_argument("--bloque-km", type=float, default=25.0)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--min-libre-gb", type=float, default=80.0,
                    help="aborta si el disco baja de aquí")
    ap.add_argument("--solo-plan", action="store_true",
                    help="dice cuántos bloques y cuánto disco, y no baja nada")
    args = ap.parse_args()

    trabajo = RAIZ / "data" / f"streaming-{args.nombre}"
    laz_dir = trabajo / "laz"
    salidas = trabajo / "bloques"
    for d in (laz_dir, salidas):
        d.mkdir(parents=True, exist_ok=True)
    estado = trabajo / "bloques_hechos.json"
    hechos = set(json.loads(estado.read_text())) if estado.exists() else set()

    w, s, e, n = args.bbox
    x0, y0 = utm(w, s)
    x1, y1 = utm(e, n)
    paso = args.bloque_km * 1000.0
    bloques = []
    by = math.floor(y0 / paso) * paso
    while by < y1:
        bx = math.floor(x0 / paso) * paso
        while bx < x1:
            bloques.append((bx, by, min(bx + paso, x1), min(by + paso, y1)))
            bx += paso
        by += paso
    # Orden de filas: dos bloques seguidos comparten borde, y asi lo que pide el
    # siguiente no se borra para volver a bajarlo.
    bloques.sort(key=lambda b: (b[1], b[0]))

    necesita = [teselas_de(b[0] - HALO_M, b[1] - HALO_M,
                           b[2] + HALO_M, b[3] + HALO_M) for b in bloques]
    todas = set().union(*necesita) if necesita else set()
    print(f"territorio: {len(bloques)} bloques de {args.bloque_km:.0f} km | "
          f"{len(todas)} teselas únicas (~{len(todas)*64/1024:.0f} GB si se "
          f"bajaran todas)", flush=True)
    pico = max((len(t) for t in necesita), default=0)
    print(f"pico de disco con streaming: ~{pico*64/1024:.1f} GB "
          f"(el bloque mayor)", flush=True)
    rehecho = sum(len(t) for t in necesita) - len(todas)
    print(f"teselas rebajadas por solape de halo: {rehecho} "
          f"({100*rehecho/max(len(todas),1):.0f}% de más)", flush=True)
    if hechos:
        print(f"reanudando: {len(hechos)} bloques ya hechos", flush=True)
    if args.solo_plan:
        return 0

    py = str(RAIZ / ".venv-gpu/bin/python")
    if not Path(py).exists():
        py = sys.executable

    t_ini = time.time()
    for i, (bx, by, bx1, by1) in enumerate(bloques):
        clave = f"{int(bx/1000)}-{int(by/1000)}"
        if clave in hechos:
            continue
        libre = shutil.disk_usage(trabajo).free / 1e9
        if libre < args.min_libre_gb:
            print(f"ABORTA: quedan {libre:.0f} GB, por debajo de "
                  f"{args.min_libre_gb:.0f}", flush=True)
            return 1

        lo0, la0 = a_lonlat(bx - HALO_M, by - HALO_M)
        lo1, la1 = a_lonlat(bx1 + HALO_M, by1 + HALO_M)
        print(f"\n=== bloque {i+1}/{len(bloques)} [{clave}] "
              f"({time.time()-t_ini:.0f}s) ===", flush=True)

        # 1. bajar el bloque con su halo. El descargador ya es reanudable y no
        #    vuelve a pedir lo que esta en disco.
        r = subprocess.run(
            [py, str(RAIZ / "scripts/download_trasancos_lidar.py"),
             "--out-dir", str(trabajo), "--laz-dir", str(laz_dir),
             "--bbox", f"{lo0}", f"{la0}", f"{lo1}", f"{la1}",
             "--min-free-gb", str(args.min_libre_gb / 2)],
            capture_output=True, text=True)
        if r.returncode != 0:
            print(f"  descarga rc={r.returncode}: {r.stdout[-400:]}", flush=True)
            continue

        # 2. barrer SOLO el bloque; el halo esta en disco para que las celdas
        #    del borde vean su ventana entera.
        lo0b, la0b = a_lonlat(bx, by)
        lo1b, la1b = a_lonlat(bx1, by1)
        out = salidas / f"bloque_{clave}.tsv"
        r = subprocess.run(
            [py, str(RAIZ / "scripts/sweep_grid_lidar.py"),
             "--laz-dir", str(laz_dir), "--checkpoint", str(args.checkpoint),
             "--out", str(out),
             "--bbox", f"{lo0b}", f"{la0b}", f"{lo1b}", f"{la1b}",
             "--workers", str(args.workers), "--batch", str(args.batch)],
            capture_output=True, text=True)
        if r.returncode != 0:
            print(f"  BARRIDO rc={r.returncode}: {r.stdout[-600:]}", flush=True)
            continue
        for linea in r.stdout.strip().splitlines()[-2:]:
            print(f"  {linea}", flush=True)

        hechos.add(clave)
        estado.write_text(json.dumps(sorted(hechos)))

        # 3. soltar lo que ya no hace falta. Se conserva lo del bloque
        #    siguiente, que comparte borde con este.
        futuras = set().union(*necesita[i+1:]) if i + 1 < len(necesita) else set()
        borradas = 0
        for f in laz_dir.glob("*.laz"):
            p = f.stem.split("-")
            try:
                tid = (int(p[3]), int(p[4]))
            except (IndexError, ValueError):
                continue
            if tid not in futuras:
                f.unlink()
                borradas += 1
        print(f"  liberadas {borradas} teselas | disco libre "
              f"{shutil.disk_usage(trabajo).free/1e9:.0f} GB", flush=True)

    # 4. juntar. `detection_eval.py` solo mira lon, lat y score.
    final = RAIZ / "data" / f"sweep_streaming_{args.nombre}.tsv"
    n = 0
    with open(final, "w", newline="", encoding="utf-8") as fh:
        wr = csv.writer(fh, delimiter="\t")
        wr.writerow(["id", "lon", "lat", "score", "p_fondo", "p_castro", "p_mamoa"])
        for f in sorted(salidas.glob("bloque_*.tsv")):
            with open(f, encoding="utf-8") as g:
                for r in csv.DictReader(g, delimiter="\t"):
                    wr.writerow([n, r["lon"], r["lat"], r["score"],
                                 r.get("p_fondo", ""), r.get("p_castro", ""),
                                 r.get("p_mamoa", "")])
                    n += 1
    print(f"\nlisto: {n} celdas en {final}", flush=True)
    print(f"quedan {len(bloques)-len(hechos)} bloques sin hacer", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
