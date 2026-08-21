#!/usr/bin/env python3
"""¿Manda mas el modelo o el sitio? Descomposicion de la varianza del F1.

Ocho versiones y cuatro bloques. La pregunta que ordena el proyecto entero: si
la mayor parte de la variacion del `F1` la explica **que bloque es** y no **que
modelo es**, entonces seguir sacando versiones es trabajar sobre la palanca
pequena.

Se hace con las versiones que tienen los cuatro bloques completos y con las
cifras recalculadas hoy desde los barridos crudos, no desde los logs.
"""
from __future__ import annotations

import statistics as st

# F1 recalculado el 2026-08-09 con `detection_eval.py`, umbral `0,70`, mascara de
# entrenamiento aplicada. Solo las versiones con los cuatro bloques completos.
DATOS = {
    "v6focal": {"lugo": 0.630, "coruna": 0.439, "ourense": 0.430, "pontevedra": 0.264},
    "v7":      {"lugo": 0.697, "coruna": 0.396, "ourense": 0.535, "pontevedra": 0.419},
    "v8":      {"lugo": 0.631, "coruna": 0.419, "ourense": 0.439, "pontevedra": 0.374},
    "v11p":    {"lugo": 0.618, "coruna": 0.425, "ourense": 0.359, "pontevedra": 0.157},
}
BLOQUES = ["lugo", "coruna", "ourense", "pontevedra"]

todos = [v for m in DATOS.values() for v in m.values()]
gran = st.mean(todos)

# efecto de bloque: media de cada bloque sobre todos los modelos
med_b = {b: st.mean(DATOS[m][b] for m in DATOS) for b in BLOQUES}
# efecto de modelo: media de cada modelo sobre todos los bloques
med_m = {m: st.mean(DATOS[m].values()) for m in DATOS}

nb, nm = len(BLOQUES), len(DATOS)
sc_bloque = nm * sum((med_b[b] - gran) ** 2 for b in BLOQUES)
sc_modelo = nb * sum((med_m[m] - gran) ** 2 for m in DATOS)
sc_total = sum((v - gran) ** 2 for v in todos)
sc_resto = sc_total - sc_bloque - sc_modelo

print(f"  media general del F1: {gran:.3f}\n")
print("  por bloque (promediando modelos):")
for b, v in sorted(med_b.items(), key=lambda x: -x[1]):
    print(f"    {b:<12} {v:.3f}")
print(f"    rango: {max(med_b.values()) - min(med_b.values()):.3f}\n")
print("  por modelo (promediando bloques):")
for m, v in sorted(med_m.items(), key=lambda x: -x[1]):
    print(f"    {m:<12} {v:.3f}")
print(f"    rango: {max(med_m.values()) - min(med_m.values()):.3f}\n")
print("  reparto de la varianza:")
for nombre, sc in (("el BLOQUE", sc_bloque), ("el MODELO", sc_modelo),
                   ("interaccion y ruido", sc_resto)):
    print(f"    {nombre:<22} {100*sc/sc_total:>5.1f}%")
