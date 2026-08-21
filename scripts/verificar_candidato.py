#!/usr/bin/env python3
"""¿Está ya catalogado el candidato que parece un castro claro?

De los `14` candidatos mejor puntuados, mirados a ciegas junto a `6` controles,
**solo uno** parece un recinto inequivoco: `c-02`, en Pontevedra. Antes de
llamarlo hallazgo hay que descartar lo obvio: que este catalogado en algun sitio
que nuestra fusion de fuentes no recogio.

«No esta en nuestro fichero de verdad» **no es** «no esta catalogado». Se
comprueba contra todos los ficheros de puntos del repositorio y contra OSM en
vivo.

Uso: verificar_candidato.py LON LAT
"""
from __future__ import annotations

import csv
import glob
import json
import math
import sys
import urllib.parse
import urllib.request

LON, LAT = float(sys.argv[1]), float(sys.argv[2])
K = 111_320.0 * math.cos(math.radians(LAT))


def dist(lo, la):
    return math.hypot((lo - LON) * K, (la - LAT) * 110_540.0)


print(f"  candidato: {LAT:.5f}, {LON:.5f}\n")
print("  === contra todos los ficheros de puntos del repositorio ===")
hallado = False
for f in sorted(set(glob.glob("data/**/*.tsv", recursive=True))):
    if "sweep" in f or "orto" in f:
        continue
    try:
        rs = list(csv.DictReader(open(f, encoding="utf-8"), delimiter="\t"))
    except Exception:
        continue
    if not rs or not ({"lon", "lat"} <= set(rs[0])):
        continue
    cerca = []
    for r in rs:
        try:
            d = dist(float(r["lon"]), float(r["lat"]))
        except (TypeError, ValueError):
            continue
        if d < 1000:
            cerca.append((d, (r.get("name") or r.get("nombre") or "?")[:42]))
    if cerca:
        hallado = True
        cerca.sort()
        print(f"    {f}")
        for d, n in cerca[:3]:
            print(f"        {d:6.0f} m  {n}")
if not hallado:
    print("    nada a menos de 1 km en ningun fichero del repositorio")

print("\n  === contra OSM en vivo, radio 2 km ===")
q = (f'[out:json][timeout:60];('
     f'nwr(around:2000,{LAT},{LON})["historic"];'
     f'nwr(around:2000,{LAT},{LON})["name"~"[Cc]astro|[Cc]id[aá]|[Cc]roa|[Cc]oto"];'
     f');out center tags;')
try:
    req = urllib.request.Request(
        "https://overpass-api.de/api/interpreter",
        data=urllib.parse.urlencode({"data": q}).encode(),
        headers={"User-Agent": "castros-ia (investigacion arqueologica)"})
    els = json.load(urllib.request.urlopen(req, timeout=90)).get("elements", [])
    if not els:
        print("    OSM: nada historico ni con toponimo de castro en 2 km")
    for e in els[:10]:
        c = e.get("center", e)
        t = e.get("tags", {})
        print(f"        {dist(c['lon'], c['lat']):6.0f} m  "
              f"{t.get('name', '?')[:36]:<36} {t.get('historic', '-')}")
except Exception as e:
    print(f"    *** OSM FALLO: {type(e).__name__} {str(e)[:60]} ***")
    print("    NO se puede concluir nada de esta parte")
