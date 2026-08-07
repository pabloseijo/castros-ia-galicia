# Preregistro: v9, la ortofoto en fusión temprana

**Escrito el 2026-08-07 a las 22:25, con v8 en la época 4 de 16 y sin ninguna
cifra de barrido de v7t ni de v8.** Se escribe ahora precisamente porque **el
listón de v9 depende de si v8 gana o pierde**: si esperase a saberlo, estaría
eligiendo la referencia con información en la mano.

## La hipótesis, y por qué no es la criba refutada

El `2026-08-07` se probó un clasificador de ortofoto como **criba posterior**
sobre candidatos ya detectados. Salió **anticorrelado**: la precisión de
despliegue cayó de `0.200` a `0.062`, porque aprendió «rural contra urbano» y en
la ría de Vigo los castros están rodeados de urbanización. **Eso sigue refutado,
como criba.**

Peker (`2026`, `10.1017/aap.2025.10142`) hace lo contrario sobre terrazas
agrícolas del Bozburun: mete lo espectral **como canal de entrada al entrenar**,
compara cuatro arquitecturas —temprana, intermedia, tardía y solo RGB— y **gana
la temprana** con `IoU 0.754`; su modelo saca más precisión que la digitalización
experta (`87,4%` contra `79,3%`).

Filtrar al final con un clasificador entrenado aparte no es lo mismo que dejar
que la red aprenda desde el principio a combinar textura con relieve. El
resultado negativo propio no toca esta vía.

Ataca el cuello más caro medido: la precisión cae de `0.826` en Lugo a `0.391` en
Pontevedra, donde el confusor es obra moderna en paisaje periurbano — justo lo
que una imagen ve y un modelo digital del terreno no.

## La referencia, definida antes de conocerla

**v9 se compara contra el mejor de v7 y v8, y ese es el que decida el
`PREREGISTRO-v8.md`**, no el que a mí me parezca mejor cuando lo vea:

- **Si v8 alcanza `F1` medio `>= 0.542`**, el canal de apertura entra. v9 son
  **siete canales** (`4` topográficos `+ 3` de ortofoto) y su referencia es el
  `F1` medio de v8.
- **Si v8 no llega**, el canal de apertura queda refutado. v9 son **seis
  canales** (`3` topográficos `+ 3` de ortofoto), se entrena sobre el corpus de
  v7, y su referencia es el `F1` medio de v7: `0.512`.

En los dos casos **el listón es `+0.03` sobre esa referencia**, igual que en v4,
v7t y v8. Con `n` entre `36` y `75` castros por bloque, en v4 se midió que un
`+0.019` no se distingue de cero; por eso el listón está donde está y no se mueve.

## Lo que hace comparable la medida

El corpus no cambia: los canales topográficos son los mismos y el color **se
concatena al vuelo** desde un directorio paralelo, así que v8 y v9 comparten el
relieve exacto. `15.151` ortofotos de corpus y `32.442` de rejilla, verificadas
contra los índices reales, al `99,99%`.

Dos detalles que, mal hechos, habrían invalidado el experimento en silencio:

- **El color se concatena ANTES de aumentar.** Si se añadiera después del volteo
  y el giro, la ortofoto quedaría rotada respecto a su propio terreno y la red
  aprendería a ignorarla. Un canal inútil por un fallo de montaje se lee igual
  que un canal inútil de verdad.
- **El barrido se niega a correr sin ortofoto.** Sin esa guardia rellenaría las
  celdas con gris neutro y puntuaría tres canales inexistentes, dando cifras
  peores sin fallar.

## Medida secundaria, que no decide

La hipótesis es específica sobre el **confusor moderno**. Así que además del `F1`
medio se mirará la **precisión de Pontevedra** —hoy `0.391`, la peor de los
cuatro bloques— y los falsos positivos sobre `modern_infrastructure`.

Si el `F1` medio no llega al listón pero la precisión de Pontevedra sube
claramente, v9 queda refutado igual, y se escribe el detalle: significaría que la
ortofoto sirve donde se esperaba y que el promedio la esconde.

## Qué se hace con el resultado

Va al preprint gane o pierda, como los otros tres.
