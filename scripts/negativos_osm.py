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
    # --- confusor AGRICOLA, anadido el 2026-08-07 ---
    # Las diez familias de arriba son obra moderna, y con ellas la precision de
    # Pontevedra subio de `0.179` a `0.235`. Pero Ourense salio a `0.372`
    # —parecido a la ria de Vigo pese a ser interior rural, rompiendo la
    # explicacion «interior contra costa»— y al bajar la ortofoto de sus falsos
    # positivos **no aparecio ni una infraestructura moderna**: lo que hay es
    # **vinnedo en bancales y laderas aterrazadas**. O Ribeiro entero esta
    # socalcado, y un bancal tiene la misma firma de relieve que un parapeto.
    #
    # Ninguna de las diez familias anteriores lo cubria, asi que el corpus no
    # tenia de donde aprenderlo. Estas tres van a buscarlo a proposito.
    #
    # **Cautela al usarlas:** al contrario que una cantera, un bancal es
    # antiguo y a veces esta ENCIMA de un yacimiento —se cultivo la ladera del
    # castro—. Hay que comprobar que estos negativos no caen sobre castros
    # catalogados antes de meterlos al corpus, o se le ensena a la red a
    # apagar justo lo que busca.
    "vinnedo":      '["landuse"="vineyard"]',
    "frutal":       '["landuse"="orchard"]',
    "bancal":       '["man_made"="embankment"]',
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
    # **Sin esto, las familias agrícolas envenenan el corpus.** Un bancal o un
    # viñedo no es como una cantera: es antiguo y muchas veces está ENCIMA del
    # yacimiento, porque la ladera del castro se cultivó. Meter esa viñeta como
    # negativo le enseña a la red a apagar exactamente lo que busca, y el fallo
    # no se ve en ninguna métrica —solo baja el recall y parece que el modelo es
    # peor—. Ya había indicio con las familias modernas: un campo de fútbol caía
    # sobre `1` de `17` castros.
    ap.add_argument("--excluir-cerca-de", type=Path, default=None,
                    help="TSV de yacimientos conocidos; se descarta cualquier "
                         "negativo a menos de --margen-castro de uno")
    ap.add_argument("--margen-castro", type=float, default=250.0)
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

    # Fuera lo que caiga sobre un yacimiento conocido. Ver la nota del argumento.
    if args.excluir_cerca_de and Path(args.excluir_cerca_de).exists():
        sitios = []
        with open(args.excluir_cerca_de, encoding="utf-8") as fh:
            for r in csv.DictReader(fh, delimiter="\t"):
                lo = r.get("lon") or r.get("longitude")
                la = r.get("lat") or r.get("latitude")
                try:
                    sitios.append((float(lo), float(la)))
                except (TypeError, ValueError):
                    continue
        antes = len(filas)
        filas = [r for r in filas
                 if all(math.hypot((r["lat"]-la)*111320,
                                   (r["lon"]-lo)*111320*math.cos(math.radians(la)))
                        > args.margen_castro for lo, la in sitios)]
        print("\ndescartados por caer sobre un yacimiento conocido (<%.0f m): %d"
              % (args.margen_castro, antes - len(filas)), flush=True)

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
