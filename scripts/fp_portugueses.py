#!/usr/bin/env python3
"""Los falsos positivos de la cabecera portuguesa, para que alguien los mire.

## Por que

El precinto dejo una pregunta sin responder: la precision cae a la mitad al
cruzar la frontera (VPP 0,61 -> 0,31) con el recall IDENTICO. Dos explicaciones
compiten —mas confusores en el terreno, o un catalogo menos completo— y no se
separan con datos: hay que mirar los recortes.

Si un tercio de esos falsos positivos fueran yacimientos, no solo se explicaria
la caida: **serian castros ineditos**, que es el objetivo del proyecto.

## Que hace

Cruza el top-100 de la fusion con la verdad del precinto (ya abierto, asi que
mirarlo no lo rompe mas) y separa aciertos de fallos. De los fallos, marca
cuales caen en ordenes cuyo LiDAR sigue en disco, que son los unicos de los que
se puede hacer ficha sin rebajar 30 GB.
"""
import csv
import math
import sys
from pathlib import Path

TOL_M = 500.0


def carga(p, campos=("lon", "lat")):
    out = []
    with open(p, encoding="utf-8") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            try:
                d = {c: float(r[c]) for c in campos}
                d["_raw"] = r
                out.append(d)
            except (KeyError, ValueError):
                pass
    return out


def dist_m(a, b):
    dx = (a["lon"] - b["lon"]) * 111320 * math.cos(math.radians((a["lat"] + b["lat"]) / 2))
    dy = (a["lat"] - b["lat"]) * 110540
    return math.hypot(dx, dy)


pred_p = Path("data/sweep_test_portugal_TODO_fusion.tsv")
if not pred_p.exists():
    print(f"no existe {pred_p}", file=sys.stderr)
    sys.exit(1)

pred = carga(pred_p)
pred.sort(key=lambda r: -float(r["_raw"].get("score", 0)))
verdad = carga("data/precinto-portugal-cubiertos.tsv")

# rectangulos de las ordenes cuyo LiDAR sigue en disco
ordenes_con_laz = []
for r in csv.DictReader(open("data/plan-descarga-portugal.tsv", encoding="utf-8"), delimiter="\t"):
    if r["orden"] in ("1", "2", "22"):
        ordenes_con_laz.append((r["orden"], float(r["lon_min"]), float(r["lat_min"]),
                                float(r["lon_max"]), float(r["lat_max"])))


def orden_de(p):
    for o, lo, la, LO, LA in ordenes_con_laz:
        if lo <= p["lon"] <= LO and la <= p["lat"] <= LA:
            return o
    return ""


TOP = 100
tp, fp = [], []
for p in pred[:TOP]:
    if any(dist_m(p, v) <= TOL_M for v in verdad):
        tp.append(p)
    else:
        fp.append(p)

print(f"top-{TOP} de la fusion: {len(tp)} aciertos, {len(fp)} fallos")
con_laz = [(p, orden_de(p)) for p in fp]
disp = [(p, o) for p, o in con_laz if o]
print(f"de los {len(fp)} fallos, {len(disp)} caen en ordenes con LiDAR en disco (1, 2, 22)")
print()

out = Path("data/fp-portugal-revisar.tsv")
with open(out, "w", encoding="utf-8") as fh:
    fh.write("n\torden\tscore\tlat\tlon\tvista_aerea\n")
    for i, (p, o) in enumerate(disp, 1):
        url = f"https://www.google.com/maps/@{p['lat']:.6f},{p['lon']:.6f},250m/data=!3m1!1e3"
        fh.write(f"{i}\t{o}\t{p['_raw'].get('score','')}\t{p['lat']:.5f}\t{p['lon']:.5f}\t{url}\n")
        if i <= 12:
            print(f"  {i:2}  orden {o:>2}  score {p['_raw'].get('score','')[:8]:>8}  "
                  f"{p['lat']:.5f}, {p['lon']:.5f}")
print(f"\n-> {out}")
