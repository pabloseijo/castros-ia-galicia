#!/usr/bin/env python3
"""Barrido ciego sobre una rejilla, cortando del LiDAR y puntuando con la red.

Es la pieza que faltaba entre el modelo entrenado y `detection_eval.py`. Todo lo
medido hasta ahora en este proyecto se mide sobre **viñetas centradas en el
yacimiento**, lo que responde «¿sabe ordenar candidatos ya localizados?» y no
«¿sabe encontrarlos?». La distinción no es teórica: el ranker anterior tenía
`0.944` de AUC sobre holdouts y recuperó **el `18%`** en barrido ciego, porque
sus features eran concéntricas respecto al centro del recorte.

Dos decisiones vienen de la literatura, no de la intuición:

- **Paso de media ventana** (`50%` de solape). Landauer lo fijó empíricamente y
  Canedo lo justifica: garantiza que un sitio hipotético se vea **entero al menos
  una vez**. Es `4x` celdas, no el `16x` que costaría un solape del `75%`.
- **No se guardan las viñetas.** Un barrido de Trasancos a paso `256 m` son
  ~`11.000` recortes de `512x512x3`; escribirlos serían decenas de GB que solo
  se leen una vez. Se cortan, se puntúan y se tiran, y lo que se guarda es el
  TSV de coordenadas y puntuación, que pesa nada.

La salida alimenta directamente a `detection_eval.py`, que agrupa, filtra y
reporta F1 con tolerancia de distancia y VPP a la tasa base real.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
           "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_trasancos_vignettes import (channels_from_dem,  # noqa: E402
                                       diezmar_a_densidad, grid_from_points,
                                       group_samples_by_tiles, laz_bounds,
                                       lonlat_to_utm29)

GROUND_CLASS = 2


# --- PENDIENTE, y es la palanca grande del proyecto ---------------------------
#
# **La redundancia de 8,4x no es un problema de formato: es el orden del bucle.**
# `group_samples_by_tiles` agrupa celdas por su *conjunto* de teselas, y despues
# cada grupo abre las suyas. Una tesela compartida por ocho grupos se descomprime
# ocho veces: 5.145 lecturas para 611 teselas unicas.
#
# Medido el 2026-08-06: la descompresion es el 87,6% del coste y son 0,194 s de
# CPU por MB. Galicia son 113 horas-CPU en una pasada limpia, contra 953 con la
# redundancia actual — de 9,4 h de reloj a 79 h sobre 12 hilos. Y no lo arregla
# mas paralelismo: cada `laspy.read()` ya usa ~5 hilos, asi que con 2 obreros la
# maquina de 12 nucleos **ya esta saturada**.
#
# Dos arreglos, ambos **exactos por construccion** —mismos puntos, mismos
# numeros, nada que verificar—, al contrario que la cache de DEM, que exige
# reproducir el otro camino y ahi lleva tres intentos fallidos:
#
#   1. **Cache LRU de teselas.** Ordenar las tareas para que los grupos que
#      comparten teselas vayan seguidos, y retener las ultimas 6-8 leidas. Un
#      grupo toca 4 teselas como maximo, asi que la mayoria de relecturas pasan a
#      ser aciertos. ~15 lineas, captura la mayor parte del 8,4x.
#
#   2. **Recorrer por tesela y no por grupo.** Leer cada tesela una vez y volcar
#      sus puntos en todas las ventanas que la necesiten, cerrando ventanas segun
#      se completan. Es el 8,4x entero. Con ventanas de 512 m sobre teselas de
#      1 km, una ventana toca 4 teselas, asi que en orden de filas el numero de
#      ventanas abiertas queda acotado (~1,4 GB estimados, cabe).
#
# Prioridad alta: la descarga se paga una vez —ya hay 106 GB en disco— pero la
# redundancia se paga en **cada** barrido, y van siete en dos dias.


def cupo_vram(dev):
    """Limita la VRAM de ESTE proceso a la fraccion de `CASTROS_VRAM_FRAC`.

    Contexto (2026-08-08). La GPU del nodo estaba en `Exclusive_Process`: un solo
    contexto CUDA a la vez, aunque sobraran `7` de los `8` GB. Eso serializaba
    todo el trabajo de GPU y era la causa real de que el entrenamiento de v10 y
    el modelo de vision fallaran con «device is busy».

    Al pasarla a `Default` los procesos ya conviven, pero aparece el problema
    contrario: **compiten por la VRAM** y el que llega segundo muere con
    `CUDA error: out of memory`. Le paso al barrido de A Coruna nada mas
    arrancar el entrenamiento.

    El cupo lo arregla: cada proceso reserva como mucho su fraccion, asi que
    ninguno puede vaciarle la memoria a otro. Repartir `1.0` entre los procesos
    que vayan a convivir — p. ej. `0.45` el entrenamiento y `0.15` cada barrido.

    Es lo que hace un planificador de verdad (Slurm, Ray) al declarar recursos;
    aqui se hace a mano porque no hay ninguno instalado todavia.
    """
    import os

    import torch          # importado aqui: el modulo lo carga tarde a proposito

    if dev != "cuda":
        return
    f = os.environ.get("CASTROS_VRAM_FRAC")
    if not f:
        return
    try:
        frac = float(f)
    except ValueError:
        print(f"CASTROS_VRAM_FRAC no numerico: {f!r} — sin cupo", flush=True)
        return
    if not 0.0 < frac <= 1.0:
        print(f"CASTROS_VRAM_FRAC fuera de (0,1]: {frac} — sin cupo", flush=True)
        return
    torch.cuda.set_per_process_memory_fraction(frac)
    tot = torch.cuda.get_device_properties(0).total_memory / 2**30
    print(f"cupo de VRAM: {frac:.0%} de {tot:.1f} GB = {frac*tot:.1f} GB", flush=True)


def cortar_desde_dem(args_tuple):
    """Igual que `cortar_grupo`, pero leyendo el DEM ya rasterizado.

    Medido el `2026-08-06`: el barrido gasta el **`87,6%`** del tiempo
    descomprimiendo LAZ y además lo hace **`8,4` veces por tesela** —`5.145`
    lecturas para `611` teselas únicas—, porque agrupa celdas por conjunto de
    teselas y cada grupo vuelve a abrir las suyas. Rasterizar es el `1,1%`.

    Con la caché de `laz_a_dem.py` cada tesela se descomprimió **una vez**, y
    aquí solo se recorta del ráster.

    **No está lista, y el motivo está medido.** Comparada contra la vía del
    `.laz` sobre las mismas celdas: la orientación es correcta —correlación
    `0.987` tal cual, frente a `0.16` volteada— pero queda una diferencia media
    de `0,23 m` de cota, y tras `channels_from_dem`, que normaliza por ventana,
    la correlación de los canales baja hasta `0.53` en el peor caso.

    La causa es **desalineamiento sub-píxel**: el DEM bina desde el borde de su
    tesela, redondeado a metro entero (`np.floor(x.min())`), mientras que la
    rejilla del barrido arranca en `lonlat_to_utm29(bbox)`, una coordenada
    arbitraria. `int(round(...))` al recortar snapea hasta medio metro, y medio
    metro horizontal en ladera son decímetros de cota.

    **El arreglo es alinear la rejilla del barrido a metro entero de UTM**, no
    tocar la caché: así ambos binados caen en la misma retícula y el recorte es
    exacto. Queda pendiente de hacer y de volver a pasar `verificar_dem.py`, que
    es quien cazó esto.
    """
    # Las tareas se arman en un solo sitio y llevan siete elementos; esta via
    # solo usa los cuatro primeros. Se desempaqueta con holgura para no reventar
    # con un `ValueError` opaco el dia que alguien reactive `--dem-dir`, que
    # esta desactivado desde el 2026-08-06 por el desfase de binado.
    dem_paths, celdas, extent, res = args_tuple[:4]
    half = extent / 2.0
    trozos = []
    for dp in dem_paths:
        try:
            z = np.load(dp)
        except Exception:
            continue
        trozos.append((z["dem"], z["bounds"], float(z["res"])))
    if not trozos:
        return []
    salida = []
    for c in celdas:
        b = (c["x"] - half, c["y"] - half, c["x"] + half, c["y"] + half)
        n = int(round(extent / res))
        mosaico = np.full((n, n), np.nan, dtype=np.float32)
        for dem, bounds, r in trozos:
            minx, miny, maxx, maxy = [float(v) for v in bounds]
            # indices del recorte dentro de esta tesela, en pixeles
            c0 = int(round((b[0] - minx) / r)); c1 = c0 + n
            f0 = int(round((maxy - b[3]) / r)); f1 = f0 + n
            sc0, sf0 = max(c0, 0), max(f0, 0)
            sc1, sf1 = min(c1, dem.shape[1]), min(f1, dem.shape[0])
            if sc1 <= sc0 or sf1 <= sf0:
                continue
            hueco = np.isnan(mosaico[sf0-f0:sf1-f0, sc0-c0:sc1-c0])
            parche = dem[sf0:sf1, sc0:sc1]
            destino = mosaico[sf0-f0:sf1-f0, sc0-c0:sc1-c0]
            destino[hueco] = parche[hueco]
        cubierto = np.isfinite(mosaico)
        if cubierto.mean() < 0.30:
            continue
        if not cubierto.all():
            # **Vecino más próximo, no la mediana.** `grid_from_points` rellena
            # los huecos con `distance_transform_edt`, y rellenarlos aquí con la
            # mediana de la ventana daba valores completamente distintos justo en
            # las zonas sin retorno — que es donde más se nota, porque son
            # bosque cerrado, que es donde vive el castro que se busca. Era la
            # causa de que la caché no reprodujera el camino del `.laz`.
            try:
                from scipy import ndimage
                idx = ndimage.distance_transform_edt(
                    ~cubierto, return_distances=False, return_indices=True)
                mosaico = mosaico[tuple(idx)]
            except Exception:
                mosaico[~cubierto] = float(np.median(mosaico[cubierto]))
        arr = channels_from_dem(mosaico, res).astype(np.float16)
        salida.append((c["id"], c["lon"], c["lat"], arr))
    return salida


_CACHE_TESELA = {}
_CACHE_ORDEN = []
# **Ocho, y no cuatro.** La nota de abajo decía «cada una son ~400 MB en
# memoria» y por eso la caché se dejó en cuatro entradas. Medido el 2026-08-07
# sobre una tesela real de Lugo: `1.700.024` puntos de suelo, `x`,`y`,`z` en
# `float32` = **`20 MB`**, no `400`. El comentario erraba por veinte veces y
# estaba limitando la caché por un coste que no existe.
#
# Simulado sobre las `2.337` tareas del bloque de Lugo, con `2` obreros y lotes
# de `200`: con `4` entradas la redundancia es `2.83x` y con `8` baja a
# **`1.96x`**. De `8` en adelante no mejora —un grupo toca `4` teselas como
# máximo y el reúso se agota—, así que ocho es el punto donde deja de rendir.
# Cuesta `0,31 GB` entre los dos obreros.
_CACHE_MAX = 8


def _puntos_de_tesela(tp, laspy):
    """Puntos de suelo de una tesela, con caché LRU dentro del obrero.

    Aquí muere la redundancia de `8,4x`. El barrido agrupa celdas por conjunto
    de teselas y luego cada grupo abre las suyas, así que una tesela compartida
    por ocho grupos se descomprime ocho veces: `5.145` lecturas para `611`
    teselas únicas. Y descomprimir es el `87,6%` del coste — `0,194 s` de CPU por
    MB—, de modo que Galicia son `953` horas-CPU en vez de `113`.

    Como las tareas van ordenadas por conjunto de teselas, los grupos que
    comparten tesela caen seguidos y una caché de cuatro entradas convierte casi
    todas las relecturas en aciertos. **Es exacto por construcción**: devuelve
    los mismos puntos, así que no hay nada que verificar — al contrario que la
    caché de DEM, que exige reproducir el otro camino.

    Cuatro entradas y no más porque un grupo toca cuatro teselas como máximo
    (medido: mediana `2`, máximo `4`) y cada una son ~`400 MB` en memoria.
    """
    if tp in _CACHE_TESELA:
        _CACHE_ORDEN.remove(tp)
        _CACHE_ORDEN.append(tp)
        return _CACHE_TESELA[tp]
    xs_l, ys_l, zs_l = [], [], []
    try:
        with laspy.open(tp) as fh:
            for puntos in fh.chunk_iterator(4_000_000):
                keep = np.asarray(puntos.classification) == GROUND_CLASS
                if not keep.any():
                    continue
                xs_l.append(np.asarray(puntos.x)[keep].astype(np.float32))
                ys_l.append(np.asarray(puntos.y)[keep].astype(np.float32))
                zs_l.append(np.asarray(puntos.z)[keep].astype(np.float32))
    except Exception:
        return None
    if not xs_l:
        dato = None
    else:
        dato = (np.concatenate(xs_l), np.concatenate(ys_l), np.concatenate(zs_l))
    _CACHE_TESELA[tp] = dato
    _CACHE_ORDEN.append(tp)
    while len(_CACHE_ORDEN) > _CACHE_MAX:
        _CACHE_TESELA.pop(_CACHE_ORDEN.pop(0), None)
    return dato


def cortar_grupo(args_tuple):
    """Corta todas las celdas de un grupo que comparte teselas. Devuelve arrays."""
    # El septimo elemento es la ortofoto y llega solo cuando el checkpoint pide
    # siete canales. Se desempaqueta por longitud para no romper las llamadas
    # viejas, que es como ya se hizo con `con_apertura`.
    # **Desempaquetado tolerante a la longitud.** Esta funcion la llaman tres
    # sitios con firmas distintas: el barrido (7 elementos, con ortofoto),
    # `minar_negativos_duros.py` (5, sin densidad ni apertura) y las llamadas
    # antiguas (6). Fijar una longitud rompe a los otros dos en silencio hasta
    # que revientan en un obrero, que es como se perdio la cadena de v10 el
    # 2026-08-08 con «expected 6, got 5».
    tile_paths, celdas, extent, res = args_tuple[:4]
    dens_obj = args_tuple[4] if len(args_tuple) > 4 else None
    con_apertura = args_tuple[5] if len(args_tuple) > 5 else False
    orto = args_tuple[6] if len(args_tuple) > 6 else None
    import laspy
    half = extent / 2.0

    # Recuadro que de verdad hace falta: la union de las celdas del grupo.
    # Sin esto se cargaban los puntos de hasta cuatro teselas enteras en float64,
    # y con varios obreros a la vez el OOM killer se llevo el barrido dos veces
    # el 2026-08-05, la segunda ya con solo tres obreros. Filtrar al leer y
    # guardar en float32 es la diferencia entre caber y no caber en 8 GB.
    ux0 = min(c["x"] for c in celdas) - half
    ux1 = max(c["x"] for c in celdas) + half
    uy0 = min(c["y"] for c in celdas) - half
    uy1 = max(c["y"] for c in celdas) + half

    xs_l, ys_l, zs_l = [], [], []
    for tp in tile_paths:
        dato = _puntos_de_tesela(tp, laspy)
        if dato is None:
            continue
        x, y, z = dato
        dentro = (x >= ux0) & (x <= ux1) & (y >= uy0) & (y <= uy1)
        if not dentro.any():
            continue
        xs_l.append(x[dentro]); ys_l.append(y[dentro]); zs_l.append(z[dentro])
    if not xs_l:
        return []
    xs = np.concatenate(xs_l); del xs_l
    ys = np.concatenate(ys_l); del ys_l
    zs = np.concatenate(zs_l); del zs_l

    # Igualar la densidad antes de rasterizar. Medido el 2026-08-06: las teselas
    # de Trasancos traen `1,56 pt/m2` de suelo y las de Lugo `2,44` —misma serie
    # `PNOA-2024-GAL`, pero entregas separadas nueve meses—, así que el `F1 0.415`
    # contra `0.743` podía ser densidad y no geografía. Y el conjunto de prueba
    # portugués vuela a `10 pt/m2`: sin igualar, una caída allí no se podría
    # separar en «no generaliza» contra «otro sensor».
    if dens_obj:
        xs, ys, zs = diezmar_a_densidad(xs, ys, zs, dens_obj)

    salida = []
    for c in celdas:
        b = (c["x"] - half, c["y"] - half, c["x"] + half, c["y"] + half)
        m = (xs >= b[0]) & (xs <= b[2]) & (ys >= b[1]) & (ys <= b[3])
        if m.sum() < 2000:
            continue
        dem = grid_from_points(xs[m], ys[m], zs[m], b, res)
        if dem is None:
            continue
        arr = channels_from_dem(dem, res,
                                con_apertura=con_apertura).astype(np.float16)
        if orto is not None:
            # Mismos tres canales y mismo orden que en el entrenamiento, y el
            # mismo relleno neutro `0.5` cuando falta la imagen: tras la
            # normalizacion `(x-0.5)/0.5` un cero seria `-1`, que es negro y es
            # una senal, no una ausencia. Si aqui se rellenara distinto que al
            # entrenar, el modelo veria en despliegue algo que nunca vio.
            d_orto, pref = orto
            f = Path(d_orto) / f"{pref}{c['id']}.jpg"
            if f.exists():
                from PIL import Image
                im = Image.open(f).convert("RGB")
                if im.size != (arr.shape[2], arr.shape[1]):
                    im = im.resize((arr.shape[2], arr.shape[1]))
                rgb = (np.asarray(im, np.float32).transpose(2, 0, 1)
                       / 255.0).astype(np.float16)
            else:
                rgb = np.full((3,) + arr.shape[1:], 0.5, np.float16)
            arr = np.concatenate([arr, rgb], axis=0)
        salida.append((c["id"], c["lon"], c["lat"], arr))
    return salida


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--laz-dir", type=Path, nargs="+", required=True)
    ap.add_argument("--dem-dir", type=Path, default=None,
                    help="caché de DEM de laz_a_dem.py. NO USAR TODAVÍA: la "
                         "rejilla del barrido no está alineada con el ráster y "
                         "sale un desfase sub-píxel. Ver la nota en "
                         "`cortar_desde_dem`")
    ap.add_argument("--checkpoint", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--bbox", type=float, nargs=4, required=True,
                    metavar=("W", "S", "E", "N"))
    ap.add_argument("--extent-m", type=float, default=512.0)
    ap.add_argument("--step-m", type=float, default=None,
                    help="por defecto media ventana, como Landauer y Canedo")
    ap.add_argument("--res-m", type=float, default=1.0)
    ap.add_argument("--workers", type=int, default=4,
                    help="lo limita la RAM por obrero, no el numero de hilos")
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--chunk", type=int, default=200,
                    help="tareas consecutivas por obrero. Grande para que las "
                         "que comparten tesela caigan en el mismo obrero y "
                         "acierten en su caché: medido, de 1 a 200 la "
                         "redundancia de lectura baja de 3.82x a 1.96x")
    ap.add_argument("--max-celdas-tarea", type=int, default=40,
                    help="techo de celdas por tarea. Acota el recuadro union "
                         "que carga cada obrero, que es lo que reventó la RAM "
                         "el 2026-08-08 (un obrero a 4,86 GB)")
    ap.add_argument("--ortofoto-dir", type=Path, default=None,
                    help="cache de ortofotos por celda ({prefijo}{id}.jpg). "
                         "Obligatorio si el checkpoint pide 7 canales")
    ap.add_argument("--ortofoto-prefijo", default="",
                    help="prefijo del bloque en la cache, p.ej. `lugo_`")
    ap.add_argument("--densidad-suelo", type=float, default=None,
                    metavar="PT_M2",
                    help="diezma la nube a esta densidad de puntos de suelo "
                         "antes de rasterizar, para que dos bloques con vuelos "
                         "distintos sean comparables. No hace nada si la nube ya "
                         "es igual o más pobre")
    args = ap.parse_args()
    step = args.step_m or args.extent_m / 2.0
    res = args.res_m

    import math
    import signal as _sig
    import torch

    # **Matar a los obreros si muere el padre.** Es el fallo que mas veces ha
    # parado esta maquina: el OOM se lleva al padre, los obreros quedan vivos, y
    # `pgrep` sigue encontrando algo — asi que quien espera al barrido espera
    # para siempre. Peor desde que la GPU esta en EXCLUSIVE_PROCESS: el contexto
    # CUDA del padre muerto lo mantienen abierto sus hijos y **bloquea la maquina
    # entera**. Paso cuatro veces el 2026-08-06, la ultima dejando una cadena
    # parada 1h 18m.
    #
    # `prctl(PR_SET_PDEATHSIG)` hace que el kernel envie SIGKILL al hijo en
    # cuanto muere su padre. Se instala en cada obrero al arrancar.
    def _morir_con_el_padre():
        try:
            import ctypes
            ctypes.CDLL("libc.so.6").prctl(1, _sig.SIGKILL)  # PR_SET_PDEATHSIG
        except Exception:
            pass
    from train_unet_multiclass import UNetMulticlass

    # --- rejilla ---
    w, s, e, n = args.bbox
    x0, y0 = lonlat_to_utm29(w, s)
    x1, y1 = lonlat_to_utm29(e, n)
    # **Alinear la rejilla a metro entero de UTM.** `lonlat_to_utm29` devuelve una
    # coordenada arbitraria, mientras que la caché de DEM bina desde el borde de
    # su tesela redondeado a entero (`np.floor(x.min())`). Con los dos orígenes
    # desfasados, recortar del ráster snapea hasta medio metro, y medio metro
    # horizontal en ladera son decímetros de cota que `channels_from_dem`
    # amplifica al normalizar por ventana: la correlación de los canales caía a
    # `0.53` y por eso `--dem-dir` estaba desactivado.
    #
    # Con la rejilla en enteros los dos binados caen en la misma retícula y el
    # recorte es exacto. Es lo que desbloquea la caché, y con ella el `8,4×`:
    # está medido que cada tesela se descomprime `8,4` veces —`5.145` lecturas
    # para `611` teselas— y que eso es el `87,6%` del coste del barrido.
    x0 = float(math.floor(x0 / res) * res)
    y0 = float(math.floor(y0 / res) * res)
    x1 = float(math.ceil(x1 / res) * res)
    y1 = float(math.ceil(y1 / res) * res)
    from pyproj import Transformer
    inv = Transformer.from_crs("EPSG:25829", "EPSG:4326", always_xy=True)
    celdas = []
    yy = y0
    while yy <= y1:
        xx = x0
        while xx <= x1:
            lon, lat = inv.transform(xx, yy)
            celdas.append({"id": len(celdas), "x": xx, "y": yy,
                           "lon": lon, "lat": lat})
            xx += step
        yy += step
    print(f"rejilla: {len(celdas)} celdas de {args.extent_m:.0f} m "
          f"con paso {step:.0f} m ({100*(1-step/args.extent_m):.0f}% de solape)",
          flush=True)

    if args.dem_dir:
        # Agrupar por tesela de DEM: se leen sus recuadros del propio .npz, que
        # es barato, en vez de deducirlos del nombre del fichero.
        demf = sorted(Path(args.dem_dir).glob("*.npz"))
        cajas = []
        for f in demf:
            try:
                b = np.load(f)["bounds"]
                cajas.append((str(f), float(b[0]), float(b[1]), float(b[2]), float(b[3])))
            except Exception:
                continue
        print(f"caché de DEM: {len(cajas)} teselas", flush=True)
        half = args.extent_m / 2.0
        grupos, huerfanas = {}, 0
        for c in celdas:
            cx0, cy0 = c["x"] - half, c["y"] - half
            cx1, cy1 = c["x"] + half, c["y"] + half
            toca = tuple(sorted(f for f, x0, y0, x1, y1 in cajas
                                if not (x1 < cx0 or x0 > cx1 or y1 < cy0 or y0 > cy1)))
            if not toca:
                huerfanas += 1
                continue
            grupos.setdefault(toca, []).append(c)
        tiles = [f for f, *_ in cajas]
    else:
        tiles = sorted({str(p) for d in args.laz_dir for p in Path(d).glob("*.laz")})
        grupos, huerfanas = group_samples_by_tiles(celdas, tiles, args.extent_m)
    cubiertas = sum(len(v) for v in grupos.values())
    print(f"teselas: {len(tiles)} | celdas con LiDAR: {cubiertas} | "
          f"fuera de cobertura: {huerfanas}", flush=True)

    # --- modelo ---
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    cupo_vram(dev)
    st = torch.load(args.checkpoint, map_location=dev, weights_only=False)
    cfg = st.get("args", {})
    # **Cuantos canales quiere este checkpoint lo dice el propio checkpoint.**
    # Se lee de la forma de `stem.0.weight`, que es `[64, in_ch, 7, 7]`. Fijarlo
    # a 3 obligaria a recordar con que corpus se entreno cada `.pt`, y el dia que
    # se olvide el barrido no falla: carga mal y puntua ruido.
    in_ch = int(st["model"]["stem.0.weight"].shape[1])
    modelo = UNetMulticlass(3, cfg.get("encoder", "resnet34"),
                            cfg.get("head", "cls"), pretrained=False,
                            in_ch=in_ch).to(dev)
    modelo.load_state_dict(st["model"])
    modelo.eval()
    # `7 = 4 topograficos + 3 de ortofoto`; `4 = con apertura`; `3 = el de
    # siempre`. Se deduce del checkpoint y no de una bandera para que no se pueda
    # barrer con canales distintos a los del entrenamiento.
    n_rgb = 3 if in_ch >= 7 else 0
    con_apertura = (in_ch - n_rgb) >= 4
    # **Si el modelo pide ortofoto y no se le da, se para.** Sin esto el barrido
    # rellenaria las 8.658 celdas con el gris neutro y puntuaria un modelo de
    # siete canales como si tres de ellos no existieran: no fallaria, daria
    # cifras peores y nadie sabria por que. Es exactamente la forma de error que
    # este proyecto lleva todo el dia encontrando.
    orto = None
    if n_rgb:
        if not args.ortofoto_dir:
            raise SystemExit(
                f"el checkpoint pide {in_ch} canales, o sea {n_rgb} de ortofoto,"
                f" y falta --ortofoto-dir")
        if not Path(args.ortofoto_dir).is_dir():
            raise SystemExit(f"no existe {args.ortofoto_dir}")
        orto = (str(args.ortofoto_dir), args.ortofoto_prefijo)
    print(f"modelo: cabeza {cfg.get('head')} | epoca {st.get('epoch', -1)+1} "
          f"| canales {in_ch}{' (con apertura)' if con_apertura else ''} "
          f"| dispositivo {dev}", flush=True)

    # --- reanudacion: no recortar lo ya puntuado ---
    hechas = set()
    if args.out.exists():
        with open(args.out, encoding="utf-8") as fh:
            for r in csv.DictReader(fh, delimiter="\t"):
                hechas.add(int(r["id"]))
        print(f"reanudando: {len(hechas)} celdas ya puntuadas", flush=True)

    # **Los grupos grandes se parten.** `cortar_grupo` carga el recuadro UNION de
    # las celdas del grupo, asi que un grupo con muchas celdas repartidas trae un
    # rectangulo enorme de puntos. El `2026-08-08` el OOM killer se llevo un
    # obrero con `4,86 GB` de RSS —no los `1,7 GB` tipicos— y con el, cuatro
    # horas de barrido de v8.
    #
    # Partir por numero de celdas acota el recuadro sin cambiar ningun resultado:
    # cada celda se puntua igual. Y no cuesta relecturas, porque las tareas van
    # ordenadas por conjunto de teselas y la cache LRU de `_CACHE_MAX` entradas
    # las sirve seguidas.
    tareas = []
    for k, v in grupos.items():
        pend = [c for c in v if c["id"] not in hechas]
        for i in range(0, len(pend), args.max_celdas_tarea):
            trozo = pend[i:i + args.max_celdas_tarea]
            tareas.append((list(k), trozo, args.extent_m, args.res_m,
                           args.densidad_suelo, con_apertura, orto))

    # **Ordenar por conjunto de teselas.** Sin esto la caché LRU no sirve: los
    # grupos que comparten tesela llegan salteados y cada uno la vuelve a
    # descomprimir. Ordenados, caen seguidos y la caché de cuatro entradas
    # convierte casi todas las relecturas en aciertos. El orden no cambia ningún
    # resultado —cada celda se puntúa igual— solo cuándo se lee cada fichero.
    tareas.sort(key=lambda t: tuple(sorted(t[0])))

    nuevo = not args.out.exists()
    fh = open(args.out, "a", newline="", encoding="utf-8")
    wr = csv.writer(fh, delimiter="\t")
    if nuevo:
        wr.writerow(["id", "lon", "lat", "score", "p_fondo", "p_castro", "p_mamoa"])

    t0, hechos = time.time(), 0
    with ProcessPoolExecutor(max_workers=args.workers,
                             initializer=_morir_con_el_padre) as ex:
        cortador = cortar_desde_dem if args.dem_dir else cortar_grupo
        # **Set, no lista.** `Future.result()` no libera nada: el objeto se queda
        # con su resultado en `_result` para siempre. Con una lista viva durante
        # todo el barrido, cada grupo ya procesado seguía ocupando memoria por los
        # arrays que ya se habían volcado a `lote_arr` — 8.658 celdas de Lugo por
        # ~1,5 MB (512x512x3 float16) son ~13 GB en una máquina de 8. Es la fuga
        # que mató en silencio los barridos del 2026-08-05 y 06 (confirmado por
        # `dmesg`: seis OOM-kill de este mismo proceso, con `anon-rss` subiendo de
        # forma sostenida hasta cortar sobre el 55-75% de cobertura, según cuánto
        # llevara corriendo). El wrapper (`cadena_v5.sh`/`cadena_v6.sh`) no
        # comprobaba el `rc` de este paso —a diferencia del de entrenamiento—, así
        # que el `SIGKILL` no dejaba rastro ni en el log ni en el código de salida
        # que se miraba.
        #
        # **`map` con lotes grandes, y no `submit` uno a uno.** Con `submit`, los
        # obreros van sacando tareas alternadas de una cola compartida, así que
        # dos tareas vecinas —que comparten teselas— caen en obreros distintos y
        # **cada uno la descomprime por su cuenta**: la caché de cada obrero se
        # llena de teselas que el otro ya tenía. Medido sobre Lugo: con reparto
        # alterno la redundancia es `3.82x` y con lotes de `200` tareas
        # consecutivas baja a **`1.96x`**, la mitad de descompresiones para el
        # mismo resultado. Y como descomprimir es el `87,6%` del coste, eso son
        # ~`1,75x` de barrido real.
        #
        # `Executor.map` además **suelta cada future al entregarla** —las va
        # sacando de su propia lista—, así que no reintroduce la fuga de memoria
        # que mató los barridos del 2026-08-05 y 06: la lista completa de
        # `Future` viva retenía cada resultado ya consumido, `~1,5 MB` por celda,
        # `~13 GB` en Lugo sobre una máquina de `8`. Seis OOM-kill confirmados en
        # `dmesg`, y ninguno visible en el log porque el wrapper no miraba el
        # `rc`.
        # **Y el lote no puede ser mayor que el trabajo dividido entre obreros.**
        # Con `81` tareas y lotes de `200`, `map` mete las `81` en un solo lote,
        # se lo da a un obrero y **el otro se queda de brazos cruzados** toda la
        # ejecución. Se ve como una mejora pobre —`132 s` a `116 s` en vez del
        # `1,75x` esperado— y no como el fallo que es. Con tres lotes por obrero
        # hay margen para que ninguno acabe antes y quede ocioso.
        chunk = max(1, min(args.chunk, len(tareas) // (args.workers * 3) or 1))
        if chunk != args.chunk:
            print(f"  lote ajustado a {chunk} para que los {args.workers} "
                  f"obreros tengan trabajo ({len(tareas)} tareas)", flush=True)
        resultados = ex.map(cortador, tareas, chunksize=chunk)
        lote_meta, lote_arr = [], []

        def vaciar():
            nonlocal lote_meta, lote_arr, hechos
            if not lote_arr:
                return
            x = torch.from_numpy(
                (np.stack(lote_arr).astype(np.float32) - 0.5) / 0.5).to(dev)
            with torch.no_grad(), torch.autocast("cuda", enabled=(dev == "cuda")):
                logits, _ = modelo(x)
            p = torch.softmax(logits.float(), 1).cpu().numpy()
            for (cid, lon, lat), pr in zip(lote_meta, p):
                wr.writerow([cid, f"{lon:.6f}", f"{lat:.6f}", f"{pr[1]:.6f}",
                             f"{pr[0]:.6f}", f"{pr[1]:.6f}", f"{pr[2]:.6f}"])
            hechos += len(lote_meta)
            fh.flush()
            lote_meta, lote_arr = [], []

        for i, res in enumerate(resultados, 1):
            for cid, lon, lat, arr in res:
                lote_meta.append((cid, lon, lat))
                lote_arr.append(arr)
                if len(lote_arr) >= args.batch:
                    vaciar()
            del res
            if i % 25 == 0 or i == len(tareas):
                print(f"  {i}/{len(tareas)} grupos, {hechos} celdas puntuadas "
                      f"({time.time()-t0:.0f}s)", flush=True)
        vaciar()
    fh.close()
    print(f"\nlisto: {hechos} celdas nuevas en {args.out}", flush=True)
    print("siguiente: scripts/detection_eval.py --pred "
          f"{args.out} --truth <castros.tsv>", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
