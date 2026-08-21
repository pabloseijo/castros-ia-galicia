#!/usr/bin/env python3
"""¿Se pierden los castros que están en campo abierto? Los 214, no 24.

El `2026-08-09` se midió sobre `18` perdidos y `6` controles de A Coruña que los
castros que el modelo no encuentra están en terreno **claro y liso** —labradío,
prado, aldea— y los que sí encuentra bajo **dosel oscuro y rugoso**: luminancia
`116` contra `95` (`p = 0,028`) y textura `12,9` contra `16,9` (`p = 0,024`).

Con `6` controles eso es una señal, no un resultado. Esto lo repite sobre **los
`214` castros catalogados de los cuatro bloques**, con dos ventajas:

- `n` suficiente para que el contraste signifique algo.
- **Cuatro bloques**, así que se puede ver si el efecto es general o solo de A
  Coruña. Si aparece en los cuatro, es un mecanismo; si solo en uno, es una
  peculiaridad de ese sitio.

Dos índices sobre el centro (`256 m`): luminancia y textura de la ortofoto del
PNOA, que **no viene del LiDAR** y por tanto no es circular con la predicción.
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

import numpy as np
from PIL import Image

sys.path.insert(0, "scripts")
from build_trasancos_vignettes import lonlat_to_utm29  # noqa: E402

WMS = "https://www.ign.es/wms-inspire/pnoa-ma"
LADO = PX = 512
B = 8
UMBRAL, RADIO = 0.70, 250.0
CACHE = Path("data/orto-214")
CACHE.mkdir(exist_ok=True)
BLOQUES = ["lugo", "coruna", "ourense", "pontevedra"]


def leer(p):
    with Path(p).open(encoding="utf-8") as fh:
        return [r for r in csv.DictReader(fh, delimiter="\t")
                if r.get("lon") and r.get("lat")]


def bajar(x, y, dest: Path, intentos=4):
    if dest.exists() and dest.stat().st_size > 3000:
        return True
    h = LADO / 2
    url = WMS + "?" + urllib.parse.urlencode(
        {"SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetMap",
         "LAYERS": "OI.OrthoimageCoverage", "STYLES": "", "CRS": "EPSG:25829",
         "FORMAT": "image/jpeg", "BBOX": f"{x-h},{y-h},{x+h},{y+h}",
         "WIDTH": str(PX), "HEIGHT": str(PX)})
    for i in range(intentos):
        try:
            with urllib.request.urlopen(url, timeout=90) as r:
                d = r.read()
            # el WMS devuelve 200 con un XML de excepcion: hay que mirar los bytes
            if d[:2] == b"\xff\xd8":
                dest.write_bytes(d)
                return True
        except Exception:
            pass
        time.sleep(4 * (i + 1))
    return False


def indices(f: Path):
    c = np.asarray(Image.open(f).convert("RGB"), dtype=np.float32)[128:384, 128:384]
    lum = c.mean(axis=2)
    h, w = (lum.shape[0] // B) * B, (lum.shape[1] // B) * B
    tex = lum[:h, :w].reshape(h // B, B, w // B, B).std(axis=(1, 3)).mean()
    return float(lum.mean()), float(tex)


filas = []
fallos = 0
for b in BLOQUES:
    truth, pred = leer(f"data/{b}_fus_truth_limpia.tsv"), leer(f"data/sweep_val_{b}_v7.tsv")
    lat0 = sum(float(t["lat"]) for t in truth) / len(truth)
    k = 111_320.0 * math.cos(math.radians(lat0))
    celdas = [(float(r["lon"]) * k, float(r["lat"]) * 110_540.0,
               float(r.get("score", 0))) for r in pred]
    for j, t in enumerate(truth):
        tx, ty = float(t["lon"]) * k, float(t["lat"]) * 110_540.0
        cerca = [s for px, py, s in celdas
                 if (px - tx) ** 2 + (py - ty) ** 2 <= RADIO * RADIO]
        sc = max(cerca) if cerca else 0.0
        x, y = lonlat_to_utm29(float(t["lon"]), float(t["lat"]))
        f = CACHE / f"{b}-{j:03d}.jpg"
        if not bajar(x, y, f):
            fallos += 1
            continue
        lum, tex = indices(f)
        filas.append({"bloque": b, "score": round(sc, 3),
                      "hallado": int(sc >= UMBRAL), "lum": round(lum, 2),
                      "tex": round(tex, 2), "nombre": t.get("name", "")})
    print(f"  {b}: {sum(1 for r in filas if r['bloque']==b)} medidos", flush=True)

Path("data/uso_suelo_214.json").write_text(json.dumps(filas))
print(f"\n  {len(filas)} castros medidos | {fallos} sin ortofoto")
if fallos > 0.15 * (len(filas) + fallos):
    sys.exit("ABORTA: demasiadas ortofotos fallidas; el reparto no seria fiable")
