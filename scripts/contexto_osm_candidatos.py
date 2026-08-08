#!/usr/bin/env python3
"""Contexto OSM por candidato: las trampas que la revisión visual encontró, en lote.

La revisión a ojo de `25` fichas el `2026-08-08` encontró cuatro clases de falso
positivo que OSM **sí** sabe delatar, aunque no sepa delatar el viñedo:

- **Enlaces de autovía**: dos candidatos eran literalmente el lazo de una rampa
  (Abegondo y Nigrán), con contrastes de anillo de `2,16` y `2,69`.
- **Fincas de pazo**: el mejor contraste de toda la cola (`2,93`, Ordes) era el
  cierre de una finca señorial con jardines y estanque.
- **Depósitos de agua**: círculos perfectos de `10-20 m`.
- **Urbanización densa**: donde hay decenas de edificios en `250 m`, la lectura
  morfológica vale poco.

Este script pregunta esas cuatro cosas por candidato, con pausas de cortesía.
**Corre en la Raspberry**: es red pura. Y NO descalifica nada — produce columnas
para que el informe las enseñe y quien revise decida.

Uso:
    python3 contexto_osm_candidatos.py --candidatos todos.tsv --out contexto.tsv
    (todos.tsv: columnas bloque, n, lon, lat)
"""
from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

ESPEJOS = ("https://overpass.kumi.systems/api/interpreter",
           "https://overpass-api.de/api/interpreter")
UA = "castros-ia (investigacion arqueologica no comercial)"


def overpass(q, intentos=4):
    for i in range(intentos):
        try:
            req = urllib.request.Request(
                ESPEJOS[i % len(ESPEJOS)],
                data=urllib.parse.urlencode({"data": q}).encode(),
                headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.load(r)
        except Exception as e:
            print("    reintento %d: %s" % (i + 1, e), flush=True)
            time.sleep(8 * (i + 1))
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidatos", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--pausa", type=float, default=4.0)
    args = ap.parse_args()

    filas = list(csv.DictReader(open(args.candidatos, encoding="utf-8"),
                                delimiter="\t"))
    print("candidatos: %d" % len(filas), flush=True)

    hechos = {}
    if args.out.exists():
        for r in csv.DictReader(open(args.out, encoding="utf-8"),
                                delimiter="\t"):
            hechos[(r["bloque"], r["n"])] = r
        print("reanudando: %d ya consultados" % len(hechos), flush=True)

    nuevo = not args.out.exists()
    fh = open(args.out, "a", newline="", encoding="utf-8")
    w = csv.writer(fh, delimiter="\t")
    if nuevo:
        w.writerow(["bloque", "n", "autovia_250m", "pazo_finca_250m",
                    "deposito_agua_150m", "edificios_250m", "via_mayor"])

    for i, r in enumerate(filas, 1):
        clave = (r["bloque"], r["n"])
        if clave in hechos:
            continue
        lat, lon = float(r["lat"]), float(r["lon"])
        q = (
            '[out:json][timeout:120];('
            f'way["highway"~"motorway|trunk|primary"](around:250,{lat},{lon});'
            f'nwr["highway"~"motorway_link|trunk_link"](around:250,{lat},{lon});'
            f'nwr["historic"~"manor|castle"](around:250,{lat},{lon});'
            f'nwr["leisure"="garden"](around:250,{lat},{lon});'
            f'nwr["building"~"manor|villa|country_house"](around:250,{lat},{lon});'
            f'nwr["man_made"~"water_tower|storage_tank|reservoir_covered"]'
            f'(around:150,{lat},{lon});'
            f'way["building"](around:250,{lat},{lon});'
            ');out tags;')
        d = overpass(q)
        if d is None:
            print("  %s-%s sin respuesta" % clave, flush=True)
            continue
        n_auto = n_pazo = n_dep = n_edif = 0
        via = ""
        for el in d.get("elements", []):
            t = el.get("tags", {})
            hw = t.get("highway", "")
            if hw.startswith(("motorway", "trunk")) or hw == "primary":
                n_auto += 1
                via = via or hw
            if (t.get("historic") in ("manor", "castle")
                    or t.get("leisure") == "garden"
                    or t.get("building") in ("manor", "villa", "country_house")):
                n_pazo += 1
            if t.get("man_made") in ("water_tower", "storage_tank",
                                     "reservoir_covered"):
                n_dep += 1
            if "building" in t:
                n_edif += 1
        w.writerow([r["bloque"], r["n"], n_auto, n_pazo, n_dep, n_edif, via])
        fh.flush()
        print("  %d/%d %s-%s: autovia %d, pazo %d, deposito %d, edif %d"
              % (i, len(filas), r["bloque"], r["n"], n_auto, n_pazo, n_dep,
                 n_edif), flush=True)
        time.sleep(args.pausa)
    fh.close()
    print("\nescrito: %s" % args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
