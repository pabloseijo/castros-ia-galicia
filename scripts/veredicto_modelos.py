"""Aplica los tres preregistros y dicta el veredicto. Sin margen de interpretacion.

Lee los `detection_eval` de la cadena de noche y compara cada modelo contra su
liston, que se escribio ANTES de existir los resultados:

  PREREGISTRO-v7t.md : F1 medio >= 0.542  (v7 = 0.512, liston +0.03)
  PREREGISTRO-v8.md  : F1 medio >= 0.542
  PREREGISTRO-v9.md  : +0.03 sobre el mejor de v7 y v8

La regla de los preregistros es «sin excepciones por bloque»: con n entre 36 y 75
castros, un bloque suelto a favor es la forma que tiene el ruido de parecer un
hallazgo.
"""
import re
import sys
from pathlib import Path

LOG = Path(sys.argv[1] if len(sys.argv) > 1 else "logs/cadena_noche.log")
UMBRAL = "0.70"
REF_V7 = {"lugo": 0.697, "coruna": 0.396, "ourense": 0.535, "pontevedra": 0.419}
LISTON = 0.03

texto = LOG.read_text(encoding="utf-8", errors="replace").splitlines()
res = {}
mod = blo = None
for i, ln in enumerate(texto):
    m = re.search(r"EVALUACION (\w+) con (\w+)", ln)
    if m:
        blo, mod = m.group(1), m.group(2)
        continue
    if mod and blo:
        # las lineas de detection_eval traen «umbral 0.70 ... F1 0.xxx»
        mm = re.search(r"umbral\s+" + UMBRAL + r"\b.*?F1\s+([0-9.]+)", ln)
        if not mm:
            mm = re.search(r"^\s*" + UMBRAL + r"\s+.*?([0-9.]+)\s*$", ln)
        if mm:
            res.setdefault(mod, {})[blo] = float(mm.group(1))
            mod = blo = None

print("F1 por bloque a umbral %s, metro fusionado\n" % UMBRAL)
print("%-8s%10s%10s%10s%12s%10s" % ("modelo", "lugo", "coruna", "ourense",
                                    "pontevedra", "MEDIA"))
print("%-8s%10.3f%10.3f%10.3f%12.3f%10.3f"
      % ("v7", REF_V7["lugo"], REF_V7["coruna"], REF_V7["ourense"],
         REF_V7["pontevedra"], sum(REF_V7.values()) / 4))
medias = {"v7": sum(REF_V7.values()) / 4}
for m in ("v8", "v7t", "v9"):
    if m not in res:
        continue
    v = res[m]
    if len(v) < 4:
        print("%-8s  incompleto: %s" % (m, ", ".join(sorted(v))))
        continue
    med = sum(v.values()) / 4
    medias[m] = med
    print("%-8s%10.3f%10.3f%10.3f%12.3f%10.3f"
          % (m, v["lugo"], v["coruna"], v["ourense"], v["pontevedra"], med))

print("\n" + "=" * 62)
print("VEREDICTO CONTRA LOS PREREGISTROS")
print("=" * 62)
base = medias["v7"]
for m in ("v8", "v7t"):
    if m not in medias:
        print("  %-5s sin resultado completo todavia" % m); continue
    d = medias[m] - base
    ok = d >= LISTON
    print("  %-5s %.3f  (v7 %.3f, diferencia %+.3f)  ->  %s"
          % (m, medias[m], base, d, "PASA" if ok else "REFUTADO"))
    if not ok and d > 0:
        print("        mejora, pero no llega al liston. La regla es la regla:")
        print("        en v4 se midio que un +0.019 no se distingue de cero.")

if "v9" in medias:
    ref = max(medias.get("v8", 0), base)
    quien = "v8" if medias.get("v8", 0) > base else "v7"
    d = medias["v9"] - ref
    print("  %-5s %.3f  (referencia %s %.3f, diferencia %+.3f)  ->  %s"
          % ("v9", medias["v9"], quien, ref, d,
             "PASA" if d >= LISTON else "REFUTADO"))

if len(medias) > 1:
    mejor = max(medias, key=medias.get)
    print("\n  mejor F1 medio: %s (%.3f)" % (mejor, medias[mejor]))
    if mejor != "v7" and medias[mejor] - base < LISTON:
        print("  PERO no clarea el liston, asi que el modelo de produccion")
        print("  sigue siendo v7. Un maximo no es una mejora demostrada.")
