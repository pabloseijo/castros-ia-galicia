#!/usr/bin/env python3
"""¿Cuántos falsos positivos se pueden etiquetar como no-castro SIN arqueólogo?

Canedo obtiene su `99,3%` de reducción de falsos positivos con **una ronda de
minería en la que dos arqueólogos revisan la salida**. Aquí no hay arqueólogo,
y sustituirlo por «distancia al catálogo» ya se probó: fue v12 y quedó en
`F1 0,459`, porque minó los `524` errores **a ciegas** —incluidos los que
podrían ser castros inéditos de verdad, que es exactamente lo que el sistema
busca—.

Hay una franja intermedia que no se ha probado: **los falsos positivos que se
pueden verificar como no-castros por evidencia objetiva**. Una detección
encima de una cantera activa, de un polígono industrial o de un enlace de
autovía no necesita criterio experto para descartarse: la evidencia es
cartográfica y comprobable.

Si ese conjunto es grande, es un corpus de negativos duros **con etiqueta
fiable**, que es lo único que le faltaba a v12.

Este script **solo lo cuenta**. No entrena nada: dice si la vía es viable
antes de gastar GPU en ella.

## Lo que NO cuenta como verificado

- **Distancia al catálogo**: es lo que hizo v12 y es circular — un sitio no
  catalogado es justo lo que se busca.
- **Un falso positivo de otro barrido cerca**: es la misma detección hecha por
  otro modelo. Contarla como evidencia es circular.
- **Suelo urbano genérico**: un castro puede estar dentro de un pueblo. Hace
  falta un rasgo que sea incompatible con que el yacimiento siga ahí.

Uso:
    python3 scripts/negativos_verificables.py --entrada data/calib_morfo.tsv
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

OVERPASS = "https://overpass-api.de/api/interpreter"
# Radio por defecto. **Es un parámetro que puede matar la hipótesis solo
# por ser estrecho**: la celda de detección mide 512 m, así que un rasgo a
# 250 m del centro sigue estando dentro de lo que el modelo miró.
RADIO = 150.0

# Rasgos incompatibles con que un castro siga siendo reconocible en el relieve.
# Cada uno es cartográfico y comprobable: no exige criterio arqueológico.
#
# **Cada entrada lleva su filtro Overpass Y el par clave/valor con que se
# reconoce después.** La primera versión guardaba solo el filtro y clasificaba
# buscando el nombre español dentro de las etiquetas —`"cantera" in tags`—,
# contra unas etiquetas que OSM escribe en inglés. Resultado: de los seis
# rasgos **solo acertaba `industrial`**, por la casualidad de escribirse igual
# en los dos idiomas, y salía que ni una sola detección caía sobre una cantera
# en toda Galicia. Se descargaban bien; se comparaban mal.
RASGOS = {
    "cantera": ('["landuse"="quarry"]', ("landuse", "quarry")),
    "industrial": ('["landuse"="industrial"]', ("landuse", "industrial")),
    "vertedero": ('["landuse"="landfill"]', ("landuse", "landfill")),
    "embalse": ('["natural"="water"]["water"="reservoir"]',
                ("water", "reservoir")),
    "enlace_autovia": ('["highway"="motorway_junction"]',
                       ("highway", "motorway_junction")),
    "deposito": ('["man_made"="storage_tank"]', ("man_made", "storage_tank")),
}


def consulta(bbox: tuple[float, float, float, float]) -> dict:
    """Una sola consulta por bloque, no una por punto. Las consultas por punto
    con expresiones regulares caras dieron 504 y 429 el 2026-08-09."""
    s, w, n, e = bbox
    partes = []
    for filtro, _ in RASGOS.values():
        for tipo in ("node", "way", "relation"):
            partes.append(f"{tipo}{filtro}({s},{w},{n},{e});")
    q = f"[out:json][timeout:180];({''.join(partes)});out center tags;"
    datos = urllib.parse.urlencode({"data": q}).encode()
    # **El User-Agent no es cortesía: sin él, Apache devuelve `406 Not
    # Acceptable`.** `urllib` se identifica como `Python-urllib/3.x` y
    # `overpass-api.de` lo rechaza de plano. La primera versión de este script
    # comió los cuatro `406` como excepciones genéricas, devolvió listas vacías
    # y **concluyó «NO VIABLE: 0 negativos verificados»** — una descarga fallida
    # informada como si fuera una medida.
    peticion = urllib.request.Request(
        OVERPASS, data=datos,
        headers={"User-Agent": "CastrosIA/1.0 (investigacion arqueologica; "
                               "kelterastudio@gmail.com)",
                 "Accept": "application/json"})
    ultimo = None
    for intento in range(4):
        try:
            with urllib.request.urlopen(peticion, timeout=200) as r:
                return json.load(r)
        except Exception as ex:
            ultimo = ex
            detalle = getattr(ex, "code", "")
            espera = 20 * (intento + 1)
            print("    Overpass falló (%s %s), reintento en %ds"
                  % (type(ex).__name__, detalle, espera), flush=True)
            time.sleep(espera)
    # **Se para, no se devuelve vacío.** Un conjunto vacío por fallo de red es
    # indistinguible de un conjunto vacío por ausencia de canteras, y la
    # diferencia entre los dos es todo el resultado.
    raise SystemExit("Overpass no respondió tras 4 intentos (%s: %s). "
                     "NO hay medida: no se informa 0."
                     % (type(ultimo).__name__, ultimo))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--entrada", type=Path, default=Path("data/calib_morfo.tsv"))
    ap.add_argument("--radio", type=float, default=RADIO)
    ap.add_argument("--cache", type=Path,
                    default=Path("data/osm_negativos_cache.json"))
    args = ap.parse_args()

    filas = [r for r in csv.DictReader(args.entrada.open(encoding="utf-8"),
                                       delimiter="\t")]
    falsos = [r for r in filas if r.get("etiqueta") == "falso"]
    castros = [r for r in filas if r.get("etiqueta") == "castro"]
    print("falsos positivos: %d   aciertos: %d" % (len(falsos), len(castros)))

    cache = {}
    if args.cache.exists():
        cache = json.loads(args.cache.read_text())

    por_bloque = {}
    for r in filas:
        por_bloque.setdefault(r["bloque"], []).append(r)

    elementos = {}
    for bloque, rs in por_bloque.items():
        if bloque in cache:
            elementos[bloque] = cache[bloque]
            print("  %s: %d rasgos (cache)" % (bloque, len(cache[bloque])))
            continue
        lons = [float(r["lon"]) for r in rs]
        lats = [float(r["lat"]) for r in rs]
        m = 0.02
        d = consulta((min(lats) - m, min(lons) - m,
                      max(lats) + m, max(lons) + m))
        els = []
        for e in d.get("elements", []):
            c = e.get("center") or e
            if "lat" in c and "lon" in c:
                els.append({"lat": c["lat"], "lon": c["lon"],
                            "tags": e.get("tags", {})})
        elementos[bloque] = els
        cache[bloque] = els
        args.cache.write_text(json.dumps(cache))
        print("  %s: %d rasgos descargados" % (bloque, len(els)))
        time.sleep(5)

    radio = args.radio

    def clasificar(grupo):
        cnt = Counter()
        tocados = 0
        for r in grupo:
            lat0, lon0 = float(r["lat"]), float(r["lon"])
            k = 111_320.0 * math.cos(math.radians(lat0))
            visto = set()
            for e in elementos.get(r["bloque"], []):
                dx = (e["lon"] - lon0) * k
                dy = (e["lat"] - lat0) * 110_540.0
                if dx * dx + dy * dy <= radio * radio:
                    t = e["tags"]
                    for nombre, (_, (clave, valor)) in RASGOS.items():
                        if str(t.get(clave, "")).lower() == valor:
                            visto.add(nombre)
            if visto:
                tocados += 1
                for v in visto:
                    cnt[v] += 1
        return tocados, cnt

    nf, cf = clasificar(falsos)
    nc, cc = clasificar(castros)

    print("\n%s" % ("=" * 60))
    print("FALSOS con rasgo verificable a <%.0f m: %d de %d (%.0f%%)"
          % (radio, nf, len(falsos), 100 * nf / max(len(falsos), 1)))
    for k, v in cf.most_common():
        print("    %-16s %3d" % (k, v))
    print("\nCONTROL — aciertos (castros reales) con rasgo: %d de %d (%.0f%%)"
          % (nc, len(castros), 100 * nc / max(len(castros), 1)))
    for k, v in cc.most_common():
        print("    %-16s %3d" % (k, v))

    print("\n%s" % ("=" * 60))
    if nf < 30:
        print("NO VIABLE: %d negativos verificados son muy pocos para entrenar."
              % nf)
        print("v12 minó 524 y no bastó; con %d no hay ni que intentarlo." % nf)
    elif nc / max(len(castros), 1) > 0.10:
        print("NO VIABLE por otra razón: el %.0f%% de los CASTROS REALES también"
              % (100 * nc / max(len(castros), 1)))
        print("tiene el rasgo. El criterio no separa, etiquetaría castros como")
        print("negativos y envenenaría el corpus.")
    else:
        print("VIABLE: %d negativos con etiqueta objetiva, y solo el %.0f%% de"
              % (nf, 100 * nc / max(len(castros), 1)))
        print("los castros reales los tocaría. Es el corpus que le faltó a v12.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
