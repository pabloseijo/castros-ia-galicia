#!/usr/bin/env python3
"""Separa del conjunto precintado los castros que no estan en Portugal.

Hallado el `2026-08-09` al construir v14: el fichero llamado
`portugal-test_truth_limpia.tsv` contiene **`71` castros gallegos** de Ourense y
Pontevedra, un `20%` del total. Rompe el conjunto de prueba por los dos lados:

- **Por arriba**: un castro gallego sellado puede estar en el corpus de
  entrenamiento —`6` lo estaban en v11p, a `0 m`— y entonces el examen final
  mide memoria, no generalizacion.
- **Por abajo**: el LiDAR de la DGT portuguesa **no cubre Galicia**, asi que esos
  `71` no pueden aparecer en un barrido de Portugal y contarian como fallos
  automaticos. Hasta un `20%` de recall perdido sin que el modelo falle.

**La latitud no sirve para separarlos**: Melgaço, que es portugues, llega a
`42,094`, y Baltar, que es gallego, esta en `41,901`. El unico campo que los
distingue es el municipio.

Esto **no es romper el precinto**: no se evalua nada ni se mira ninguna
prediccion. Se corrige la composicion del conjunto segun el criterio con el que
se definio —el norte de Portugal—, que es justo lo que hay que hacer *antes* de
abrirlo. Queda anotado en `data/PRECINTO-TEST.md`, que es append-only.

Autorizado por Pablo el `2026-08-10`.
"""
from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

# Concellos de Ourense y Pontevedra presentes en el fichero. Cuidado con los
# pares que se llaman casi igual a un lado y otro de la raya: Gondomar (el
# gallego esta a 42,08; el portugues, junto a Porto, a 41,14), Viana do Bolo
# (gallego) frente a Viana do Castelo (portugues), y Melgaço, Monção, Valença,
# Vila Nova de Cerveira, Paredes de Coura y Arcos de Valdevez, que son
# portugueses aunque esten pegados a la frontera.
GALEGOS = {
    "As Neves", "Baltar", "Bande", "Calvos de Randín", "Castrelo do Val",
    "Gondomar", "Laza", "Monterrei", "Muíños", "O Rosal", "Oia", "Os Blancos",
    "Rairiz de Veiga", "Riós", "Salceda de Caselas", "Sarreaus", "Tomiño",
    "Trasmiras", "Tui", "Verea", "Viana do Bolo", "Vilar de Santos",
    "Vilardevós", "Xinzo de Limia",
}

ORIG = Path("data/portugal-test_truth_limpia.tsv")
t = list(csv.DictReader(ORIG.open(encoding="utf-8"), delimiter="\t"))
campos = list(t[0].keys())

gal = [r for r in t if (r.get("concello") or "").strip() in GALEGOS]
por = [r for r in t if (r.get("concello") or "").strip() not in GALEGOS]

# Comprobacion de que el Gondomar que sale es el gallego y no el de Porto. Si
# algun dia entra el portugues, este aborto evita apartarlo por error.
for r in gal:
    if (r.get("concello") or "").strip() == "Gondomar" and float(r["lat"]) < 41.5:
        raise SystemExit("ABORTA: hay un Gondomar portugues clasificado como gallego")

for filas, nombre in ((por, "data/precinto-portugal.tsv"),
                      (gal, "data/precinto-DESCARTADOS-galicia.tsv")):
    with Path(nombre).open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=campos, delimiter="\t")
        w.writeheader()
        w.writerows(filas)

print(f"  precinto original: {len(t)}")
print(f"    -> Portugal de verdad:  {len(por)}  (data/precinto-portugal.tsv)")
print(f"    -> gallegos apartados:  {len(gal)}  ({100*len(gal)/len(t):.0f}%)")

libro = Path("data/PRECINTO-TEST.md")
linea = (
    f"\n## {dt.date.today().isoformat()} — correccion de composicion "
    f"(NO es una evaluacion)\n\n"
    f"Se apartan **{len(gal)} castros gallegos** de los {len(t)} del fichero, "
    f"detectados al construir v14 porque 6 de ellos aparecian a `0 m` del "
    f"entrenamiento de v11p. Estan en Ourense y Pontevedra; el LiDAR de la DGT "
    f"portuguesa no los cubre, asi que contarian como fallos automaticos. "
    f"El conjunto de prueba queda en **{len(por)} castros del norte de "
    f"Portugal**.\n\n"
    f"No se ha evaluado ningun modelo contra ellos ni se ha mirado ninguna "
    f"prediccion. Autorizado por Pablo. Ficheros: `data/precinto-portugal.tsv` "
    f"y `data/precinto-DESCARTADOS-galicia.tsv`.\n")
with libro.open("a", encoding="utf-8") as fh:
    fh.write(linea)
print(f"  anotado en {libro}")
