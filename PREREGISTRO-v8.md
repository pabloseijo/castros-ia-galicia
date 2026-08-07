# Preregistro: v8, el canal de apertura

**Escrito el 2026-08-07 a las 22:15, con v8 en la época 3 de 16 y sin una sola
cifra de barrido a la vista.** El commit que lo introduce es anterior al
resultado; ese es todo su propósito.

## Por qué existe este fichero

Porque a v7t —la traslación— le puse un listón antes de mirar, y a v8 no. Si
mañana v8 sale con un `+0.02` y lo acepto porque «el canal tiene justificación
física», estaría usando dos varas distintas para dos experimentos de la misma
sesión. La justificación física es una razón para **probar** algo, no para
rebajarle el listón.

## La hipótesis, y de dónde sale

El candidato `OU-8` tenía el mejor perfil topográfico de los `27` de Ourense
—`49,3 m` de prominencia, `100%` del entorno debajo, plataforma llana— y en el
sombreado se veían arcos concéntricos envolviendo la cima. **Eran pistas
forestales**, y lo delató la ortofoto.

Los tres canales de v7 —MDT normalizado, relieve local y pendiente— no tienen
forma de distinguirlas de un parapeto: una pista es un **corte**, un rasgo lineal
fino de un tono; un parapeto es **caballón más foso**, un alto y un bajo pegados.
La apertura topográfica (Doneus, `2013`, `10.3390/rs5126427`) resalta a la vez lo
más alto y lo más bajo, que es exactamente esa firma.

**Comprobado sobre dato propio antes de entrenar**: la correlación del canal de
apertura con los otros tres es `+0.087`, `+0.231` y `+0.016`, o sea que aporta
información que no está en ellos. Y su media es menor en castro (`0.477`) y
mámoa (`0.463`) que en terreno aleatorio (`0.542`) y pista forestal (`0.518`):
un recinto está, literalmente, más cerrado.

## Qué hace comparable la medida

El corpus de v8 es **el mismo que el de v7**, verificado con
`scripts/comparar_corpus.py`: `15.311` filas, mismo conjunto de `sid`, mismos
`split` (`12.136` / `2.991` / `184`) y mismos recuentos por grupo. **La única
variable que cambia es el número de canales.**

Esto costó rehacer el corpus entero: el primer intento tenía `3.458` viñetas y
cero `random_terrain`, y habría dado un resultado peor que yo habría atribuido al
canal.

## La regla, escrita antes de mirar

**Métrica primaria**: media de `F1` sobre los cuatro bloques —Lugo, A Coruña,
Ourense, Pontevedra— con el metro fusionado y umbral `0.70`, idéntico a como
está medido v7.

Referencia de v7, publicada y no revisable:

| bloque | precisión | F1 |
|---|---:|---:|
| Lugo | `0.826` | `0.697` |
| A Coruña | `0.769` | `0.396` |
| Ourense | `0.543` | `0.535` |
| Pontevedra | `0.391` | `0.419` |
| **media** | `0.632` | **`0.512`** |

**El listón es `+0.03`, el mismo que se le puso a v4 y a v7t.** No se rebaja por
tener mejor justificación ni por lo que ha costado el corpus.

- **`F1` medio de v8 `>= 0.542`** → el canal aporta. Entra en el modelo de
  producción y v9 se construye encima de él.
- **`F1` medio de v8 `< 0.542`** → **el canal de apertura queda refutado** y v9
  se construye sobre v7, con tres canales topográficos más la ortofoto.

**Sin excepciones por bloque.** Con `n` entre `36` y `75` castros, un bloque
suelto a favor es la forma que tiene el ruido de parecer un hallazgo. El listón
está en `+0.03` justamente porque en v4 se midió que un `+0.019` no se distingue
de cero con estos tamaños de muestra.

## Una medida secundaria que no decide, pero se mira

La hipótesis es específica: **distinguir un parapeto de una pista forestal**. Así
que además de la métrica primaria se mirará qué pasa con los falsos positivos
sobre `forest_track` y con el candidato `OU-8`, que es el caso que motivó todo.

Si el `F1` medio no llega al listón **pero** los falsos positivos sobre pistas
forestales caen claramente, eso no rescata al canal —la regla es la regla— pero
sí se escribe, porque señalaría que la idea es buena y el problema es otro.

## Qué se hace con el resultado

Va al preprint gane o pierda. Un resultado negativo con la regla escrita antes y
el corpus verificado vale más que el positivo pequeño que se habría podido
fabricar moviendo el listón.
