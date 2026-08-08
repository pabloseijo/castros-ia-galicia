"""¿El agrupado de enlace simple funde castros distintos cuando el suelo baja?

Sintoma que lo motiva: subir el suelo de `0.40` a `0.50` MEJORA el resultado de
las `100` primeras fichas (`35` -> `49` castros en Lugo). Eso no puede ser real
—las `100` mejores por puntuacion no dependen de donde este el suelo—, asi que
tiene que ser el agrupado: con mas puntos, el enlace simple encadena sitios
separados en un unico grupo, y una ficha que contiene tres castros solo cuenta
como una.
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "scripts")
from detection_eval import a_metros, agrupar, leer_tsv

b = sys.argv[1] if len(sys.argv) > 1 else "lugo"
mod = sys.argv[2] if len(sys.argv) > 2 else "v7"

ps = [p for p in leer_tsv(Path(f"data/sweep_val_{b}_{mod}.tsv"), ("lon", "lat", "score"))
      if "score" in p]
for p in ps:
    p["score"] = float(p["score"])
ts = leer_tsv(Path(f"data/{b}_fus_truth_limpia.tsv"))
lat0 = float(np.mean([t["lat"] for t in ts]))
tx, ty = a_metros([t["lon"] for t in ts], [t["lat"] for t in ts], lat0)

print(f"{b} / {mod} — {len(ts)} castros conocidos\n")
cab = ("suelo", "puntos", "grupos", "pts/gr", "mayor", "castros en el mayor")
print(f"  {cab[0]:>6}{cab[1]:>9}{cab[2]:>9}{cab[3]:>9}{cab[4]:>8}{cab[5]:>22}")
for s in (0.30, 0.40, 0.50, 0.60, 0.70):
    sel = [p for p in ps if p["score"] >= s]
    if len(sel) < 5:
        continue
    px, py = a_metros([p["lon"] for p in sel], [p["lat"] for p in sel], lat0)
    gs = agrupar(px, py, 512.0)
    mayor = max(gs, key=len)
    dentro = sum(1 for i in range(len(tx))
                 if np.hypot(px[mayor] - tx[i], py[mayor] - ty[i]).min() <= 500)
    print(f"  {s:>6.2f}{len(sel):>9}{len(gs):>9}{len(sel)/len(gs):>9.1f}"
          f"{len(mayor):>8}{dentro:>22}")

print("\nSi 'castros en el mayor' es > 1, el agrupado esta fundiendo sitios")
print("distintos en una sola ficha, y la cola subestima lo que un revisor veria.")
