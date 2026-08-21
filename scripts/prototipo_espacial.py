#!/usr/bin/env python3
"""El prototipo espacial: ¿se parece un candidato a la imagen media de un castro?

Es la técnica que más aportó en la etapa de generación de propuestas del TFG de
los pingüinos (`reTAG`, 2026, §3.5): **`+0,50 pp` de `mAP`**, la mayor
contribución individual de sus seis mejoras de esa etapa.

> «El sistema no tenía ni idea de cómo se ve un ED. […] La solución: construir
> un modelo visual medio a partir de todas las instancias etiquetadas, y medir
> cuánto se parece cada bloque a ese prototipo.»

## Por qué aquí, y por qué ahora

El `2026-08-10` se midió que la red **subajusta**: recall `0,710` sobre los
castros que vio y `0,711` sobre los que no. Y la causa candidata está
cuantificada: la cabeza hace *global average pooling* sobre `256` celdas de las
que un castro ocupa `8`, así que **su evidencia se atenúa `32×`**.

Un prototipo **no promedia nada**: es una plantilla `2D` que conserva dónde está
cada cosa. Y a diferencia de los cuatro descriptores morfológicos ya refutados
—cobertura angular, contraste, radio, número de máximos—, que colapsan la viñeta
en un número, aquí se compara imagen contra imagen.

## Lo que se mide, y el control que decide

**No basta con separar castro de terreno llano.** Eso ya lo hacen los cuatro
descriptores (`AUC 0,68`–`0,79`) y no sirve de nada, porque los falsos positivos
del modelo **son geométricamente castros**. La prueba de verdad es la segunda:

1. **Control**: castros contra terreno que el modelo rechaza. Si aquí no separa,
   el prototipo está mal construido y lo demás no significa nada.
2. **La prueba**: aciertos contra **falsos positivos del modelo**. Es donde
   murieron los otros cuatro.

## Sin fuga de datos

El prototipo se construye **solo con los castros de la partición de
entrenamiento** del corpus, que está separada por bloques espaciales de los
cuatro bloques de validación donde viven los candidatos que se puntúan.

Uso:
    python3 scripts/prototipo_espacial.py --vig data/galicia-vignettes-v7 \\
        --puntos data/calib_morfo.tsv --out data/proto_calib.tsv
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "scripts"))

# Lado del recorte con que se compara, en metros. Un castro mide ~102 m de
# diámetro (radio mediano 50,8 m medido sobre 211), así que 300 m deja
# contexto sin ahogar el objeto: ocupa el 9% del área en vez del 3,1% de la
# ventana de 512 m con que trabaja la red.
LADO_M = 300.0
CANAL_LRM = 1          # ndtm, lrm, slope


def recorte_central(a: np.ndarray, lado_px: int) -> np.ndarray:
    """El cuadrado central de `lado_px` de un array (C, H, W) o (H, W)."""
    h, w = a.shape[-2:]
    y0 = (h - lado_px) // 2
    x0 = (w - lado_px) // 2
    return a[..., y0:y0 + lado_px, x0:x0 + lado_px]


def normalizar(p: np.ndarray) -> np.ndarray:
    """Centra en cero y escala a norma 1: el coseno solo mide la FORMA."""
    p = p - p.mean()
    n = float(np.linalg.norm(p))
    return p / n if n > 1e-9 else p


def construir_prototipo(vig: Path, lado_px: int) -> tuple[np.ndarray, int]:
    idx = vig / "index.tsv"
    arr = vig / "arrays"
    filas = [r for r in csv.DictReader(idx.open(encoding="utf-8"),
                                       delimiter="\t")
             if r.get("split") == "train"
             and (r.get("group") or "").strip() == "castro"
             and (arr / f"{r['sid']}.npz").exists()]
    if not filas:
        raise SystemExit("sin castros en la partición de entrenamiento")
    acum = None
    n = 0
    for r in filas:
        a = np.load(arr / f"{r['sid']}.npz")["x"].astype(np.float32)
        p = normalizar(recorte_central(a[CANAL_LRM], lado_px))
        acum = p if acum is None else acum + p
        n += 1
    return normalizar(acum / n), n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vig", type=Path, default=Path("data/galicia-vignettes-v7"))
    ap.add_argument("--puntos", type=Path, required=True)
    ap.add_argument("--laz-base", type=Path, default=Path("data/external"))
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--res-m", type=float, default=1.0)
    args = ap.parse_args()

    from build_trasancos_vignettes import (channels_from_dem, grid_from_points,
                                           group_samples_by_tiles,
                                           lonlat_to_utm29)
    import laspy

    lado_px = int(round(LADO_M / args.res_m))
    proto, n_proto = construir_prototipo(args.vig, lado_px)
    print("prototipo construido con %d castros de ENTRENAMIENTO, %dx%d px"
          % (n_proto, lado_px, lado_px), flush=True)
    np.save(args.out.with_suffix(".proto.npy"), proto)

    filas = list(csv.DictReader(args.puntos.open(encoding="utf-8"),
                                delimiter="\t"))
    hechos = set()
    if args.out.exists():
        hechos = {(r["bloque"], r["n"]) for r in
                  csv.DictReader(args.out.open(encoding="utf-8"),
                                 delimiter="\t")}
        print("reanudando: %d hechos" % len(hechos), flush=True)

    nuevo = not args.out.exists()
    fh = args.out.open("a", newline="", encoding="utf-8")
    w = csv.writer(fh, delimiter="\t")
    if nuevo:
        w.writerow(["bloque", "n", "etiqueta", "similitud"])

    por_bloque = {}
    for r in filas:
        if (r["bloque"], r["n"]) not in hechos:
            por_bloque.setdefault(r["bloque"], []).append(r)

    half = LADO_M / 2.0
    for bloque, cs in por_bloque.items():
        teselas = sorted(str(p) for p in
                         (args.laz_base / f"lidar-val-{bloque}").glob("*.laz"))
        celdas = []
        for c in cs:
            x, y = lonlat_to_utm29(float(c["lon"]), float(c["lat"]))
            celdas.append({"id": c["n"], "x": x, "y": y, "fila": c})
        grupos, _ = group_samples_by_tiles(celdas, teselas, LADO_M + 40)
        print("== %s: %d puntos en %d grupos" % (bloque, len(cs), len(grupos)),
              flush=True)
        for tp, cls_ in grupos.items():
            xs, ys, zs = [], [], []
            for t in tp:
                try:
                    las = laspy.read(t)
                    k = np.asarray(las.classification) == 2
                    if not k.any():
                        continue
                    xs.append(np.asarray(las.x)[k])
                    ys.append(np.asarray(las.y)[k])
                    zs.append(np.asarray(las.z)[k])
                except Exception:
                    continue
            if not xs:
                continue
            X = np.concatenate(xs); Y = np.concatenate(ys)
            Z = np.concatenate(zs)
            for c in cls_:
                b = (c["x"] - half, c["y"] - half,
                     c["x"] + half, c["y"] + half)
                m = (X >= b[0]) & (X <= b[2]) & (Y >= b[1]) & (Y <= b[3])
                if m.sum() < 2000:
                    continue
                dem = grid_from_points(X[m], Y[m], Z[m], b, args.res_m)
                if dem is None or np.ndim(dem) != 2:
                    continue
                ch = channels_from_dem(dem, args.res_m)
                p = recorte_central(ch[CANAL_LRM], lado_px)
                if p.shape != proto.shape:
                    continue
                s = float(np.dot(normalizar(p).ravel(), proto.ravel()))
                w.writerow([bloque, c["id"], c["fila"].get("etiqueta", ""),
                            "%.4f" % s])
                fh.flush()
            del X, Y, Z
    fh.close()
    print("\nescrito: %s" % args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
