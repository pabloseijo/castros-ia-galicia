#!/usr/bin/env python3
"""Baja la ortofoto del PNOA de cada viñeta de un corpus, para el canal de v9.

**Por qué, y por qué NO es la criba refutada.** El `2026-08-07` se probó un
clasificador de ortofoto como **criba posterior** sobre candidatos ya detectados
y salió **anticorrelado**: la precisión de despliegue cayó de `0.200` a `0.062`,
porque aprendió «rural contra urbano» y en la ría de Vigo los castros están
rodeados de urbanización. Eso queda refutado, **como criba**.

Peker (`2026`, `10.1017/aap.2025.10142`) hace lo contrario sobre terrazas
agrícolas del Bozburun: mete lo espectral **como canal de entrada al entrenar**,
y compara cuatro arquitecturas —fusión temprana, intermedia, tardía y solo RGB—.
**Gana la temprana**, con `IoU 0.754` y `85,9%` de acierto, y su modelo saca más
precisión que la digitalización experta (`87,4%` contra `79,3%`).

Son dos cosas distintas: filtrar al final con un clasificador entrenado aparte no
es lo mismo que dejar que la red aprenda desde el principio a combinar textura
con relieve. El resultado negativo propio no toca esta vía.

Y es la vía con mejor pinta para el cuello más caro medido: la precisión cae de
`0.826` en Lugo a `0.391` en Pontevedra, donde el confusor es obra moderna en un
paisaje periurbano — justo lo que una imagen ve y un modelo digital del terreno
no.

## Detalles que importan

- Se pide el **mismo recuadro** que la viñeta —`512 m` de lado, `512 px`— para
  que el canal quede pixel a pixel alineado con el relieve. Sin eso la fusión
  temprana no tiene sentido.
- Se guarda **JPEG y no array**: `512x512x3` en `uint8` son `786 KB`, que por
  `15.311` viñetas serían `12 GB`. En JPEG son unos `765 MB`.
- **Va en la Raspberry**, no en `oval-server`: es red pura y de CPU baja, y
  `oval-server` tiene la GPU y los núcleos ocupados. Si hay que mover el
  resultado entre nodos lo lanza el orquestador (arquitectura en estrella: los
  nodos no se hablan entre sí).
- Concurrencia baja a propósito. El WMS del IGN es un servicio público y
  gratuito; `4` conexiones con pausa son de sobra y no se le hace daño.

Uso:
    python3 scripts/bajar_ortofotos_corpus.py \\
        --index data/galicia-vignettes-v7/index.tsv \\
        --cache data/ortofotos-corpus --workers 4
"""
from __future__ import annotations

import argparse
import csv
import sys
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

WMS = "https://www.ign.es/wms-inspire/pnoa-ma"
UA = "castros-ia (investigacion arqueologica no comercial)"
_SEM = threading.Semaphore(4)
_LOCK = threading.Lock()


def a_utm29(lon, lat):
    """WGS84 a UTM 29N sin pyproj, que no esta en la Pi.

    Transversa de Mercator con los parametros de EPSG:25829 (meridiano central
    `-9`, factor de escala `0.9996`, falso este `500000`), sobre el elipsoide
    GRS80. Comprobada contra pyproj: el error es de centimetros, y la viñeta
    mide `512 m`.
    """
    import math
    a, f = 6378137.0, 1 / 298.257222101
    e2 = f * (2 - f)
    ep2 = e2 / (1 - e2)
    k0, lon0, FE, FN = 0.9996, math.radians(-9.0), 500000.0, 0.0
    p, l = math.radians(lat), math.radians(lon)
    N = a / math.sqrt(1 - e2 * math.sin(p) ** 2)
    T = math.tan(p) ** 2
    C = ep2 * math.cos(p) ** 2
    A = (l - lon0) * math.cos(p)
    e4, e6 = e2 * e2, e2 * e2 * e2
    M = a * ((1 - e2/4 - 3*e4/64 - 5*e6/256) * p
             - (3*e2/8 + 3*e4/32 + 45*e6/1024) * math.sin(2*p)
             + (15*e4/256 + 45*e6/1024) * math.sin(4*p)
             - (35*e6/3072) * math.sin(6*p))
    x = FE + k0 * N * (A + (1-T+C)*A**3/6 + (5-18*T+T*T+72*C-58*ep2)*A**5/120)
    y = FN + k0 * (M + N*math.tan(p) * (A*A/2 + (5-T+9*C+4*C*C)*A**4/24
                   + (61-58*T+T*T+600*C-330*ep2)*A**6/720))
    return x, y


def pedir(x, y, lado, px, intentos=4):
    h = lado / 2.0
    q = {"SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetMap",
         "LAYERS": "OI.OrthoimageCoverage", "STYLES": "", "CRS": "EPSG:25829",
         "FORMAT": "image/jpeg", "BBOX": f"{x-h},{y-h},{x+h},{y+h}",
         "WIDTH": str(px), "HEIGHT": str(px)}
    url = WMS + "?" + urllib.parse.urlencode(q)
    for i in range(intentos):
        try:
            with _SEM:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=120) as r:
                    d = r.read()
            if d.startswith(b"\xff\xd8"):     # cabecera JPEG
                return d
        except Exception:
            pass
        time.sleep(3 * (i + 1))
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--index", type=Path, required=True)
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--lado-m", type=float, default=512.0)
    ap.add_argument("--px", type=int, default=512)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limite", type=int, default=0)
    args = ap.parse_args()

    args.cache.mkdir(parents=True, exist_ok=True)
    filas = list(csv.DictReader(open(args.index, encoding="utf-8"),
                                delimiter="\t"))
    if args.limite:
        filas = filas[:args.limite]
    print(f"viñetas en el índice: {len(filas)}", flush=True)

    pend = [r for r in filas
            if not (args.cache / f"{r['sid']}.jpg").exists()]
    print(f"ya en caché: {len(filas)-len(pend)} | pendientes: {len(pend)}",
          flush=True)
    if not pend:
        print("nada que bajar"); return 0

    hechas = fallos = 0
    t0 = time.time()

    def tarea(r):
        nonlocal hechas, fallos
        try:
            x, y = a_utm29(float(r["lon"]), float(r["lat"]))
        except (KeyError, TypeError, ValueError):
            return False
        d = pedir(x, y, args.lado_m, args.px)
        if d is None:
            with _LOCK:
                fallos += 1
            return False
        (args.cache / f"{r['sid']}.jpg").write_bytes(d)
        with _LOCK:
            hechas += 1
            if hechas % 200 == 0:
                dt = time.time() - t0
                ritmo = hechas / max(dt, 1) * 60
                queda = (len(pend) - hechas) / max(ritmo, 1e-9)
                print(f"  {hechas}/{len(pend)} | {ritmo:.0f}/min | "
                      f"faltan {queda:.0f} min | fallos {fallos}", flush=True)
        time.sleep(0.25)
        return True

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        list(ex.map(tarea, pend))

    mb = sum(f.stat().st_size for f in args.cache.glob("*.jpg")) / 1e6
    print(f"\nbajadas {hechas} | fallos {fallos} | caché {mb:.0f} MB en "
          f"{args.cache}")
    if fallos:
        print("los fallos se reintentan volviendo a ejecutar: es reanudable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
