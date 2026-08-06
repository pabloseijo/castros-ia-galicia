#!/usr/bin/env python3
"""Criba automática por OSM: descarta lo que es obra moderna, sin juicio arqueológico.

Medido el `2026-08-06`, el problema no es el recall sino la precisión, y depende
de la comarca:

| bloque | precisión | recall |
|---|---:|---:|
| Lugo (interior rural) | `0.808` | `0.689` |
| Pontevedra (ría de Vigo) | `0.179` | `0.586` |

El modelo encuentra los castros igual de bien en los dos sitios; en el urbanizado
dispara además sobre canteras, polígonos, terraplenes y urbanizaciones. Esta
criba ataca eso y **no exige ser arqueólogo**: una cantera es una cantera.

Lo que decide si sirve no es cuántos falsos quita, sino **cuántos castros reales
se lleva por delante**. Las dos cifras se reportan juntas.
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

UA = "castros-ia (investigacion arqueologica)"
OVERPASS = ("https://overpass-api.de/api/interpreter",
            "https://overpass.kumi.systems/api/interpreter")
# Lo que descalifica: obra moderna con firma de relieve parecida a un parapeto.
MODERNO = {"landuse": ("quarry", "industrial", "residential", "retail",
                       "construction", "landfill", "commercial"),
           "man_made": ("works", "wastewater_plant", "water_works", "silo",
                        "storage_tank", "pier", "breakwater"),
           "aeroway": ("aerodrome", "runway"),
           "waterway": ("dam",),
           "leisure": ("pitch", "sports_centre", "golf_course", "stadium")}


def overpass(consulta, intentos=4):
    for i in range(intentos):
        url = OVERPASS[i % len(OVERPASS)]
        try:
            req = urllib.request.Request(
                url, data=urllib.parse.urlencode({"data": consulta}).encode(),
                headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.load(r)
        except Exception as e:
            print("  overpass %s: %s" % (url.split("/")[2], str(e)[:50]),
                  file=sys.stderr)
            time.sleep(8 * (i + 1))
    return None


def contexto(puntos, radio_m=200, lote=25):
    """Devuelve, por punto, las etiquetas modernas a menos de `radio_m`."""
    fuera = [[] for _ in puntos]
    for ini in range(0, len(puntos), lote):
        trozo = puntos[ini:ini+lote]
        partes = []
        for lon, lat in trozo:
            for k, vs in MODERNO.items():
                partes.append('nwr(around:%d,%f,%f)["%s"~"%s"];'
                              % (radio_m, lat, lon, k, "|".join(vs)))
            partes.append('nwr(around:%d,%f,%f)["building"];' % (radio_m, lat, lon))
        d = overpass("[out:json][timeout:180];(" + "".join(partes) + ");out center tags;")
        if not d:
            continue
        for e in d.get("elements", []):
            c = e.get("center") or e
            ela, elo = c.get("lat"), c.get("lon")
            if ela is None:
                continue
            t = e.get("tags") or {}
            for j, (lon, lat) in enumerate(trozo):
                dd = math.hypot((lat-ela)*111320,
                                (lon-elo)*111320*math.cos(math.radians(lat)))
                if dd > radio_m:
                    continue
                for k, vs in MODERNO.items():
                    if t.get(k) in vs:
                        fuera[ini+j].append("%s=%s" % (k, t[k]))
                if "building" in t:
                    fuera[ini+j].append("building")
        time.sleep(2)
    return fuera


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--detecciones", type=Path, required=True,
                    help="TSV con lon, lat, clase (TP/FP)")
    ap.add_argument("--radio-m", type=int, default=200)
    ap.add_argument("--min-edificios", type=int, default=3,
                    help="cuántos edificios hacen falta para descartar; uno "
                         "solo puede ser una casa junto a un castro")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    filas = list(csv.DictReader(open(args.detecciones, encoding="utf-8"),
                               delimiter="\t"))
    pts = [(float(r["lon"]), float(r["lat"])) for r in filas]
    print("detecciones: %d" % len(pts), flush=True)
    ctx = contexto(pts, args.radio_m)

    for r, c in zip(filas, ctx):
        edif = sum(1 for x in c if x == "building")
        duro = [x for x in c if x != "building"]
        r["osm"] = ",".join(sorted(set(duro))[:3]) or ("%d edificios" % edif if edif else "")
        r["descartado"] = "1" if (duro or edif >= args.min_edificios) else "0"

    for clase in ("TP", "FP"):
        sub = [r for r in filas if r.get("clase") == clase]
        if not sub:
            continue
        d = sum(1 for r in sub if r["descartado"] == "1")
        print("  %s: %d, descartados por OSM %d (%.0f%%)"
              % (clase, len(sub), d, 100*d/len(sub)))
    tp = [r for r in filas if r.get("clase") == "TP"]
    fp = [r for r in filas if r.get("clase") == "FP"]
    if tp and fp:
        tp_v = sum(1 for r in tp if r["descartado"] == "0")
        fp_v = sum(1 for r in fp if r["descartado"] == "0")
        p0 = len(tp)/(len(tp)+len(fp))
        p1 = tp_v/(tp_v+fp_v) if tp_v+fp_v else 0
        print("\n  precisión %.3f -> %.3f  (%+.3f)" % (p0, p1, p1-p0))
        print("  castros conservados: %d de %d (%.0f%%)"
              % (tp_v, len(tp), 100*tp_v/len(tp)))
    if args.out:
        with open(args.out, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(filas[0].keys()), delimiter="\t")
            w.writeheader(); w.writerows(filas)
        print("\nescrito: %s" % args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
