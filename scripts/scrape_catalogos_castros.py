#!/usr/bin/env python3
"""Reúne catálogos de castros que NO están en el inventario de la Xunta.

Nace de un caso concreto y demoledor. El `2026-08-07` el sistema marcó como
«falso positivo» un candidato en O Carballiño que resultó ser el **Castro do
Coto do Mosteiro**: excavado en `1984` por Luis Orero Grandal, ocupación del
siglo IV a.C. al I d.C., material publicado y piezas expuestas en el Museo
Arqueolóxico da Provincia de Ourense. **No está en el Catálogo PBA da Xunta**,
que es la verdad de campo contra la que se mide todo en este proyecto.

O sea: **la métrica castigó al modelo por encontrar un castro de la Edad del
Hierro**. Y no es un caso aislado —es la lección de Caracol, donde el LiDAR
encontró un `15%` más de estructuras que la prospección a pie: **la verdad de
campo puede ser lo incompleto**.

Mientras la verdad de campo tenga agujeros, ninguna cifra de precisión de este
proyecto significa lo que dice. Así que antes de seguir afinando el modelo hay
que arreglar el metro.

## Las fuentes, y por qué estas

- **patrimoniogalego.net** — catálogo *social*, abierto desde `2011`, con
  `~13.846` fichas y **`842` castros** geolocalizados en los `313` concellos
  gallegos. Es exactamente el tipo de catálogo que sí recoge lo que la
  administración no ha inventariado, porque lo alimenta gente que camina el
  monte. Tiene **API REST de WordPress abierta**, así que no hace falta raspar
  listados: se pagina por API y solo se baja el HTML de la ficha para sacar las
  coordenadas, que la API no expone.

Se deja preparado para añadir más fuentes: el diseño separa «listar fichas» de
«extraer coordenadas», y cada fuente aporta lo suyo.

## Cómo se ejecuta, que aquí hay reglas

Sigue el patrón ya depurado del proyecto: **concurrente con `ThreadPoolExecutor`
y semáforo por dominio** —cortesía con el servidor, no límite de la máquina—,
**backoff** ante error, **checkpoint incremental** para poder reanudar, y
**registro por obrero**. Un `for` con `sleep` viola la regla escrita en
`CLAUDE.md` y tarda muchísimo más.

El semáforo va deliberadamente bajo: es un proyecto voluntario y sin ánimo de
lucro, y bajarles `14.000` páginas a toda velocidad sería un abuso.

Uso:
    python3 scripts/scrape_catalogos_castros.py --out data/catalogo-externo \\
        --solo-castros --workers 4
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

BASE = "https://patrimoniogalego.net/index.php/wp-json/wp/v2"
UA = ("castros-ia/1.0 (investigacion arqueologica no comercial; "
      "contacto a traves del repositorio)")
_SEM = threading.Semaphore(3)      # cortesia: proyecto voluntario
_LOCK = threading.Lock()

# La ficha trae las coordenadas en el HTML, no en la API. Se buscan en el rango
# de Galicia para no coger cualquier par de numeros de la pagina.
RE_COORD = re.compile(r"(4[1-4]\.\d{4,})[^0-9\-]{1,14}(-[6-9]\.\d{4,})")
# Que cuenta como castro. `croa` y `cividade` son sinonimos gallegos; se excluye
# lo que solo comparte raiz —«Castrelo» es un topónimo, «castiñeiro» un arbol—.
RE_CASTRO = re.compile(r"\b(castro|castros|croa|cividade|citania|castelo\s+de\s+"
                       r"orixe\s+castrex\w+)\b", re.I)
RE_NO = re.compile(r"castrelo|castiñeir|castañeir", re.I)


def pedir(url, intentos=4, espera=3.0):
    """GET con backoff. Devuelve `(cuerpo, cabeceras)` o `(None, None)`."""
    for i in range(intentos):
        try:
            with _SEM:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=90) as r:
                    return r.read(), dict(r.headers)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None, None
            time.sleep(espera * (2 ** i))
        except Exception:
            time.sleep(espera * (2 ** i))
    return None, None


def listar_pagina(n):
    cuerpo, _ = pedir(f"{BASE}/posts?per_page=100&page={n}"
                      f"&_fields=id,link,title,categories")
    if not cuerpo:
        return []
    try:
        return json.loads(cuerpo)
    except Exception:
        return []


def limpiar(html_txt):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html_txt)).strip()


def coords_de_ficha(url, log):
    cuerpo, _ = pedir(url)
    if not cuerpo:
        log(f"sin cuerpo: {url}")
        return None
    t = cuerpo.decode("utf-8", "replace")
    m = RE_COORD.search(t)
    if not m:
        return None
    # El concello y la tipologia suelen ir en el propio titulo o en migas.
    tipo = ""
    mt = re.search(r"<title>(.*?)</title>", t, re.S)
    if mt:
        tipo = limpiar(mt.group(1))[:120]
    return float(m.group(2)), float(m.group(1)), tipo


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--solo-castros", action="store_true",
                    help="filtra por titulo antes de bajar cada ficha")
    ap.add_argument("--max-paginas", type=int, default=0)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    logs = args.out / "worker-logs"
    logs.mkdir(exist_ok=True)
    destino = args.out / "patrimoniogalego.tsv"

    def log_de(nombre):
        def _l(msg):
            with open(logs / f"{nombre}.log", "a", encoding="utf-8") as fh:
                fh.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
        return _l

    # --- checkpoint: no volver a pedir lo ya resuelto -----------------------
    hechos = {}
    if destino.exists():
        with open(destino, encoding="utf-8") as fh:
            for r in csv.DictReader(fh, delimiter="\t"):
                hechos[r["id"]] = r
        print(f"reanudando: {len(hechos)} fichas ya resueltas", flush=True)

    # **Sondear con el mismo `per_page` con el que se va a paginar.** Con
    # `per_page=1` el servidor responde `X-WP-TotalPages: 13846` —una pagina por
    # ficha— y el bucle pediria 13.846 paginas de 100 en vez de 139: cien veces
    # mas peticiones a un proyecto voluntario. Se calcula de `X-WP-Total`, que no
    # depende del tamano de pagina.
    POR_PAGINA = 100
    _, cab = pedir(f"{BASE}/posts?per_page={POR_PAGINA}&_fields=id")
    total = int(cab.get("X-WP-Total", 0)) if cab else 0
    paginas = -(-total // POR_PAGINA) if total else 0
    if args.max_paginas:
        paginas = min(paginas, args.max_paginas)
    print(f"catálogo: {total} fichas en {paginas} páginas", flush=True)

    # --- 1. listar (concurrente, la API aguanta) ----------------------------
    fichas = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for lote in ex.map(listar_pagina, range(1, paginas + 1)):
            fichas.extend(lote)
    print(f"fichas listadas: {len(fichas)}", flush=True)

    if args.solo_castros:
        antes = len(fichas)
        fichas = [f for f in fichas
                  if RE_CASTRO.search(limpiar(f["title"]["rendered"]))
                  and not RE_NO.search(limpiar(f["title"]["rendered"]))]
        print(f"filtradas por título como castro: {len(fichas)} de {antes}",
              flush=True)

    pend = [f for f in fichas if str(f["id"]) not in hechos]
    print(f"pendientes de coordenadas: {len(pend)}", flush=True)

    # --- 2. coordenadas, ficha a ficha --------------------------------------
    nuevo = not destino.exists()
    fh_out = open(destino, "a", newline="", encoding="utf-8")
    wr = csv.writer(fh_out, delimiter="\t")
    if nuevo:
        wr.writerow(["id", "lon", "lat", "nombre", "titulo_pagina", "url"])

    def tarea(f):
        nombre = threading.current_thread().name
        r = coords_de_ficha(f["link"], log_de(nombre))
        return f, r

    hechas, sin_coord = 0, 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(tarea, f) for f in pend}
        for i, fut in enumerate(as_completed(futs), 1):
            f, r = fut.result()
            if r:
                lon, lat, tit = r
                with _LOCK:
                    wr.writerow([f["id"], f"{lon:.6f}", f"{lat:.6f}",
                                 limpiar(f["title"]["rendered"])[:90], tit,
                                 f["link"]])
                    fh_out.flush()
                hechas += 1
            else:
                sin_coord += 1
            futs.discard(fut)
            if i % 25 == 0:
                print(f"  {i}/{len(pend)} | con coordenadas {hechas} | "
                      f"sin {sin_coord}", flush=True)
    fh_out.close()
    print(f"\nescrito: {destino}")
    print(f"  con coordenadas: {hechas} | sin coordenadas: {sin_coord}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
