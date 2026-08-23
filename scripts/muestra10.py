#!/usr/bin/env python3
"""Diez candidatos de los 419 VERIFICADOS, ESTRATIFICADOS por bloque.

## De que lista

Hay cinco ficheros de candidatos y dos numeros circulando como si fueran uno:

    candidatos-ineditos.tsv      616   lista cruda
    candidatos-limpios.tsv       540   los que no tienen explicacion conocida
    candidatos-verificados.tsv   419   + descontado catalogo, entrenamiento y margen

La primera version muestreo de los 616 crudos y **solo 4 de 10 estaban en la
lista verificada**: seis eran candidatos que el proyecto ya habia descartado.
Mandar eso habria sesgado el test hacia el «0 de 10», que es justo el resultado
que cierra la linea de descubrimiento.

## Por que estratificado y no aleatorio simple

La segunda version, aleatoria simple sobre los 419, **no saco ni un candidato de
Pontevedra** —un 2,8% de probabilidad, pero toco—. Y Pontevedra es el bloque mas
informativo del test: es donde el modelo dispara mas alto (score p95 0,5321, el
mayor de los cuatro), donde menos castros hay catalogados, y donde las primeras
50 fichas de la cola **no reencuentran ni un castro conocido**. Si en algun sitio
hay yacimientos sin catalogar, es ahi.

Una muestra que no cubre el bloque mas informativo no puede contestar la
pregunta. Se estratifica proporcionalmente y se sortea dentro de cada estrato.

## Al azar dentro del estrato, y no los mejores

Los mejores ya se miraron: de los 14 primeros, 11 quedaron ambiguos, 2 no eran
nada, y el unico que parecia un recinto inequivoco resulto estar catalogado a
77 m. Ordenar por puntuacion contesta «como es el mejor candidato»; lo que hay
que medir es la tasa de acierto de la cola.

Semilla fija: reproducible, y nadie puede reelegirla tras ver las respuestas.
"""
import csv
import random
from collections import defaultdict

random.seed(20260819)
filas = list(csv.DictReader(open("data/candidatos-verificados.tsv", encoding="utf-8"),
                            delimiter="\t"))
por_bloque = defaultdict(list)
for r in filas:
    por_bloque[r["bloque"]].append(r)

# reparto proporcional, con al menos 2 por bloque para que ninguno quede fuera
CUPO = {"ourense": 3, "pontevedra": 3, "lugo": 2, "coruna": 2}

muestra = []
for b, k in CUPO.items():
    muestra += random.sample(por_bloque[b], k)
random.shuffle(muestra)

print("n\tbloque\tscore\tlat\tlon\tvista_aerea")
for i, r in enumerate(muestra, 1):
    lat, lon = float(r["lat"]), float(r["lon"])
    url = f"https://www.google.com/maps/@{lat:.6f},{lon:.6f},250m/data=!3m1!1e3"
    print(f"{i}\t{r['bloque']}\t{r['score']}\t{lat:.5f}\t{lon:.5f}\t{url}")
