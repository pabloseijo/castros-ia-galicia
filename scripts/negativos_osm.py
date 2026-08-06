#!/usr/bin/env python3
"""Fabrica negativos duros de obra moderna, en masa, desde OpenStreetMap.

El corpus tiene un defecto de construcción: **el `98,2%` de sus negativos vive a
menos de `5 km` de un castro catalogado**, porque el LiDAR se descargó centrado
en positivos. El modelo nunca vio un polígono industrial ni una cantera, y eso se
paga exactamente donde se ha medido: la precisión cae de `0.808` en el interior
rural de Lugo a `0.179` en la ría de Vigo, con el recall intacto.

La minería a partir de falsos positivos del barrido da `107` ejemplos y exige
barrer primero. Esto da **miles y no exige barrer nada**: la obra moderna está
mapeada, así que se puede ir a buscarla en lugar de esperar a tropezarse con
ella. Es la diferencia entre recoger errores y fabricar el negativo a propósito.

Qué se extrae, y por qué cada cosa: todas tienen firma de relieve que se parece a
un parapeto o a un recinto.

- **canteras y minas**: bancos y terraplenes anulares.
- **polígonos y naves**: plataformas rectangulares aterrazadas.
- **campos de fútbol y polideportivos**: en el barrido de Pontevedra aparecieron
  en `10` de `78` falsos positivos y en solo `1` de `17` castros — es el confusor
  con mejor relación de todos los medidos.
- **embalses, presas, depósitos, EDAR**: diques y cubetas.
- **enlaces de autovía**: un lazo de rotonda **cierra en los doce sectores** y
  tiene terraplén de varios metros. Fue el candidato con mejor puntuación
  morfológica de Trasancos.

Uso:
    python3 scripts/negativos_osm.py --laz-dir data/external/lidar-val-lugo \\
        --out data/negativos-osm-lugo.tsv --max 1500
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_trasancos_vignettes import laz_bounds

UA = "castros-ia (investigacion arqueologica)"
ESPEJOS = ("https://overpass-api.de/api/interpreter",
           "https://overpass.kumi.systems/api/interpreter",
           "https://overpass.osm.jp/api/interpreter")

# Cada consulta es una familia de confusores con su firma de relieve.
FAMILIAS = {
    "cantera":      '["landuse"="quarry"]',
    "mina":         '["man_made"="mineshaft"]',
    "industrial":   '["landuse"="industrial"]',
    "deportivo":    '["leisure"~"pitch|sports_centre|stadium|golf_course"]',
    "embalse":      '["natural"="water"]["water"="reservoir"]',
    "presa":        '["waterway"="dam"]',
    "deposito":     '["man_made"~"storage_tank|water_tower|silo|wastewater_plant"]',
    "vertedero":    '["landuse"="landfill"]',
    "enlace_via":   '["highway"="motorway_junction"]',
    "obra":         '["landuse"="construction"]',
}


def overpass(consulta, intentos=6):
    for i in range(intentos):
        url = ESPEJOS[i % len(ESPEJOS)]
        try:
            req = urllib.request.Request(
                url, data=urllib.parse.urlencode({"data": consulta}).encode(),
                headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=240) as r:
                return json.load(r)
        except Exception as e:
            print("    %s: %s" % (url.split("/")[2][:22], str(e)[:44]),
                  file=sys.stderr, flush=True)
            time.sleep(10 * (i + 1))
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--laz-dir", type=Path, nargs="+", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--max", type=int, default=2000)
    ap.add_argument("--separacion-m", type=float, default=300.0,
                    help="mínima entre negativos, para no repetir el mismo sitio")
    args = ap.parse_args()

    # Recuadro de lo que hay con LiDAR: no sirve un negativo sin datos.
    from pyproj import Transformer
    inv = Transformer.from_crs("EPSG:25829", "EPSG:4326", always_xy=True)
    xs, ys = [], []
    for d in args.laz_dir:
        for p in Path(d).glob("*.laz"):
            try:
                b = laz_bounds(str(p))
                xs += [b[0], b[2]]; ys += [b[1], b[3]]
            except Exception:
                continue
    if not xs:
        raise SystemExit("sin teselas: nada que acotar")
    w, s = inv.transform(min(xs), min(ys))
    e, n = inv.transform(max(xs), max(ys))
    print("recuadro con LiDAR: %.4f %.4f %.4f %.4f" % (w, s, e, n), flush=True)

    filas = []
    for nombre, filtro in FAMILIAS.items():
        q = ('[out:json][timeout:240];('
             'nwr%s(%.5f,%.5f,%.5f,%.5f););out center 400;'
             % (filtro, s, w, n, e))
        d = overpass(q)
        if not d:
            print("  %-12s sin respuesta" % nombre, flush=True)
            continue
        k = 0
        for el in d.get("elements", []):
            c = el.get("center") or el
            if c.get("lat") is None:
                continue
            filas.append({"lon": round(float(c["lon"]), 6),
                          "lat": round(float(c["lat"]), 6),
                          "familia": nombre, "clase": "FP"})
            k += 1
        print("  %-12s %d" % (nombre, k), flush=True)
        time.sleep(4)

    # Separar: dos naves contiguas son el mismo negativo para una ventana de 512 m.
    filas.sort(key=lambda r: r["familia"])
    guardadas = []
    for r in filas:
        if all(math.hypot((r["lat"]-g["lat"])*111320,
                          (r["lon"]-g["lon"])*111320*math.cos(math.radians(r["lat"])))
               > args.separacion_m for g in guardadas):
            guardadas.append(r)
        if len(guardadas) >= args.max:
            break

    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=["lon", "lat", "familia", "clase"],
                            delimiter="\t")
        wr.writeheader(); wr.writerows(guardadas)
    from collections import Counter
    print("\n%d negativos tras separar a %.0f m (de %d brutos)"
          % (len(guardadas), args.separacion_m, len(filas)))
    print("  por familia: %s" % Counter(r["familia"] for r in guardadas).most_common())
    print("escrito: %s" % args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
