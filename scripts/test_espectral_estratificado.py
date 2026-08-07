#!/usr/bin/env python3
"""La versión justa del test espectral: por cubierta y por fecha.

El test simple (`test_via_espectral.py`) dio negativo en los dos bloques —mejor
`d` de Cohen `0.31` en Ourense y `-0.31` en Lugo, y con el signo cambiado entre
ellos—. Pero ese resultado tiene dos objeciones legítimas y hay que atenderlas
antes de cerrar la vía:

1. **La marca de cultivo aparece en una ventana estrecha.** Agapiou midió `71`
   índices de vegetación a lo largo de un ciclo fenológico entero y la
   separabilidad cambia radicalmente con la fecha. Una escena de julio no
   falsea nada por sí sola.
2. **Los castros conocidos están bajo la misma cubierta que su entorno.** Se
   conservan justamente porque nadie los aró: son cerros con monte, rodeados de
   monte. Que no se separen espectralmente puede decir «no hay vía espectral» o
   puede decir «aquí no hay contraste de cubierta que medir», y son cosas
   distintas.

La objeción de fondo, que es de Pablo y es correcta: si existe una población de
castros **arrasados por el arado**, esos estarían en suelo abierto y sí podrían
dar marca. El problema es que **no hay ni un solo ejemplo etiquetado** de esa
clase —si se conocieran, ya estarían en el catálogo—, así que no se puede
entrenar ni validar un detector para ella. Lo único que se puede hacer es
comprobar si la **física** permite la señal, usando los sitios conocidos que sí
estén en suelo abierto.

Esto estratifica por NDVI —lo más parecido a «cuánto dosel hay» que da la propia
imagen— y repite el contraste en varias fechas del año.

Uso:
    python3 scripts/test_espectral_estratificado.py --truth data/lugo_truth_limpia.tsv
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import urllib.request
from pathlib import Path

import numpy as np

STAC = "https://earth-search.aws.element84.com/v1/search"


def escenas(lon, lat, ventanas, nubes=15):
    out = []
    for desde, hasta in ventanas:
        cuerpo = json.dumps({
            "collections": ["sentinel-2-l2a"],
            "intersects": {"type": "Point", "coordinates": [lon, lat]},
            "datetime": f"{desde}/{hasta}",
            "query": {"eo:cloud_cover": {"lt": nubes}},
            "sortby": [{"field": "properties.eo:cloud_cover", "direction": "asc"}],
            "limit": 1}).encode()
        req = urllib.request.Request(STAC, data=cuerpo,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                d = json.load(r)
            if d.get("features"):
                out.append(d["features"][0])
        except Exception as exc:
            print(f"  ventana {desde[:10]}: {str(exc)[:60]}", flush=True)
    return out


def medir(f, sitios, radio, anillo):
    """Devuelve, por sitio: NDVI del sitio y (dentro, fuera) de cada banda."""
    import rasterio
    from rasterio.windows import from_bounds
    from pyproj import Transformer

    datos = {}
    for b in ("red", "nir", "green", "swir16"):
        if b not in f["assets"]:
            continue
        url = "/vsicurl/" + f["assets"][b]["href"]
        try:
            with rasterio.open(url) as src:
                tr = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
                for i, (lon, lat) in enumerate(sitios):
                    x, y = tr.transform(lon, lat)
                    R = anillo
                    try:
                        a = src.read(1, window=from_bounds(x-R, y-R, x+R, y+R,
                                                           src.transform))
                        a = a.astype(np.float32)
                    except Exception:
                        continue
                    if a.size == 0:
                        continue
                    yy, xx = np.ogrid[:a.shape[0], :a.shape[1]]
                    cy, cx = (a.shape[0]-1)/2, (a.shape[1]-1)/2
                    res = 2*R/max(a.shape[0], 1)
                    d = np.hypot((yy-cy)*res, (xx-cx)*res)
                    vin = a[(d <= radio)]; vin = vin[np.isfinite(vin) & (vin > 0)]
                    vout = a[(d > radio*1.6) & (d <= R)]
                    vout = vout[np.isfinite(vout) & (vout > 0)]
                    if len(vin) < 3 or len(vout) < 10:
                        continue
                    datos.setdefault(i, {})[b] = (float(np.median(vin)),
                                                  float(np.median(vout)))
        except Exception as exc:
            print(f"  banda {b}: {str(exc)[:70]}", flush=True)
    return datos


def cohen(par):
    if len(par) < 5:
        return None
    a = np.array([p[0] for p in par]); c = np.array([p[1] for p in par])
    dif = a - c
    s = dif.std(ddof=1)
    return float(dif.mean()/s) if s > 0 else 0.0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--truth", type=Path, required=True)
    ap.add_argument("--radio-m", type=float, default=60.0)
    ap.add_argument("--anillo-m", type=float, default=200.0)
    ap.add_argument("--max-sitios", type=int, default=40)
    ap.add_argument("--anno", default="2024")
    args = ap.parse_args()

    sitios = []
    with open(args.truth, encoding="utf-8") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            try:
                sitios.append((float(r["lon"]), float(r["lat"])))
            except (KeyError, ValueError):
                continue
    sitios = sitios[:args.max_sitios]
    A = args.anno
    ventanas = [(f"{A}-02-01T00:00:00Z", f"{A}-03-15T23:59:59Z"),
                (f"{A}-04-15T00:00:00Z", f"{A}-05-31T23:59:59Z"),
                (f"{A}-06-15T00:00:00Z", f"{A}-07-31T23:59:59Z"),
                (f"{A}-08-15T00:00:00Z", f"{A}-09-30T23:59:59Z")]
    print(f"sitios: {len(sitios)} | ventanas: {len(ventanas)}", flush=True)
    fs = escenas(sitios[0][0], sitios[0][1], ventanas)
    print(f"escenas encontradas: {len(fs)}\n", flush=True)

    print(f"{'fecha':<12} {'cubierta':<16} {'n':>4} "
          f"{'d(NDVI)':>9} {'d(rojo)':>9} {'d(SWIR)':>9}")
    print("-" * 64)
    for f in fs:
        fecha = f["properties"]["datetime"][:10]
        datos = medir(f, sitios, args.radio_m, args.anillo_m)
        if not datos:
            continue
        # NDVI del entorno = proxy de cubierta. Alto => dosel/vegetacion densa.
        grupos = {"abierto (NDVI<0.6)": [], "vegetado (NDVI>=0.6)": []}
        for i, v in datos.items():
            if "red" not in v or "nir" not in v:
                continue
            r_out, n_out = v["red"][1], v["nir"][1]
            ndvi_out = (n_out - r_out)/(n_out + r_out) if (n_out+r_out) else 0
            k = "abierto (NDVI<0.6)" if ndvi_out < 0.6 else "vegetado (NDVI>=0.6)"
            ndvi_in = ((v["nir"][0]-v["red"][0])/(v["nir"][0]+v["red"][0])
                       if (v["nir"][0]+v["red"][0]) else 0)
            grupos[k].append({"ndvi": (ndvi_in, ndvi_out), "red": v["red"],
                              "swir": v.get("swir16")})
        for k, xs in grupos.items():
            if len(xs) < 5:
                print(f"{fecha:<12} {k:<16} {len(xs):>4}   (pocos sitios)")
                continue
            d_ndvi = cohen([x["ndvi"] for x in xs])
            d_red = cohen([x["red"] for x in xs])
            sw = [x["swir"] for x in xs if x["swir"]]
            d_sw = cohen(sw) if len(sw) >= 5 else None
            fmt = lambda v: f"{v:>9.2f}" if v is not None else f"{'--':>9}"
            print(f"{fecha:<12} {k:<16} {len(xs):>4} "
                  f"{fmt(d_ndvi)} {fmt(d_red)} {fmt(d_sw)}")

    print("\nUn |d| >= 0.8 en ALGUNA fecha y cubierta abriria la via.")
    print("Por debajo de 0.5 las distribuciones se solapan y no hay detector.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
