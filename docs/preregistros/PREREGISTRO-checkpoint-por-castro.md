# Preregistro — ¿la métrica de selección está congelando el checkpoint equivocado?

**Escrito el 2026-08-10, antes de barrer nada con `last.pt`.**

## El hallazgo que lo motiva

`selection_score` promedia el `F1` de castro y el de mámoa. Sobre la historia
completa de v7, `16` épocas:

| época | `F1` castro | recall castro | `F1` mámoa | **selección** |
| ---: | ---: | ---: | ---: | ---: |
| **`9`** | `0,5518` | `0,711` | `0,369` | **`0,4605`** ← congelada |
| `15` | `0,5525` | `0,833` | `0,362` | `0,4572` |
| **`16`** | **`0,5640`** | **`0,844`** | `0,334` | `0,4492` |

**La época `16` es la mejor en castro en todo** —`F1` y recall— y se descartó
porque su `F1` de mámoa era `0,035` peor. La mámoa tiene `n = 122` y precisión
`0,21`–`0,24`: es la clase más ruidosa del corpus, y está eligiendo el modelo.

**Y la época `16` es `last.pt`**, que ya está en disco para los quince
checkpoints. No hay que entrenar nada.

## Por qué esto no es «mover la vara»

El entregable de este proyecto es **una cola de candidatos a castro**. Que una
clase secundaria decida qué modelo se congela es un desajuste entre la métrica y
el objetivo, no una preferencia.

Y elegir el checkpoint mirando validación **es para lo que existe la
validación**. No se toca el precinto, no se cambia el listón, y no se altera
`best.pt`: se añade `best_castro.pt` para los modelos futuros y se mide
`last.pt` para los que ya existen.

## Lo que se hace

Barrer los **cuatro bloques** con `data/cls-v7/last.pt` y evaluar igual que
siempre: umbral `0,70`, misma verdad, misma máscara, **con la cobertura al lado
de cada cifra**.

## Las hipótesis

**H1**: `last.pt` bate a `best.pt` en `F1` de detección. El `+0,133` de recall
de viñeta se traduce en más castros hallados.

**H0**: no lo bate, y entonces hay algo que aprender: **el `F1` de viñeta no
predice el `F1` de detección**. Sería un resultado importante por sí solo,
porque toda la selección de modelo de este proyecto se hace sobre viñetas.

## Lo que se declara de antemano

1. **La cifra que decide es la media de los cuatro bloques.** Nada de quedarse
   con el bloque que salga mejor.
2. **Si `last.pt` gana, no se sustituye `best.pt` en el registro histórico.** Se
   documenta que el criterio de selección era subóptimo y se congela `last.pt`
   para la fase 2. Los nueve veredictos ya escritos se midieron con `best.pt` y
   siguen diciendo lo que decían.
3. **Cobertura al lado de cada `F1`.** La lección del `2026-08-10`.
4. **Esto no invalida ninguna refutación anterior.** v11p, v13, v12 y v14 se
   compararon con v7-`best` y perdían por márgenes de `0,05` a `0,12`; un
   `+0,012` de `F1` de viñeta no les da la vuelta. Si alguna quedara a tiro,
   **se dirá**.
