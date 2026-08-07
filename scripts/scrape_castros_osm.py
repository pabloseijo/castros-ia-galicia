#!/usr/bin/env python3
"""Castros de OpenStreetMap: la fuente abierta que el proyecto no había mirado.

El `2026-08-07` se fusionaron el catálogo PBA da Xunta y `patrimoniogalego.net`,
y aparecieron `151` castros que la administración no tenía. Eso demostró que la
verdad de campo estaba incompleta, pero solo se probó con **una** fuente
alternativa.

OSM es la siguiente obvia y estaba sin tocar. Tiene `historic=archaeological_site`
con `site_type=fortification`, más `historic=castle` con `castle_type=hillfort`, y
lo alimenta gente que camina el monte — el mismo perfil que hizo útil a
patrimoniogalego. Es gratis, es machine-readable y ya se consulta a Overpass en
este repo para obra moderna, así que no añade dependencias.

**No sustituye a los catálogos oficiales ni pretende ser exhaustivo.** Sirve para
lo mismo que la fusión anterior: comprobar si el metro con el que se mide sigue
teniendo agujeros, y por dónde.

## Cautelas

- **Un `archaeological_site` no es un castro.** Se filtra por `site_type` y por
  el nombre, con las mismas raíces que usa el resto del proyecto —`castro`,
  `croa`, `cividade`, `citania`— y excluyendo `castrelo` y `castiñeiro`, que solo
  comparten raíz.
- **Puede haber duplicados con lo que ya tenemos.** Este script solo baja y
  normaliza; la deduplicación la hace quien fusione, igual que con
  patrimoniogalego, y midiendo la distancia.
- Se pide por provincia y no de una vez: Galicia entera en una consulta hace
  trabajar a Overpass más de lo razonable para un servicio público.
- **Se pide por ÁREA ADMINISTRATIVA, no por recuadro.** La primera versión usaba
  recuadros y los de Ourense y Pontevedra cruzaban la frontera: devolvieron el
  `Castelo de Lindoso`, el `Acampamento Romano do Alto da Pedrada` y otros seis
  sitios **portugueses**. El norte de Portugal es el conjunto de prueba
  precintado (regla `15`), así que fusionar aquello habría metido el `test` en el
  catálogo de entrenamiento sin que nada fallara. Con `area["ISO3166-2"="ES-GA"]`
  la frontera la pone el propio OSM y no un rectángulo mío.

Uso:
    python3 scripts/scrape_castros_osm.py --out data/catalogo-externo/osm.tsv
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

ESPEJOS = ("https://overpass.kumi.systems/api/interpreter",
           "https://overpass-api.de/api/interpreter")
UA = "castros-ia (investigacion arqueologica no comercial)"

# **Provincias por area administrativa de OSM, no por recuadro.** Un recuadro no
# sabe donde acaba Galicia: los de Ourense y Pontevedra se metian en Portugal y
# traian sitios del conjunto de prueba precintado. `ISO3166-2` los delimita bien.
PROVINCIAS = {
    "a-coruna":   "ES-C",
    "lugo":       "ES-LU",
    "ourense":    "ES-OR",
    "pontevedra": "ES-PO",
}

# Que se pide. `site_type=fortification` es el literal de OSM para un recinto
# fortificado; `castle_type=hillfort` es como se etiqueta un castro cuando se
# mete por la rama de `castle`.
CONSULTAS = (
    '["historic"="archaeological_site"]["site_type"="fortification"]',
    '["historic"="castle"]["castle_type"="hillfort"]',
    '["historic"="archaeological_site"]["archaeological_site"="fortification"]',
)
# Y ademas, cualquier yacimiento arqueologico cuyo NOMBRE lo delate.
CONSULTA_NOMBRE = '["historic"="archaeological_site"]["name"]'

SI = re.compile(r"\b(castro|castros|croa|cividade|citania|castromao)\b", re.I)
NO = re.compile(r"castrelo|casti[nñ]eir|casta[nñ]eir", re.I)


def overpass(q, intentos=4):
    for i in range(intentos):
        try:
            req = urllib.request.Request(
                ESPEJOS[i % len(ESPEJOS)],
                data=urllib.parse.urlencode({"data": q}).encode(),
                headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=240) as r:
                return json.load(r)
        except Exception as e:
            print(f"    reintento {i+1}: {e}", flush=True)
            time.sleep(10 * (i + 1))
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--pausa", type=float, default=8.0,
                    help="segundos entre consultas: Overpass es publico")
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    vistos, filas = set(), []
    for prov, iso in PROVINCIAS.items():
        partes = [f"nwr{c}(area.p);" for c in CONSULTAS]
        partes.append(f"nwr{CONSULTA_NOMBRE}(area.p);")
        q = (f'[out:json][timeout:220];'
             f'area["ISO3166-2"="{iso}"]->.p;'
             f"({''.join(partes)});out center tags;")
        print(f"  {prov}...", flush=True)
        d = overpass(q)
        if d is None:
            print(f"    sin respuesta para {prov}"); continue
        n_prov = 0
        for el in d.get("elements", []):
            t = el.get("tags", {})
            nombre = t.get("name") or ""
            por_tipo = (t.get("site_type") == "fortification"
                        or t.get("castle_type") == "hillfort"
                        or t.get("archaeological_site") == "fortification")
            por_nombre = bool(SI.search(nombre)) and not NO.search(nombre)
            if not (por_tipo or por_nombre):
                continue
            c = el.get("center") or el
            lon, lat = c.get("lon"), c.get("lat")
            if lon is None or lat is None:
                continue
            clave = (el.get("type"), el.get("id"))
            if clave in vistos:
                continue
            vistos.add(clave)
            filas.append({
                "osm_type": el.get("type"), "osm_id": el.get("id"),
                "longitude": f"{float(lon):.6f}", "latitude": f"{float(lat):.6f}",
                "name": nombre[:90], "provincia": prov,
                "site_type": t.get("site_type") or t.get("castle_type")
                or t.get("archaeological_site") or "",
                "por": "tipo" if por_tipo else "nombre",
                "source": "OpenStreetMap (Overpass)",
            })
            n_prov += 1
        print(f"    {n_prov} castros", flush=True)
        time.sleep(args.pausa)

    if not filas:
        print("\nninguno: revisar las consultas antes de concluir que no hay")
        return 1
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        w_ = csv.DictWriter(fh, fieldnames=list(filas[0].keys()), delimiter="\t")
        w_.writeheader(); w_.writerows(filas)
    por_tipo = sum(1 for r in filas if r["por"] == "tipo")
    print(f"\nescrito: {args.out}")
    print(f"  total {len(filas)}  |  por etiqueta de tipo {por_tipo}  |  "
          f"solo por nombre {len(filas)-por_tipo}")
    print("\nLos de «solo por nombre» son los mas dudosos: un yacimiento llamado")
    print("«Castro» puede ser otra cosa. Se dejan marcados para que la fusion")
    print("decida, en vez de descartarlos aqui.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
