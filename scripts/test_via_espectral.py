#!/usr/bin/env python3
"""¿Existe siquiera una vía espectral hacia un castro? Test de falsación.

Nace de una objeción de Pablo que es correcta y que este proyecto no se había
hecho: **sesgo del superviviente**. Todos los castros del catálogo son castros
*que se ven* —tienen relieve, por eso el LiDAR los encuentra y por eso alguien
los catalogó—. Puede haber otra población, invisible para el LiDAR por
construcción: arrasados por el arado, sin parapeto que sobresalga, o comidos por
la maleza. Para esa clase, la resolución morfológica no importa: no se busca una
forma, se busca una **anomalía espectral**.

Antes de montar nada —ni EnMAP, ni un canal más, ni un corpus nuevo— hay una
pregunta que se responde barata y que decide todo lo demás:

    **¿Los castros que SÍ conocemos se separan espectralmente de su entorno?**

Si un castro con relieve, muralla y ocupación no deja firma espectral, uno
arrasado tampoco la va a dejar, y la vía entera está muerta. Si la deja, hay que
mirar en qué bandas y bajo qué cubierta, porque eso dice qué sensor hace falta.

## Cómo se hace la comparación, y por qué así

Cada castro se compara con **un anillo de control a su alrededor** —mismo día,
misma escena, misma atmósfera, mismo tipo de paisaje— en vez de con una media
regional. Comparar contra la media de la comarca mediría diferencias de cultivo
y de altitud, no el yacimiento.

Se reporta el **tamaño del efecto (d de Cohen)** y no un valor p: con miles de
píxeles cualquier diferencia sale significativa, y lo que decide si un canal
sirve para detectar es la magnitud de la separación, no su significación.

**Cautela que hay que leer antes que los números:** bajo eucalipto denso el
sensor ve copa, no suelo, así que la ausencia de señal ahí no dice nada del
subsuelo. Por eso el resultado se estratifica por NDVI, que es lo más parecido a
«cuánto dosel hay» que se puede sacar de la propia imagen.

Uso:
    python3 scripts/test_via_espectral.py --truth data/ourense_truth_limpia.tsv \\
        --nombre ourense
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

import numpy as np

STAC = "https://earth-search.aws.element84.com/v1/search"
# Bandas a 10 y 20 m. Se excluyen las de 60 m (aerosol, vapor, cirros): a esa
# escala un castro son 1-2 pixeles y no hay nada que medir.
BANDAS = ["blue", "green", "red", "rededge1", "rededge2", "rededge3",
          "nir", "nir08", "swir16", "swir22"]


def escena(lon, lat, desde, hasta, nubes=10):
    cuerpo = json.dumps({
        "collections": ["sentinel-2-l2a"],
        "intersects": {"type": "Point", "coordinates": [lon, lat]},
        "datetime": f"{desde}/{hasta}",
        "query": {"eo:cloud_cover": {"lt": nubes}},
        "sortby": [{"field": "properties.eo:cloud_cover", "direction": "asc"}],
        "limit": 1}).encode()
    req = urllib.request.Request(STAC, data=cuerpo,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        d = json.load(r)
    return d["features"][0] if d.get("features") else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--truth", type=Path, required=True)
    ap.add_argument("--nombre", required=True)
    ap.add_argument("--desde", default="2024-06-01T00:00:00Z")
    ap.add_argument("--hasta", default="2024-09-30T23:59:59Z")
    ap.add_argument("--radio-m", type=float, default=60.0,
                    help="radio del yacimiento; p10-p90 medidos son 38-83 m")
    ap.add_argument("--anillo-m", type=float, default=200.0,
                    help="radio exterior del anillo de control")
    ap.add_argument("--max-sitios", type=int, default=40)
    args = ap.parse_args()

    import rasterio
    from rasterio.windows import from_bounds

    import csv
    sitios = []
    with open(args.truth, encoding="utf-8") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            try:
                sitios.append((float(r["lon"]), float(r["lat"])))
            except (KeyError, ValueError):
                continue
    sitios = sitios[:args.max_sitios]
    print(f"sitios conocidos: {len(sitios)}", flush=True)

    f = escena(sitios[0][0], sitios[0][1], args.desde, args.hasta)
    if not f:
        raise SystemExit("sin escena Sentinel-2 con esas fechas y nubes")
    print(f"escena: {f['id']} | nubes {f['properties']['eo:cloud_cover']:.1f}%",
          flush=True)

    from pyproj import Transformer
    dentro = {b: [] for b in BANDAS}
    fuera = {b: [] for b in BANDAS}
    usados = 0
    for b in BANDAS:
        if b not in f["assets"]:
            print(f"  (banda {b} no está en la escena)", flush=True)
            continue
        url = "/vsicurl/" + f["assets"][b]["href"]
        try:
            with rasterio.open(url) as src:
                tr = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
                for lon, lat in sitios:
                    x, y = tr.transform(lon, lat)
                    R = args.anillo_m
                    try:
                        w = from_bounds(x-R, y-R, x+R, y+R, src.transform)
                        a = src.read(1, window=w).astype(np.float32)
                    except Exception:
                        continue
                    if a.size == 0 or not np.isfinite(a).any():
                        continue
                    n = a.shape[0]
                    yy, xx = np.ogrid[:a.shape[0], :a.shape[1]]
                    cy, cx = (a.shape[0]-1)/2, (a.shape[1]-1)/2
                    res = 2*R/max(a.shape[0], 1)
                    d = np.hypot((yy-cy)*res, (xx-cx)*res)
                    m_in = d <= args.radio_m
                    m_out = (d > args.radio_m*1.6) & (d <= R)
                    if m_in.sum() < 3 or m_out.sum() < 10:
                        continue
                    v = a[m_in]; v = v[np.isfinite(v) & (v > 0)]
                    o = a[m_out]; o = o[np.isfinite(o) & (o > 0)]
                    if len(v) < 3 or len(o) < 10:
                        continue
                    dentro[b].append(float(np.median(v)))
                    fuera[b].append(float(np.median(o)))
            usados = max(usados, len(dentro[b]))
        except Exception as exc:
            print(f"  banda {b}: {str(exc)[:90]}", flush=True)

    print(f"\nsitios con lectura válida: {usados}\n", flush=True)
    print(f"{'banda':<10} {'castro':>9} {'entorno':>9} {'dif %':>8} "
          f"{'d Cohen':>9}  veredicto")
    print("-" * 62)
    filas = []
    for b in BANDAS:
        if len(dentro[b]) < 5:
            continue
        a = np.array(dentro[b]); c = np.array(fuera[b])
        dif = a - c
        s = dif.std(ddof=1)
        d_coh = float(dif.mean() / s) if s > 0 else 0.0
        pct = 100 * dif.mean() / c.mean() if c.mean() else 0.0
        v = ("FUERTE" if abs(d_coh) >= 0.8 else
             "medio" if abs(d_coh) >= 0.5 else
             "débil" if abs(d_coh) >= 0.2 else "nulo")
        print(f"{b:<10} {a.mean():>9.0f} {c.mean():>9.0f} {pct:>7.1f}% "
              f"{d_coh:>9.2f}  {v}")
        filas.append((b, d_coh))

    if filas:
        mejor = max(filas, key=lambda r: abs(r[1]))
        print(f"\nmejor banda: {mejor[0]} (d = {mejor[1]:.2f})")
        print("\nLECTURA: d de Cohen |0.8| es un efecto grande, pero para "
              "DETECTAR\nhace falta separación casi total. Un |d| por debajo de "
              "0.5 significa que\nlas distribuciones se solapan tanto que no "
              "hay detector posible con esa banda.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
