"""Corroboracion independiente: los 54 candidatos contra el catalogo de OSM.

OSM no entro en el entrenamiento ni en la verdad de campo, asi que si un
candidato del modelo cae encima de un yacimiento que OSM tiene y el catalogo
oficial no, eso es una comprobacion externa, no una circularidad.
"""
import csv, glob, math, os
import numpy as np
from scipy.spatial import cKDTree

osm = list(csv.DictReader(open("data/osm.tsv", encoding="utf-8"), delimiter="\t"))
cand = []
for f in sorted(glob.glob("data/triaje-v7g/*_triaje.csv")):
    b = os.path.basename(f).split("_")[1]
    for r in csv.DictReader(open(f, encoding="utf-8")):
        if (r.get("veredicto") or "") == "YA CATALOGADO":
            continue
        r["_b"] = b
        cand.append(r)
print("candidatos: %d | entradas OSM: %d\n" % (len(cand), len(osm)))

lat0 = 42.8
k = 111320.0 * math.cos(math.radians(lat0))
O = np.array([[float(r["longitude"])*k, float(r["latitude"])*110540.0] for r in osm])
arbol = cKDTree(O)
P = np.array([[float(r["lon"])*k, float(r["lat"])*110540.0] for r in cand])
d, j = arbol.query(P)

for umbral in (150, 250, 400):
    print("candidatos con una entrada OSM a menos de %3d m: %d de %d"
          % (umbral, int((d < umbral).sum()), len(cand)))

print("\nlos que coinciden a menos de 400 m:")
print("%-12s%8s  %-34s%-12s%s" % ("bloque", "dist", "nombre en OSM", "por", "triaje"))
orden = np.argsort(d)
for i in orden:
    if d[i] >= 400:
        break
    o = osm[j[i]]
    print("%-12s%7.0fm  %-34s%-12s%s" % (cand[i]["_b"], d[i],
                                         (o["name"] or "(sin nombre)")[:32],
                                         o["por"], cand[i]["triaje"]))
