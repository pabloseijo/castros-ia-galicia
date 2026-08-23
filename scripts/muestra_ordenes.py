#!/usr/bin/env python3
"""Diez ordenes AL AZAR de las 58 sin barrer, para medir el sesgo de densidad.

## El problema

`plan-descarga-portugal.tsv` esta ordenado **por castros aportados**, asi que
barrer las 18 primeras no es barrer medio precinto al azar: es barrer la mitad
mas densa. Medido:

    ordenes 1-18   (barridas)   8,0 castros por orden
    ordenes 19-76  (sin barrer) 2,4 castros por orden   -> 3,4x menos

Y este proyecto tiene medido que **el bloque explica el 79,5% de la varianza del
F1**. Asi que una cifra obtenida solo en zona densa no es extrapolable al norte
de Portugal entero: seria la misma trampa que comparar dos barridos con distinta
cobertura, en otra forma.

## Por que muestrear y no censar

Barrer las 58 restantes cuesta ~290 h. Barrer **diez al azar** cuesta ~50 h y
contesta la pregunta que importa: **¿cambia el resultado entre zona densa y zona
rala?** Si no cambia, las 18 valen como estimacion y no hace falta seguir. Si
cambia, se sabra en que direccion y cuanto.

Es muestreo, no censo, y se decide ANTES de mirar ningun resultado.

Semilla fija para que nadie pueda reelegirlas despues.
"""
import csv
import random

random.seed(20260823)
filas = list(csv.DictReader(open("data/plan-descarga-portugal.tsv", encoding="utf-8"),
                            delimiter="\t"))
resto = [f for f in filas if int(f["orden"]) > 18]
muestra = sorted(random.sample(resto, 10), key=lambda f: int(f["orden"]))

print("orden\tcastros\tlon_min\tlat_min\tlon_max\tlat_max")
for f in muestra:
    print(f"{f['orden']}\t{f['castros']}\t{f['lon_min']}\t{f['lat_min']}\t{f['lon_max']}\t{f['lat_max']}")

tot = sum(int(f["castros"]) for f in muestra)
print(f"\n# {len(muestra)} ordenes, {tot} castros nuevos", file=__import__("sys").stderr)
print(f"# media {tot/len(muestra):.1f} castros/orden (las barridas: 8,0)", file=__import__("sys").stderr)
