#!/usr/bin/env python3
"""Stage 1: cut 1 m relief vignettes for the Trasancos classifier.

Landauer et al. (2025) swept 180.000 km2 with a *classifier* over 768x768 m
LiDAR vignettes, not a segmenter. That matters here: a classifier needs one
point and one label per sample, while segmentation needs drawn masks, and
Trasancos only has 8 OSM polygons. So the classifier is the route that is
actually unblocked today.

Three channels, all from the bare-earth point cloud, chosen to be what a
model pretrained on natural images can still read:

  0. normalised DTM   - min/max scaled height. Landauer found raw normalised
                        elevation beat hillshade, which is worth respecting.
  1. local relief     - DTM minus a smoothed DTM, so the hillside is removed
                        and the rampart survives. This is the channel that
                        works under canopy.
  2. slope            - degrees; ditches and scarps read as edges here.

Runs on the Raspberry: needs only laspy and numpy, no torch and no GPU. Output
is a compact .npz cache that the training stage consumes anywhere.

Concurrent over LAZ tiles with progress, because reading a 45 MB tile is slow
and there are ~700 of them.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

# El paralelismo util aqui es de proceso, no de hilo: cada viñeta son arrays de
# 512x512, demasiado pequeños para que BLAS multihilo compense su coordinacion.
# Sin fijar esto, 3 workers x 5 hilos sobre 4 nucleos dan carga 7.8 y se pelean
# entre si. Debe ir antes de importar numpy.
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
           "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LAZ_DIR = PROJECT_ROOT / "data/external/lidar-trasancos-v1"
OUT_DIR = PROJECT_ROOT / "data/trasancos-vignettes-v1"
MASTER = PROJECT_ROOT / "data/weak-label-splits-v1/weak_label_master.tsv"
HARD_NEG = PROJECT_ROOT / "data/trasancos-hard-negatives-v1/trasancos_hard_negatives.tsv"

TRASANCOS = {"Ferrol", "Narón", "Naron", "Neda", "Fene", "Valdoviño",
             "Valdovino", "San Sadurniño", "San Sadurnino"}
# O Val is the untouched final holdout: it carries Pena Lopesa, the project's
# historical control case, and it must never be trained on.
O_VAL = (-8.2411, 43.5346, -8.1932, 43.5890)  # W, S, E, N

GROUND_CLASS = 2
EXTENT_M = 512.0      # vignette side; a 114 m castro fills ~22% of the frame
PIXEL_M = 1.0
BLOCK_M = 2000.0      # spatial block size for the train/val split


_TRANSFORMER = None


def lonlat_to_utm29(lon, lat):
    """Convierte a UTM 29N reutilizando el transformador y aceptando secuencias.

    Antes construia un `Transformer` nuevo en cada llamada, y como se llamaba una
    vez por muestra, a escala Galicia eran `41.259` construcciones: cada una abre
    `proj.db` y cuesta milisegundos, asi que la carga de muestras se comia varios
    minutos al `100%` de un nucleo antes de imprimir la primera linea. Construirlo
    una vez y pasarle los arrays completos deja eso en milisegundos.
    """
    global _TRANSFORMER
    if _TRANSFORMER is None:
        from pyproj import Transformer
        _TRANSFORMER = Transformer.from_crs("EPSG:4326", "EPSG:25829",
                                            always_xy=True)
    return _TRANSFORMER.transform(lon, lat)


def in_bbox(lon, lat, bbox):
    w, s, e, n = bbox
    return w <= lon <= e and s <= lat <= n


def load_samples(scope: str = "trasancos", extra_negatives=None):
    """Positives, mound hard negatives and named modern/natural negatives.

    `scope="trasancos"` keeps the six-council pilot. `scope="galicia"` opens it
    to every trainable positive in the catalogue, which is what the
    label-centred LiDAR sampling exists to serve: 747 positives spread over 286
    blocks instead of 68 in one comarca, and a +-0.033 interval on sensitivity
    instead of +-0.109.
    """
    samples = []
    if MASTER.exists():
        for r in csv.DictReader(open(MASTER, encoding="utf-8"), delimiter="\t"):
            if scope == "trasancos" and (r.get("municipality") or "") not in TRASANCOS:
                continue
            try:
                lon, lat = float(r["longitude"]), float(r["latitude"])
            except (KeyError, TypeError, ValueError):
                continue
            split = r.get("final_split") or ""
            if r.get("label_class") == "1":
                # excluded_review holds the toponymic noise the project already
                # flagged: streets, buildings and chapels named "Castro".
                if split == "excluded_review":
                    continue
                samples.append({"label": 1, "group": "castro",
                                "name": r.get("name", ""), "lon": lon, "lat": lat})
            elif "megalithic" in (r.get("negative_type") or ""):
                samples.append({"label": 0, "group": "mamoa",
                                "name": r.get("name", ""), "lon": lon, "lat": lat})
    # Los negativos con nombre se extrajeron sobre el bbox de Trasancos, asi que
    # en alcance galicia entran igual pero solo cubriran esa zona. El resto de
    # Galicia aporta por ahora negativos de catalogo (mamoas), y hara falta una
    # pasada de Overpass a escala gallega antes de entrenar en serio.
    neg_files = [HARD_NEG] + [Path(p) for p in (extra_negatives or [])]
    for nf in neg_files:
        if not Path(nf).exists():
            print(f"  AVISO: no existe el fichero de negativos {nf}", flush=True)
            continue
        leidas = saltadas = 0
        for r in csv.DictReader(open(nf, encoding="utf-8"), delimiter="\t"):
            # **Nombres de columna, no uno solo.** El 2026-08-08 este bucle leia
            # solo `longitude`/`latitude`, y `negativos_puntuados_v3.tsv` trae
            # `lon`/`lat`: el `except KeyError: continue` descarto sus **10.667
            # filas en silencio**, sin una linea de aviso. El corpus de v11p salio
            # con `0` de los `10.742` `random_terrain` que tiene v7, o sea con
            # otro balance de clases por completo, y solo se detecto al comparar
            # las composiciones a mano.
            lon = r.get("longitude") or r.get("lon") or r.get("x")
            lat = r.get("latitude") or r.get("lat") or r.get("y")
            try:
                lon, lat = float(lon), float(lat)
            except (TypeError, ValueError):
                saltadas += 1
                continue
            leidas += 1
            grupo = (r.get("negative_class") or r.get("group") or "other")
            samples.append({"label": 0, "group": grupo,
                            "name": r.get("name", ""), "lon": lon, "lat": lat})
        # **Se cuenta y se dice.** Un fichero que aporta cero filas es un fallo,
        # no un caso normal, y tiene que verse en el log sin ir a buscarlo.
        print(f"  negativos de {Path(nf).name}: {leidas} leidas, {saltadas} saltadas",
              flush=True)
        if leidas == 0:
            print(f"  *** {Path(nf).name} NO APORTO NINGUNA FILA: revisa sus "
                  f"columnas (se esperan longitude/latitude o lon/lat) ***", flush=True)

    # Una sola llamada con los arrays completos, no una por muestra.
    if samples:
        xs, ys = lonlat_to_utm29([s["lon"] for s in samples],
                                 [s["lat"] for s in samples])
        for smp, x, y in zip(samples, xs, ys):
            smp["x"], smp["y"] = x, y
    for smp in samples:
        # O Val permanece intocable en ambos alcances: lleva Pena Lopesa, el caso
        # de control historico del proyecto, y nunca debe entrar en entrenamiento.
        smp["split"] = "test_o_val" if in_bbox(smp["lon"], smp["lat"], O_VAL) else "pool"

    # ## Regla 15: el precinto del norte de Portugal
    #
    # **Esto no es defensivo, es correctivo.** El 2026-08-09, al ampliar la
    # descarga de LiDAR, el corpus arrastro **`65` castros del conjunto sellado a
    # `0 m`** —las mismas coordenadas— hacia `train`. Si entrenan, la unica
    # estimacion insesgada que el proyecto va a producir nace contaminada, y no
    # habria forma de saberlo despues: el precinto se rompe en silencio.
    #
    # Antes no pasaba porque no habia LiDAR de esa zona descargado. El fallo no
    # estaba en el codigo: estaba esperando a que llegara el dato.
    sellados = _leer_precinto()
    if sellados:
        fuera = 0
        for smp in samples:
            if smp["split"] != "pool":
                continue
            for slat, slon in sellados:
                if abs(slat - smp["lat"]) > 0.01:
                    continue
                dlat = (slat - smp["lat"]) * 111320.0
                dlon = (slon - smp["lon"]) * 111320.0 * math.cos(math.radians(slat))
                if math.hypot(dlat, dlon) < 300.0:
                    smp["split"] = "excluido_precinto"
                    fuera += 1
                    break
        print(f"  precinto: {fuera} muestras excluidas por estar a <300 m de los "
              f"{len(sellados)} castros sellados", flush=True)
    else:
        print("  *** AVISO: no se pudo leer la verdad precintada; el corpus puede "
              "contener castros del conjunto de prueba ***", flush=True)
    return samples


def _leer_precinto(ruta="data/portugal-test_truth_limpia.tsv"):
    """Coordenadas de los castros precintados, o lista vacia si no se puede leer."""
    p = PROJECT_ROOT / ruta
    if not p.exists():
        return []
    out = []
    with p.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            try:
                out.append((float(r.get("lat") or r["latitude"]),
                            float(r.get("lon") or r["longitude"])))
            except (TypeError, ValueError, KeyError):
                pass
    return out


def diezmar_a_densidad(xs, ys, zs, objetivo_pt_m2, semilla=20260806):
    """Reduce la nube a una densidad objetivo de puntos de suelo por m².

    Existe porque **el conjunto de prueba tiene otro sensor**. El LiDAR de la DGT
    portuguesa vuela a `10 pt/m²`; el PNOA con el que se entrenó, no. Y sin
    igualarlo, una caída de rendimiento en Portugal no se podría separar en «no
    generaliza geográficamente» contra «no generaliza a otra densidad», y esa
    ambigüedad no tiene arreglo a posteriori.

    Pero medir la densidad propia destapó algo que no se sabía: **nuestros dos
    bloques tampoco son iguales**. Suelo, medido el `2026-08-06`:

    | bloque | total | suelo |
    |---|---:|---:|
    | Trasancos | `4,11 pt/m²` | `1,67` (min `0,13`) |
    | Lugo | `10,46 pt/m²` | `2,33` (min `1,53`) |

    Son vuelos distintos del PNOA. Así que parte de la diferencia entre el
    `F1 0.415` de Trasancos y el `0.743` de Lugo puede ser densidad y no
    geografía — y esta función es también la forma de comprobarlo, diezmando
    Lugo a la densidad de Trasancos y volviendo a medir.

    El diezmado es **aleatorio uniforme y con semilla fija**: no reproduce el
    patrón de barrido de un vuelo menos denso, pero es la aproximación estándar y
    es reproducible, que es lo que exige un conjunto de prueba.
    """
    n = len(xs)
    if n == 0 or objetivo_pt_m2 is None or objetivo_pt_m2 <= 0:
        return xs, ys, zs
    area = (float(xs.max()) - float(xs.min())) * (float(ys.max()) - float(ys.min()))
    if area <= 0:
        return xs, ys, zs
    actual = n / area
    if actual <= objetivo_pt_m2:
        return xs, ys, zs                 # ya es igual o más pobre: no se toca
    quedan = int(round(objetivo_pt_m2 * area))
    rng = np.random.default_rng(semilla)
    idx = rng.choice(n, size=quedan, replace=False)
    idx.sort()                            # conservar el orden espacial original
    return xs[idx], ys[idx], zs[idx]


def grid_from_points(xs, ys, zs, bounds, res):
    """Lowest ground return per cell, then fill gaps by nearest valid neighbour."""
    minx, miny, maxx, maxy = bounds
    w = int(round((maxx - minx) / res))
    h = int(round((maxy - miny) / res))
    if w < 8 or h < 8:
        return None
    ix = np.clip(((xs - minx) / res).astype(np.int64), 0, w - 1)
    iy = np.clip(((maxy - ys) / res).astype(np.int64), 0, h - 1)
    flat = iy * w + ix
    dem = np.full(w * h, np.inf, dtype=np.float64)
    np.minimum.at(dem, flat, zs)
    dem = dem.reshape(h, w)
    valid = np.isfinite(dem)
    if valid.mean() < 0.30:
        return None
    if not valid.all():
        from scipy import ndimage  # optional; fall back to median fill
        try:
            idx = ndimage.distance_transform_edt(
                ~valid, return_distances=False, return_indices=True)
            dem = dem[tuple(idx)]
        except Exception:
            dem[~valid] = np.median(dem[valid])
    return dem.astype(np.float32)


def boxblur(a, radius):
    """Separable mean filter via summed-area table; no scipy dependency."""
    if radius < 1:
        return a
    pad = np.pad(a, radius, mode="edge")
    c = np.cumsum(np.cumsum(pad, axis=0), axis=1)
    c = np.pad(c, ((1, 0), (1, 0)))
    k = 2 * radius + 1
    h, w = a.shape
    tot = (c[k:k + h, k:k + w] - c[0:h, k:k + w]
           - c[k:k + h, 0:w] + c[0:h, 0:w])
    return (tot / (k * k)).astype(np.float32)


def channels_from_dem(dem, res, lrm_radius_m=60.0, con_apertura=False):
    """Normalised DTM, local relief and slope, each scaled to [0, 1].

    Con `con_apertura=True` anade un cuarto canal: la **apertura topografica**.

    Se anade por lo que paso con `OU-8` el `2026-08-07`. Tenia el mejor perfil
    topografico de sus 27 —49,3 m de prominencia, 100% del entorno debajo— y en
    el sombreado se veian arcos concentricos envolviendo la cima. Eran **pistas
    forestales**, y lo delato la ortofoto: ninguno de estos tres canales las
    distingue de un parapeto.

    La razon es fisica. Una pista es **un corte**: un rasgo lineal fino de un
    solo tono. Un parapeto es **caballon mas foso**: un alto y un bajo pegados.
    El MDT normalizado da la altura, el relieve local quita la ladera y la
    pendiente da la inclinacion, pero **ninguno mira si hay un alto y un bajo
    juntos**, que es la firma que los separa.

    La apertura si (Doneus 2013, `10.3390/rs5126427`): sin sesgo direccional,
    sin desplazamiento horizontal, y resaltando a la vez lo mas alto y lo mas
    bajo. Verificado sobre dato propio: un castro conocido sale como anillo
    cerrado de tono doble y `OU-8` como lineas finas de tono unico.
    """
    def mm(a):
        lo, hi = np.nanpercentile(a, 1), np.nanpercentile(a, 99)
        if not np.isfinite(lo) or not np.isfinite(hi) or hi - lo < 1e-6:
            return np.zeros_like(a, dtype=np.float32)
        return np.clip((a - lo) / (hi - lo), 0, 1).astype(np.float32)

    ndtm = mm(dem)
    lrm = dem - boxblur(dem, int(round(lrm_radius_m / res)))
    lrm = mm(lrm)
    gy, gx = np.gradient(dem, res)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    slope = np.clip(slope / 45.0, 0, 1).astype(np.float32)
    if not con_apertura:
        return np.stack([ndtm, lrm, slope], axis=0)
    from openness import canal_rapido
    return np.stack([ndtm, lrm, slope, canal_rapido(dem, res)], axis=0)


_BOUNDS_CACHE: dict[str, tuple] = {}


def laz_bounds(path):
    import laspy
    key = str(path)
    if key not in _BOUNDS_CACHE:
        with laspy.open(path) as rd:
            h = rd.header
            _BOUNDS_CACHE[key] = (float(h.mins[0]), float(h.mins[1]),
                                  float(h.maxs[0]), float(h.maxs[1]))
    return _BOUNDS_CACHE[key]


def process_group(args_tuple):
    """Cut every vignette in a group that needs the same set of LAZ tiles.

    CNIG ships 1 km tiles and a vignette is 512 m, so a site anywhere but the
    middle of a tile straddles two or four of them. Requiring the extent to sit
    inside a single tile silently drops about three quarters of the samples,
    so the tiles are unioned per group instead.
    """
    if len(args_tuple) == 6:
        tile_paths, samples, extent, res, out_dir, con_apertura = args_tuple
    else:
        tile_paths, samples, extent, res, out_dir = args_tuple
        con_apertura = False
    import laspy
    half = extent / 2.0

    # Si el grupo entero ya esta cortado, ni se abren los LAZ: son ~45 MB cada
    # uno y un grupo puede tocar cuatro.
    pending = [s for s in samples
               if not (Path(out_dir) / f"{s['sid']}.npz").exists()]
    if not pending:
        return len(samples), len(samples)

    xs_l, ys_l, zs_l = [], [], []
    for tp in tile_paths:
        las = laspy.read(tp)
        keep = np.asarray(las.classification) == GROUND_CLASS
        if not keep.any():
            continue
        xs_l.append(np.asarray(las.x)[keep])
        ys_l.append(np.asarray(las.y)[keep])
        zs_l.append(np.asarray(las.z)[keep])
    if not xs_l:
        return 0, len(samples)
    xs = np.concatenate(xs_l)
    ys = np.concatenate(ys_l)
    zs = np.concatenate(zs_l)

    written = 0
    for s in samples:
        # Reanudacion: esta maquina ha perdido el disco tres veces hoy, asi que
        # recalcular una viñeta ya escrita es tiempo regalado. Comprobar el
        # fichero cuesta un stat; recortarla cuesta leer decenas de MB de LAZ.
        out_npz = Path(out_dir) / f"{s['sid']}.npz"
        if out_npz.exists() and out_npz.stat().st_size > 0:
            written += 1
            continue
        b = (s["x"] - half, s["y"] - half, s["x"] + half, s["y"] + half)
        m = (xs >= b[0]) & (xs <= b[2]) & (ys >= b[1]) & (ys <= b[3])
        if m.sum() < 2000:
            continue
        dem = grid_from_points(xs[m], ys[m], zs[m], b, res)
        if dem is None:
            continue
        arr = channels_from_dem(dem, res, con_apertura=con_apertura)
        np.savez_compressed(Path(out_dir) / f"{s['sid']}.npz",
                            x=arr.astype(np.float16), label=s["label"])
        written += 1
    return written, len(samples)


def group_samples_by_tiles(samples, tiles, extent):
    """Map each sample to the tiles its vignette overlaps, then group by that set."""
    half = extent / 2.0
    bounds = {t: laz_bounds(t) for t in tiles}
    groups = defaultdict(list)
    orphans = 0
    for s in samples:
        b = (s["x"] - half, s["y"] - half, s["x"] + half, s["y"] + half)
        need = tuple(sorted(
            t for t, (mnx, mny, mxx, mxy) in bounds.items()
            if not (b[2] < mnx or b[0] > mxx or b[3] < mny or b[1] > mxy)))
        if not need:
            orphans += 1
            continue
        groups[need].append(s)
    return groups, orphans


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    # Varios directorios, y no uno, porque las teselas viven separadas por cómo
    # se descargaron —`lidar-positives-v1` centrado en positivos, `lidar-trasancos-v1`
    # cubriendo la comarca— y usar solo el primero dejaba fuera el 93% de los
    # negativos con nombre. La cobertura es la union de todos.
    ap.add_argument("--laz-dir", type=Path, nargs="+", default=[LAZ_DIR])
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    ap.add_argument("--extent-m", type=float, default=EXTENT_M)
    ap.add_argument("--res-m", type=float, default=PIXEL_M)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--scope", choices=("trasancos", "galicia"), default="trasancos")
    ap.add_argument("--extra-negatives", nargs="*", default=None,
                    help="TSV adicionales de negativos (mismo formato)")
    ap.add_argument("--con-apertura", action="store_true",
                    help="anade la apertura topografica como cuarto canal. "
                         "Cuesta 1,6 s por vinneta y separa un parapeto —que es "
                         "caballon mas foso— de una pista forestal, que solo es "
                         "un corte. Los tres canales actuales no distinguen eso")
    ap.add_argument("--splits-de", default=None,
                    help="hereda los splits de otro index.tsv: el examen queda fijo y lo nuevo va a train")
    ap.add_argument("--cuarentena-o-val", action="store_true",
                    help="excluye de train/val los bloques que tocan la caja de O Val")
    ap.add_argument("--val-every", type=int, default=5,
                    help="1 de cada N bloques espaciales va a validacion")
    args = ap.parse_args()

    arr_dir = args.out_dir / "arrays"
    arr_dir.mkdir(parents=True, exist_ok=True)

    samples = load_samples(args.scope, args.extra_negatives)
    # El identificador se deriva de las coordenadas, no del índice en la lista.
    # Con el índice, añadir una fuente de negativos desplaza a todos los demás
    # y la reanudación empieza a saltar ficheros que corresponden a otro sitio:
    # datos corruptos en silencio, que es peor que recalcular.
    for s in samples:
        key = f"{s['lon']:.6f},{s['lat']:.6f}".encode()
        s["sid"] = (f"{s['label']}_{s['group']}_"
                    f"{hashlib.sha1(key).hexdigest()[:10]}")
    seen = set()
    unique = []
    for s in samples:
        if s["sid"] in seen:
            continue
        seen.add(s["sid"])
        unique.append(s)
    if len(unique) != len(samples):
        print(f"  {len(samples)-len(unique)} duplicados por coordenada descartados",
              flush=True)
    samples = unique
    pos = sum(1 for s in samples if s["label"] == 1)
    print(f"samples: {len(samples)} ({pos} positives, {len(samples)-pos} negatives)",
          flush=True)
    for g, n in Counter(s["group"] for s in samples).most_common():
        print(f"   {g}: {n}", flush=True)

    tiles = sorted({str(p) for d in args.laz_dir for p in Path(d).glob("*.laz")})
    if not tiles:
        print(f"no LAZ tiles in {args.laz_dir}; run download_trasancos_lidar.py first")
        return 1
    for d in args.laz_dir:
        print(f"   {d}: {len(list(Path(d).glob('*.laz')))} teselas", flush=True)
    print(f"tiles: {len(tiles)} | workers {args.workers}", flush=True)

    slim = [{k: s[k] for k in ("sid", "x", "y", "label")} for s in samples]
    groups, orphans = group_samples_by_tiles(slim, tiles, args.extent_m)
    covered = sum(len(v) for v in groups.values())
    print(f"groups: {len(groups)} | samples covered by LiDAR: {covered} "
          f"| outside coverage: {orphans}", flush=True)

    tasks = [(list(k), v, args.extent_m, args.res_m, str(arr_dir),
              args.con_apertura) for k, v in groups.items()]
    if args.con_apertura:
        print("cortando CON el cuarto canal de apertura (~1,6 s extra por "
              "vinneta)", flush=True)

    written = 0
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(process_group, t): t for t in tasks}
        for i, f in enumerate(as_completed(futs), 1):
            try:
                w, tried = f.result()
                written += w
            except Exception as exc:
                print(f"  FAIL group of {len(futs[f][1])}: {exc}", flush=True)
            if i % 25 == 0 or i == len(tasks):
                print(f"  progress {i}/{len(tasks)} groups, {written} vignettes",
                      flush=True)

    # Spatial blocks, so train and val never share a hillside. O Val stays out.
    made = {p.stem for p in arr_dir.glob("*.npz")}
    index = []
    for s in samples:
        if s["sid"] not in made:
            continue
        blk = f"{int(s['x'] // BLOCK_M)}_{int(s['y'] // BLOCK_M)}"
        index.append({"sid": s["sid"], "label": s["label"], "group": s["group"],
                      "name": s["name"], "lon": s["lon"], "lat": s["lat"],
                      "block": blk, "split": s["split"]})

    # **Cuarentena de los bloques que tocan O Val.**
    #
    # `test_o_val` se asigna por caja envolvente, ANTES de trocear en bloques de
    # `2 km`. Un bloque que cruza el borde de la caja queda partido: parte de sus
    # viñetas caen en `test_o_val` y parte en `pool`, y de ahi pasan a `train`.
    #
    # Medido el 2026-08-08 sobre el corpus de v7: **`9` bloques de `1.108`**
    # repartidos asi, y `1` de los `7` castros de O Val —O Castrillon— acaba a
    # `461 m` de una viñeta de entrenamiento, cuando las viñetas miden `512 m`.
    # O sea, se solapan. Con `n = 7`, ese caso pesa el `14%` de la unica cifra
    # que mide el pueblo de casa.
    #
    # El arreglo es tratar el bloque como la unidad indivisible que dice ser: si
    # un bloque contiene UNA viñeta de `test_o_val`, el bloque entero queda fuera
    # de `train` y de `val`. Cuesta unas pocas viñetas y elimina la fuga de raiz.
    #
    # ## Por que es una opcion y no el comportamiento por defecto
    #
    # La cuarentena saca tambien `37` viñetas de `val`, y eso **cambia el
    # conjunto de validacion**. El proyecto compara variantes por su
    # `selection_best`, que se calcula sobre `val`: si `val` cambia, la cifra deja
    # de ser comparable con v7, v8 y v9, y con ella se cae la regla de cribado.
    #
    # Asi que la regla de uso es:
    #
    # - **Experimentos comparativos** (v11p, v11, cualquier variante que se mida
    #   contra v7): **sin** cuarentena, y el sesgo de O Val se declara. Es
    #   identico en los dos lados de la comparacion, luego no la sesga.
    # - **El modelo final**, ese cuya cifra de O Val se vaya a publicar: **con**
    #   cuarentena, porque ahi la cifra de O Val ya no es un metadato sino un
    #   resultado.
    #
    # Elegir lo contrario —limpiar el experimento y ensuciar el resultado— es el
    # error facil, y por eso queda escrito aqui y no en la memoria de nadie.
    tocados = {r["block"] for r in index if r["split"] == "test_o_val"}
    n_cuarentena = sum(1 for r in index
                       if r["split"] == "pool" and r["block"] in tocados)
    if args.cuarentena_o_val:
        for r in index:
            if r["split"] == "pool" and r["block"] in tocados:
                r["split"] = "excluido_frontera"
        print(f"  cuarentena: {n_cuarentena} viñetas en los {len(tocados)} bloques "
              f"que tocan O Val quedan fuera de train/val", flush=True)
    elif n_cuarentena:
        print(f"  AVISO: {n_cuarentena} viñetas comparten bloque con O Val y van "
              f"a train/val (usa --cuarentena-o-val para excluirlas)", flush=True)

    # ## Heredar el examen, para que el experimento sea controlado
    #
    # Un experimento de dosis varia el conjunto de ENTRENAMIENTO y deja fijo el de
    # validacion. Si el examen cambia a la vez que los apuntes, la cifra final no
    # dice si el modelo aprendio mas: dice que le preguntaron otra cosa.
    #
    # El 2026-08-09 el corpus de v11p salio con `2.958` viñetas de validacion que
    # v7 no tiene y `2.879` de v7 que el no tiene. Su `selection_best` no habria
    # sido comparable con v7, v8 ni v9, y con el se caia tambien la regla de
    # cribado, que se apoya en que todos comparten examen.
    #
    # Con `--splits-de`, cada viñeta que exista en el corpus de referencia hereda
    # su split; las nuevas van todas a `train`, que es exactamente la dosis.
    heredados = 0
    if args.splits_de:
        ref = {}
        with open(args.splits_de, encoding="utf-8") as fh:
            for r in csv.DictReader(fh, delimiter="\t"):
                ref[r["sid"]] = (r.get("split") or "").strip()
        for r in index:
            s = ref.get(r["sid"])
            if s in ("val", "test_o_val"):
                r["split"] = s
                heredados += 1
            elif s == "train" and r["split"] == "pool":
                r["split"] = "train"
                heredados += 1
        print(f"  splits heredados de {args.splits_de}: {heredados}", flush=True)
        # lo que no estaba en la referencia y sigue en el pool es dosis nueva:
        nuevos = sum(1 for r in index if r["split"] == "pool")
        print(f"  viñetas nuevas que van a train (la dosis): {nuevos}", flush=True)
        for r in index:
            if r["split"] == "pool":
                r["split"] = "train"
    else:
        blocks = sorted({r["block"] for r in index if r["split"] == "pool"})
        val_blocks = set(blocks[::args.val_every])  # 1 de cada N bloques
        for r in index:
            if r["split"] == "pool":
                r["split"] = "val" if r["block"] in val_blocks else "train"

    with open(args.out_dir / "index.tsv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, delimiter="\t",
                           fieldnames=["sid", "label", "group", "name",
                                       "lon", "lat", "block", "split"])
        w.writeheader()
        for r in index:
            w.writerow(r)

    stats = defaultdict(Counter)
    for r in index:
        stats[r["split"]][r["label"]] += 1
    meta = {"extent_m": args.extent_m, "res_m": args.res_m,
            "channels": ["normalised_dtm", "local_relief", "slope"],
            "blocks": len(blocks), "val_blocks": len(val_blocks),
            "counts": {k: dict(v) for k, v in stats.items()}}
    (args.out_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print(f"\ndone in {(time.time()-t0)/60:.1f} min | {len(index)} vignettes indexed",
          flush=True)
    for sp in ("train", "val", "test_o_val"):
        c = stats[sp]
        print(f"   {sp}: {c[1]} positives, {c[0]} negatives", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
