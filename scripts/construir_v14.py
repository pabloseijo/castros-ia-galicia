#!/usr/bin/env python3
"""v14: v11p sin los positivos que no tienen fondo en su propio bloque.

Ver `docs/preregistros/PREREGISTRO-v14-confusion-espacial.md`. En una linea: el `53%` de los
positivos de v11p vive en bloques de los que el modelo no ve ni una viñeta de
fondo, y eso es un atajo —reconocer el sitio en vez del yacimiento— que en el
barrido real no existe.

**No corta ni descarga nada**: las viñetas de los `2.603` positivos ya estan en
v11p. Esto escribe un `index.tsv` nuevo y enlaza los mismos arrays.

La reparticion se rehace **por bloques enteros** y solo sobre los bloques que
tienen las dos cosas, para que el examen tampoco tenga el atajo. El fondo de los
bloques sin castros se queda entero en `train`: un negativo suelto no confunde,
solo enseña.
"""
from __future__ import annotations

import csv
import math
import random
from collections import Counter
from pathlib import Path

ORIG = Path("data/galicia-vignettes-v11p")
DEST = Path("data/galicia-vignettes-v14")
FRAC_VAL = 0.20
SEMILLA = 20260809

filas = list(csv.DictReader((ORIG / "index.tsv").open(encoding="utf-8"), delimiter="\t"))
campos = list(filas[0].keys())


def es_pos(r):
    return (r.get("group") or "").strip().startswith("castro")


con_pos = {(r.get("block") or "").strip() for r in filas if es_pos(r)}
con_fondo = {(r.get("block") or "").strip() for r in filas if not es_pos(r)}
compartidos = con_pos & con_fondo

# --- el filtro: fuera los positivos huerfanos de fondo -----------------------
sobreviven = [r for r in filas
              if not es_pos(r) or (r.get("block") or "").strip() in compartidos]
caidos = len(filas) - len(sobreviven)

# --- regla 15: fuera lo que toque el precinto --------------------------------
# El corpus de v11p arrastra `6` castros que estan a `0 m` de sitios del fichero
# precintado, porque ese fichero incluye `71` castros gallegos ademas del norte
# de Portugal. **No se toca el precinto** —esa decision no es de este script—:
# se aparta lo nuestro, que es lo conservador y cuesta seis viñetas.
PRECINTO = Path("data/portugal-test_truth_limpia.tsv")
RADIO_M = 300.0
sellados = [(float(r["lon"]), float(r["lat"]))
            for r in csv.DictReader(PRECINTO.open(encoding="utf-8"), delimiter="\t")]


def toca_precinto(r) -> bool:
    try:
        lon, lat = float(r["lon"]), float(r["lat"])
    except (KeyError, TypeError, ValueError):
        return False
    coslat = math.cos(math.radians(lat))
    for slon, slat in sellados:
        dx = (lon - slon) * 111_320.0 * coslat
        dy = (lat - slat) * 110_540.0
        if dx * dx + dy * dy < RADIO_M * RADIO_M:
            return True
    return False


antes = len(sobreviven)
sobreviven = [r for r in sobreviven if not toca_precinto(r)]
por_precinto = antes - len(sobreviven)

# --- reparticion nueva, por bloque entero ------------------------------------
rnd = random.Random(SEMILLA)
orden = sorted(compartidos)
rnd.shuffle(orden)
val_bloques = set(orden[:max(1, round(len(orden) * FRAC_VAL))])

for r in sobreviven:
    b = (r.get("block") or "").strip()
    # el fondo de bloques sin castros se queda entero en train
    r["split"] = "val" if b in val_bloques else "train"

DEST.mkdir(parents=True, exist_ok=True)
enlace = DEST / "arrays"
if not enlace.exists():
    enlace.symlink_to((ORIG / "arrays").resolve())

with (DEST / "index.tsv").open("w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=campos, delimiter="\t")
    w.writeheader()
    w.writerows(sobreviven)

# --- lo que hay que poder leer de un vistazo ---------------------------------
print(f"  bloques: {len(con_pos)} con castros | {len(con_fondo)} con fondo | "
      f"{len(compartidos)} con ambos")
print(f"  caen {caidos} positivos huerfanos y {por_precinto} por el precinto; "
      f"quedan {len(sobreviven)} viñetas\n")
for split in ("train", "val"):
    pos, neg = Counter(), Counter()
    for r in sobreviven:
        if r["split"] != split:
            continue
        (pos if es_pos(r) else neg)[(r.get("block") or "").strip()] += 1
    solo = sum(pos[b] for b in set(pos) - set(neg))
    tp, tn = sum(pos.values()), sum(neg.values())
    print(f"  {split:<6} castros {tp:>5}  fondo {tn:>6}  "
          f"({100*tp/max(tp+tn,1):.1f}% positivos)   "
          f"en bloques sin fondo: {solo} ({100*solo/max(tp,1):.0f}%)")
