#!/usr/bin/env python3
"""Los castros que el modelo NO encuentra, ¿siguen ahi?

A Coruna tiene el peor recall de los cuatro bloques (`0,267`): se le escapan `55`
castros catalogados de `75`. Cinco hipotesis han fallado ya al explicarlo
—densidad LiDAR, solape de ventana, deriva de calibracion, cambio costa-interior
y criba OSM—, y **todas suponian que el fallo era del modelo**.

Esta pregunta es la contraria: ¿y si buena parte de esos castros ya no se ve en
el terreno? Un castro bajo un poligono industrial, una urbanizacion o una
cantera **no tiene relieve que detectar**, y ningun modelo lo encontrara en un
modelo digital del terreno.

Ojo con el precedente: la criba OSM se probo **sobre las predicciones** y quedo
refutada como filtro. Esto la aplica **sobre la verdad**, que es otra pregunta:
alli era «¿puedo descartar detecciones?», aqui es «¿era alcanzable el objetivo?».

**El control que hace que la cifra signifique algo**: se compara contra los
castros *hallados* del mismo bloque. Si el `40%` de los perdidos esta urbanizado
pero tambien lo esta el `40%` de los hallados, la urbanizacion no explica nada.

Nota de implementacion, que costo dos intentos: se hace **una consulta por
bloque**, no una por castro. Preguntar `["building"~"."]` alrededor de cada punto
obliga a Overpass a un barrido con expresion regular sobre todos los edificios y
devuelve `504` en los dos espejos. Una sola caja por bloque, sin regex sobre
`building`, y el cruce espacial en local.
"""
from __future__ import annotations

import csv
import json
import math
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

BLOQUES = {"lugo": "-7.375 42.625 -7.125 42.875",
           "coruna": "-8.50 43.00 -8.25 43.25",
           "ourense": "-8.25 42.25 -8.00 42.50",
           "pontevedra": "-8.875 42.125 -8.625 42.375"}
TOL, UMBRAL, RADIO = 500.0, 0.70, 250.0
OVERPASS = ("https://overpass-api.de/api/interpreter",
            "https://overpass.kumi.systems/api/interpreter")
CACHE = Path("data/osm-urbano")
CACHE.mkdir(exist_ok=True)


def leer(p):
    with Path(p).open(encoding="utf-8") as fh:
        return [r for r in csv.DictReader(fh, delimiter="\t")
                if r.get("lon") and r.get("lat")]


def pedir(consulta, intentos=6):
    for i in range(intentos):
        url = OVERPASS[i % len(OVERPASS)]
        try:
            req = urllib.request.Request(
                url, data=urllib.parse.urlencode({"data": consulta}).encode(),
                headers={"User-Agent": "castros-ia (investigacion arqueologica)"})
            with urllib.request.urlopen(req, timeout=300) as r:
                return json.load(r)
        except Exception as e:
            print(f"    {url.split('/')[2]}: {str(e)[:44]}", file=sys.stderr, flush=True)
            time.sleep(10 * (i + 1))
    return None


def urbano_del_bloque(bloque):
    """Todos los rasgos modernos de la caja, en una sola consulta. Se cachea."""
    f = CACHE / f"{bloque}.json"
    if f.exists():
        return json.loads(f.read_text())
    w, s, e, n = map(float, BLOQUES[bloque].split())
    caja = f"{s},{w},{n},{e}"
    q = ("[out:json][timeout:280];("
         f'way["landuse"~"industrial|residential|retail|commercial|quarry|construction|landfill"]({caja});'
         f'way["man_made"~"quarry|works"]({caja});'
         f'way["aeroway"~"aerodrome|runway"]({caja});'
         f'way["leisure"~"pitch|golf_course|stadium|sports_centre"]({caja});'
         ");out center;")
    d = pedir(q)
    if d is None:
        sys.exit(f"ABORTA en {bloque}: Overpass no responde. Un cero aqui seria "
                 f"indistinguible de un fallo de red.")
    pts = [(el["center"]["lon"], el["center"]["lat"])
           for el in d.get("elements", []) if "center" in el]
    f.write_text(json.dumps(pts))
    print(f"  {bloque}: {len(pts)} rasgos modernos cacheados", flush=True)
    return pts


print(f"  radio {RADIO:.0f} m alrededor de cada castro | umbral {UMBRAL}\n")
for b in BLOQUES:
    truth, pred = leer(f"data/{b}_fus_truth_limpia.tsv"), leer(f"data/sweep_val_{b}_v7.tsv")
    urb = urbano_del_bloque(b)
    lat0 = sum(float(t["lat"]) for t in truth) / len(truth)
    k = 111_320.0 * math.cos(math.radians(lat0))
    det = [(float(r["lon"]) * k, float(r["lat"]) * 110_540.0)
           for r in pred if float(r.get("score", 0)) >= UMBRAL]
    up = [(x * k, y * 110_540.0) for x, y in urb]

    hall = perd = hu = pu = 0
    for t in truth:
        tx, ty = float(t["lon"]) * k, float(t["lat"]) * 110_540.0
        visto = any((px - tx) ** 2 + (py - ty) ** 2 <= TOL * TOL for px, py in det)
        cerca = any((ux - tx) ** 2 + (uy - ty) ** 2 <= RADIO * RADIO for ux, uy in up)
        if visto:
            hall += 1; hu += cerca
        else:
            perd += 1; pu += cerca
    fh_, fp_ = 100 * hu / max(hall, 1), 100 * pu / max(perd, 1)
    print(f"  {b:<12} hallados {hall:>3} ({fh_:>3.0f}% urbanizados) | "
          f"perdidos {perd:>3} ({fp_:>3.0f}% urbanizados) | "
          f"diferencia {fp_-fh_:+5.0f} pp", flush=True)
