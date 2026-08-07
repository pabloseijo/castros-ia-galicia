#!/usr/bin/env python3
"""Triaje automático de candidatos: todo lo comprobable sin pisar el monte.

Diseñado para lo que viene. Hoy se ha barrido el `8,5%` de Galicia y han salido
`50` candidatos sin catalogar; a esa densidad, Galicia entera daría del orden de
`590`. Revisarlos a mano de uno en uno no escala, y **la mayor parte del descarte
no exige criterio arqueológico**: una cantera es una cantera y un terraplén de
autovía es un terraplén de autovía.

Así que esto hace las comprobaciones que una máquina puede hacer, deja cada
candidato con una **puntuación y un motivo escrito**, y produce la lista ordenada
que un humano sí tiene que mirar. No decide: **prioriza y explica**.

Sigue el bucle de Bickler y colegas (*Scientific Reports* `2023`,
`10.1038/s41598-023-36015-5`): el modelo propone, el experto revisa en su SIG, y
**sus veredictos vuelven al conjunto de entrenamiento**. Por eso la salida es un
CSV con columna `veredicto` vacía para rellenar, y no un informe cerrado.

## Las seis comprobaciones, y por qué cada una

1. **¿Ya está catalogado?** Distancia al yacimiento conocido más próximo, de
   cualquier clase. Un candidato a `60 m` de un castro conocido no es hallazgo:
   es el mismo sitio con la coordenada corrida.
2. **¿Está donde va un castro?** Prominencia, dominancia y llaneza, calibradas
   contra castros conocidos: los `12` de Ourense dan **`23`-`53 m` de
   prominencia, sin excepción**.
3. **¿Hay obra moderna encima?** Se pregunta a OpenStreetMap por cantera,
   polígono, vertedero, presa, enlace de autovía o edificio en el radio. Se usa
   **el vector, no la imagen**: un clasificador de ortofoto se probó el
   `2026-08-07` y salió **anticorrelado** —consideraba los castros reales más
   modernos que los falsos positivos, porque aprendió «rural contra urbano» y en
   la ría de Vigo los castros están rodeados de urbanización—.
4. **¿Lo dice el topónimo?** `castro`, `croa`, `cividade`, `coto`, `medorra`,
   `cerca`... En Galicia el nombre del sitio recuerda lo que hubo mucho después
   de que el sitio deje de verse. Es la comprobación más barata y de las más
   informativas.
5. **¿Se puede fiar uno del dato?** Densidad de puntos de suelo. Con el `14%` de
   retornos llegando al suelo —medido en `LU-8`— el modelo digital es ruido y
   cualquier lectura morfológica vale poco.
6. **¿Hay paisaje arqueológico alrededor?** Mámoas y petroglifos cerca no prueban
   nada por sí solos, pero un castro aparece antes donde ya hay prehistoria
   documentada que en medio de la nada.

**Ninguna de las seis confirma nada.** Sirven para **descartar barato** y para
ordenar la cola. La confirmación empieza donde acaba esto: regla `16`.

Uso:
    python3 scripts/verificar_candidatos.py --candidatos data/candidatos_ourense.tsv \\
        --laz-dir data/external/lidar-val-ourense --out data/triaje_ourense
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

import numpy as np

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "scripts"))

# **El maestro FUSIONADO, no el original.** Hasta el 2026-08-07 esto apuntaba a
# `weak-label-splits-v1/weak_label_master.tsv`, que tiene `3.929` castros: los de
# la Xunta y nada mas. El fusionado tiene `4.080` porque incorpora los `151` de
# patrimoniogalego. Con el maestro viejo, un candidato plantado encima de un
# castro que solo conoce el catalogo social salia como «lejos de lo catalogado»
# y subia en la cola. Todo el trabajo de fusionar catalogos no servia de nada si
# el triaje seguia preguntandole al de antes.
MAESTRO = RAIZ / "data/weak_label_master_fusionado.tsv"

# Distancia por debajo de la cual un candidato NO es un hallazgo, sino el mismo
# sitio con la coordenada corrida. No es una constante elegida a ojo: es el
# contrato de `extraer_candidatos.py`, que ya descarta con `--tolerancia-m 500`
# contra el catalogo entero. Si algo llega aqui por debajo de eso, la entrada
# esta rancia o se genero sin el arreglo del desborde de recuadro.
#
# **Hizo falta porque el decaimiento gaussiano no basta.** Un candidato a `22 m`
# del Castro da Igrexa/Castro de Lebruxo cobraba `-2,0` por cercania y luego
# recuperaba `+2` de prominencia y `+1` de dominancia —porque ES un castro y por
# eso su topografia es inmejorable— y acababa **tercero de la lista**. La
# gaussiana esta bien para la zona ambigua, la del Coto do Mosteiro a `104 m`,
# donde de verdad puede haber dos sitios distintos. Por debajo, ninguna
# topografia excelente debe rescatar nada: es el mismo monumento.
DIST_MISMO_SITIO_M = 500.0
ESPEJOS = ("https://overpass-api.de/api/interpreter",
           "https://overpass.kumi.systems/api/interpreter")
UA = "castros-ia (investigacion arqueologica)"

# Raices de toponimo que en Galicia delatan un yacimiento. `croa` es la
# plataforma superior de un castro; `cividade` y `castro` son literales;
# `medorra` es tumulo; `coto` y `cerca` son mas debiles y puntuan menos.
TOPONIMOS = {"castro": 3, "castrom": 3, "cividade": 3, "croa": 3, "crus": 0,
             "medorra": 2, "mamoa": 2, "modorra": 2, "cast": 1,
             "coto": 1, "cerca": 1, "torre": 1, "outeiro": 1}

# Lo que descalifica: si esto esta encima, el relieve es moderno.
MODERNO = ('["landuse"~"quarry|industrial|landfill|construction"]',
           '["man_made"~"storage_tank|water_tower|wastewater_plant"]',
           '["waterway"="dam"]', '["highway"="motorway_junction"]',
           '["leisure"~"pitch|golf_course|stadium"]')


def overpass(consulta, intentos=4):
    for i in range(intentos):
        url = ESPEJOS[i % len(ESPEJOS)]
        try:
            req = urllib.request.Request(
                url, data=urllib.parse.urlencode({"data": consulta}).encode(),
                headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.load(r)
        except Exception:
            time.sleep(6 * (i + 1))
    return None


def consultar_osm(lon, lat, radio=250):
    """Obra moderna y topónimos en el entorno, en una sola consulta."""
    partes = []
    for f in MODERNO:
        partes.append(f'nwr{f}(around:{radio},{lat},{lon});')
    partes.append(f'nwr["name"](around:{radio*2},{lat},{lon});')
    q = f"[out:json][timeout:120];({''.join(partes)});out center tags;"
    d = overpass(q)
    if d is None:
        return None, None
    moderno, nombres = [], []
    for el in d.get("elements", []):
        t = el.get("tags", {})
        if any(k in t for k in ("landuse", "man_made", "waterway", "highway",
                                "leisure")) and not t.get("name"):
            moderno.append(t.get("landuse") or t.get("man_made")
                           or t.get("waterway") or t.get("highway")
                           or t.get("leisure"))
        if t.get("name"):
            nombres.append(t["name"])
        for k in ("landuse", "man_made", "waterway", "leisure"):
            if t.get(k) in ("quarry", "industrial", "landfill", "construction",
                            "dam", "pitch", "golf_course", "stadium"):
                moderno.append(t[k])
    return sorted(set(moderno)), sorted(set(nombres))


def calibrar(valores, cola=2.0, piso=0.05, minimo_fisico=0.0):
    """Deriva umbral y sigma de los ejemplos conocidos, sin elegirlos a mano.

    **El umbral no es el minimo muestral.** Con `n = 12` el menor de los doce es
    una estimacion sesgada hacia arriba del suelo real de la poblacion: la
    probabilidad de que ninguno de doce cayera por debajo es alta. Los castros
    conocidos de Ourense dan media `39,7 m` y desviacion `10,6 m`, cuyo minimo
    muestral es `23,0` — pero el **percentil `2` estimado de la poblacion** esta
    en `17,9`. Usar `23` como corte descartaba el Castro do Coto do Mosteiro,
    que tiene `19,0 m` y esta excavado desde `1984`.

    **Y sigma tampoco se elige: se despeja.** Se pide que el caso fisicamente
    imposible —prominencia `0`, terreno llano— valga `piso`, y de ahi sale
    `sigma = umbral / sqrt(2 ln(1/piso))`. Asi el unico parametro que queda es
    interpretable: *«cuanto quiero que puntue un llano»*.

    Sobre los `12` de Ourense, con `cola = 2%` y `piso = 0.05`:

    | prominencia | factor |
    |---:|---:|
    | `23,0 m` (minimo conocido) | `1.00` |
    | **`19,0 m` (Coto do Mosteiro)** | **`1.00`** |
    | `15,0 m` | `0.93` |
    | `11,3 m` | `0.67` |
    | `5,0 m` | `0.21` |
    | `0,0 m` (llano) | `0.05` |

    Un candidato a cuatro metros del minimo conocido **no pierde nada**, que es
    lo razonable: quien levanto estos recintos no llevaba cinta metrica, y cuatro
    metros de diferencia no distinguen un castro de otra cosa.
    """
    v = np.asarray([x for x in valores if np.isfinite(x)], dtype=float)
    if len(v) < 5:
        raise ValueError("hacen falta al menos 5 ejemplos para calibrar")
    # **Percentil empirico, no ajuste normal.** Se probo con la normal y falla:
    # la distribucion de prominencias tiene un SUELO —un castro no se pone en un
    # llano— y la cola inferior no es gaussiana. Sobre los 36 castros del bloque
    # de Ourense (media 29,6, desviacion 13,6, minimo real 7,6) el ajuste normal
    # situaba el percentil 2 en **1,7 m**, muy por debajo del castro mas bajo que
    # existe, y con `sigma = 0,7` el criterio dejaba de discriminar: todo lo que
    # pasara de 1,7 m sacaba la puntuacion entera.
    #
    # El percentil empirico lo da el propio dato: `p5 = 10,8 m` con `n = 36`, que
    # es practicamente el segundo mas bajo observado. Respeta la distribucion en
    # vez de extrapolarla.
    umbral = max(float(np.percentile(v, cola * 2.5)), minimo_fisico)
    sigma = max(umbral - minimo_fisico, 1e-6) / math.sqrt(2 * math.log(1 / piso))
    return umbral, sigma


def decae(valor, umbral, sigma, mayor_mejor=True):
    """Decaimiento gaussiano en vez de umbral duro: `exp(-deficit^2 / 2 sigma^2)`.

    Es **Soft-NMS** (Bodla et al. 2017, `10.1109/iccv.2017.593`) trasladado: en
    vez de eliminar lo que no llega al umbral, **rebajarle la puntuacion en
    proporcion a cuanto le falta**. Es tambien lo que Pablo hizo en su TFG —
    lambda adaptativo por percentil en lugar de umbrales fijos—.

    **Lo pedia un caso caro.** Con umbral duro en `23 m`, el candidato `OU-1`
    quedaba fuera por tener `19,0`... y `OU-1` es el **Castro do Coto do
    Mosteiro**, excavado en `1984`, publicado, con material en el Museo
    Arqueoloxico de Ourense. Un corte sacado de doce ejemplos habria tirado un
    castro de la Edad del Hierro por cuatro metros.

    Los dos parametros salen de `calibrar`, no de la intuicion.
    """
    d = (umbral - valor) if mayor_mejor else (valor - umbral)
    if d <= 0:
        return 1.0
    return float(math.exp(-(d * d) / (2.0 * sigma * sigma)))


# Lo que NO cuenta aunque lleve la raiz dentro. Medido el 2026-08-07: el
# emparejador marcaba «Castrelo de Miño» —nombre del concello, sale en todos sus
# candidatos por igual— y «Rúa do Outeiro», que es una calle.
VIARIO = ("rúa ", "rua ", "calle ", "avenida ", "camiño ", "camino ",
          "estrada ", "carretera ", "praza ", "plaza ", "travesía ")


def puntuar_toponimo(nombres, concello=""):
    """El mejor topónimo delator del entorno, o `0` si ninguno lo es.

    **Ojo con lo que parece topónimo y no lo es.** Se descartan los nombres de
    viario —una «Rúa do Outeiro» no dice que ahí hubiera un outeiro
    arqueológico— y el nombre del propio concello, porque sale en todos sus
    candidatos por igual y no distingue nada. `Castrelo de Miño` marcaba `castr`
    en cuatro candidatos de Ourense sin aportar ni un bit.
    """
    mejor, cual = 0, ""
    conc = (concello or "").lower().strip()
    for n in nombres or []:
        b = n.lower().strip()
        if any(b.startswith(v) for v in VIARIO):
            continue
        if conc and (b == conc or b.startswith(conc)):
            continue
        for raiz, p in TOPONIMOS.items():
            if raiz in b and p > mejor:
                mejor, cual = p, n
    return mejor, cual


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--candidatos", type=Path, required=True)
    ap.add_argument("--laz-dir", type=Path, nargs="+", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--radio-osm", type=float, default=250.0)
    ap.add_argument("--calibrar-con", type=Path, default=None,
                    help="TSV de castros conocidos del mismo bloque; de ellos "
                         "salen umbral y sigma en vez de constantes")
    ap.add_argument("--sin-osm", action="store_true",
                    help="salta Overpass; útil si el servicio está caído")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    filas = list(csv.DictReader(open(args.candidatos, encoding="utf-8"),
                                delimiter="\t"))
    print(f"candidatos: {len(filas)}", flush=True)

    # --- 1. catalogo ---------------------------------------------------------
    cast, patr = [], []
    with open(MAESTRO, encoding="utf-8") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            try:
                p = (float(r["longitude"]), float(r["latitude"]),
                     r.get("name", ""), r.get("municipality", ""))
            except (KeyError, TypeError, ValueError):
                continue
            patr.append(p)
            if r["label_class"] == "1":
                cast.append(p)
    k = 111320.0

    def dist(lon, lat, pts):
        best, info = 1e9, ("", "")
        for x, y, n, m in pts:
            d = math.hypot((lon-x)*k*math.cos(math.radians(lat)), (lat-y)*k)
            if d < best:
                best, info = d, (n, m)
        return best, info

    # --- 2. topografia -------------------------------------------------------
    from contexto_topografico import medir
    from build_trasancos_vignettes import (grid_from_points,
                                           group_samples_by_tiles,
                                           lonlat_to_utm29)
    import laspy
    ext, res = 540.0, 2.0
    celdas = [{"id": i, "x": lonlat_to_utm29(float(r["lon"]), float(r["lat"]))[0],
               "y": lonlat_to_utm29(float(r["lon"]), float(r["lat"]))[1],
               "lon": float(r["lon"]), "lat": float(r["lat"])}
              for i, r in enumerate(filas)]
    tiles = sorted(str(p) for d in args.laz_dir for p in Path(d).glob("*.laz"))
    grupos, _ = group_samples_by_tiles(celdas, tiles, ext)
    topo, dens = {}, {}
    for tp, cs in grupos.items():
        xs, ys, zs = [], [], []
        for t in tp:
            try:
                with laspy.open(t) as fh:
                    for p in fh.chunk_iterator(4_000_000):
                        kk = np.asarray(p.classification) == 2
                        if not kk.any():
                            continue
                        xs.append(np.asarray(p.x)[kk].astype(np.float32))
                        ys.append(np.asarray(p.y)[kk].astype(np.float32))
                        zs.append(np.asarray(p.z)[kk].astype(np.float32))
            except Exception:
                continue
        if not xs:
            continue
        X = np.concatenate(xs); Y = np.concatenate(ys); Z = np.concatenate(zs)
        for c in cs:
            h = ext / 2.0
            b = (c["x"]-h, c["y"]-h, c["x"]+h, c["y"]+h)
            m = (X >= b[0]) & (X <= b[2]) & (Y >= b[1]) & (Y <= b[3])
            if m.sum() < 2000:
                continue
            dens[c["id"]] = float(m.sum() / (ext*ext))
            dem = grid_from_points(X[m], Y[m], Z[m], b, res)
            if dem is None or np.ndim(dem) != 2:
                continue
            r = medir(dem, res, 60.0, 250.0)
            if r:
                topo[c["id"]] = r
        del X, Y, Z
    print(f"topografía leída: {len(topo)}/{len(filas)}", flush=True)

    # **Calibrar contra castros conocidos del propio bloque**, no contra
    # constantes. Si no los hay, se usa el valor de Ourense como respaldo y se
    # dice, para que nadie confunda una calibracion local con una heredada.
    u_prom, s_prom = 17.9, 7.3
    if args.calibrar_con and Path(args.calibrar_con).exists():
        conocidos = list(csv.DictReader(open(args.calibrar_con, encoding="utf-8"),
                                        delimiter="\t"))
        cel2, proms = [], []
        for j, r in enumerate(conocidos[:40]):
            x2, y2 = lonlat_to_utm29(float(r["lon"]), float(r["lat"]))
            cel2.append({"id": j, "x": x2, "y": y2,
                         "lon": float(r["lon"]), "lat": float(r["lat"])})
        g2, _ = group_samples_by_tiles(cel2, tiles, ext)
        for tp, cs in g2.items():
            xs, ys, zs = [], [], []
            for tt in tp:
                try:
                    with laspy.open(tt) as fh:
                        for pp in fh.chunk_iterator(4_000_000):
                            kk = np.asarray(pp.classification) == 2
                            if not kk.any():
                                continue
                            xs.append(np.asarray(pp.x)[kk].astype(np.float32))
                            ys.append(np.asarray(pp.y)[kk].astype(np.float32))
                            zs.append(np.asarray(pp.z)[kk].astype(np.float32))
                except Exception:
                    continue
            if not xs:
                continue
            X = np.concatenate(xs); Y = np.concatenate(ys); Z = np.concatenate(zs)
            for c in cs:
                h = ext / 2.0
                b = (c["x"]-h, c["y"]-h, c["x"]+h, c["y"]+h)
                m = (X >= b[0]) & (X <= b[2]) & (Y >= b[1]) & (Y <= b[3])
                if m.sum() < 2000:
                    continue
                dem = grid_from_points(X[m], Y[m], Z[m], b, res)
                if dem is None or np.ndim(dem) != 2:
                    continue
                rr = medir(dem, res, 60.0, 250.0)
                if rr:
                    proms.append(rr["prominencia_m"])
            del X, Y, Z
        if len(proms) >= 5:
            u_prom, s_prom = calibrar(proms)
            print(f"calibrado con {len(proms)} castros conocidos del bloque: "
                  f"umbral {u_prom:.1f} m, sigma {s_prom:.1f} m", flush=True)
        else:
            print(f"solo {len(proms)} castros con lectura: se usan los valores "
                  f"de Ourense (umbral {u_prom} m)", flush=True)
    else:
        print(f"sin --calibrar-con: valores de Ourense "
              f"(umbral {u_prom} m, sigma {s_prom} m)", flush=True)

    # --- 3-6. OSM, toponimo, patrimonio --------------------------------------
    salida = []
    for i, r in enumerate(filas):
        lon, lat, sc = float(r["lon"]), float(r["lat"]), float(r["score"])
        d_cast, info_c = dist(lon, lat, cast)
        d_patr, info_p = dist(lon, lat, patr)
        mod, nombres = (None, None) if args.sin_osm else \
            consultar_osm(lon, lat, args.radio_osm)
        if not args.sin_osm:
            time.sleep(3)
        tp_p, tp_n = puntuar_toponimo(nombres, info_p[1])
        t = topo.get(i, {})

        # Puntuacion: suma de indicios, con el motivo escrito al lado.
        pts, motivos = 0.0, []
        # **Guardian de sitio ya catalogado, antes de puntuar nada.** Ver
        # `DIST_MISMO_SITIO_M`. Se marca en `veredicto` en vez de borrarlo, para
        # que quede el rastro de por que no esta en la cola: un candidato que
        # desaparece sin explicacion se vuelve a proponer en el siguiente barrido.
        ya = d_cast < DIST_MISMO_SITIO_M
        # Todo lo continuo entra con decaimiento gaussiano, no con umbral duro.
        # Ver `decae` y el caso del Castro do Coto do Mosteiro.
        f_dup = decae(d_cast, 400.0, 250.0)          # cerca de un conocido: penaliza
        if f_dup < 0.9:
            pts -= 3 * (1 - f_dup)
            motivos.append(f"a {d_cast:.0f} m de castro conocido")
        f_lejos = decae(d_cast, 1000.0, 500.0)
        if f_lejos > 0.3:
            pts += 1 * f_lejos; motivos.append("lejos de lo catalogado")
        if t:
            f_prom = decae(t["prominencia_m"], u_prom, s_prom)
            pts += 2 * f_prom
            motivos.append(f"prominencia {t['prominencia_m']:.0f} m "
                           f"(x{f_prom:.2f})")
            f_dom = decae(t["pct_entorno_debajo"], 0.85, 0.20)
            pts += 1 * f_dom
            if f_dom > 0.5:
                motivos.append(f"domina el {100*t['pct_entorno_debajo']:.0f}%")
        if mod:
            pts -= 3; motivos.append("obra moderna: " + ", ".join(mod[:3]))
        if tp_p >= 2:
            pts += tp_p; motivos.append(f"topónimo «{tp_n}»")
        if d_patr < 1500:
            pts += 0.5; motivos.append("paisaje arqueológico próximo")
        dd = dens.get(i)
        if dd is not None:
            f_den = decae(dd, 1.0, 0.4)
            if f_den < 0.9:
                pts -= 1 * (1 - f_den)
                motivos.append(f"LiDAR pobre ({dd:.2f} pt/m²)")

        salida.append({
            "n": i+1, "lon": f"{lon:.6f}", "lat": f"{lat:.6f}",
            "score_modelo": f"{sc:.3f}", "triaje": f"{pts:.1f}",
            "d_castro_m": f"{d_cast:.0f}", "castro_proximo": info_c[0][:36],
            "concello": info_p[1][:22],
            "prominencia_m": f"{t.get('prominencia_m', float('nan')):.1f}" if t else "",
            "pct_domina": f"{100*t['pct_entorno_debajo']:.0f}" if t else "",
            "densidad_suelo": f"{dd:.2f}" if dd else "",
            "obra_moderna": ", ".join(mod[:3]) if mod else "",
            "toponimo": tp_n,
            "motivos": " | ".join(motivos),
            "veredicto": "YA CATALOGADO" if ya else "",
            "revisor": "guardián automático" if ya else "", "notas": "",
        })
        print(f"  {i+1}/{len(filas)} triaje {pts:+.1f}"
              + (f"  *** YA CATALOGADO: {d_cast:.0f} m de "
                 f"{info_c[0][:40]} ***" if ya else ""), flush=True)

    salida.sort(key=lambda r: -float(r["triaje"]))
    dest = args.out / (args.candidatos.stem + "_triaje.csv")
    with open(dest, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(salida[0].keys()))
        w.writeheader(); w.writerows(salida)
    print(f"\nescrito: {dest}")
    print("\nLas columnas `veredicto`, `revisor` y `notas` van vacías a "
          "propósito:\nse rellenan al revisar y ese resultado vuelve al corpus. "
          "Ver regla 16.")
    # **El corte de prioridad es relativo al bloque, no absoluto.** Un umbral
    # fijo no vale porque la puntuacion no significa lo mismo en dos sitios: la
    # calibracion de la prominencia sale de los castros conocidos del propio
    # bloque —`10,8 m` en Ourense, `5,6 m` en Lugo— asi que el mismo candidato
    # sacaria notas distintas segun donde este. Con corte fijo en `3` salian `14
    # de 16` en Ourense y `2 de 6` en A Coruna, que no compara nada.
    #
    # El cuartil superior siempre selecciona la misma fraccion, que es lo que
    # una cola de revision necesita: «los mejores de aqui», no «los que pasan de
    # una nota que me invente».
    #
    # Los marcados `YA CATALOGADO` salen del calculo del cuartil ademas de salir
    # de la cola: si no, tres castros conocidos con topografia inmejorable suben
    # el percentil 75 y expulsan de la lista a candidatos que si eran nuevos.
    revisables = [r for r in salida if r["veredicto"] != "YA CATALOGADO"]
    n_ya = len(salida) - len(revisables)
    if n_ya:
        print(f"\n*** {n_ya} descartados por el guardián: a menos de "
              f"{DIST_MISMO_SITIO_M:.0f} m de un castro catalogado.")
        print("    No son hallazgos, es el mismo sitio. Si aparecen aquí, la "
              "entrada\n    viene sin el arreglo del desborde de recuadro "
              "(extraer_candidatos.py).")
    if not revisables:
        print("\nno queda ningún candidato revisable en este bloque")
        return 0
    v = np.array([float(r["triaje"]) for r in revisables])
    corte = float(np.percentile(v, 75)) if len(v) >= 4 else v.min()
    alto = [r for r in revisables if float(r["triaje"]) >= corte]
    print(f"\nrango de triaje en este bloque: {v.min():.2f} a {v.max():.2f}")
    print(f"prioridad alta (cuartil superior, corte {corte:.2f}): "
          f"{len(alto)} de {len(revisables)} revisables")
    for r in alto[:10]:
        print(f"  #{r['n']:>3} triaje {r['triaje']:>5} | {r['lat']},{r['lon']} "
              f"| {r['motivos'][:80]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
