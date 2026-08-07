"""Densidad de puntos de suelo por bloque: separa techo de dato de techo de modelo.

Mayoral Herrera y colegas (`2025`, `10.1002/arp.1975`), sobre castros de la Edad
del Hierro del suroeste ibérico, avisan de que el LiDAR abierto de los servicios
regionales vale para escala media o grande pero **falla en la microtopografía
sutil a escala de sitio**. Eso abría la posibilidad de que el `F1 0.396` de A
Coruña —cuyos castros conocidos tienen `8,4 m` de prominencia mediana— fuera
techo del dato y no del modelo.

**Medido el 2026-08-07, y la hipótesis se cae:**

| bloque | pt/m² de suelo | `F1` |
|---|---:|---:|
| A Coruña | `2,69` — la mayor | `0.396` |
| Lugo | `2,48` | `0.697` |
| Ourense | `1,73` | `0.535` |
| Pontevedra | `1,72` | `0.419` |

A Coruña tiene **más** puntos que ningún otro bloque y el segundo peor `F1`, y
Ourense lo supera con un `36%` menos de densidad. Dentro del rango que entrega el
PNOA abierto la densidad **no predice el rendimiento**: las diferencias son
paisaje, no resolución.

No contradice a Mayoral, que habla de saltar a dron —otro orden de magnitud, el
conjunto de prueba portugués vuela a `10 pt/m²`—. Lo que queda descartado es
explicar las diferencias **entre estos bloques** por el dato, y con ello la idea
de ir a buscar LiDAR más denso para arreglar A Coruña.

Uso:
    python3 scripts/medir_densidad_bloques.py
"""
import glob, random, sys
import numpy as np, laspy

random.seed(20260807)
cab = ("bloque", "teselas", "muestra", "pt/m2", "p10", "p90")
print("{:<12}{:>8}{:>8}{:>9}{:>8}{:>8}".format(*cab))
res = {}
for B in ["lugo", "coruna", "ourense", "pontevedra"]:
    ts = sorted(glob.glob("data/external/lidar-val-%s/*.laz" % B))
    if not ts:
        print("%-12s sin teselas" % B); continue
    m = random.sample(ts, min(6, len(ts)))
    ds = []
    for t in m:
        try:
            las = laspy.read(t)
            k = np.asarray(las.classification) == 2
            n = int(k.sum())
            if n < 1000:
                continue
            x = np.asarray(las.x)[k]; y = np.asarray(las.y)[k]
            area = (x.max() - x.min()) * (y.max() - y.min())
            if area > 0:
                ds.append(n / area)
        except Exception as e:
            print("  %s: %s" % (t, e), file=sys.stderr)
    if ds:
        a = np.array(ds)
        res[B] = float(a.mean())
        print("{:<12}{:>8}{:>8}{:>9.2f}{:>8.2f}{:>8.2f}".format(
            B, len(ts), len(ds), a.mean(), np.percentile(a, 10), np.percentile(a, 90)))
if res:
    lo = min(res.values())
    print("\nla mas baja: %.2f pt/m2" % lo)
    print("igualar todos los bloques a esa densidad separa dato de modelo:")
    for b, v in sorted(res.items(), key=lambda kv: -kv[1]):
        print("  %-12s %.2f  (x%.2f sobre la minima)" % (b, v, v / lo))
