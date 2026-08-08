# Preregistro: v11, el corpus con todos los positivos

**Escrito el 2026-08-08 a las 19:55, con la descarga de LiDAR al `52%` (`3.306`
de `6.274` teselas) y sin haber cortado ni una viñeta del corpus nuevo.** No
existe ninguna cifra de v11 en el momento de escribir esto.

Se escribe ahora, y no cuando el corpus esté listo, porque **v11 es la vía viva**:
las cinco anteriores están refutadas y la tentación de mover el listón cuando por
fin algo funcione es máxima justo aquí.

## Qué cambia, y por qué no es «otra versión»

Las versiones v4 a v10 movían **arquitectura o pérdida** sobre el mismo corpus.
Todas fracasaron:

| versión | qué probaba | resultado |
| --- | --- | --- |
| v4 / v7t | traslación como aumento | refutada, `F1 0,139` |
| v8 | apertura topográfica como canal | refutada, `0,631` vs `0,697` |
| v9 | ortofoto como canal (Peker) | refutada, `0,222` vs `0,697` |
| v10 | negativos duros con peso `8` | refutada, castro recall `0,256` |

v11 no toca ni la arquitectura ni la pérdida. **Cambia el conjunto de
entrenamiento**, y por eso su listón es distinto.

El diagnóstico, medido el `2026-08-08`: Galicia tiene `3.781` castros
catalogados y el corpus solo contiene **`960` con viñeta (`25%`)**, de los cuales
`773` en entrenamiento. El resto no estaba porque **no había LiDAR descargado**:
solo el `15%` del territorio. Cinco versiones peleando por `±0,03` de `F1` sobre
`773` positivos, cuando el dato para triplicarlos estaba a una descarga de
distancia.

## El listón, y por qué no es `+0,03`

Los preregistros de v4, v7t, v8, v9 y v10 pedían **`+0,03` sobre la referencia**,
porque medían un cambio de método a corpus constante y con `n` de `36` a `75`
castros por bloque un `+0,019` no se distingue de cero.

**Aquí el listón es otro y hay que decir por qué.** Triplicar los positivos de
entrenamiento no es una hipótesis fina: es la única palanca que la literatura
señala sin ambigüedad, y si no mueve nada el proyecto tiene un problema mucho más
grave que la elección de canales. Así que:

- **Éxito**: `F1` medio sobre los cuatro bloques **`≥ 0,60`** (referencia v7:
  `0,542`). Es `+0,058`, casi el doble del listón habitual, porque el cambio es
  mucho mayor que los anteriores.
- **Resultado neutro y decepcionante**: entre `0,542` y `0,60`. Se reporta como
  «el dato ayuda menos de lo que la literatura promete» y **no** se presenta como
  victoria.
- **Fracaso**: por debajo de `0,542`. Si triplicar los positivos empeora, hay un
  fallo en el corpus nuevo (contaminación, mal registro, positivos de mala
  calidad) y **hay que buscarlo antes de tocar nada más**.

## Lo que hay que comprobar antes de creerse cualquier cifra

Tres controles, y los tres se hacen **antes** de mirar el `F1`:

1. **La partición no puede mezclarse.** Los positivos nuevos deben repartirse
   respetando los mismos bloques espaciales. Un castro nuevo que caiga en un
   bloque de validación **no puede** entrar en entrenamiento. Si esto se rompe,
   la cifra sube y no significa nada — es lo que pasó en Trasancos, donde `86` de
   `93` castros estaban en `train`/`val`.
2. **El conjunto de validación debe quedar idéntico al de v7.** Solo así la
   comparación mide el efecto del dato de entrenamiento y no un cambio de examen.
   Se verifica con `scripts/comparar_corpus.py`.
3. **El precinto de Portugal sigue cerrado.** Regla `15`. Ninguna cifra de v11
   es una estimación insesgada de despliegue.

## La predicción, escrita antes

Con la regla de cribado formulada hoy —`selection_best` ordena igual que el
barrido en `n = 4`—, la predicción es que v11 dé **`selection_best ≥ 0,50`**. Si
sale por debajo de `0,40`, **no se barre** y se busca el fallo del corpus.

Anotar aquí lo que se espera obliga a reconocer después si se acertó, y la regla
de cribado necesita puntos que no sean todos refutaciones.

## Lo que este preregistro NO cubre

- No dice nada sobre el **peso de los negativos duros**, que v10 dejó abierto: el
  peso `8` está refutado, la escala `2`–`4` no se ha probado. Es otro experimento
  y necesita su propio preregistro.
- No cubre la vía espectral en **Pontevedra**, que quedó sin medir al parar v9
  tras un bloque.
