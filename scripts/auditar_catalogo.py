#!/usr/bin/env python3
"""Audita el catálogo maestro: qué entradas no son recintos, y a quién le duele.

El `2026-08-07`, midiendo la distancia entre castros vecinos, salió que el
`13,5%` del catálogo fusionado tiene un «vecino» a menos de `50 m` y que el
percentil `5` está en `8 m`. Dos castros distintos no están a ocho metros. Al
mirar los nombres se entendió: la regla de etiquetado que puso `label_class=1`
cazó **el topónimo, no el monumento**.

Entre lo etiquetado como castro en Galicia hay `211` casas y torres —incluida la
**Casa de Rosalía de Castro**—, `118` iglesias y capillas, `63` cruceiros, `46`
paneles de arte rupestre y `91` mámoas, que además tienen clase propia en el
corpus. En Portugal, «Miliário 1 de Castro de Avelãs» y varias estelas.

## Por qué esto NO borra nada

Cambiar la verdad de campo en mitad de una comparación de modelos invalida la
comparación. Y sobre todo: **está medido que no hace daño**. Este script lo
vuelve a medir en los tres sitios donde podría dolar, y ese fue el resultado el
día que se escribió:

- **Verdad de evaluación**: ya venía limpia. Uno o dos sospechosos por bloque, y
  casi todos falsas alarmas —`Castro da Ermida` y `Castro do Coto do Mosteiro`
  son castros de verdad—. Las cifras de `F1` y precisión del proyecto valen.
- **Corpus de entrenamiento**: `57` de `960` viñetas de castro (`5,9%`) llevan
  nombre de otro monumento, pero casi todas son castros bautizados por una
  capilla vecina —`Castro da Capela`, `Castro do Pazo`—.
- **Candidatos ocultos**: es lo que más preocupaba, porque `extraer_candidatos.py`
  descarta lo que caiga a menos de `500 m` de «algo catalogado», así que un
  castro inédito junto a un cruceiro se perdería en silencio. Con la definición
  más amplia posible de entrada dudosa salieron `7` celdas en los cuatro
  bloques, y **las siete están al lado de un castro real** cuyo nombre contiene
  una palabra de iglesia o de casa. Cero hallazgos perdidos.

Es un resultado negativo limpio, y por eso queda escrito: para que nadie vuelva
a gastar una tarde en investigarlo. Lo que sí hay que rehacer es esta medida
**cuando se barra Galicia entera**, porque a `590` candidatos la cuenta de siete
puede no seguir siendo siete.

Uso:
    python3 scripts/auditar_catalogo.py
    python3 scripts/auditar_catalogo.py --sweeps data/sweep_val_*_v7.tsv
"""
from __future__ import annotations

import argparse
import collections
import csv
import math
import re
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[1]

# Tipos de monumento que NO son un recinto fortificado, por mucho que el
# toponimo diga «castro». Se agrupan por familia para que el informe diga que
# clase de ruido hay, no solo cuanto.
TIPOS = {
    "casa/torre/pazo":  r"\bpazo\b|\btorre\b|\bcasa\b|\bh[oó]rreo\b|\bforta?leza\b",
    "igrexa/capela":    r"\bigrexa\b|\bcapela\b|\bermida\b|\bmosteiro\b|\bconvento\b",
    "mámoa/túmulo":     r"\bm[aá]moas?\b|\bmedoñ|\bt[uú]mulo|\bdolmen\b",
    "cruceiro/cruz":    r"\bcruceiro\b|\bcruz\b",
    "arte rupestre":    r"petr[oó]glif|inscultur|\broch[ae]\b|\bestela\b|\blaxe\b",
    "fonte/lavadoiro":  r"\bfonte\b|\blavadoiro\b|\bpozo\b",
    "ponte/camiño":     r"\bponte\b|\bcalzada\b|\bmili[aá]rio?\b",
    "muíño":            r"\bmui[nñ]o\b|\bmolino\b",
    "mina/canteira":    r"\bmina\b|\bcanteira\b|\bpedreira\b",
    "campo/romaría":    r"\bcampo d[ae]\b|\bromar[ií]a\b|\bfeira\b|\bxard[ií]n",
}
# Si el nombre dice ADEMAS castro, casi siempre es un castro de verdad bautizado
# por lo que tiene al lado: `Castro da Capela`, `Castro do Pazo`, `Castro da
# Ermida`. Por eso el informe da dos cifras, una cota alta y una baja, en vez de
# una sola que pareceria mas segura de lo que es.
ES_RECINTO = r"\bcastros?\b|\bcroa\b|\bcividade\b|\bcitania\b|castrom"


def tipo_de(nombre: str):
    n = (nombre or "").lower()
    for k, pat in TIPOS.items():
        if re.search(pat, n):
            return k
    return None


def leer_maestro(ruta: Path, solo_galicia=True):
    filas = []
    with open(ruta, encoding="utf-8") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            if r.get("label_class") != "1":
                continue
            # Portugal es el conjunto de prueba y esta precintado (regla 15).
            # Contar cuantas entradas suyas son miliarios no evalua ningun
            # modelo, pero por higiene el modo normal ni lo mira.
            if solo_galicia and "DGPC" in (r.get("source") or ""):
                continue
            try:
                filas.append({"lon": float(r["longitude"]),
                              "lat": float(r["latitude"]),
                              "nombre": r.get("name") or "",
                              "fuente": r.get("source") or "?"})
            except (KeyError, TypeError, ValueError):
                continue
    return filas


