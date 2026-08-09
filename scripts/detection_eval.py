#!/usr/bin/env python3
"""Evaluación a nivel de yacimiento, que es como mide el campo, más el VPP.

Hasta ahora este proyecto evaluaba **por celda**: cada viñeta acierta o falla y
de ahí salen recall y precisión. La literatura del dominio no hace eso, y por eso
nuestras cifras no eran comparables con las suyas.

Landauer et al. (2025) declara explícitamente que **los verdaderos negativos no
son significativos** —«el resto del paisaje puede considerarse esencialmente
TN»—, agrupa las detecciones y cuenta un acierto cuando el grupo cae a menos de
`500 m` de un yacimiento conocido. Reporta **F1 `36%`** sobre Inglaterra entera.
Canedo et al. (2025) hace lo mismo y llega a **F1 `66%`** tras minería de
negativos duros.

Este script produce las dos lecturas, porque responden preguntas distintas:

- **F1 con tolerancia de distancia**: sirve para compararnos con la literatura.
- **VPP a la tasa base real** (`1:475`): sirve para saber cuántas celdas hay que
  abrir en QGIS, que es lo que decide si el proyecto es viable para una persona.

Aplica además los cuatro filtros de despliegue de Canedo, en orden:

1. **Umbral de confianza.**
2. **Unión de detecciones solapadas**, para no contar el mismo sitio dos veces.
   Es lo que convierte «celdas» en «yacimientos candidatos».
3. **Área mínima**: descarta grupos de una sola celda, incoherentes con el tamaño
   de un castro. Es el filtro de tamaño que el plan ya había identificado como
   capaz de descartar el `96,7%` de las mámoas.
4. **Filtro de margen**: descarta detecciones pegadas al borde de la cobertura.
   Los objetos cortados por el borde de una tesela «suelen ser indicativos de
   falso positivo».

Uso:
    python3 scripts/detection_eval.py --pred barrido.tsv --truth castros.tsv
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from honest_eval import ppv_from, wilson  # noqa: E402

# Tasa base medida en el barrido propio de Trasancos: 91 castros / 43.215 celdas.
PREVALENCIA_DESPLIEGUE = 91 / 43215


def a_metros(lon, lat, lat0):
    """Proyección local rápida a metros. Suficiente para distancias de km.

    `lat0` es **obligatorio y compartido**: la primera versión lo calculaba como
    la media del array recibido, de modo que las predicciones y la verdad de
    campo acababan proyectadas a sistemas distintos y las distancias entre ambas
    no significaban nada. Se veía en que bajar el umbral perdía aciertos, lo cual
    es imposible. Un evaluador con ese fallo no da error: da cifras plausibles y
    falsas.
    """
    lon = np.asarray(lon, float)
    lat = np.asarray(lat, float)
    x = np.radians(lon) * 6371000.0 * math.cos(math.radians(lat0))
    y = np.radians(lat) * 6371000.0
    return x, y


def agrupar(x, y, enlace_m, min_vecinos=1):
    """Une detecciones a menos de `enlace_m`. Con `min_vecinos > 1`, por densidad.

    Rejilla y no matriz de distancias: un barrido de Galicia son millones de
    celdas y una matriz `n^2` no cabe en ninguna parte.

    ## Por que existe `min_vecinos`

    Con `min_vecinos = 1` esto es **enlace simple**, y el enlace simple
    **encadena**: basta un reguero de puntos separados por menos de `enlace_m`
    para soldar dos sitios que no tienen nada que ver. Medido en Lugo el
    2026-08-09 con un suelo de puntuacion de `0.30`: **un unico grupo se trago
    `5.325` puntos y `62` de los `63` castros del bloque**. Con la rejilla del
    barrido a `256 m` y un enlace de `512 m`, cada celda tiene vecinas por
    construccion, asi que el ruido de fondo suelda la malla entera.

    Se detecto por un sintoma imposible: **subir el suelo mejoraba** el resultado
    de las `100` primeras fichas, y las `100` mejores por puntuacion no pueden
    depender de donde este el suelo si el orden no cambia.

    La solucion esta documentada: **DB-NMS** (Yang et al.,
    `10.1007/s00521-021-06628-w`), *improving non-maximum suppression with
    density-based clustering*. Un punto solo une a sus vecinos si el mismo es
    **nucleo**, es decir, si tiene al menos `min_vecinos` a menos de `enlace_m`.
    Un reguero fino no cumple esa condicion, asi que **deja de encadenar**.

    El valor por defecto es `1` a proposito: reproduce exactamente el
    comportamiento anterior, de modo que ninguna cifra ya publicada cambia sin
    pedirlo. `--min-vecinos 3` activa el agrupado por densidad.
    """
    n = len(x)
    padre = list(range(n))

    def buscar(i):
        while padre[i] != i:
            padre[i] = padre[padre[i]]
            i = padre[i]
        return i

    def unir(i, j):
        ri, rj = buscar(i), buscar(j)
        if ri != rj:
            padre[rj] = ri

    celda = {}
    for i in range(n):
        celda.setdefault((int(x[i] // enlace_m), int(y[i] // enlace_m)), []).append(i)
    for (cx, cy), idxs in celda.items():
        vecinos = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                vecinos += celda.get((cx + dx, cy + dy), [])
        for i in idxs:
            # **Solo los nucleos unen.** Un punto con menos de `min_vecinos`
            # vecinos dentro del radio no propaga la union: puede acabar pegado a
            # un grupo si un nucleo lo alcanza, pero no sirve de puente entre dos.
            # Es lo que impide que un reguero de ruido suelde dos sitios.
            cercanos = [j for j in vecinos
                        if j != i and math.hypot(x[i] - x[j], y[i] - y[j]) <= enlace_m]
            if min_vecinos > 1 and len(cercanos) < min_vecinos:
                continue
            for j in cercanos:
                if j > i:
                    unir(i, j)
    grupos = {}
    for i in range(n):
        grupos.setdefault(buscar(i), []).append(i)
    return list(grupos.values())


def leer_tsv(path, cols=("lon", "lat")):
    filas = []
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            try:
                filas.append({c: float(r[c]) for c in cols if c in r}
                             | {k: v for k, v in r.items() if k not in cols})
            except (KeyError, TypeError, ValueError):
                continue
    return filas


def evaluar(pred, truth, umbral, enlace_m, min_celdas, margen_m, tol_m, lat0,
            mascara=None, min_vecinos=1):
    """`mascara` son yacimientos que el modelo vio en entrenamiento.

    Una detección que cae sobre uno de ellos no es prospección: es memoria. No
    puede sumar como acierto, pero tampoco es justo restarla como falso positivo
    —el sitio existe—. Se excluye de ambos recuentos, que es como se trata la
    contaminación de conjunto en cualquier evaluación honesta.
    """
    sel = [p for p in pred if p["score"] >= umbral]
    if not sel:
        return {"umbral": umbral, "detecciones": 0, "tp": 0, "fp": 0,
                "fn": len(truth), "precision": 0.0, "recall": 0.0, "f1": 0.0}

    px, py = a_metros([p["lon"] for p in sel], [p["lat"] for p in sel], lat0)
    grupos = agrupar(px, py, enlace_m, min_vecinos)

    # 3. area minima: un grupo de una sola celda no es un castro
    grupos = [g for g in grupos if len(g) >= min_celdas]

    centros = [(float(np.mean(px[g])), float(np.mean(py[g])), len(g)) for g in grupos]

    # 4. filtro de margen: fuera lo pegado al borde de la cobertura
    if margen_m > 0 and centros:
        ax, ay = a_metros([p["lon"] for p in pred], [p["lat"] for p in pred], lat0)
        x0, x1, y0, y1 = ax.min(), ax.max(), ay.min(), ay.max()
        centros = [c for c in centros
                   if x0 + margen_m <= c[0] <= x1 - margen_m
                   and y0 + margen_m <= c[1] <= y1 - margen_m]

    tx, ty = a_metros([t["lon"] for t in truth], [t["lat"] for t in truth], lat0)
    if mascara:
        mx, my = a_metros([m["lon"] for m in mascara],
                          [m["lat"] for m in mascara], lat0)
    encontrado = [False] * len(truth)
    tp = 0
    duplicadas = 0
    enmascaradas = 0
    for cx, cy, _ in centros:
        d = np.hypot(tx - cx, ty - cy)
        j = int(np.argmin(d)) if len(d) else -1
        if j >= 0 and d[j] <= tol_m:
            # **Un yacimiento se acierta una vez.** Antes cada detección que
            # caía sobre el mismo castro sumaba otro acierto, y con un enlace
            # corto eso infla la precisión sin encontrar nada nuevo: en Lugo, 44
            # de 92 «aciertos» eran el mismo sitio contado otra vez, y el F1
            # subía de 0.667 a 0.754 sin que cambiara ni un castro hallado.
            # La detección repetida no es un fallo —el sitio está ahí— pero
            # tampoco es un hallazgo: se excluye, como la máscara.
            if encontrado[j]:
                duplicadas += 1
            else:
                tp += 1
                encontrado[j] = True
            continue
        if mascara and np.hypot(mx - cx, my - cy).min() <= tol_m:
            enmascaradas += 1          # yacimiento visto en entrenamiento: no cuenta
    fp = len(centros) - tp - enmascaradas - duplicadas
    fn = sum(1 for e in encontrado if not e)
    evaluables = len(centros) - enmascaradas - duplicadas
    prec = tp / evaluables if evaluables > 0 else 0.0
    rec = sum(encontrado) / len(truth) if truth else float("nan")
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
    return {"umbral": umbral, "detecciones": len(centros), "tp": tp, "fp": fp,
            "enmascaradas": enmascaradas, "duplicadas": duplicadas,
            "fn": fn, "precision": prec, "recall": rec, "f1": f1,
            "recall_ci95": list(wilson(sum(encontrado), len(truth))) if truth else [0, 1]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pred", type=Path, required=True,
                    help="TSV del barrido con columnas lon, lat, score")
    ap.add_argument("--truth", type=Path, required=True,
                    help="TSV de yacimientos conocidos con lon, lat")
    ap.add_argument("--tolerancia-m", type=float, default=500.0,
                    help="distancia de acierto; 500 m es lo que usa Landauer")
    # Medido en Lugo el 2026-08-06 y validado dejando un concello fuera: la
    # configuración anterior (`enlace 256`, `min-celdas 2`) estaba **al revés**.
    # Exigía dos celdas a un umbral tan bajo que el ruido también produce
    # parejas, y a la vez fundía detecciones vecinas en cúmulos cuyo centro se
    # aleja del yacimiento. Lo correcto es **enlace corto y aceptar celda
    # única**, dejando que el umbral haga el filtrado: 8 de los 9 pliegues
    # eligieron `0.70 / 128 / 1` por su cuenta. F1 honesto `0.618` contra `0.590`.
    ap.add_argument("--enlace-m", type=float, default=512.0,
                    help="distancia para unir detecciones vecinas")
    ap.add_argument("--min-vecinos", type=int, default=1,
                    help="1 = enlace simple (el de siempre); >1 = agrupado por densidad, que impide que un reguero de ruido suelde dos sitios")
    ap.add_argument("--min-celdas", type=int, default=1,
                    help="un castro puede caer en una sola celda; filtrar por "
                         "tamaño de cúmulo cuesta más recall del que ahorra")
    ap.add_argument("--margen-m", type=float, default=0.0)
    ap.add_argument("--umbrales", type=float, nargs="+",
                    default=[0.3, 0.5, 0.6, 0.7, 0.8])
    ap.add_argument("--romper-precinto", metavar="MOTIVO", default=None,
                    help="obligatorio para evaluar sobre el conjunto de prueba "
                         "precintado (norte de Portugal). Cada mirada al test lo "
                         "convierte en validación: se rompe una vez, al final. "
                         "Ver data/PRECINTO-TEST.md")
    ap.add_argument("--mascara", type=Path,
                    help="TSV de yacimientos vistos en entrenamiento; las "
                         "detecciones sobre ellos se excluyen del recuento")
    ap.add_argument("--out-json", type=Path)
    args = ap.parse_args()

    pred = [p for p in leer_tsv(args.pred, ("lon", "lat", "score"))
            if "score" in p]
    for p in pred:
        p["score"] = float(p["score"])
    if "portugal" in str(args.truth).lower() or "-test-" in str(args.truth).lower():
        if not args.romper_precinto:
            raise SystemExit(
                "PRECINTO: '%s' es conjunto de PRUEBA y no se toca hasta cerrar "
                "el modelo sobre Galicia.\nSi de verdad toca romperlo, pasa "
                "--romper-precinto \"motivo\". Lee data/PRECINTO-TEST.md primero."
                % args.truth.name)
        import datetime as _dt
        _pre = Path(__file__).resolve().parent.parent / "data/PRECINTO-TEST.md"
        if _pre.exists():
            with open(_pre, "a", encoding="utf-8") as _fh:
                _fh.write("\n- **%s** — %s (verdad: `%s`)\n"
                          % (_dt.date.today().isoformat(),
                             args.romper_precinto, args.truth.name))
        print("*** PRECINTO ROTO: %s ***" % args.romper_precinto, flush=True)
    truth = leer_tsv(args.truth)
    mascara = leer_tsv(args.mascara) if args.mascara else None
    print(f"predicciones: {len(pred)} | yacimientos conocidos: {len(truth)}",
          flush=True)
    if not pred or not truth:
        raise SystemExit("faltan predicciones o verdad de campo")

    # Una sola latitud de referencia para todo, o las distancias no comparan.
    lat0 = float(np.mean([t["lat"] for t in truth]))

    # **La cobertura, antes de cualquier cifra.** Un barrido que se paró a medias
    # da un F1 plausible y falso: mide los agujeros, no el modelo. Ha pasado tres
    # veces —el primer Lugo al 59%, Pontevedra al 76%, el Lugo de v5 al 74%— y
    # cada vez la cifra parecía razonable. Va aquí y no en el guion de turno,
    # porque el guion se olvida y esto no.
    _px, _py = a_metros([p["lon"] for p in pred], [p["lat"] for p in pred], lat0)
    _tx, _ty = a_metros([t["lon"] for t in truth], [t["lat"] for t in truth], lat0)
    _d = np.array([float(np.hypot(_px - _tx[i], _py - _ty[i]).min())
                   for i in range(len(_tx))])
    _cob = float((_d <= 256.0).mean())
    print("cobertura: %d de %d yacimientos con celda a <256 m (%.0f%%)"
          % ((_d <= 256).sum(), len(_d), 100 * _cob))
    if _cob < 0.95:
        print("*** AVISO: cobertura %.0f%%. Las cifras de abajo miden el barrido,"
              " no el modelo. %d yacimientos sin celda a <512 m. ***"
              % (100 * _cob, int((_d > 512).sum())), flush=True)
    filas = []
    print(f"\n{'umbral':>7} {'detec':>7} {'TP':>5} {'FP':>6} {'FN':>5} "
          f"{'prec':>6} {'recall':>7} {'F1':>7} {'VPP@1:475':>10}")
    for u in args.umbrales:
        r = evaluar(pred, truth, u, args.enlace_m, args.min_celdas,
                    args.margen_m, args.tolerancia_m, lat0, mascara,
                    args.min_vecinos)
        # El VPP se recalcula a la prevalencia real, que es lo unico trasladable.
        espec = 1 - (r["fp"] / max(len(pred), 1))
        r["vpp_tasa_real"] = ppv_from(r["recall"], espec, PREVALENCIA_DESPLIEGUE) \
            if r["recall"] == r["recall"] else float("nan")
        filas.append(r)
        print(f"{u:7.2f} {r['detecciones']:7d} {r['tp']:5d} {r['fp']:6d} "
              f"{r['fn']:5d} {r['precision']:6.3f} {r['recall']:7.3f} "
              f"{r['f1']:7.3f} {r['vpp_tasa_real']:10.4f}")

    mejor = max(filas, key=lambda r: r["f1"])
    print(f"\nmejor F1: {mejor['f1']:.3f} en umbral {mejor['umbral']:.2f} "
          f"(recall {mejor['recall']:.3f} "
          f"IC95% [{mejor['recall_ci95'][0]:.2f}, {mejor['recall_ci95'][1]:.2f}])")
    # Aquí había un veredicto automático —«por encima de Landauer, por debajo de
    # Canedo»— y **hay que no volver a escribirlo**. La propia revisión del
    # estado del arte de este proyecto lo prohíbe por escrito: «las métricas no
    # son comparables entre sí: cada trabajo define positivo, unidad de
    # evaluación y umbral de forma distinta. F1 66% de Canedo y F1 38% de
    # Landauer no miden lo mismo». Y el 0.66 de Canedo es **posterior** a que dos
    # arqueólogos revisaran su salida; compararle un número pre-revisión es
    # compararse contra otra etapa del proceso, no contra otro método.
    print("\nContexto, y NO es una comparación:")
    print("  Landauer et al. 2025 reporta F1 0.36 sobre Inglaterra entera.")
    print("  Canedo et al. 2025 reporta F1 0.66 TRAS una ronda de minería con")
    print("  dos arqueólogos revisando su salida.")
    print("  Ninguna de las dos define positivo, unidad ni umbral como aquí.")
    print("  Colocarse en esa escala exige replicar su protocolo, no su cifra.")

    if args.out_json:
        args.out_json.write_text(json.dumps(
            {"config": vars(args), "resultados": filas}, indent=2, default=str),
            encoding="utf-8")
        print(f"guardado: {args.out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
