#!/usr/bin/env python3
"""Descarga la ortofoto PNOA de cada candidato, para mirarla junto al relieve.

Canedo et al. declaran que fusionan relieve y ortofoto **«para replicar el
análisis multi-dato que hace un arqueólogo experto durante la prospección
digital»**. Nosotros veníamos usando solo relieve. La ortofoto no añade
capacidad de ver un castro —bajo eucalipto no se ve nada—; añade capacidad de
**descartar**: una cantera, una rotonda, un depósito de agua, un aparcamiento o
un búnker de costa tienen en relieve la misma firma anular que un parapeto, y en
ortofoto son inconfundibles.

Es decir: la ortofoto automatiza la mitad *negativa* de la revisión humana, que
es justo la mitad que no requiere ser arqueólogo.

Uso:
    python3 scripts/fetch_candidate_orthophotos.py --puntos data/cola_triada_v3.tsv \\
        --out data/revision-visual-v1/orto --lado-m 512
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

WMS = "https://www.ign.es/wms-inspire/pnoa-ma"
CAPA = "OI.OrthoimageCoverage"
UA = "castros-ia/1.0 (investigacion arqueologica)"


def bbox(lon, lat, lado_m):
    dlat = lado_m / 2 / 111320.0
    dlon = lado_m / 2 / (111320.0 * math.cos(math.radians(lat)))
    return lon - dlon, lat - dlat, lon + dlon, lat + dlat


def bajar(args_t):
    i, lon, lat, lado, px, destino = args_t
    if destino.exists() and destino.stat().st_size > 5000:
        return i, "cache"
    x0, y0, x1, y1 = bbox(lon, lat, lado)
    q = urllib.parse.urlencode({
        "SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetMap",
        "LAYERS": CAPA, "STYLES": "", "CRS": "CRS:84",
        "BBOX": "%.8f,%.8f,%.8f,%.8f" % (x0, y0, x1, y1),
        "WIDTH": px, "HEIGHT": px, "FORMAT": "image/png"})
    for intento in range(3):
        try:
            req = urllib.request.Request(WMS + "?" + q, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=90) as r:
                datos = r.read()
            # el WMS devuelve XML de error con HTTP 200: comprobar la firma PNG
            if not datos.startswith(b"\x89PNG"):
                return i, "no-png:" + datos[:60].decode("utf-8", "replace")
            destino.write_bytes(datos)
            return i, "ok"
        except Exception as e:
            if intento == 2:
                return i, "error:" + str(e)[:50]
            time.sleep(3 * (intento + 1))
    return i, "error"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--puntos", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--lado-m", type=float, default=512.0)
    ap.add_argument("--px", type=int, default=512)
    ap.add_argument("--solo-estado", default="CANDIDATO",
                    help="filtra por la columna `estado`; vacío para no filtrar")
    ap.add_argument("--workers", type=int, default=4,
                    help="cortesía con el WMS del IGN, no límite nuestro")
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    filas = list(csv.DictReader(open(args.puntos, encoding="utf-8"), delimiter="\t"))
    if args.solo_estado:
        filas = [r for r in filas if r.get("estado") == args.solo_estado]
    print("puntos: %d" % len(filas), flush=True)

    tareas = [(i, float(r["lon"]), float(r["lat"]), args.lado_m, args.px,
               args.out / ("cand-%02d.png" % i)) for i, r in enumerate(filas)]
    hechos = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(bajar, t) for t in tareas]
        for f in as_completed(futs):
            i, est = f.result()
            hechos += est in ("ok", "cache")
            if not est.startswith(("ok", "cache")):
                print("  cand-%02d: %s" % (i, est), file=sys.stderr)
    print("descargadas %d de %d en %s" % (hechos, len(tareas), args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
