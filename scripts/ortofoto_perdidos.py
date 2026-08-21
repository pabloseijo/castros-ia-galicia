#!/usr/bin/env python3
"""Ortofoto de los castros que A Coruna pierde: la fuente independiente.

La mirada a ciegas del `2026-08-09` tiene una circularidad que hay que romper:
**yo leia los mismos tres canales que lee el modelo**, asi que coincidir en `30`
de `30` demuestra que el modelo esta calibrado con su propia entrada, no que el
catalogo este mal.

La ortofoto **no viene del LiDAR**. Es la imagen aerea del PNOA, y en ella un
recinto arrasado suele seguir viendose como marca de cultivo: el anillo aparece
en el color del suelo o en la vegetacion aunque el relieve ya no lo acuse.

- Si en la ortofoto **se ve el anillo** -> el sitio existe y el problema es el
  `DTM`, no el catalogo. El techo de A Coruna seria del canal, no del dato.
- Si **no se ve nada** en ninguna de las dos fuentes -> el catalogo registra ahi
  algo que hoy no deja rastro medible.

Se descargan tambien los `6` controles de puntuacion alta, para tener con que
comparar: sin ellos, mirar dieciocho imagenes aereas de campo gallego no dice
nada.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, "scripts")
from build_trasancos_vignettes import lonlat_to_utm29  # noqa: E402

WMS = "https://www.ign.es/wms-inspire/pnoa-ma"
LADO, PX = 512, 512
ORIG = Path("reports/dudosos-coruna")
SALIDA = Path("reports/ortofoto-perdidos")
SALIDA.mkdir(parents=True, exist_ok=True)


def ortofoto(x, y, intentos=4):
    h = LADO / 2
    q = {"SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetMap",
         "LAYERS": "OI.OrthoimageCoverage", "STYLES": "", "CRS": "EPSG:25829",
         "FORMAT": "image/jpeg", "BBOX": f"{x-h},{y-h},{x+h},{y+h}",
         "WIDTH": str(PX), "HEIGHT": str(PX)}
    url = WMS + "?" + urllib.parse.urlencode(q)
    for i in range(intentos):
        try:
            with urllib.request.urlopen(url, timeout=90) as r:
                d = r.read()
            # El WMS devuelve `200` con un XML de excepcion cuando algo falla, asi
            # que hay que mirar los bytes: un JPEG empieza por `FF D8`.
            if d[:2] == b"\xff\xd8":
                return d
            print(f"    no es JPEG ({d[:60]!r})", file=sys.stderr, flush=True)
        except Exception as e:
            print(f"    wms: {str(e)[:50]}", file=sys.stderr, flush=True)
        time.sleep(5 * (i + 1))
    return None


clave = json.loads((ORIG / "CLAVE.json").read_text())
lote = [d for d in clave if d["grupo"] in ("dudoso-coruna", "control-coruna")]
print(f"  {len(lote)} sitios ({sum(1 for d in lote if d['grupo']=='dudoso-coruna')} "
      f"perdidos + {sum(1 for d in lote if d['grupo']=='control-coruna')} controles)",
      flush=True)

ok = fallos = 0
for d in lote:
    f = SALIDA / f"sitio-{d['n']:02d}.jpg"
    if f.exists() and f.stat().st_size > 3000:
        ok += 1
        continue
    x, y = lonlat_to_utm29(float(d["lon"]), float(d["lat"]))
    img = ortofoto(x, y)
    if img is None:
        fallos += 1
        continue
    f.write_bytes(img)
    ok += 1
    time.sleep(1.5)

print(f"\n  {ok} ortofotos en {SALIDA} | {fallos} fallidas")
if fallos > len(lote) * 0.25:
    sys.exit("ABORTA: mas de un cuarto fallido; un 'no se ve nada' aqui seria "
             "indistinguible de un fallo del servicio")
