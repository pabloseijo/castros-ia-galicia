#!/usr/bin/env python3
"""Verifica los 419 candidatos contra todo lo conocido, uno a uno.

El `2026-08-09` el único candidato que parecía un recinto claro resultó ser
**«Castro do Monte da Guía», ya catalogado**, colado por un fallo de centroide.
Se corrigió, pero la lección es que **un candidato no es un hallazgo hasta que se
comprueba contra todo lo que se sabe**, y comprobarlo a mano de uno en uno no
escala a `419`.

Esto lo hace en lote y en dos frentes:

1. **Todos los ficheros de puntos del repositorio** —verdad de los bloques,
   máscaras de entrenamiento, maestros, censos—, que es donde vive lo que el
   proyecto ya conoce.
2. **OSM en vivo**, por si el sitio está catalogado en un sitio donde nosotros no
   miramos. Se pide **una caja por bloque**, no una consulta por candidato: son
   `419` puntos y Overpass no aguanta eso, además de que ya reventó una vez por
   pedirle de más.

Sale un TSV con la distancia a lo más cercano de cada fuente, para poder ordenar
la revisión por «cuán inédito parece».
"""
from __future__ import annotations

import csv
import glob
import json
import math
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np

BLOQUES = {"lugo": "-7.375 42.625 -7.125 42.875",
           "coruna": "-8.50 43.00 -8.25 43.25",
           "ourense": "-8.25 42.25 -8.00 42.50",
           "pontevedra": "-8.875 42.125 -8.625 42.375"}
OVERPASS = ("https://overpass-api.de/api/interpreter",
            "https://overpass.kumi.systems/api/interpreter")
CACHE = Path("data/osm-arqueo")
CACHE.mkdir(exist_ok=True)


def leer(p):
    with Path(p).open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


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


def arqueologia_osm(bloque):
    """Todo lo arqueológico y todo topónimo de castro de la caja, cacheado."""
    f = CACHE / f"{bloque}.json"
    if f.exists():
        return json.loads(f.read_text())
    w, s, e, n = map(float, BLOQUES[bloque].split())
    caja = f"{s},{w},{n},{e}"
    q = ("[out:json][timeout:280];("
         f'nwr["historic"]({caja});'
         f'nwr["archaeological_site"]({caja});'
         f'nwr["name"~"[Cc]astr|[Cc]id[aá]|[Cc]roa|[Cc]oto|[Mm]edorr|[Mm][aá]moa"]({caja});'
         ");out center tags;")
    d = pedir(q)
    if d is None:
        sys.exit(f"ABORTA en {bloque}: Overpass no responde. Un 'nada cerca' aquí "
                 f"sería indistinguible de un fallo de red.")
    pts = []
    for el in d.get("elements", []):
        c = el.get("center", el)
        if c.get("lon") is None:
            continue
        t = el.get("tags", {})
        pts.append([c["lon"], c["lat"], (t.get("name") or t.get("historic") or "?")[:50]])
    f.write_text(json.dumps(pts))
    print(f"  {bloque}: {len(pts)} rasgos arqueológicos/toponímicos en OSM", flush=True)
    return pts


# --- todo lo que el repositorio ya conoce -----------------------------------
conocido = []
for f in sorted(set(glob.glob("data/**/*.tsv", recursive=True))):
    b = Path(f).name
    if "sweep" in b or "candidatos" in b or "orto" in b or "tmp-union" in f:
        continue
    try:
        rs = list(csv.DictReader(open(f, encoding="utf-8"), delimiter="\t"))
    except Exception:
        continue
    if not rs or not ({"lon", "lat"} <= set(rs[0])):
        continue
    for r in rs:
        try:
            conocido.append((float(r["lon"]), float(r["lat"]),
                             (r.get("name") or r.get("nombre") or "?")[:44], b))
        except (TypeError, ValueError):
            pass
print(f"  catálogo interno: {len(conocido)} puntos de "
      f"{len({c[3] for c in conocido})} ficheros", flush=True)

cand = leer("data/candidatos-ineditos.tsv")
osm = {b: arqueologia_osm(b) for b in BLOQUES}

filas = []
for c in cand:
    lon, lat = float(c["lon"]), float(c["lat"])
    k = 111_320.0 * math.cos(math.radians(lat))

    def cerca(puntos):
        if not puntos:
            return 9e9, "", ""
        d = [(math.hypot((p[0] - lon) * k, (p[1] - lat) * 110_540.0), p) for p in puntos]
        dd, p = min(d, key=lambda t: t[0])
        return dd, p[2], (p[3] if len(p) > 3 else "")

    d_int, n_int, f_int = cerca(conocido)
    d_osm, n_osm, _ = cerca(osm.get(c["bloque"], []))
    filas.append({**c,
                  "d_catalogo": f"{d_int:.0f}", "cerca_catalogo": n_int,
                  "fichero": f_int,
                  "d_osm": f"{d_osm:.0f}" if d_osm < 9e8 else "",
                  "cerca_osm": n_osm})

# se ordena por «cuán inédito parece»: lejos de todo primero
filas.sort(key=lambda r: -min(float(r["d_catalogo"]),
                              float(r["d_osm"] or 9e9)))
salida = Path("data/candidatos-verificados.tsv")
with salida.open("w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=list(filas[0].keys()), delimiter="\t")
    w.writeheader()
    w.writerows(filas)

sospechosos = [r for r in filas if float(r["d_catalogo"]) < 500
               or (r["d_osm"] and float(r["d_osm"]) < 300)]
print(f"\n  {len(filas)} candidatos verificados -> {salida}")
print(f"  con algo conocido MUY cerca (posible ya catalogado): {len(sospechosos)}")
print(f"\n  los 12 más aislados de todo lo conocido:")
for r in filas[:12]:
    print(f"    {r['score']}  {r['bloque']:<11} {r['lat']},{r['lon']}  "
          f"catálogo a {r['d_catalogo']} m | OSM a {r['d_osm'] or '—'} m")