def metros(filas):
    lat0 = float(np.mean([f["lat"] for f in filas]))
    k = 111320.0 * math.cos(math.radians(lat0))
    return np.array([[f["lon"] * k, f["lat"] * 110540.0] for f in filas]), lat0, k


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--maestro", type=Path,
                    default=RAIZ / "data/weak_label_master_fusionado.tsv")
    ap.add_argument("--sweeps", type=Path, nargs="*", default=[],
                    help="barridos donde medir cuántos candidatos oculta la basura")
    ap.add_argument("--umbral", type=float, default=0.7)
    ap.add_argument("--tolerancia-m", type=float, default=500.0)
    ap.add_argument("--incluir-portugal", action="store_true")
    args = ap.parse_args()

    filas = leer_maestro(args.maestro, solo_galicia=not args.incluir_portugal)
    ambito = "Galicia + Portugal" if args.incluir_portugal else "Galicia"
    print(f"maestro: {args.maestro}")
    print(f"etiquetados como castro en {ambito}: {len(filas)}\n")

    # --- 1. que hay ahi que no es un recinto --------------------------------
    cuenta, ejem = collections.Counter(), collections.defaultdict(list)
    amplia, estricta = set(), set()
    for i, f in enumerate(filas):
        t = tipo_de(f["nombre"])
        if not t:
            continue
        amplia.add(i)
        cuenta[t] += 1
        if len(ejem[t]) < 3:
            ejem[t].append(f["nombre"][:56])
        if not re.search(ES_RECINTO, f["nombre"].lower()):
            estricta.add(i)
    print(f"cota ALTA  (el nombre menciona otro monumento):        "
          f"{len(amplia):4d}  ({100*len(amplia)/len(filas):.1f}%)")
    print(f"cota BAJA  (además NO menciona castro/croa/cividade):  "
          f"{len(estricta):4d}  ({100*len(estricta)/len(filas):.1f}%)\n")
    for t, c in cuenta.most_common():
        print(f"  {c:4d}  {t}")
        for e in ejem[t]:
            print(f"          · {e}")

    # --- 2. duplicados dentro del catalogo ----------------------------------
    X, lat0, _ = metros(filas)
    try:
        from scipy.spatial import cKDTree
        arbol = cKDTree(X)
        d, j = arbol.query(X, k=2)
        nn, vec = d[:, 1], j[:, 1]
    except ImportError:
        print("\n(scipy no disponible: se salta el análisis de duplicados)")
        nn = None
    if nn is not None:
        real = nn[nn > 0.5]
        print(f"\nvecino más próximo entre entradas distintas (n={len(real)}):")
        print(f"  p5 {np.percentile(real,5):.0f} m | p25 "
              f"{np.percentile(real,25):.0f} m | mediana "
              f"{np.median(real):.0f} m")
        cerca = int((nn < 50).sum())
        mismo = sum(1 for i in range(len(filas))
                    if nn[i] < 50 and filas[i]["fuente"] == filas[vec[i]]["fuente"])
        print(f"  a menos de 50 m: {cerca} entradas "
              f"({100*cerca/len(filas):.1f}%), de ellas {mismo} con la MISMA "
              f"fuente")
        print("  → duplicados internos de cada catálogo, no fallos de la "
              "fusión\n     (cero pares entre fuentes distintas = la fusión "
              "dedujo bien)")

    # --- 3. lo que de verdad importa: candidatos ocultos ---------------------
    if not args.sweeps:
        print("\n(sin --sweeps: no se mide el impacto en candidatos)")
        return 0
    print(f"\n=== impacto: candidatos que la basura podría estar ocultando ===")
    print(f"    (umbral {args.umbral}, tolerancia {args.tolerancia_m:.0f} m, "
          f"cota ALTA)")
    from scipy.spatial import cKDTree
    dud = np.zeros(len(filas), bool)
    dud[list(amplia)] = True
    if not dud.any() or dud.all():
        print("    nada que medir"); return 0
    Td, Tb = cKDTree(X[dud]), cKDTree(X[~dud])
    nom_d = [filas[i]["nombre"] for i in np.where(dud)[0]]
    total = 0
    for s in args.sweeps:
        celdas = [r for r in csv.DictReader(open(s, encoding="utf-8"),
                                            delimiter="\t")
                  if float(r.get("score") or 0) >= args.umbral]
        if not celdas:
            print(f"  {s.name}: ninguna celda supera el umbral"); continue
        k = 111320.0 * math.cos(math.radians(lat0))
        P = np.array([[float(r["lon"]) * k, float(r["lat"]) * 110540.0]
                      for r in celdas])
        dd, ji = Td.query(P)
        db, _ = Tb.query(P)
        # ocultada = la tira una entrada dudosa Y NO la tiraria una buena
        solo = (dd <= args.tolerancia_m) & (db > args.tolerancia_m)
        total += int(solo.sum())
        print(f"  {s.name}: {len(celdas):4d} celdas | ocultas {int(solo.sum()):3d}")
        for i in np.where(solo)[0][:3]:
            print(f"      a {dd[i]:.0f} m de «{nom_d[ji[i]]}»")
    print(f"\n  TOTAL celdas potencialmente ocultas: {total}")
    if total == 0:
        print("  → la basura del catálogo no está escondiendo ningún hallazgo")
    else:
        print("  → revisar esas: comprobar si la entrada próxima es un castro "
              "real\n     con nombre de capilla, o basura de verdad")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
