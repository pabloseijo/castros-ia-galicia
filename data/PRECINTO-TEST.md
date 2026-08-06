# PRECINTO — el conjunto de prueba no se toca

**Sellado el 2026-08-06 por decisión de Pablo.**

## Los tres conjuntos

| conjunto | qué es | para qué |
|---|---|---|
| **train** | viñetas `split=train` del corpus v3 | ajustar pesos |
| **validation** | `split=val` + **todos los bloques gallegos** (Trasancos, Lugo, Pontevedra, y los que vengan) | elegir checkpoint, umbral, enlace, `min-celdas`, criba |
| **TEST — PRECINTADO** | **norte de Portugal**: Viana do Castelo, Braga, Porto, Vila Real, Bragança | **una sola medición, al final** |

## Por qué Portugal, y por qué está limpio

- **Son los mismos castros.** Cultura castreña galaico-portuguesa: el objeto es el
  mismo a los dos lados del Miño.
- **Cubre los dos regímenes.** Porto y Viana son costa industrializada; Bragança
  y Vila Real, interior rural. Es justo la variable que Trasancos (`F1 0.415`) y
  Lugo (`0.743`) sugieren que manda.
- **`269` de `272` castros están sin tocar.** Solo `3` caen a menos de `300 m` de
  una viñeta de entrenamiento. Es `4,4×` el tamaño de Lugo.
- **Hay LiDAR y es abierto.** La DGT completó la cobertura nacional en marzo de
  2025: `10 pt/m²` y MDT en GeoTIFF a `50 cm`. Mejor que el PNOA, y ya rasterizado.

## La regla

**No se ejecuta ninguna evaluación sobre Portugal hasta que el modelo esté
cerrado sobre las cuatro provincias gallegas.** Ni para «echar un vistazo», ni
para «comprobar que el script funciona». Cada mirada al test lo convierte en
validación, y a partir de ahí sus cifras están infladas igual que las de Lugo.

Motivo concreto, medido en este proyecto: sobre Lugo se ajustaron umbral, enlace
y `min-celdas`. Su `F1 0.743` **ya no es una estimación insesgada**, y solo se
sabrá cuánto vale de verdad cuando se rompa este precinto.

## Cómo se rompe

`detection_eval.py` se niega a evaluar sobre una verdad de campo marcada como
precintada salvo que se pase `--romper-precinto`, y al hacerlo **escribe la fecha
y el motivo en este fichero**. Se rompe una vez. Si hace falta romperlo dos
veces, la segunda cifra ya no es de prueba.

## Registro de roturas

_(ninguna todavía)_

- **2026-08-06** — ⚠️ NO ES UNA ROTURA REAL. Se ejecutó la guarda con un fichero
  de predicciones vacío, solo para comprobar que bloquea y que deja rastro. **No
  se midió nada sobre Portugal**: la salida fue `predicciones: 0`. El precinto
  sigue intacto.
