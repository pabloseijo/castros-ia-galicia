#!/usr/bin/env python3
"""¿Están los candidatos inéditos bajo monte? Prueba de una predicción escrita.

La página [[el-arado-y-no-el-ladrillo]] (`2026-08-09`) afirma, y lo dejó escrito
**antes** de comprobarlo:

> «los que quedan por descubrir estaran, por el mismo argumento, **bajo monte**,
> que es donde el modelo funciona y donde la fotografia aerea no llega».

Es una prediccion y se puede falsar. Se miden los mismos dos indices sobre los
`120` candidatos mejor puntuados y se comparan con **los castros catalogados que
el modelo si detecta**, que es el grupo correcto: si los candidatos son castros
de verdad todavia sin catalogar, deberian parecerse a los conservados —monte
oscuro y rugoso— y no al parcelario donde el arado borro los otros.

Si salen **mas claros y lisos** que los catalogados hallados, la prediccion falla
y hay que decirlo: querria decir que buena parte de la lista es ruido de campo
labrado, no castros escondidos.
"""
from __future__ import annotations

import csv
import json
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
N = 120
CACHE = Path("data/orto-candidatos")
CACHE.mkdir(exist_ok=True)


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
            if d[:2] == b"\xff\xd8":       # el WMS da 200 con XML de excepcion
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
    return (float(lum.mean()),
            float(lum[:h, :w].reshape(h // B, B, w // B, B).std(axis=(1, 3)).mean()))


cand = list(csv.DictReader(open("data/candidatos-ineditos.tsv", encoding="utf-8"),
                           delimiter="\t"))[:N]
filas, fallos = [], 0
for i, c in enumerate(cand):
    x, y = lonlat_to_utm29(float(c["lon"]), float(c["lat"]))
    f = CACHE / f"{i:03d}.jpg"
    if not bajar(x, y, f):
        fallos += 1
        continue
    lum, tex = indices(f)
    filas.append({"bloque": c["bloque"], "score": float(c["score"]),
                  "lum": round(lum, 2), "tex": round(tex, 2)})
    if (i + 1) % 30 == 0:
        print(f"  {i+1}/{len(cand)}", flush=True)

Path("data/uso_suelo_candidatos.json").write_text(json.dumps(filas))
print(f"\n  {len(filas)} candidatos medidos | {fallos} sin ortofoto")
if fallos > 0.15 * len(cand):
    sys.exit("ABORTA: demasiadas ortofotos fallidas")
