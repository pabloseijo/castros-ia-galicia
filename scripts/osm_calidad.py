"""Cuantos de los 'nuevos' de OSM son castros y cuantos son otra fortificacion."""
import csv, math, re
import numpy as np
from scipy.spatial import cKDTree

CASTRO = re.compile(r"\b(castro|castros|croa|cividade|citania|castromao)\b", re.I)
OTRA = re.compile(r"\bcastelo\b|\bforte\b|\bfortaleza\b|\btorre\b|\bmuralla\b|"
                  r"\bcastillo\b|\bbater[ií]a\b|\bfort[ií]n\b", re.I)

osm = list(csv.DictReader(open("data/osm.tsv", encoding="utf-8"), delimiter="\t"))
mst = []
for r in csv.DictReader(open("data/weak_label_master_fusionado.tsv",
                             encoding="utf-8"), delimiter="\t"):
    if r.get("label_class") == "1":
        try:
            mst.append((float(r["longitude"]), float(r["latitude"])))
        except (TypeError, ValueError):
            pass

lat0 = float(np.mean([m[1] for m in mst]))
k = 111320.0 * math.cos(math.radians(lat0))
arbol = cKDTree(np.array([[m[0]*k, m[1]*110540.0] for m in mst]))

tipo = [r for r in osm if r["por"] == "tipo"]
P = np.array([[float(r["longitude"])*k, float(r["latitude"])*110540.0] for r in tipo])
d, _ = arbol.query(P)
nuevos = [r for r, dd in zip(tipo, d) if dd > 250]

def clase(n):
    n = n or ""
    if CASTRO.search(n):
        return "dice castro"
    if OTRA.search(n):
        return "dice castelo/forte"
    return "sin nombre util" if not n.strip() else "otro nombre"

import collections
c = collections.Counter(clase(r["name"]) for r in nuevos)
print("De los %d etiquetados como fortificacion y NUEVOS (>250 m):\n" % len(nuevos))
for k_, v in c.most_common():
    print("  %-22s %3d   (%.0f%%)" % (k_, v, 100*v/len(nuevos)))

print("\nlos que dicen castelo/forte, que NO deben entrar como castro:")
for r in nuevos:
    if clase(r["name"]) == "dice castelo/forte":
        print("   %-40s %s" % (r["name"][:38], r["provincia"]))

buenos = [r for r in nuevos if clase(r["name"]) == "dice castro"]
print("\n%d candidatos a castro nuevo, con el nombre a favor:" % len(buenos))
for r in buenos[:12]:
    print("   %-40s %-12s %s,%s" % (r["name"][:38], r["provincia"],
                                    r["latitude"], r["longitude"]))
